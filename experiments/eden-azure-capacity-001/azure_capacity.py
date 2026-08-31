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

EXP = "EDEN-AZURE-CAPACITY-001"
ROOT = Path("experiments/eden-azure-capacity-001")
RESULTS = ROOT / "results"
RESULTS.mkdir(parents=True, exist_ok=True)


def utcnow():
    return datetime.now(timezone.utc).isoformat()


def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


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


def progress(label, n, total, every):
    if every and (n % every == 0 or n == total):
        print(f"{label}: {n:,}/{total:,} ({n/total*100:.1f}%)", flush=True)


def run_baseline(seeds, iterations, progress_every):
    outputs = []
    started_utc = utcnow()
    cpu_start = time.process_time_ns()
    wall_start = time.perf_counter_ns()
    for idx, seed in enumerate(seeds, 1):
        outputs.append(workload(seed, iterations))
        progress("BASELINE", idx, len(seeds), progress_every)
    cpu_end = time.process_time_ns()
    wall_end = time.perf_counter_ns()
    completed_utc = utcnow()
    wall_seconds = (wall_end - wall_start) / 1_000_000_000
    cpu_seconds = (cpu_end - cpu_start) / 1_000_000_000
    return {
        "mode": "CONTROL",
        "started_utc": started_utc,
        "completed_utc": completed_utc,
        "cpu_seconds": cpu_seconds,
        "wall_seconds": wall_seconds,
        "full_executions": len(seeds),
        "verified_reuse_hits": 0,
        "max_rss_kb": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        "output_commitment": commitment(outputs),
        "outputs_per_second": len(seeds) / wall_seconds,
        "outputs_per_cpu_second": len(seeds) / cpu_seconds,
        "outputs_per_vm_hour": (len(seeds) / wall_seconds) * 3600.0,
    }


def run_eden(seeds, iterations, progress_every):
    cache = {}
    outputs = []
    full_executions = 0
    reuse_hits = 0
    started_utc = utcnow()
    cpu_start = time.process_time_ns()
    wall_start = time.perf_counter_ns()
    for idx, seed in enumerate(seeds, 1):
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
        progress("EDEN", idx, len(seeds), progress_every)
    cpu_end = time.process_time_ns()
    wall_end = time.perf_counter_ns()
    completed_utc = utcnow()
    wall_seconds = (wall_end - wall_start) / 1_000_000_000
    cpu_seconds = (cpu_end - cpu_start) / 1_000_000_000
    return {
        "mode": "EDEN",
        "started_utc": started_utc,
        "completed_utc": completed_utc,
        "cpu_seconds": cpu_seconds,
        "wall_seconds": wall_seconds,
        "full_executions": full_executions,
        "verified_reuse_hits": reuse_hits,
        "observed_reuse_fraction": reuse_hits / len(seeds),
        "max_rss_kb": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        "output_commitment": commitment(outputs),
        "outputs_per_second": len(seeds) / wall_seconds,
        "outputs_per_cpu_second": len(seeds) / cpu_seconds,
        "outputs_per_vm_hour": (len(seeds) / wall_seconds) * 3600.0,
    }


def pct_gain(before, after):
    return ((after / before) - 1.0) * 100.0 if before else 0.0


