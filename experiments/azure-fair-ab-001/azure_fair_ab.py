#!/usr/bin/env python3
"""AZURE-FAIR-AB-001: identical-boundary Azure control vs EDEN benchmark.

Both benchmark arms enter through the same local HTTP endpoint and use the same
Azure OpenAI deployment. CONTROL is a conventional exact-cache service. EDEN
uses the same exact-cache primitive and additionally executes the EDEN Core
Refinery -> ChronoNav -> Chrysalis -> Marble v2 -> verify path.

The benchmark intentionally separates:
- provider-reported token usage and request identifiers;
- locally measured wall/CPU time;
- optional token-price-derived MODELLED cost;
- optional externally supplied Azure billing evidence.

It never treats token-derived cost as provider billing and never estimates Azure
energy unless a separate defensible measurement source is supplied.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import statistics
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from eden_core.core import EdenCore  # noqa: E402

SCHEMA = "eden.azure.fair_ab.v1"
ALLOWED_ARMS = ("control", "eden")


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sha256_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def sha256_obj(value: Any) -> str:
    return sha256_bytes(canonical_bytes(value))


def percentile(values: List[float], fraction: float) -> Optional[float]:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round((len(ordered) - 1) * fraction))))
    return ordered[index]


def mean(values: List[float]) -> Optional[float]:
    return statistics.mean(values) if values else None


def exact_cache_key(prompt: str, deployment: str, max_output_tokens: int) -> str:
    return sha256_obj({
        "prompt": prompt,
        "deployment": deployment,
        "max_output_tokens": max_output_tokens,
    })


def expected_for(task_index: int) -> Dict[str, Any]:
    a = (task_index * 7919 + 104729) % 1000003
    b = (task_index * 15485863 + 32452843) % 10000019
    return {
        "index": task_index,
        "checksum": (a * b + task_index) % 2147483647,
    }


def prompt_for(task_index: int) -> str:
    expected = expected_for(task_index)
    a = (task_index * 7919 + 104729) % 1000003
    b = (task_index * 15485863 + 32452843) % 10000019
    return (
        "Azure validation workload. Return STRICT JSON only with keys "
        "index, checksum, classification, summary. "
        f"index={task_index}; a={a}; b={b}; checksum={expected['checksum']}. "
        "classification must be KEEP, STRUCTURE, DETAIL, or VOID. "
        "summary must be <= 12 words."
    )


def extract_output_text(obj: Mapping[str, Any]) -> str:
    direct = obj.get("output_text")
    if isinstance(direct, str):
        return direct
    parts: List[str] = []
    output = obj.get("output")
    if isinstance(output, list):
        for item in output:
            if not isinstance(item, Mapping):
                continue
            content = item.get("content")
            if not isinstance(content, list):
                continue
            for piece in content:
                if isinstance(piece, Mapping) and isinstance(piece.get("text"), str):
                    parts.append(str(piece["text"]))
    return "\n".join(parts)


def validate_quality(text: str, task_index: int) -> Dict[str, Any]:
    expected = expected_for(task_index)
    try:
        obj = json.loads(text)
    except Exception:
        return {"pass": False, "reason": "invalid_json", "score": 0.0}
    if not isinstance(obj, Mapping):
        return {"pass": False, "reason": "not_object", "score": 0.0}
    allowed = {"KEEP", "STRUCTURE", "DETAIL", "VOID"}
    checks = {
        "index": obj.get("index") == expected["index"],
        "checksum": obj.get("checksum") == expected["checksum"],
        "classification": obj.get("classification") in allowed,
        "summary": isinstance(obj.get("summary"), str) and len(str(obj.get("summary", "")).split()) <= 12,
    }
    score = sum(1 for ok in checks.values() if ok) / len(checks)
    return {"pass": all(checks.values()), "score": score, "checks": checks}


@dataclass
class ProviderResult:
    text: str
    usage: Dict[str, Any]
    latency_s: float
    response_id: Optional[str]
    headers: Dict[str, str]
    raw_sha256: str


class AzureProvider:
    def __init__(self, endpoint: str, key: str, deployment: str, max_output_tokens: int) -> None:
        self.endpoint = endpoint.rstrip("/")
        self.key = key
        self.deployment = deployment
        self.max_output_tokens = max_output_tokens

    def call(self, prompt: str) -> ProviderResult:
        payload = {
            "model": self.deployment,
            "input": prompt,
            "max_output_tokens": self.max_output_tokens,
        }
        req = urllib.request.Request(
            self.endpoint + "/openai/v1/responses",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "api-key": self.key},
            method="POST",
        )
        t0 = time.perf_counter()
        with urllib.request.urlopen(req, timeout=120) as response:
            raw = response.read()
            selected_headers = {
                k.lower(): v for k, v in response.headers.items()
                if k.lower() in {
                    "x-ms-request-id", "apim-request-id", "x-request-id", "traceparent",
                    "x-ratelimit-remaining-requests", "x-ratelimit-remaining-tokens",
                }
            }
        latency = time.perf_counter() - t0
        obj = json.loads(raw)
        usage = obj.get("usage") if isinstance(obj.get("usage"), Mapping) else {}
        return ProviderResult(
            text=extract_output_text(obj),
            usage=dict(usage),
            latency_s=latency,
            response_id=obj.get("id") if isinstance(obj.get("id"), str) else None,
            headers=selected_headers,
            raw_sha256=sha256_bytes(raw),
        )


class MockProvider:
    """Deterministic provider for CI. It is never classified as Azure measurement."""
    deployment = "mock-edition"
    max_output_tokens = 96

    def __init__(self, latency_s: float = 0.001) -> None:
        self.latency_s = latency_s

    def call(self, prompt: str) -> ProviderResult:
        marker = "index="
        task_index = int(prompt.split(marker, 1)[1].split(";", 1)[0])
        expected = expected_for(task_index)
        text = json.dumps({
            "index": task_index,
            "checksum": expected["checksum"],
            "classification": "KEEP",
            "summary": "deterministic mock response",
        }, separators=(",", ":"))
        time.sleep(self.latency_s)
        return ProviderResult(
            text=text,
            usage={"input_tokens": max(1, len(prompt) // 4), "output_tokens": max(1, len(text) // 4)},
            latency_s=self.latency_s,
            response_id=f"mock-{task_index}",
            headers={"x-request-id": f"mock-{task_index}"},
            raw_sha256=sha256_bytes(text.encode("utf-8")),
        )


class FairABService:
    def __init__(self, provider: Any, state_dir: Path, event_log: Path) -> None:
        self.provider = provider
        self.deployment = getattr(provider, "deployment", "unknown")
        self.max_output_tokens = int(getattr(provider, "max_output_tokens", 96))
        self.core = EdenCore(repo_root=REPO_ROOT, state_dir=state_dir / "eden-core")
        self.caches: Dict[str, Dict[str, ProviderResult]] = {arm: {} for arm in ALLOWED_ARMS}
        self.event_log = event_log
        self.event_log.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def _append_event(self, record: Mapping[str, Any]) -> None:
        line = json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n"
        with self._lock:
            with self.event_log.open("a", encoding="utf-8") as handle:
                handle.write(line)

    def reset_arm(self, arm: str) -> None:
        if arm not in ALLOWED_ARMS:
            raise ValueError("unknown arm")
        with self._lock:
            self.caches[arm].clear()

    def evaluate(self, payload: Mapping[str, Any]) -> Dict[str, Any]:
        arm = str(payload.get("arm", ""))
        if arm not in ALLOWED_ARMS:
            raise ValueError(f"arm must be one of {ALLOWED_ARMS}")
        request_uid = str(payload.get("request_uid", ""))
        task_index = int(payload.get("task_index"))
        prompt = str(payload.get("prompt", ""))
        if not request_uid or not prompt:
            raise ValueError("request_uid and prompt are required")

        wall0 = time.perf_counter()
        cpu0 = time.process_time()
        key = exact_cache_key(prompt, self.deployment, self.max_output_tokens)
        with self._lock:
            cached = self.caches[arm].get(key)
        cache_hit = cached is not None
        provider_called = not cache_hit
        if cached is None:
            result = self.provider.call(prompt)
            with self._lock:
                self.caches[arm][key] = result
        else:
            result = cached

        quality = validate_quality(result.text, task_index)
        eden_summary = None
        if arm == "eden":
            pipeline_payload = {
                "run_id": f"AZURE-FAIR-AB-{request_uid}",
                "refinery": {"input": prompt, "output": result.text, "classification": "KEEP"},
                "chrononav": {
                    "predicted_seconds": {"1": max(result.latency_s, 0.000001)},
                    "deadline_seconds": max(result.latency_s * 2.0, 0.001),
                    "prediction_provenance": "OBSERVED_PROVIDER_LATENCY_USED_AS_REFERENCE_ONLY",
                },
                "chrysalis": {
                    "baseline": {"quality": 1.0, "total": max(result.latency_s, 0.000001)},
                    "candidates": [{
                        "id": "exact-reuse" if cache_hit else "provider-result",
                        "quality": float(quality.get("score", 0.0)),
                        "total": max(result.latency_s if provider_called else 0.000001, 0.000001),
                    }],
                    "policy": {"minimum_quality": 1.0, "minimum_net_reduction_fraction": 0.0},
                },
                "observed_resources": {
                    "provider_called": provider_called,
                    "provider_latency_s": result.latency_s if provider_called else 0.0,
                    "input_tokens_provider_reported": int(result.usage.get("input_tokens", 0) or 0) if provider_called else 0,
                    "output_tokens_provider_reported": int(result.usage.get("output_tokens", 0) or 0) if provider_called else 0,
                },
                "quality": {"status": "PASS" if quality.get("pass") else "FAIL", "score": quality.get("score")},
                "instrumentation": ["time.perf_counter", "time.process_time", "Azure Responses usage when provider_called"],
            }
            integrated = self.core.integrated_run(pipeline_payload)
            eden_summary = {
                "marble_id": integrated.get("marble", {}).get("marble_id"),
                "integrity_verified": integrated.get("verification", {}).get("integrity_verified"),
                "chrysalis_status": integrated.get("chrysalis", {}).get("status"),
                "chrononav_selected_workers": integrated.get("chrononav", {}).get("selected_workers"),
            }

        wall_s = time.perf_counter() - wall0
        cpu_s = time.process_time() - cpu0
        record = {
            "schema": SCHEMA,
            "timestamp_utc": utcnow(),
            "request_uid": request_uid,
            "task_index": task_index,
            "arm": arm,
            "input_sha256": sha256_bytes(prompt.encode("utf-8")),
            "output_sha256": sha256_bytes(result.text.encode("utf-8")),
            "cache": {"type": "EXACT_SHA256", "hit": cache_hit, "key": key},
            "provider_called": provider_called,
            "provider": {
                "deployment": self.deployment,
                "response_id": result.response_id if provider_called else None,
                "response_headers": result.headers if provider_called else {},
                "provider_latency_s": result.latency_s if provider_called else 0.0,
                "usage": result.usage if provider_called else {"input_tokens": 0, "output_tokens": 0},
                "raw_response_sha256": result.raw_sha256 if provider_called else None,
            },
            "service": {"wall_seconds": wall_s, "cpu_seconds": cpu_s},
            "quality": quality,
            "eden": eden_summary,
        }
        record["record_sha256"] = sha256_obj(record)
        self._append_event(record)
        return record


class Handler(BaseHTTPRequestHandler):
    service: FairABService

    def _write(self, status: int, payload: Mapping[str, Any]) -> None:
        raw = json.dumps(payload, sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_POST(self) -> None:
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            if self.path == "/evaluate":
                self._write(200, self.service.evaluate(payload))
            elif self.path == "/reset":
                self.service.reset_arm(str(payload.get("arm", "")))
                self._write(200, {"status": "ok"})
            else:
                self._write(404, {"error": "not_found"})
        except Exception as exc:
            self._write(400, {"error": type(exc).__name__, "message": str(exc)})

    def log_message(self, fmt: str, *args: Any) -> None:
        return


def make_workload(requests: int, unique_tasks: int, seed: int) -> List[Dict[str, Any]]:
    if requests <= 0 or unique_tasks <= 0 or unique_tasks > requests:
        raise ValueError("require 0 < unique_tasks <= requests")
    rng = random.Random(seed)
    tasks = list(range(unique_tasks))
    sequence = list(tasks)
    while len(sequence) < requests:
        sequence.append(rng.choice(tasks))
    rng.shuffle(sequence)
    return [
        {
            "request_uid": f"r{i:06d}",
            "task_index": task_index,
            "prompt": prompt_for(task_index),
        }
        for i, task_index in enumerate(sequence)
    ]


def post_json(url: str, payload: Mapping[str, Any]) -> Dict[str, Any]:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=180) as response:
        return json.loads(response.read())


def summarize(records: List[Mapping[str, Any]], input_price_per_1m: Optional[float], output_price_per_1m: Optional[float]) -> Dict[str, Any]:
    service_wall = [float(r["service"]["wall_seconds"]) for r in records]
    service_cpu = [float(r["service"]["cpu_seconds"]) for r in records]
    provider_lat = [float(r["provider"]["provider_latency_s"]) for r in records if r.get("provider_called")]
    input_tokens = sum(int(r["provider"]["usage"].get("input_tokens", 0) or 0) for r in records)
    output_tokens = sum(int(r["provider"]["usage"].get("output_tokens", 0) or 0) for r in records)
    modeled_cost = None
    if input_price_per_1m is not None and output_price_per_1m is not None:
        modeled_cost = (input_tokens / 1_000_000.0) * input_price_per_1m + (output_tokens / 1_000_000.0) * output_price_per_1m
    return {
        "requests": len(records),
        "provider_calls": sum(1 for r in records if r.get("provider_called")),
        "cache_hits": sum(1 for r in records if r.get("cache", {}).get("hit")),
        "quality_passes": sum(1 for r in records if r.get("quality", {}).get("pass")),
        "quality_pass_rate": sum(1 for r in records if r.get("quality", {}).get("pass")) / len(records) if records else None,
        "provider_reported_input_tokens": input_tokens,
        "provider_reported_output_tokens": output_tokens,
        "service_wall_mean_s": mean(service_wall),
        "service_wall_p50_s": percentile(service_wall, 0.50),
        "service_wall_p95_s": percentile(service_wall, 0.95),
        "service_cpu_mean_s": mean(service_cpu),
        "provider_latency_mean_s": mean(provider_lat),
        "provider_latency_p95_s": percentile(provider_lat, 0.95),
        "modeled_token_cost": modeled_cost,
        "modeled_token_cost_class": "MODELLED_FROM_PROVIDER_REPORTED_USAGE" if modeled_cost is not None else "NOT_COMPUTED",
    }


def load_billing(path: Optional[str]) -> Dict[str, Any]:
    if not path:
        return {"status": "NOT_SUPPLIED"}
    p = Path(path)
    obj = json.loads(p.read_text(encoding="utf-8"))
    return {
        "status": "SUPPLIED_EXTERNAL_EVIDENCE",
        "file": str(p),
        "sha256": sha256_bytes(p.read_bytes()),
        "content": obj,
        "boundary": "Billing evidence is supplied by the operator and preserved with a file hash; this harness does not independently attest the Azure billing system.",
    }


def run(args: argparse.Namespace) -> Dict[str, Any]:
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    event_log = out / "service-events.jsonl"
    if event_log.exists():
        event_log.unlink()

    if args.provider == "mock":
        provider: Any = MockProvider()
        provider_class = "SIMULATED_MOCK_PROVIDER"
    else:
        endpoint = os.environ["AZURE_OPENAI_ENDPOINT"]
        key = os.environ["AZURE_OPENAI_API_KEY"]
        deployment = os.environ["AZURE_OPENAI_DEPLOYMENT"]
        provider = AzureProvider(endpoint, key, deployment, args.max_output_tokens)
        provider_class = "AZURE_OPENAI_PROVIDER"

    Handler.service = FairABService(provider, out / "state", event_log)
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"

    workload = make_workload(args.requests, args.unique_tasks, args.seed)
    records_by_arm: Dict[str, List[Dict[str, Any]]] = {arm: [] for arm in ALLOWED_ARMS}
    order_rng = random.Random(args.seed ^ 0xEDEN if False else args.seed ^ 0xEDEA)
    started = time.time()
    try:
        for item in workload:
            arm_order = list(ALLOWED_ARMS)
            order_rng.shuffle(arm_order)
            for arm in arm_order:
                payload = dict(item)
                payload["arm"] = arm
                records_by_arm[arm].append(post_json(base_url + "/evaluate", payload))
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    input_price = args.input_price_per_1m
    output_price = args.output_price_per_1m
    summaries = {
        arm: summarize(records, input_price, output_price)
        for arm, records in records_by_arm.items()
    }
    for arm, records in records_by_arm.items():
        path = out / f"{arm}-records.jsonl"
        path.write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in records), encoding="utf-8")

    control = summaries["control"]
    eden = summaries["eden"]
    comparison = {
        "service_wall_delta_fraction": (
            (eden["service_wall_mean_s"] - control["service_wall_mean_s"]) / control["service_wall_mean_s"]
            if control.get("service_wall_mean_s") else None
        ),
        "service_cpu_delta_fraction": (
            (eden["service_cpu_mean_s"] - control["service_cpu_mean_s"]) / control["service_cpu_mean_s"]
            if control.get("service_cpu_mean_s") else None
        ),
        "provider_call_delta": eden["provider_calls"] - control["provider_calls"],
        "input_token_delta": eden["provider_reported_input_tokens"] - control["provider_reported_input_tokens"],
        "output_token_delta": eden["provider_reported_output_tokens"] - control["provider_reported_output_tokens"],
        "modeled_token_cost_delta": (
            eden["modeled_token_cost"] - control["modeled_token_cost"]
            if eden.get("modeled_token_cost") is not None and control.get("modeled_token_cost") is not None else None
        ),
        "quality_pass_rate_delta": eden["quality_pass_rate"] - control["quality_pass_rate"],
    }
    manifest = {
        "schema": SCHEMA,
        "experiment": "AZURE-FAIR-AB-001",
        "timestamp_utc": utcnow(),
        "provider_class": provider_class,
        "service_boundary": "IDENTICAL_LOCAL_HTTP_POST_/evaluate",
        "control_path": "HTTP -> deserialize -> exact SHA256 cache -> Azure on miss -> response",
        "eden_path": "HTTP -> deserialize -> same exact SHA256 cache -> Azure on miss -> EDEN Core integrated evidence path -> response",
        "requests_per_arm": args.requests,
        "unique_tasks": args.unique_tasks,
        "seed": args.seed,
        "wall_seconds_total": time.time() - started,
        "summaries": summaries,
        "comparison": comparison,
        "billing": load_billing(args.billing_json),
        "files": {},
        "truth_boundary": {
            "claims": [
                "both arms used the same local HTTP endpoint and workload sequence",
                "provider-reported token usage is captured on actual provider calls",
                "local service wall and CPU time are measured by the harness",
            ],
            "not_claimed": [
                "Azure energy use unless separately instrumented",
                "provider billing from modeled token prices",
                "independent validation",
                "general Azure efficiency superiority",
            ],
        },
    }
    for name in ("control-records.jsonl", "eden-records.jsonl", "service-events.jsonl"):
        p = out / name
        manifest["files"][name] = sha256_bytes(p.read_bytes())
    manifest["manifest_sha256"] = sha256_obj(manifest)
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", choices=("azure", "mock"), default="azure")
    parser.add_argument("--requests", type=int, default=100)
    parser.add_argument("--unique-tasks", type=int, default=25)
    parser.add_argument("--seed", type=int, default=260830)
    parser.add_argument("--max-output-tokens", type=int, default=96)
    parser.add_argument("--output-dir", default="experiments/azure-fair-ab-001/results/latest")
    parser.add_argument("--input-price-per-1m", type=float, default=None)
    parser.add_argument("--output-price-per-1m", type=float, default=None)
    parser.add_argument("--billing-json", default=None)
    return parser.parse_args(argv)


def main() -> None:
    args = parse_args()
    manifest = run(args)
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
