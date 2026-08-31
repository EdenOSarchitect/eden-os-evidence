#!/usr/bin/env python3

import argparse
import hashlib
import json
import os
import platform
import random
import resource
import statistics
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

EXP = "EDEN-AZURE-CAPACITY-002"
ROOT = Path("experiments/eden-azure-capacity-002")
RESULTS = ROOT / "results"
WORKLOAD = "deterministic-xorshift-v1"


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


def percentile(values, p):
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    pos = (len(ordered) - 1) * p
    lo = int(pos)
    hi = min(lo + 1, len(ordered) - 1)
    frac = pos - lo
    return ordered[lo] * (1 - frac) + ordered[hi] * frac


def evidence_record(seed, iterations, value, reused, arm):
    descriptor = {"workload": WORKLOAD, "seed": seed, "iterations": iterations}
    resource_claim = {
        "arm": arm,
        "reused": bool(reused),
        "full_execution": not bool(reused),
        "output_value": value,
    }
    input_commitment = commitment(descriptor)
    output_commitment = commitment({"value": value})
    resource_commitment = commitment(resource_claim)
    marble_identity = commitment({
        "schema": "eden.capacity002.marble.v1",
        "input_commitment": input_commitment,
        "output_commitment": output_commitment,
        "resource_commitment": resource_commitment,
    })
    return {
        "input_commitment": input_commitment,
        "output_commitment": output_commitment,
        "resource_commitment": resource_commitment,
        "marble_identity": marble_identity,
    }


def run_arm(arm, seeds, iterations, progress_every):
    cache = {}
    outputs = []
    latencies = []
    full_executions = 0
    reuse_hits = 0
    evidence_chain = hashlib.sha256()
    started_utc = utcnow()
    cpu_start = time.process_time_ns()
    wall_start = time.perf_counter_ns()

    for idx, seed in enumerate(seeds, 1):
        req_start = time.perf_counter_ns()
        reused = False

        if arm == "CONTROL":
            value = workload(seed, iterations)
            full_executions += 1

        elif arm == "CACHE":
            key = (seed, iterations)
            if key in cache:
                value = cache[key]
                reused = True
                reuse_hits += 1
            else:
                value = workload(seed, iterations)
                cache[key] = value
                full_executions += 1

        elif arm == "EDEN":
            descriptor = {"workload": WORKLOAD, "seed": seed, "iterations": iterations}
            key = commitment(descriptor)
            if key in cache:
                record = cache[key]
                check = commitment({"key": key, "value": record["value"]})
                if check != record["commitment"]:
                    raise RuntimeError("EDEN CACHE VERIFICATION FAILURE")
                value = record["value"]
                reused = True
                reuse_hits += 1
            else:
                value = workload(seed, iterations)
                cache[key] = {
                    "value": value,
                    "commitment": commitment({"key": key, "value": value}),
                }
                full_executions += 1
            ev = evidence_record(seed, iterations, value, reused, arm)
            evidence_chain.update(canonical(ev))

        elif arm == "EDEN_NOREUSE":
            value = workload(seed, iterations)
            full_executions += 1
            ev = evidence_record(seed, iterations, value, False, arm)
            evidence_chain.update(canonical(ev))

        else:
            raise ValueError(f"unknown arm: {arm}")

        outputs.append(value)
        latencies.append((time.perf_counter_ns() - req_start) / 1_000_000)
        if progress_every and (idx % progress_every == 0 or idx == len(seeds)):
            print(f"{arm}: {idx:,}/{len(seeds):,} ({idx/len(seeds)*100:.1f}%)", flush=True)

    cpu_seconds = (time.process_time_ns() - cpu_start) / 1_000_000_000
    wall_seconds = (time.perf_counter_ns() - wall_start) / 1_000_000_000
    completed_utc = utcnow()
    evidence_digest = "sha256:" + evidence_chain.hexdigest() if arm.startswith("EDEN") else None

    return {
        "arm": arm,
        "started_utc": started_utc,
        "completed_utc": completed_utc,
        "cpu_seconds": cpu_seconds,
        "wall_seconds": wall_seconds,
        "full_executions": full_executions,
        "reuse_hits": reuse_hits,
        "observed_reuse_fraction": reuse_hits / len(seeds),
        "outputs_per_second": len(seeds) / wall_seconds,
        "outputs_per_vm_hour": (len(seeds) / wall_seconds) * 3600.0,
        "outputs_per_cpu_second": len(seeds) / cpu_seconds,
        "latency_ms_mean": statistics.fmean(latencies),
        "latency_ms_p50": percentile(latencies, 0.50),
        "latency_ms_p95": percentile(latencies, 0.95),
        "process_max_rss_kb_end": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        "output_commitment": commitment(outputs),
        "evidence_chain_commitment": evidence_digest,
    }


