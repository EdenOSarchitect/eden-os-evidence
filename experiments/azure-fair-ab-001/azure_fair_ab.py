#!/usr/bin/env python3
"""AZURE-FAIR-AB-001: identical-boundary Azure CONTROL vs EDEN benchmark.

Both arms enter through the same local HTTP POST /evaluate boundary and target
the same Azure OpenAI deployment. CONTROL is a conventional exact-cache
service. EDEN uses the same exact-cache primitive and additionally executes the
EDEN Core integrated evidence path (Refinery -> ChronoNav -> Chrysalis ->
Marble v2 -> integrity verify).

Evidence boundaries:
- Azure response usage/request IDs are provider-reported observations.
- Local wall/CPU timings are measured by this harness.
- Token-price-derived cost is MODELLED, not Azure billing.
- Optional billing JSON is externally supplied evidence and is file-hashed.
- No Azure energy figure is created by this harness.
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
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from eden_core.core import EdenCore  # noqa: E402

SCHEMA = "eden.azure.fair_ab.v1"
ARMS = ("control", "eden")


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def canon(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sha256_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def sha256_obj(value: Any) -> str:
    return sha256_bytes(canon(value))


def _mean(values: List[float]) -> Optional[float]:
    return statistics.mean(values) if values else None


def _percentile(values: List[float], p: float) -> Optional[float]:
    if not values:
        return None
    ordered = sorted(values)
    idx = int(round((len(ordered) - 1) * p))
    return ordered[max(0, min(len(ordered) - 1, idx))]


def expected_for(task_index: int) -> Dict[str, int]:
    a = (task_index * 7919 + 104729) % 1000003
    b = (task_index * 15485863 + 32452843) % 10000019
    return {"index": task_index, "checksum": (a * b + task_index) % 2147483647}


def prompt_for(task_index: int) -> str:
    exp = expected_for(task_index)
    a = (task_index * 7919 + 104729) % 1000003
    b = (task_index * 15485863 + 32452843) % 10000019
    return (
        "Azure validation workload. Return STRICT JSON only with keys "
        "index, checksum, classification, summary. "
        f"index={task_index}; a={a}; b={b}; checksum={exp['checksum']}. "
        "classification must be KEEP, STRUCTURE, DETAIL, or VOID. "
        "summary must be <= 12 words."
    )


def quality_check(text: str, task_index: int) -> Dict[str, Any]:
    exp = expected_for(task_index)
    try:
        obj = json.loads(text)
    except Exception:
        return {"pass": False, "score": 0.0, "reason": "invalid_json"}
    if not isinstance(obj, Mapping):
        return {"pass": False, "score": 0.0, "reason": "not_object"}
    checks = {
        "index": obj.get("index") == exp["index"],
        "checksum": obj.get("checksum") == exp["checksum"],
        "classification": obj.get("classification") in {"KEEP", "STRUCTURE", "DETAIL", "VOID"},
        "summary": isinstance(obj.get("summary"), str) and len(str(obj.get("summary", "")).split()) <= 12,
    }
    score = sum(bool(v) for v in checks.values()) / len(checks)
    return {"pass": all(checks.values()), "score": score, "checks": checks}


def exact_cache_key(prompt: str, deployment: str, max_output_tokens: int) -> str:
    return sha256_obj({
        "prompt": prompt,
        "deployment": deployment,
        "max_output_tokens": max_output_tokens,
        "cache_policy": "EXACT_SHA256_V1",
    })


def extract_text(obj: Mapping[str, Any]) -> str:
    if isinstance(obj.get("output_text"), str):
        return str(obj["output_text"])
    parts: List[str] = []
    for item in obj.get("output", []) if isinstance(obj.get("output"), list) else []:
        if not isinstance(item, Mapping):
            continue
        for piece in item.get("content", []) if isinstance(item.get("content"), list) else []:
            if isinstance(piece, Mapping) and isinstance(piece.get("text"), str):
                parts.append(str(piece["text"]))
    return "\n".join(parts)


@dataclass
class ProviderResult:
    text: str
    usage: Dict[str, Any]
    latency_s: float
    response_id: Optional[str]
    response_headers: Dict[str, str]
    raw_response_sha256: str


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
        request = urllib.request.Request(
            self.endpoint + "/openai/v1/responses",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "api-key": self.key},
            method="POST",
        )
        t0 = time.perf_counter()
        with urllib.request.urlopen(request, timeout=120) as response:
            raw = response.read()
            headers = {
                k.lower(): v for k, v in response.headers.items()
                if k.lower() in {
                    "x-ms-request-id", "apim-request-id", "x-request-id", "traceparent",
                    "x-ratelimit-remaining-requests", "x-ratelimit-remaining-tokens",
                }
            }
        elapsed = time.perf_counter() - t0
        obj = json.loads(raw)
        usage = obj.get("usage") if isinstance(obj.get("usage"), Mapping) else {}
        return ProviderResult(
            text=extract_text(obj),
            usage=dict(usage),
            latency_s=elapsed,
            response_id=obj.get("id") if isinstance(obj.get("id"), str) else None,
            response_headers=headers,
            raw_response_sha256=sha256_bytes(raw),
        )


class MockProvider:
    """CI-only deterministic provider; never treated as Azure measurement."""
    deployment = "mock-provider"
    max_output_tokens = 96

    def __init__(self, latency_s: float = 0.001) -> None:
        self.latency_s = latency_s

    def call(self, prompt: str) -> ProviderResult:
        task_index = int(prompt.split("index=", 1)[1].split(";", 1)[0])
        exp = expected_for(task_index)
        text = json.dumps({
            "index": task_index,
            "checksum": exp["checksum"],
            "classification": "KEEP",
            "summary": "deterministic mock response",
        }, separators=(",", ":"))
        time.sleep(self.latency_s)
        return ProviderResult(
            text=text,
            usage={"input_tokens": max(1, len(prompt) // 4), "output_tokens": max(1, len(text) // 4)},
            latency_s=self.latency_s,
            response_id=f"mock-{task_index}",
            response_headers={"x-request-id": f"mock-{task_index}"},
            raw_response_sha256=sha256_bytes(text.encode("utf-8")),
        )


class FairABService:
    def __init__(self, provider: Any, state_dir: Path, event_log: Path) -> None:
        self.provider = provider
        self.deployment = str(getattr(provider, "deployment", "unknown"))
        self.max_output_tokens = int(getattr(provider, "max_output_tokens", 96))
        self.core = EdenCore(repo_root=REPO_ROOT, state_dir=state_dir / "eden-core")
        self.caches: Dict[str, Dict[str, ProviderResult]] = {arm: {} for arm in ARMS}
        self.event_log = event_log
        self.event_log.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def append_event(self, record: Mapping[str, Any]) -> None:
        with self._lock:
            with self.event_log.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")

    def evaluate(self, payload: Mapping[str, Any]) -> Dict[str, Any]:
        arm = str(payload.get("arm", ""))
        if arm not in ARMS:
            raise ValueError(f"arm must be one of {ARMS}")
        request_uid = str(payload.get("request_uid", ""))
        task_index = int(payload.get("task_index"))
        prompt = str(payload.get("prompt", ""))
        if not request_uid or not prompt:
            raise ValueError("request_uid and prompt are required")

        wall0 = time.perf_counter()
        cpu0 = time.process_time()
        cache_key = exact_cache_key(prompt, self.deployment, self.max_output_tokens)
        with self._lock:
            cached = self.caches[arm].get(cache_key)
        cache_hit = cached is not None
        provider_called = not cache_hit
        if cached is None:
            result = self.provider.call(prompt)
            with self._lock:
                self.caches[arm][cache_key] = result
        else:
            result = cached

        quality = quality_check(result.text, task_index)
        eden = None
        if arm == "eden":
            provider_cost_proxy_s = max(result.latency_s, 0.000001)
            candidate_cost_proxy_s = provider_cost_proxy_s if provider_called else 0.000001
            integrated = self.core.integrated_run({
                "run_id": f"AZURE-FAIR-AB-{request_uid}",
                "refinery": {"input": prompt, "output": result.text, "classification": "KEEP"},
                "chrononav": {
                    "predicted_seconds": {"1": provider_cost_proxy_s},
                    "deadline_seconds": max(provider_cost_proxy_s * 2.0, 0.001),
                    "prediction_provenance": "OBSERVED_PROVIDER_LATENCY_REFERENCE_NOT_ROUTING_PROOF",
                },
                "chrysalis": {
                    "baseline": {"quality": 1.0, "total": provider_cost_proxy_s},
                    "candidates": [{
                        "id": "exact-reuse" if cache_hit else "provider-result",
                        "quality": float(quality.get("score", 0.0)),
                        "total": candidate_cost_proxy_s,
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
                "instrumentation": ["time.perf_counter", "time.process_time", "Azure Responses usage on provider calls"],
            })
            eden = {
                "marble_id": integrated.get("marble", {}).get("marble_id"),
                "integrity_verified": integrated.get("verification", {}).get("integrity_verified"),
                "chrononav_selected_workers": integrated.get("chrononav", {}).get("selected_workers"),
                "chrysalis_status": integrated.get("chrysalis", {}).get("status"),
            }

        record = {
            "schema": SCHEMA,
            "timestamp_utc": utcnow(),
            "request_uid": request_uid,
            "task_index": task_index,
            "arm": arm,
            "input_sha256": sha256_bytes(prompt.encode("utf-8")),
            "output_sha256": sha256_bytes(result.text.encode("utf-8")),
            "cache": {"type": "EXACT_SHA256", "key": cache_key, "hit": cache_hit},
            "provider_called": provider_called,
            "provider": {
                "deployment": self.deployment,
                "response_id": result.response_id if provider_called else None,
                "response_headers": result.response_headers if provider_called else {},
                "provider_latency_s": result.latency_s if provider_called else 0.0,
                "usage": result.usage if provider_called else {"input_tokens": 0, "output_tokens": 0},
                "raw_response_sha256": result.raw_response_sha256 if provider_called else None,
            },
            "service": {
                "wall_seconds": time.perf_counter() - wall0,
                "cpu_seconds": time.process_time() - cpu0,
            },
            "quality": quality,
            "eden": eden,
        }
        record["record_sha256"] = sha256_obj(record)
        self.append_event(record)
        return record


class HTTPHandler(BaseHTTPRequestHandler):
    service: FairABService

    def _write(self, status: int, payload: Mapping[str, Any]) -> None:
        body = json.dumps(payload, sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:
        try:
            length = int(self.headers.get("Content-Length", "0"))
            obj = json.loads(self.rfile.read(length).decode("utf-8"))
            if self.path != "/evaluate":
                self._write(404, {"error": "not_found"})
                return
            self._write(200, self.service.evaluate(obj))
        except Exception as exc:
            self._write(400, {"error": type(exc).__name__, "message": str(exc)})

    def log_message(self, fmt: str, *args: Any) -> None:
        return


def post_json(url: str, payload: Mapping[str, Any]) -> Dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=180) as response:
        return json.loads(response.read())


def make_workload(requests: int, unique_tasks: int, seed: int) -> List[Dict[str, Any]]:
    if not (0 < unique_tasks <= requests):
        raise ValueError("require 0 < unique_tasks <= requests")
    rng = random.Random(seed)
    sequence = list(range(unique_tasks))
    while len(sequence) < requests:
        sequence.append(rng.randrange(unique_tasks))
    rng.shuffle(sequence)
    return [
        {"request_uid": f"r{i:06d}", "task_index": idx, "prompt": prompt_for(idx)}
        for i, idx in enumerate(sequence)
    ]


def summarize(records: List[Mapping[str, Any]], input_price: Optional[float], output_price: Optional[float]) -> Dict[str, Any]:
    walls = [float(r["service"]["wall_seconds"]) for r in records]
    cpus = [float(r["service"]["cpu_seconds"]) for r in records]
    provider_lat = [float(r["provider"]["provider_latency_s"]) for r in records if r.get("provider_called")]
    input_tokens = sum(int(r["provider"]["usage"].get("input_tokens", 0) or 0) for r in records)
    output_tokens = sum(int(r["provider"]["usage"].get("output_tokens", 0) or 0) for r in records)
    modeled_cost = None
    if input_price is not None and output_price is not None:
        modeled_cost = input_tokens * input_price / 1_000_000.0 + output_tokens * output_price / 1_000_000.0
    return {
        "requests": len(records),
        "provider_calls": sum(bool(r.get("provider_called")) for r in records),
        "cache_hits": sum(bool(r.get("cache", {}).get("hit")) for r in records),
        "quality_passes": sum(bool(r.get("quality", {}).get("pass")) for r in records),
        "quality_pass_rate": sum(bool(r.get("quality", {}).get("pass")) for r in records) / len(records) if records else None,
        "provider_reported_input_tokens": input_tokens,
        "provider_reported_output_tokens": output_tokens,
        "service_wall_mean_s": _mean(walls),
        "service_wall_p50_s": _percentile(walls, 0.50),
        "service_wall_p95_s": _percentile(walls, 0.95),
        "service_cpu_mean_s": _mean(cpus),
        "provider_latency_mean_s": _mean(provider_lat),
        "provider_latency_p95_s": _percentile(provider_lat, 0.95),
        "modeled_token_cost": modeled_cost,
        "modeled_token_cost_class": "MODELLED_FROM_PROVIDER_REPORTED_USAGE" if modeled_cost is not None else "NOT_COMPUTED",
    }


def load_billing(path: Optional[str]) -> Dict[str, Any]:
    if not path:
        return {"status": "NOT_SUPPLIED"}
    p = Path(path)
    content = json.loads(p.read_text(encoding="utf-8"))
    return {
        "status": "SUPPLIED_EXTERNAL_EVIDENCE",
        "file": str(p),
        "file_sha256": sha256_bytes(p.read_bytes()),
        "content": content,
        "truth_boundary": "The file is integrity-bound by this harness; Azure origin/authenticity must be established by the supplied export provenance.",
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
        provider = AzureProvider(
            os.environ["AZURE_OPENAI_ENDPOINT"],
            os.environ["AZURE_OPENAI_API_KEY"],
            os.environ["AZURE_OPENAI_DEPLOYMENT"],
            args.max_output_tokens,
        )
        provider_class = "AZURE_OPENAI_PROVIDER"

    HTTPHandler.service = FairABService(provider, out / "state", event_log)
    server = ThreadingHTTPServer(("127.0.0.1", 0), HTTPHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    endpoint = f"http://127.0.0.1:{server.server_address[1]}/evaluate"

    workload = make_workload(args.requests, args.unique_tasks, args.seed)
    records: Dict[str, List[Dict[str, Any]]] = {arm: [] for arm in ARMS}
    rng = random.Random(args.seed ^ 0xEDEA)
    started = time.time()
    try:
        for item in workload:
            order = list(ARMS)
            rng.shuffle(order)
            for arm in order:
                payload = dict(item)
                payload["arm"] = arm
                records[arm].append(post_json(endpoint, payload))
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    for arm in ARMS:
        (out / f"{arm}-records.jsonl").write_text(
            "".join(json.dumps(r, sort_keys=True) + "\n" for r in records[arm]),
            encoding="utf-8",
        )

    summaries = {
        arm: summarize(records[arm], args.input_price_per_1m, args.output_price_per_1m)
        for arm in ARMS
    }
    c = summaries["control"]
    e = summaries["eden"]
    comparison = {
        "provider_call_delta": e["provider_calls"] - c["provider_calls"],
        "provider_input_token_delta": e["provider_reported_input_tokens"] - c["provider_reported_input_tokens"],
        "provider_output_token_delta": e["provider_reported_output_tokens"] - c["provider_reported_output_tokens"],
        "quality_pass_rate_delta": e["quality_pass_rate"] - c["quality_pass_rate"],
        "service_wall_mean_delta_fraction": ((e["service_wall_mean_s"] - c["service_wall_mean_s"]) / c["service_wall_mean_s"]) if c["service_wall_mean_s"] else None,
        "service_cpu_mean_delta_fraction": ((e["service_cpu_mean_s"] - c["service_cpu_mean_s"]) / c["service_cpu_mean_s"]) if c["service_cpu_mean_s"] else None,
        "modeled_token_cost_delta": (e["modeled_token_cost"] - c["modeled_token_cost"]) if e["modeled_token_cost"] is not None and c["modeled_token_cost"] is not None else None,
    }

    manifest: Dict[str, Any] = {
        "schema": SCHEMA,
        "experiment": "AZURE-FAIR-AB-001",
        "timestamp_utc": utcnow(),
        "provider_class": provider_class,
        "service_boundary": "IDENTICAL_LOCAL_HTTP_POST_/evaluate",
        "control_path": "HTTP -> deserialize -> exact SHA256 cache -> Azure on miss -> response",
        "eden_path": "HTTP -> deserialize -> same exact SHA256 cache -> Azure on miss -> EDEN Core integrated path -> response",
        "requests_per_arm": args.requests,
        "unique_tasks": args.unique_tasks,
        "reuse_fraction_target": 1.0 - (args.unique_tasks / args.requests),
        "seed": args.seed,
        "total_wall_seconds": time.time() - started,
        "summaries": summaries,
        "comparison": comparison,
        "billing": load_billing(args.billing_json),
        "files": {},
        "truth_boundary": {
            "claims": [
                "both arms used the same local HTTP endpoint and same generated workload sequence",
                "both arms used the same exact-cache algorithm and independent cache state",
                "provider-reported token usage/request identifiers are captured only on provider calls",
                "local service wall/CPU times are measured by Python clocks",
            ],
            "not_claimed": [
                "Azure energy consumption",
                "provider billing from token-price modelling",
                "semantic-cache superiority",
                "general Azure efficiency superiority",
                "independent validation",
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
    print(json.dumps(run(args), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
