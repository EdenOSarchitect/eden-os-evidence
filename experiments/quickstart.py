#!/usr/bin/env python3
"""Small local comparison; no provider credentials or external packages."""
import argparse
import hashlib
import json
import statistics
import time


def compute(payload, iterations):
    state = hashlib.sha256(payload).digest()
    for index in range(iterations):
        state = hashlib.sha256(state + index.to_bytes(4, "big")).digest()
    return state


def run(arm, jobs, iterations):
    cache = {}
    output = []
    calls = 0
    latencies = []
    start_cpu = time.process_time()
    start_wall = time.perf_counter()
    for job in jobs:
        begin = time.perf_counter()
        key = hashlib.sha256(job).digest()
        if arm != "CONTROL" and key in cache:
            result, bound_digest = cache[key]
            if arm == "EDEN" and hashlib.sha256(key + result).digest() != bound_digest:
                raise RuntimeError("cached output commitment failed")
        else:
            result = compute(job, iterations)
            calls += 1
            if arm != "CONTROL":
                cache[key] = (result, hashlib.sha256(key + result).digest())
        output.append(result)
        latencies.append((time.perf_counter() - begin) * 1000)
    wall = time.perf_counter() - start_wall
    return {"arm": arm, "cpu_s": round(time.process_time() - start_cpu, 5),
            "wall_s": round(wall, 5), "throughput_req_s": round(len(jobs) / wall, 2),
            "p50_latency_ms": round(statistics.median(latencies), 4),
            "full_executions": calls, "avoided_executions": len(jobs) - calls,
            "output_sha256": hashlib.sha256(b"".join(output)).hexdigest()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--requests", type=int, default=60)
    parser.add_argument("--unique", type=int, default=30)
    parser.add_argument("--iterations", type=int, default=5000)
    args = parser.parse_args()
    if not (2 <= args.requests and 1 <= args.unique <= args.requests and 1 <= args.iterations <= 1000000):
        parser.error("require requests >= 2, 1 <= unique <= requests, 1 <= iterations <= 1000000")
    jobs = [f"eden-quickstart-{i % args.unique}".encode() for i in range(args.requests)]
    rows = [run(arm, jobs, args.iterations) for arm in ("CONTROL", "CACHE", "EDEN")]
    equivalent = len({row["output_sha256"] for row in rows}) == 1
    report = {"evidence": "MEASURED_HOST_PROCESS_CPU_LOCAL_SYNTHETIC_WORKLOAD",
              "configuration": vars(args), "observed_exact_reuse_fraction": (args.requests - args.unique) / args.requests,
              "output_equivalence": equivalent, "arms": rows,
              "boundary": "EDEN here verifies an input/output commitment on exact hits. This demo does not exercise the full EDEN OS stack, establish an advantage over conventional caching, or measure provider billing, GPU use, or energy."}
    print(json.dumps(report, indent=2))
    if not equivalent:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