def pct_reduction(before, after):
    return (1.0 - after / before) * 100.0 if before else 0.0


def pct_gain(before, after):
    return ((after / before) - 1.0) * 100.0 if before else 0.0


def main():
    parser = argparse.ArgumentParser(description="CONTROL vs conventional cache vs EDEN vs EDEN no-reuse on one host")
    parser.add_argument("--outputs", type=int, default=5000)
    parser.add_argument("--iterations", type=int, default=30000)
    parser.add_argument("--reuse", type=float, nargs="+", default=[0.0, 0.25, 0.50, 0.75])
    parser.add_argument("--environment", default="AZURE_VM")
    parser.add_argument("--seed", type=int, default=1729)
    parser.add_argument("--progress-every", type=int, default=1000)
    parser.add_argument("--output-dir", default=str(RESULTS))
    args = parser.parse_args()

    if args.outputs < 1 or args.iterations < 1:
        raise SystemExit("outputs and iterations must be >= 1")
    for r in args.reuse:
        if not 0 <= r < 1:
            raise SystemExit("reuse values must be >= 0 and < 1")

    outdir = Path(args.output_dir)
    outdir.mkdir(parents=True, exist_ok=True)
    run_id = str(uuid.uuid4())
    started_utc = utcnow()
    all_results = []
    arms = ["CONTROL", "CACHE", "EDEN", "EDEN_NOREUSE"]

    print("=" * 78)
    print(" EDEN AZURE CAPACITY — CONVENTIONAL CACHE COMPARISON")
    print(f" {EXP}")
    print("=" * 78)
    print(f"Environment:       {args.environment}")
    print(f"Run ID:            {run_id}")
    print(f"Outputs/arm/sweep: {args.outputs:,}")
    print(f"Iterations/output: {args.iterations:,}")
    print(f"Reuse sweep:       {', '.join(f'{x*100:.0f}%' for x in args.reuse)}")

    for sweep_index, reuse in enumerate(args.reuse):
        seeds = build_requests(args.outputs, reuse)
        request_commitment = commitment({
            "outputs": args.outputs,
            "requests": seeds,
            "iterations": args.iterations,
            "reuse_target": reuse,
            "workload": WORKLOAD,
        })
        order = arms[:]
        random.Random(args.seed + sweep_index).shuffle(order)
        print(f"\n--- reuse target {reuse*100:.2f}% | order {' -> '.join(order)} ---")

        measured = {}
        for arm in order:
            measured[arm] = run_arm(arm, seeds, args.iterations, args.progress_every)

        reference = measured["CONTROL"]["output_commitment"]
        equivalent = all(measured[a]["output_commitment"] == reference for a in arms)
        control = measured["CONTROL"]
        cache = measured["CACHE"]
        eden = measured["EDEN"]
        eden_nr = measured["EDEN_NOREUSE"]

        comparison = {
            "all_outputs_equivalent": equivalent,
            "control_to_cache_cpu_reduction_pct": pct_reduction(control["cpu_seconds"], cache["cpu_seconds"]),
            "control_to_eden_cpu_reduction_pct": pct_reduction(control["cpu_seconds"], eden["cpu_seconds"]),
            "control_to_eden_wall_reduction_pct": pct_reduction(control["wall_seconds"], eden["wall_seconds"]),
            "control_to_eden_capacity_gain_pct": pct_gain(control["outputs_per_vm_hour"], eden["outputs_per_vm_hour"]),
            "eden_overhead_vs_control_noreuse_cpu_s": eden_nr["cpu_seconds"] - control["cpu_seconds"],
            "eden_overhead_vs_control_noreuse_wall_s": eden_nr["wall_seconds"] - control["wall_seconds"],
            "assurance_premium_vs_cache_cpu_s": eden["cpu_seconds"] - cache["cpu_seconds"],
            "assurance_premium_vs_cache_wall_s": eden["wall_seconds"] - cache["wall_seconds"],
            "eden_vs_cache_cpu_delta_pct": ((eden["cpu_seconds"] / cache["cpu_seconds"]) - 1.0) * 100.0 if cache["cpu_seconds"] else 0.0,
            "eden_vs_cache_wall_delta_pct": ((eden["wall_seconds"] / cache["wall_seconds"]) - 1.0) * 100.0 if cache["wall_seconds"] else 0.0,
            "cache_executions_avoided": control["full_executions"] - cache["full_executions"],
            "eden_executions_avoided": control["full_executions"] - eden["full_executions"],
        }
        all_results.append({
            "reuse_target_fraction": reuse,
            "request_commitment": request_commitment,
            "arm_order": order,
            "arms": measured,
            "comparison": comparison,
        })

        print(f"OUTPUT EQUIVALENCE: {'PASS' if equivalent else 'FAIL'}")
        print(f"CONTROL CPU: {control['cpu_seconds']:.6f}s | CACHE: {cache['cpu_seconds']:.6f}s | EDEN: {eden['cpu_seconds']:.6f}s | EDEN_NOREUSE: {eden_nr['cpu_seconds']:.6f}s")
        print(f"EDEN CPU reduction vs CONTROL: {comparison['control_to_eden_cpu_reduction_pct']:.2f}%")
        print(f"EDEN vs CACHE CPU delta:       {comparison['eden_vs_cache_cpu_delta_pct']:+.2f}%")
        print(f"EDEN capacity gain:            {comparison['control_to_eden_capacity_gain_pct']:.2f}%")

    report = {
        "experiment": EXP,
        "schema": "eden.azure.capacity_002.v1",
        "evidence_class": "MEASURED_HOST_PROCESS_CPU_WALL_AND_WORKLOAD_CAPACITY",
        "environment": args.environment,
        "run_id": run_id,
        "started_utc": started_utc,
        "completed_utc": utcnow(),
        "system": {
            "platform": platform.platform(),
            "machine": platform.machine(),
            "python": platform.python_version(),
            "cpu_count": os.cpu_count(),
        },
        "configuration": {
            "outputs_per_arm_per_sweep": args.outputs,
            "iterations_per_output": args.iterations,
            "reuse_sweep": args.reuse,
            "order_seed": args.seed,
            "workload": WORKLOAD,
        },
        "results": all_results,
        "truth_boundary": {
            "measured": [
                "host-process CPU time",
                "host wall time",
                "per-request local latency",
                "workload throughput/capacity",
                "exact reuse hits and full executions",
                "output commitment equivalence",
                "EDEN evidence-chain commitments",
            ],
            "limitations": [
                "CACHE is a minimal in-process exact cache comparator, not Redis/Memcached or a network cache service",
                "process_max_rss_kb_end is process-wide ru_maxrss and is not an isolated per-arm memory delta",
                "sequential arms can experience host noise despite deterministic randomized arm order",
            ],
            "not_claimed": [
                "Azure datacentre energy savings",
                "Azure invoice reduction",
                "general cloud efficiency superiority",
                "EDEN superiority to all production cache systems",
                "independent validation",
            ],
        },
    }
    report["report_commitment"] = commitment(report)
    outfile = outdir / f"{EXP}-{run_id[:8]}.json"
    outfile.write_text(json.dumps(report, indent=2, sort_keys=True))

    print("\n" + "=" * 78)
    print(" COMPLETE")
    print("=" * 78)
    print(f"REPORT COMMITMENT: {report['report_commitment']}")
    print(f"SAVED: {outfile}")
    if not all(x["comparison"]["all_outputs_equivalent"] for x in all_results):
        raise SystemExit(2)


if __name__ == "__main__":
    main()
