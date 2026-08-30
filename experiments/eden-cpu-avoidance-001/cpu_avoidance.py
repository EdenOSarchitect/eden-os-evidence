#!/usr/bin/env python3
"""EDEN-CPU-AVOIDANCE-001

Deterministic A/B measurement of process CPU avoided by verified exact reuse.

CONTROL recomputes every logical job.
EDEN computes a committed workload once and reuses the verified result on repeats.

This experiment measures local process CPU time. It does not claim Azure internal
CPU/GPU/energy savings. When executed in GitHub Actions its evidence class is CI
process-CPU evidence; when run on a handset/VM it remains host-local process CPU.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Tuple

RUN_ID = "EDEN-CPU-AVOIDANCE-001"
SCHEMA = "eden.cpu.avoidance.v1"


def canonical(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def sha256_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def workload(payload: bytes, iterations: int) -> str:
    """CPU-bound deterministic workload."""
    state = hashlib.sha256(payload).digest()
    for i in range(iterations):
        state = hashlib.sha256(state + (i & 0xFFFFFFFF).to_bytes(4, "big")).digest()
    return state.hex()


def make_jobs(requests: int, reuse_fraction: float) -> Tuple[List[bytes], int]:
    if not 0.0 <= reuse_fraction < 1.0:
        raise ValueError("reuse_fraction must be >= 0 and < 1")
    unique = max(1, round(requests * (1.0 - reuse_fraction)))
    jobs = [f"eden-cpu-task-{i % unique}".encode() for i in range(requests)]
    return jobs, unique


def run_control(jobs: List[bytes], iterations: int):
    start_cpu = time.process_time_ns()
    start_wall = time.perf_counter_ns()
    outputs = [workload(job, iterations) for job in jobs]
    return {
        "outputs": outputs,
        "cpu_s": (time.process_time_ns() - start_cpu) / 1e9,
        "wall_s": (time.perf_counter_ns() - start_wall) / 1e9,
        "full_executions": len(jobs),
        "reuse_hits": 0,
    }


def run_eden(jobs: List[bytes], iterations: int):
    cache: Dict[str, str] = {}
    outputs: List[str] = []
    full = 0
    hits = 0
    verification_failures = 0

    start_cpu = time.process_time_ns()
    start_wall = time.perf_counter_ns()

    for job in jobs:
        commitment = sha256_bytes(job)
        if commitment in cache:
            candidate = cache[commitment]
            # Verification is deliberately retained as EDEN overhead. Re-derive the
            # input commitment and ensure the cached result is structurally valid.
            if sha256_bytes(job) != commitment or len(candidate) != 64:
                verification_failures += 1
                candidate = workload(job, iterations)
                cache[commitment] = candidate
                full += 1
            else:
                hits += 1
            outputs.append(candidate)
        else:
            result = workload(job, iterations)
            cache[commitment] = result
            outputs.append(result)
            full += 1

    return {
        "outputs": outputs,
        "cpu_s": (time.process_time_ns() - start_cpu) / 1e9,
        "wall_s": (time.perf_counter_ns() - start_wall) / 1e9,
        "full_executions": full,
        "reuse_hits": hits,
        "verification_failures": verification_failures,
        "cache_entries": len(cache),
    }


def one_trial(requests: int, reuse_fraction: float, iterations: int):
    jobs, unique = make_jobs(requests, reuse_fraction)
    control = run_control(jobs, iterations)
    eden = run_eden(jobs, iterations)

    equality = control["outputs"] == eden["outputs"]
    cpu_reduction = 1.0 - (eden["cpu_s"] / control["cpu_s"]) if control["cpu_s"] else None
    wall_reduction = 1.0 - (eden["wall_s"] / control["wall_s"]) if control["wall_s"] else None

    return {
        "requests": requests,
        "unique_tasks": unique,
        "reuse_fraction_target": reuse_fraction,
        "reuse_fraction_realized": eden["reuse_hits"] / requests,
        "iterations_per_full_execution": iterations,
        "control": {k: v for k, v in control.items() if k != "outputs"},
        "eden": {k: v for k, v in eden.items() if k != "outputs"},
        "output_equality": equality,
        "cpu_reduction_fraction": cpu_reduction,
        "wall_reduction_fraction": wall_reduction,
        "avoided_full_executions": control["full_executions"] - eden["full_executions"],
        "output_commitment": sha256_bytes(canonical(control["outputs"])),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--requests", type=int, default=100)
    ap.add_argument("--iterations", type=int, default=20000)
    ap.add_argument("--reuse", type=float, nargs="*", default=[0.0, 0.10, 0.25, 0.50, 0.75, 0.90, 0.99])
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--output", default="experiments/eden-cpu-avoidance-001/results/EDEN-CPU-AVOIDANCE-001.json")
    args = ap.parse_args()

    if args.requests < 2 or args.iterations < 1 or args.repeats < 1:
        raise SystemExit("requests >=2, iterations >=1 and repeats >=1 required")

    rows = []
    for reuse in args.reuse:
        trials = [one_trial(args.requests, reuse, args.iterations) for _ in range(args.repeats)]
        if not all(t["output_equality"] for t in trials):
            raise SystemExit(f"FAIL: output mismatch at reuse={reuse}")
        if any(t["eden"]["verification_failures"] for t in trials):
            raise SystemExit(f"FAIL: verification failure at reuse={reuse}")

        cpu_vals = [t["cpu_reduction_fraction"] for t in trials]
        wall_vals = [t["wall_reduction_fraction"] for t in trials]
        exemplar = trials[-1]
        rows.append({
            "reuse_fraction_target": reuse,
            "reuse_fraction_realized": exemplar["reuse_fraction_realized"],
            "unique_tasks": exemplar["unique_tasks"],
            "avoided_full_executions": exemplar["avoided_full_executions"],
            "control_full_executions": exemplar["control"]["full_executions"],
            "eden_full_executions": exemplar["eden"]["full_executions"],
            "median_cpu_reduction_fraction": statistics.median(cpu_vals),
            "median_wall_reduction_fraction": statistics.median(wall_vals),
            "cpu_reduction_trials": cpu_vals,
            "wall_reduction_trials": wall_vals,
            "output_equality_all_trials": True,
            "output_commitment": exemplar["output_commitment"],
        })

    break_even = next((r["reuse_fraction_realized"] for r in rows if r["median_cpu_reduction_fraction"] > 0), None)
    evidence_class = "MEASURED_CI_PROCESS_CPU" if os.getenv("GITHUB_ACTIONS") == "true" else "MEASURED_HOST_PROCESS_CPU"

    report = {
        "schema": SCHEMA,
        "run_id": RUN_ID,
        "timestamp_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "evidence_class": evidence_class,
        "environment": {
            "platform": platform.platform(),
            "python": platform.python_version(),
            "github_actions": os.getenv("GITHUB_ACTIONS") == "true",
        },
        "configuration": {
            "requests_per_trial": args.requests,
            "iterations_per_full_execution": args.iterations,
            "repeats": args.repeats,
            "reuse_sweep": args.reuse,
        },
        "results": rows,
        "observed_break_even_reuse_fraction_in_this_sweep": break_even,
        "truth_boundary": {
            "claims": [
                "host-local process CPU time measured with time.process_time_ns",
                "CONTROL recomputes every logical job",
                "EDEN performs full computation only on exact committed misses and verifies reuse hits",
                "CONTROL and EDEN outputs are byte-for-byte equivalent after canonicalization",
            ],
            "not_claimed": [
                "Azure internal CPU or GPU utilization",
                "Azure energy reduction",
                "Azure billing reduction",
                "datacentre-scale savings",
                "independent validation",
            ],
        },
    }
    report["report_commitment"] = sha256_bytes(canonical(report))

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")

    print(json.dumps(report, indent=2, sort_keys=True))
    print(f"SAVED: {out}")


if __name__ == "__main__":
    main()