def pct_reduction(before, after):
    return (1.0 - after / before) * 100.0 if before else 0.0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--outputs", type=int, default=20000)
    parser.add_argument("--iterations", type=int, default=30000)
    parser.add_argument("--reuse", type=float, default=0.50)
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--environment", default="AZURE_VM")
    parser.add_argument("--progress-every", type=int, default=2000)
    args = parser.parse_args()

    if args.outputs < 1:
        raise SystemExit("outputs must be >= 1")
    if args.iterations < 1:
        raise SystemExit("iterations must be >= 1")
    if not 0 <= args.reuse < 1:
        raise SystemExit("reuse must be >= 0 and < 1")

    run_id = str(uuid.uuid4())
    started_utc = utcnow()
    seeds = build_requests(args.outputs, args.reuse)
    request_commitment = commitment({
        "outputs": args.outputs,
        "requests": seeds,
        "iterations": args.iterations,
        "reuse_target": args.reuse,
        "workload": "deterministic-xorshift-v1",
    })

    print("=" * 76)
    print(" EDEN AZURE CAPACITY FLAGSHIP")
    print(f" {EXP}")
    print("=" * 76)
    print(f"Environment:            {args.environment}")
    print(f"Run ID:                 {run_id}")
    print(f"Equivalent outputs:     {args.outputs:,}")
    print(f"Iterations/output:      {args.iterations:,}")
    print(f"Reuse target:           {args.reuse*100:.2f}%")
    print(f"Request commitment:     {request_commitment}")
    print()

    print("Running CONTROL...", flush=True)
    baseline = run_baseline(seeds, args.iterations, args.progress_every)
    print("Running EDEN...", flush=True)
    eden = run_eden(seeds, args.iterations, args.progress_every)

    equivalent = baseline["output_commitment"] == eden["output_commitment"]
    executions_avoided = baseline["full_executions"] - eden["full_executions"]
    cpu_reduction = pct_reduction(baseline["cpu_seconds"], eden["cpu_seconds"])
    wall_reduction = pct_reduction(baseline["wall_seconds"], eden["wall_seconds"])
    capacity_gain = pct_gain(baseline["outputs_per_vm_hour"], eden["outputs_per_vm_hour"])
    cpu_efficiency_gain = pct_gain(baseline["outputs_per_cpu_second"], eden["outputs_per_cpu_second"])

    report = {
        "experiment": EXP,
        "evidence_class": "MEASURED_AZURE_VM_HOST_PROCESS_CPU_AND_CAPACITY",
        "environment": args.environment,
        "run_id": run_id,
        "started_utc": started_utc,
        "completed_utc": utcnow(),
        "repeat": args.repeat,
        "system": {
            "platform": platform.platform(),
            "machine": platform.machine(),
            "python": platform.python_version(),
            "cpu_count": os.cpu_count(),
        },
        "configuration": {
            "equivalent_outputs": args.outputs,
            "iterations_per_output": args.iterations,
            "reuse_target": args.reuse,
            "workload": "deterministic-xorshift-v1",
        },
        "request_commitment": request_commitment,
        "control": baseline,
        "eden": eden,
        "comparison": {
            "outputs_equivalent": equivalent,
            "executions_avoided": executions_avoided,
            "observed_reuse_fraction": eden["observed_reuse_fraction"],
            "cpu_reduction_pct": cpu_reduction,
            "wall_reduction_pct": wall_reduction,
            "capacity_gain_pct": capacity_gain,
            "cpu_efficiency_gain_pct": cpu_efficiency_gain,
            "control_outputs_per_vm_hour": baseline["outputs_per_vm_hour"],
            "eden_outputs_per_vm_hour": eden["outputs_per_vm_hour"],
            "control_outputs_per_cpu_second": baseline["outputs_per_cpu_second"],
            "eden_outputs_per_cpu_second": eden["outputs_per_cpu_second"],
        },
        "azure_monitor": {
            "status": "EXTERNAL_COLLECTION_REQUIRED",
            "note": "Use control.started_utc/completed_utc and eden.started_utc/completed_utc to query Azure Monitor Percentage CPU, disk, and network metrics for each arm."
        }
    }
    report["report_commitment"] = commitment(report)

    filename = f"{EXP}-r{args.repeat}-{run_id[:8]}.json"
    outfile = RESULTS / filename
    outfile.write_text(json.dumps(report, indent=2, sort_keys=True))

    print()
    print("=" * 76)
    print(" RESULTS")
    print("=" * 76)
    print(f"Equivalent outputs/arm:       {args.outputs:,}")
    print(f"Observed reuse:               {eden['observed_reuse_fraction']*100:.2f}%")
    print(f"Full executions avoided:      {executions_avoided:,}")
    print()
    print(f"CONTROL CPU:                  {baseline['cpu_seconds']:.6f} s")
    print(f"EDEN CPU:                     {eden['cpu_seconds']:.6f} s")
    print(f"CPU REDUCTION:                {cpu_reduction:.2f}%")
    print()
    print(f"CONTROL wall:                 {baseline['wall_seconds']:.6f} s")
    print(f"EDEN wall:                    {eden['wall_seconds']:.6f} s")
    print(f"WALL REDUCTION:               {wall_reduction:.2f}%")
    print()
    print(f"CONTROL outputs/VM-hour:      {baseline['outputs_per_vm_hour']:,.2f}")
    print(f"EDEN outputs/VM-hour:         {eden['outputs_per_vm_hour']:,.2f}")
    print(f"CAPACITY GAIN:                {capacity_gain:.2f}%")
    print()
    print(f"CONTROL outputs/CPU-second:   {baseline['outputs_per_cpu_second']:.4f}")
    print(f"EDEN outputs/CPU-second:      {eden['outputs_per_cpu_second']:.4f}")
    print(f"CPU EFFICIENCY GAIN:          {cpu_efficiency_gain:.2f}%")
    print()
    print("OUTPUT EQUIVALENCE:           " + ("PASS" if equivalent else "FAIL"))
    print("CONTROL WINDOW:              ", baseline["started_utc"], "->", baseline["completed_utc"])
    print("EDEN WINDOW:                 ", eden["started_utc"], "->", eden["completed_utc"])
    print("REQUEST COMMITMENT:          ", request_commitment)
    print("REPORT COMMITMENT:           ", report["report_commitment"])
    print("SAVED:                       ", outfile)
    print("=" * 76)

    if not equivalent:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
