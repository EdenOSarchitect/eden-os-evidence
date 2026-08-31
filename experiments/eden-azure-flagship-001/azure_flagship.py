#!/usr/bin/env python3

import argparse
import hashlib
import json
import os
import platform
import resource
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path


EXP = "EDEN-AZURE-FLAGSHIP-001"

ROOT = Path("experiments/eden-azure-flagship-001")
RESULTS = ROOT / "results"
RESULTS.mkdir(parents=True, exist_ok=True)


def utcnow():
    return datetime.now(timezone.utc).isoformat()


def canonical(obj):
    return json.dumps(
        obj,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode()


def sha256_bytes(data):
    return "sha256:" + hashlib.sha256(data).hexdigest()


def commitment(obj):
    return sha256_bytes(canonical(obj))


def workload(seed, iterations):
    x = (seed * 2654435761) & 0xFFFFFFFF
    for i in range(iterations):
        x ^= (x << 13) & 0xFFFFFFFF
        x ^= x >> 17
        x ^= (x << 5) & 0xFFFFFFFF
        x = (x + (i * 17)) & 0xFFFFFFFF
    return x


def build_requests(total, reuse_fraction):
    reuse_count = int(round(total * reuse_fraction))
    unique_count = max(1, total - reuse_count)
    seeds = list(range(1, unique_count + 1))
    i = 0
    while len(seeds) < total:
        seeds.append(seeds[i % unique_count])
        i += 1
    return seeds[:total]


def run_baseline(seeds, iterations):
    outputs = []
    cpu_start = time.process_time_ns()
    wall_start = time.perf_counter_ns()
    for seed in seeds:
        outputs.append(workload(seed, iterations))
    cpu_end = time.process_time_ns()
    wall_end = time.perf_counter_ns()
    return {
        "mode": "BASELINE",
        "cpu_seconds": (cpu_end - cpu_start) / 1_000_000_000,
        "wall_seconds": (wall_end - wall_start) / 1_000_000_000,
        "full_executions": len(seeds),
        "reuse_hits": 0,
        "max_rss_kb": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        "output_commitment": commitment(outputs),
    }


def run_eden(seeds, iterations):
    cache = {}
    outputs = []
    full_executions = 0
    reuse_hits = 0
    cpu_start = time.process_time_ns()
    wall_start = time.perf_counter_ns()
    for seed in seeds:
        input_descriptor = {
            "workload": "deterministic-xorshift-v1",
            "seed": seed,
            "iterations": iterations,
        }
        key = commitment(input_descriptor)
        if key in cache:
            record = cache[key]
            check = commitment({"key": key, "value": record["value"]})
            if check != record["commitment"]:
                raise RuntimeError("CACHE VERIFICATION FAILURE")
            value = record["value"]
            reuse_hits += 1
        else:
            value = workload(seed, iterations)
            full_executions += 1
            cache[key] = {
                "value": value,
                "commitment": commitment({"key": key, "value": value}),
            }
        outputs.append(value)
    cpu_end = time.process_time_ns()
    wall_end = time.perf_counter_ns()
    return {
        "mode": "EDEN",
        "cpu_seconds": (cpu_end - cpu_start) / 1_000_000_000,
        "wall_seconds": (wall_end - wall_start) / 1_000_000_000,
        "full_executions": full_executions,
        "reuse_hits": reuse_hits,
        "observed_reuse_fraction": reuse_hits / len(seeds),
        "max_rss_kb": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        "output_commitment": commitment(outputs),
    }


def pct_reduction(before, after):
    if before == 0:
        return 0.0
    return (1.0 - (after / before)) * 100.0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--requests", type=int, default=1000)
    parser.add_argument("--iterations", type=int, default=30000)
    parser.add_argument("--reuse", type=float, required=True)
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--environment", default="TERMUX_PREFLIGHT")
    args = parser.parse_args()

    if not 0 <= args.reuse < 1:
        raise SystemExit("Reuse must be >= 0 and < 1")

    run_id = str(uuid.uuid4())
    started = utcnow()
    seeds = build_requests(args.requests, args.reuse)
    request_commitment = commitment({
        "requests": seeds,
        "iterations": args.iterations,
        "workload": "deterministic-xorshift-v1",
    })

    print("=" * 72)
    print(" EDEN FLAGSHIP CLOUD EXPERIMENT")
    print(f" {EXP}")
    print("=" * 72)
    print()
    print("Environment:       ", args.environment)
    print("Run ID:            ", run_id)
    print("Repeat:            ", args.repeat)
    print("Requests:          ", args.requests)
    print("Reuse target:      ", f"{args.reuse*100:.2f}%")
    print("Iterations:        ", args.iterations)
    print()

    print("Running BASELINE...")
    print()
    baseline = run_baseline(seeds, args.iterations)

    print("Running EDEN...")
    print()
    eden = run_eden(seeds, args.iterations)

    cpu_reduction = pct_reduction(baseline["cpu_seconds"], eden["cpu_seconds"])
    wall_reduction = pct_reduction(baseline["wall_seconds"], eden["wall_seconds"])
    equivalent = baseline["output_commitment"] == eden["output_commitment"]
    executions_avoided = baseline["full_executions"] - eden["full_executions"]
    throughput_baseline = args.requests / baseline["wall_seconds"]
    throughput_eden = args.requests / eden["wall_seconds"]
    throughput_gain = ((throughput_eden / throughput_baseline) - 1) * 100

    report = {
        "experiment": EXP,
        "evidence_class": "MEASURED_HOST_PROCESS_CPU",
        "environment": args.environment,
        "run_id": run_id,
        "started_utc": started,
        "completed_utc": utcnow(),
        "repeat": args.repeat,
        "system": {
            "platform": platform.platform(),
            "machine": platform.machine(),
            "python": platform.python_version(),
            "cpu_count": os.cpu_count(),
        },
        "configuration": {
            "requests": args.requests,
            "iterations": args.iterations,
            "reuse_target": args.reuse,
        },
        "request_commitment": request_commitment,
        "baseline": baseline,
        "eden": eden,
        "comparison": {
            "outputs_equivalent": equivalent,
            "executions_avoided": executions_avoided,
            "observed_reuse_fraction": eden["observed_reuse_fraction"],
            "cpu_reduction_pct": cpu_reduction,
            "wall_reduction_pct": wall_reduction,
            "baseline_requests_per_second": throughput_baseline,
            "eden_requests_per_second": throughput_eden,
            "throughput_gain_pct": throughput_gain,
        },
    }

    report["report_commitment"] = commitment(report)

    reuse_code = int(round(eden["observed_reuse_fraction"] * 1000))
    filename = (
        f"{EXP}-r{args.repeat}-reuse-{reuse_code:03d}-{run_id[:8]}.json"
    )
    outfile = RESULTS / filename
    outfile.write_text(json.dumps(report, indent=2, sort_keys=True))

    print("=" * 72)
    print(" RESULTS")
    print("=" * 72)
    print(f"Requests:               {args.requests:,}")
    print(f"Reuse target:           {args.reuse*100:.2f}%")
    print(f"Observed reuse:         {eden['observed_reuse_fraction']*100:.2f}%")
    print()
    print(f"Baseline CPU:           {baseline['cpu_seconds']:.6f} s")
    print(f"EDEN CPU:               {eden['cpu_seconds']:.6f} s")
    print(f"CPU REDUCTION:          {cpu_reduction:.2f}%")
    print()
    print(f"Baseline wall:          {baseline['wall_seconds']:.6f} s")
    print(f"EDEN wall:              {eden['wall_seconds']:.6f} s")
    print(f"WALL REDUCTION:         {wall_reduction:.2f}%")
    print()
    print(f"Baseline throughput:    {throughput_baseline:.2f} req/s")
    print(f"EDEN throughput:        {throughput_eden:.2f} req/s")
    print(f"THROUGHPUT GAIN:        {throughput_gain:.2f}%")
    print()
    print(f"Full executions avoided: {executions_avoided:,}")
    print()
    print("OUTPUT EQUIVALENCE:    ", "PASS" if equivalent else "FAIL")
    print()
    print("REQUEST COMMITMENT:", request_commitment)
    print("REPORT COMMITMENT: ", report["report_commitment"])
    print()
    print("SAVED:", outfile)
    print("=" * 72)

    if not equivalent:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
