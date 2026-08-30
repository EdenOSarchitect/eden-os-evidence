#!/usr/bin/env python3
"""AZURE-LIVE-004: paired identical-provider-response EDEN overhead experiment.

Purpose
-------
Capture each unique provider result once, then replay that *identical* result
through CONTROL and EDEN local processing paths. This removes stochastic Azure
latency and reasoning-token variation from the local-overhead comparison.

Evidence boundary
-----------------
- Provider capture IDs/usage are provider-reported when --provider azure.
- Replay wall/CPU timings are measured locally with Python clocks.
- No Azure energy, Azure billing saving, or general efficiency superiority is
  claimed by this experiment.
- The replay phase does not make additional provider calls.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import statistics
import sys
import time
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from eden_core.core import EdenCore  # noqa: E402

SCHEMA = "eden.azure.live_004.v1"
EXPERIMENT = "AZURE-LIVE-004"


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def canon(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sha256_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def sha256_obj(value: Any) -> str:
    return sha256_bytes(canon(value))


def mean(values: List[float]) -> Optional[float]:
    return statistics.mean(values) if values else None


def expected_for(task_index: int) -> Dict[str, int]:
    a = (task_index * 7919 + 104729) % 1000003
    b = (task_index * 15485863 + 32452843) % 10000019
    return {"index": task_index, "checksum": (a * b + task_index) % 2147483647}


def prompt_for(task_index: int) -> str:
    exp = expected_for(task_index)
    a = (task_index * 7919 + 104729) % 1000003
    b = (task_index * 15485863 + 32452843) % 10000019
    return (
        "Azure validation workload. Return the requested structured object. "
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


def extract_text(obj: Mapping[str, Any]) -> str:
    if isinstance(obj.get("output_text"), str):
        return str(obj["output_text"])
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


def output_schema() -> Dict[str, Any]:
    return {
        "type": "json_schema",
        "name": "eden_validation_result",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "index": {"type": "integer"},
                "checksum": {"type": "integer"},
                "classification": {
                    "type": "string",
                    "enum": ["KEEP", "STRUCTURE", "DETAIL", "VOID"],
                },
                "summary": {"type": "string"},
            },
            "required": ["index", "checksum", "classification", "summary"],
            "additionalProperties": False,
        },
    }


@dataclass
class Capture:
    task_index: int
    prompt: str
    text: str
    usage: Dict[str, Any]
    response_id: Optional[str]
    latency_s: float
    raw_response_sha256: str
    provider_class: str


class AzureProvider:
    def __init__(self, endpoint: str, key: str, deployment: str, max_output_tokens: int) -> None:
        self.endpoint = endpoint.rstrip("/")
        self.key = key
        self.deployment = deployment
        self.max_output_tokens = max_output_tokens

    def capture(self, task_index: int) -> Capture:
        prompt = prompt_for(task_index)
        payload = {
            "model": self.deployment,
            "input": prompt,
            "max_output_tokens": self.max_output_tokens,
            "text": {"format": output_schema()},
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
        latency_s = time.perf_counter() - t0
        obj = json.loads(raw)
        usage = obj.get("usage") if isinstance(obj.get("usage"), Mapping) else {}
        return Capture(
            task_index=task_index,
            prompt=prompt,
            text=extract_text(obj),
            usage=dict(usage),
            response_id=obj.get("id") if isinstance(obj.get("id"), str) else None,
            latency_s=latency_s,
            raw_response_sha256=sha256_bytes(raw),
            provider_class="AZURE_OPENAI_PROVIDER",
        )


class MockProvider:
    deployment = "mock-provider"

    def capture(self, task_index: int) -> Capture:
        prompt = prompt_for(task_index)
        exp = expected_for(task_index)
        text = json.dumps({
            "index": task_index,
            "checksum": exp["checksum"],
            "classification": "KEEP",
            "summary": "deterministic replay fixture",
        }, separators=(",", ":"))
        return Capture(
            task_index=task_index,
            prompt=prompt,
            text=text,
            usage={"input_tokens": max(1, len(prompt) // 4), "output_tokens": max(1, len(text) // 4)},
            response_id=f"mock-{task_index}",
            latency_s=0.0,
            raw_response_sha256=sha256_bytes(text.encode("utf-8")),
            provider_class="SIMULATED_MOCK_PROVIDER",
        )


def base_local_processing(capture: Capture) -> Dict[str, Any]:
    quality = quality_check(capture.text, capture.task_index)
    return {
        "input_sha256": sha256_bytes(capture.prompt.encode("utf-8")),
        "output_sha256": sha256_bytes(capture.text.encode("utf-8")),
        "quality": quality,
    }


def run_control(capture: Capture) -> Dict[str, Any]:
    wall0 = time.perf_counter()
    cpu0 = time.process_time()
    base = base_local_processing(capture)
    record = {
        "base": base,
        "local_record_commitment": sha256_obj({
            "task_index": capture.task_index,
            "input_sha256": base["input_sha256"],
            "output_sha256": base["output_sha256"],
            "quality": base["quality"],
        }),
    }
    cpu_s = time.process_time() - cpu0
    wall_s = time.perf_counter() - wall0
    return {"cpu_seconds": cpu_s, "wall_seconds": wall_s, **record}


def run_eden(core: EdenCore, capture: Capture, replay_uid: str) -> Dict[str, Any]:
    wall0 = time.perf_counter()
    cpu0 = time.process_time()
    base = base_local_processing(capture)
    quality = base["quality"]
    integrated = core.integrated_run({
        "run_id": f"{EXPERIMENT}-{replay_uid}",
        "refinery": {
            "input": capture.prompt,
            "output": capture.text,
            "classification": "KEEP",
        },
        "chrononav": {
            "predicted_seconds": {"1": max(capture.latency_s, 0.000001)},
            "deadline_seconds": max(capture.latency_s * 2.0, 0.001),
            "prediction_provenance": "CAPTURED_PROVIDER_LATENCY_REFERENCE_NOT_REPLAY_COST",
        },
        "chrysalis": {
            "baseline": {"quality": 1.0, "total": max(capture.latency_s, 0.000001)},
            "candidates": [{
                "id": "identical-captured-provider-result",
                "quality": float(quality.get("score", 0.0)),
                "total": 0.000001,
            }],
            "policy": {"minimum_quality": 1.0, "minimum_net_reduction_fraction": 0.0},
        },
        "observed_resources": {
            "provider_called_during_replay": False,
            "captured_provider_latency_s": capture.latency_s,
            "captured_input_tokens_provider_reported": int(capture.usage.get("input_tokens", 0) or 0),
            "captured_output_tokens_provider_reported": int(capture.usage.get("output_tokens", 0) or 0),
        },
        "quality": {
            "status": "PASS" if quality.get("pass") else "FAIL",
            "score": quality.get("score"),
        },
        "instrumentation": [
            "time.perf_counter",
            "time.process_time",
            "captured Azure Responses usage outside replay timing",
        ],
    })
    cpu_s = time.process_time() - cpu0
    wall_s = time.perf_counter() - wall0
    return {
        "cpu_seconds": cpu_s,
        "wall_seconds": wall_s,
        "base": base,
        "marble_id": integrated.get("marble", {}).get("marble_id"),
        "integrity_verified": integrated.get("verification", {}).get("integrity_verified"),
        "chrononav_selected_workers": integrated.get("chrononav", {}).get("selected_workers"),
        "chrysalis_status": integrated.get("chrysalis", {}).get("status"),
    }


def write_jsonl(path: Path, rows: List[Mapping[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n")


def file_sha256(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", choices=["azure", "mock"], default="mock")
    ap.add_argument("--unique-tasks", type=int, default=2)
    ap.add_argument("--repeats", type=int, default=20)
    ap.add_argument("--max-output-tokens", type=int, default=512)
    ap.add_argument("--seed", type=int, default=260830004)
    ap.add_argument("--output-dir", type=Path, default=Path("experiments/azure-live-004/results/AZURE-LIVE-004"))
    args = ap.parse_args()

    if args.unique_tasks < 1 or args.repeats < 1:
        raise SystemExit("unique-tasks and repeats must be >= 1")

    if args.provider == "azure":
        endpoint = os.getenv("AZURE_OPENAI_ENDPOINT", "")
        key = os.getenv("AZURE_OPENAI_API_KEY", "")
        deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT", "")
        missing = [name for name, value in {
            "AZURE_OPENAI_ENDPOINT": endpoint,
            "AZURE_OPENAI_API_KEY": key,
            "AZURE_OPENAI_DEPLOYMENT": deployment,
        }.items() if not value]
        if missing:
            raise SystemExit("missing Azure environment variables: " + ", ".join(missing))
        provider: Any = AzureProvider(endpoint, key, deployment, args.max_output_tokens)
        deployment_name = deployment
    else:
        provider = MockProvider()
        deployment_name = provider.deployment

    out = args.output_dir
    out.mkdir(parents=True, exist_ok=True)
    core = EdenCore(repo_root=REPO_ROOT, state_dir=out / "state" / "eden-core")

    captures: List[Capture] = []
    capture_rows: List[Dict[str, Any]] = []
    for task_index in range(args.unique_tasks):
        cap = provider.capture(task_index)
        q = quality_check(cap.text, task_index)
        row = {
            "schema": SCHEMA,
            "experiment": EXPERIMENT,
            "phase": "CAPTURE",
            "timestamp_utc": utcnow(),
            "task_index": task_index,
            "provider_class": cap.provider_class,
            "deployment": deployment_name,
            "response_id": cap.response_id,
            "provider_latency_s": cap.latency_s,
            "provider_usage": cap.usage,
            "raw_response_sha256": cap.raw_response_sha256,
            "input_sha256": sha256_bytes(cap.prompt.encode("utf-8")),
            "output_sha256": sha256_bytes(cap.text.encode("utf-8")),
            "quality": q,
        }
        row["record_sha256"] = sha256_obj(row)
        captures.append(cap)
        capture_rows.append(row)

    if not all(row["quality"].get("pass") for row in capture_rows):
        write_jsonl(out / "captures.jsonl", capture_rows)
        raise SystemExit("capture quality gate failed; replay not run")

    rng = random.Random(args.seed)
    replay_rows: List[Dict[str, Any]] = []
    pair_deltas_cpu: List[float] = []
    pair_deltas_wall: List[float] = []

    for repeat in range(args.repeats):
        for cap in captures:
            order = ["control", "eden"]
            rng.shuffle(order)
            pair: Dict[str, Dict[str, Any]] = {}
            for arm in order:
                uid = f"t{cap.task_index:04d}-r{repeat:04d}-{arm}"
                result = run_control(cap) if arm == "control" else run_eden(core, cap, uid)
                row = {
                    "schema": SCHEMA,
                    "experiment": EXPERIMENT,
                    "phase": "PAIRED_REPLAY",
                    "timestamp_utc": utcnow(),
                    "task_index": cap.task_index,
                    "repeat": repeat,
                    "arm": arm,
                    "provider_called_during_replay": False,
                    "captured_response_id": cap.response_id,
                    "captured_output_sha256": sha256_bytes(cap.text.encode("utf-8")),
                    "cpu_seconds": result["cpu_seconds"],
                    "wall_seconds": result["wall_seconds"],
                    "quality": result["base"]["quality"],
                    "output_sha256": result["base"]["output_sha256"],
                    "marble_id": result.get("marble_id"),
                    "integrity_verified": result.get("integrity_verified"),
                    "chrononav_selected_workers": result.get("chrononav_selected_workers"),
                    "chrysalis_status": result.get("chrysalis_status"),
                }
                row["record_sha256"] = sha256_obj(row)
                replay_rows.append(row)
                pair[arm] = row
            pair_deltas_cpu.append(pair["eden"]["cpu_seconds"] - pair["control"]["cpu_seconds"])
            pair_deltas_wall.append(pair["eden"]["wall_seconds"] - pair["control"]["wall_seconds"])

    captures_path = out / "captures.jsonl"
    replay_path = out / "replay-records.jsonl"
    write_jsonl(captures_path, capture_rows)
    write_jsonl(replay_path, replay_rows)

    control = [r for r in replay_rows if r["arm"] == "control"]
    eden = [r for r in replay_rows if r["arm"] == "eden"]
    control_cpu = [float(r["cpu_seconds"]) for r in control]
    eden_cpu = [float(r["cpu_seconds"]) for r in eden]
    control_wall = [float(r["wall_seconds"]) for r in control]
    eden_wall = [float(r["wall_seconds"]) for r in eden]

    provider_input_tokens = sum(int(c.usage.get("input_tokens", 0) or 0) for c in captures)
    provider_output_tokens = sum(int(c.usage.get("output_tokens", 0) or 0) for c in captures)

    manifest: Dict[str, Any] = {
        "schema": SCHEMA,
        "experiment": EXPERIMENT,
        "timestamp_utc": utcnow(),
        "provider_class": captures[0].provider_class if captures else None,
        "deployment": deployment_name,
        "unique_tasks": args.unique_tasks,
        "repeats_per_task": args.repeats,
        "provider_calls_total": args.unique_tasks,
        "provider_calls_during_replay": 0,
        "provider_reported_input_tokens_capture": provider_input_tokens,
        "provider_reported_output_tokens_capture": provider_output_tokens,
        "capture_quality_pass_rate": sum(bool(r["quality"].get("pass")) for r in capture_rows) / len(capture_rows),
        "replay": {
            "pairs": len(pair_deltas_cpu),
            "control_quality_pass_rate": sum(bool(r["quality"].get("pass")) for r in control) / len(control),
            "eden_quality_pass_rate": sum(bool(r["quality"].get("pass")) for r in eden) / len(eden),
            "identical_output_hash_all_pairs": all(
                replay_rows[i]["output_sha256"] == replay_rows[i + 1]["output_sha256"]
                for i in range(0, len(replay_rows), 2)
            ),
            "eden_integrity_verified_all": all(r.get("integrity_verified") is True for r in eden),
            "control_cpu_mean_s": mean(control_cpu),
            "eden_cpu_mean_s": mean(eden_cpu),
            "paired_cpu_overhead_mean_s": mean(pair_deltas_cpu),
            "control_wall_mean_s": mean(control_wall),
            "eden_wall_mean_s": mean(eden_wall),
            "paired_wall_overhead_mean_s": mean(pair_deltas_wall),
        },
        "files": {
            "captures.jsonl": file_sha256(captures_path),
            "replay-records.jsonl": file_sha256(replay_path),
        },
        "truth_boundary": {
            "claims": [
                "each unique provider result is captured once before replay",
                "CONTROL and EDEN replay the identical captured output bytes for each pair",
                "no provider calls occur inside replay timing",
                "paired local wall/CPU overhead is measured by Python clocks",
            ],
            "not_claimed": [
                "Azure energy consumption",
                "Azure billing savings",
                "provider latency improvement",
                "general Azure efficiency superiority",
                "independent validation",
            ],
        },
    }
    manifest["manifest_sha256"] = sha256_obj(manifest)
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
