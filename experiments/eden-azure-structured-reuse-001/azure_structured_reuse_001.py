#!/usr/bin/env python3
import argparse
import hashlib
import json
import os
import random
import statistics
import time
import uuid
from pathlib import Path

RUN = "EDEN-AZURE-STRUCTURED-REUSE-001"


def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def sha256_obj(obj):
    return "sha256:" + hashlib.sha256(canonical(obj)).hexdigest()


def heavy_section(section, rounds):
    # Deterministic CPU-heavy transform over one reusable section.
    blob = canonical(section)
    h = hashlib.sha256(blob).digest()
    acc = 0
    for i in range(rounds):
        h = hashlib.sha256(h + blob + i.to_bytes(4, "little")).digest()
        acc ^= int.from_bytes(h[:8], "little")
    return {"section_id": section["section_id"], "score": acc, "digest": h.hex()}


def compose_output(request, section_outputs):
    body = {
        "request_id": request["request_id"],
        "customer": request["customer"],
        "sections": section_outputs,
        "summary": sum(x["score"] for x in section_outputs) & ((1 << 64) - 1),
    }
    return sha256_obj(body)


def build_trace(n, seed):
    rng = random.Random(seed)
    # Whole requests are unique, but sections are deliberately drawn from a reusable pool.
    pool = []
    for i in range(max(24, n // 20)):
        pool.append({
            "section_id": f"S{i:05d}",
            "values": [rng.randrange(0, 1_000_000) for _ in range(12)],
            "kind": rng.choice(["telemetry", "orders", "events", "metrics"]),
        })

    trace = []
    seen_sections = set()
    reuse_hits = 0
    total_sections = 0
    whole_keys = set()
    whole_hits = 0

    for i in range(n):
        k = rng.randint(3, 6)
        sections = [rng.choice(pool) for _ in range(k)]
        req = {
            "request_id": f"R{i:06d}",  # makes whole request unique
            "customer": f"C{rng.randrange(8):02d}",
            "sections": sections,
        }
        wk = sha256_obj(req)
        if wk in whole_keys:
            whole_hits += 1
        whole_keys.add(wk)
        for s in sections:
            sk = sha256_obj(s)
            if sk in seen_sections:
                reuse_hits += 1
            seen_sections.add(sk)
            total_sections += 1
        trace.append(req)

    return trace, {
        "whole_request_reuse_fraction": whole_hits / n if n else 0.0,
        "section_reuse_fraction": reuse_hits / total_sections if total_sections else 0.0,
        "total_sections": total_sections,
        "unique_sections": len(seen_sections),
    }


def run_control(req, rounds):
    parts = [heavy_section(s, rounds) for s in req["sections"]]
    return compose_output(req, parts)


def run_whole_cache(req, rounds, cache):
    # Strong conventional whole-request cache. Unique request_id means it should usually miss.
    key = sha256_obj(req)
    if key in cache:
        return cache[key]
    out = run_control(req, rounds)
    cache[key] = out
    return out


def run_component_cache(req, rounds, cache):
    parts = []
    for s in req["sections"]:
        key = sha256_obj(s)
        if key not in cache:
            cache[key] = heavy_section(s, rounds)
        parts.append(cache[key])
    return compose_output(req, parts)


def run_eden(req, rounds, store, evidence):
    parts = []
    used = []
    for s in req["sections"]:
        commitment = sha256_obj({"kind": "section", "payload": s, "policy": "structured-reuse-v1"})
        reused = commitment in store
        if not reused:
            store[commitment] = heavy_section(s, rounds)
        parts.append(store[commitment])
        used.append({"commitment": commitment, "reused": reused})
    out = compose_output(req, parts)
    evidence.append({
        "request_commitment": sha256_obj(req),
        "output_commitment": out,
        "components": used,
    })
    return out


def cpu_now():
    return time.process_time_ns()


def wall_now():
    return time.perf_counter_ns()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--requests", type=int, default=1200)
    ap.add_argument("--rounds", type=int, default=120)
    ap.add_argument("--seed", type=int, default=20260901)
    ap.add_argument("--environment", default="AZURE_VM")
    args = ap.parse_args()

    trace, reuse = build_trace(args.requests, args.seed)
    rng = random.Random(args.seed ^ 0xED3A)

    whole_cache = {}
    component_cache = {}
    eden_store = {}
    eden_evidence = []

    arms = ["CONTROL", "WHOLE_CACHE", "COMPONENT_CACHE", "EDEN"]
    cpu = {a: 0 for a in arms}
    wall = {a: 0 for a in arms}
    lat_cpu = {a: [] for a in arms}
    outputs = {a: [] for a in arms}

    for req in trace:
        order = arms[:]
        rng.shuffle(order)
        per = {}
        for arm in order:
            c0, w0 = cpu_now(), wall_now()
            if arm == "CONTROL":
                out = run_control(req, args.rounds)
            elif arm == "WHOLE_CACHE":
                out = run_whole_cache(req, args.rounds, whole_cache)
            elif arm == "COMPONENT_CACHE":
                out = run_component_cache(req, args.rounds, component_cache)
            else:
                out = run_eden(req, args.rounds, eden_store, eden_evidence)
            c1, w1 = cpu_now(), wall_now()
            dc, dw = c1 - c0, w1 - w0
            cpu[arm] += dc
            wall[arm] += dw
            lat_cpu[arm].append(dc / 1e6)
            outputs[arm].append(out)
            per[arm] = dc / 1e6

    equivalent = outputs["CONTROL"] == outputs["WHOLE_CACHE"] == outputs["COMPONENT_CACHE"] == outputs["EDEN"]
    paired_ec = [e - c for e, c in zip(lat_cpu["EDEN"], lat_cpu["CONTROL"])]
    paired_ew = [e - w for e, w in zip(lat_cpu["EDEN"], lat_cpu["WHOLE_CACHE"])]
    paired_es = [e - s for e, s in zip(lat_cpu["EDEN"], lat_cpu["COMPONENT_CACHE"])]

    cpu_s = {k: v / 1e9 for k, v in cpu.items()}
    wall_s = {k: v / 1e9 for k, v in wall.items()}
    ctl = cpu_s["CONTROL"]
    whole = cpu_s["WHOLE_CACHE"]
    comp = cpu_s["COMPONENT_CACHE"]
    eden = cpu_s["EDEN"]

    result = {
        "run_id": str(uuid.uuid4()),
        "experiment": RUN,
        "environment_label": args.environment,
        "configuration": vars(args),
        "trace_commitment": sha256_obj(trace),
        "reuse": reuse,
        "output_equivalence": equivalent,
        "output_commitment": sha256_obj(outputs["EDEN"]),
        "cpu_seconds": cpu_s,
        "wall_seconds": wall_s,
        "eden_cpu_reduction_vs_control_pct": (1 - eden / ctl) * 100 if ctl else None,
        "eden_cpu_reduction_vs_whole_cache_pct": (1 - eden / whole) * 100 if whole else None,
        "eden_cpu_delta_vs_component_cache_pct": (eden / comp - 1) * 100 if comp else None,
        "paired_cpu_ms_per_request": {
            "EDEN-CONTROL_mean": statistics.mean(paired_ec),
            "EDEN-WHOLE_CACHE_mean": statistics.mean(paired_ew),
            "EDEN-COMPONENT_CACHE_mean": statistics.mean(paired_es),
        },
        "eden_evidence_events": len(eden_evidence),
        "truth_boundary": {
            "evidence_class": "MEASURED_HOST_PROCESS_CPU",
            "claims": "Host/process workload behavior on the executing VM only.",
            "not_claimed": [
                "Azure datacentre energy reduction",
                "Azure billing reduction",
                "general production speedup",
                "EDEN is non-caching technology"
            ],
            "interpretation": "This benchmark tests reuse below whole-request granularity. COMPONENT_CACHE is the strongest conventional comparator; EDEN should normally be slightly more expensive than it because EDEN adds commitments/evidence."
        },
    }
    result["report_commitment"] = sha256_obj(result)

    outdir = Path(__file__).parent / "results"
    outdir.mkdir(parents=True, exist_ok=True)
    short = result["run_id"][:8]
    path = outdir / f"{RUN}-{short}.json"
    path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")

    print("=" * 78)
    print(" RESULTS")
    print("=" * 78)
    print(f"WHOLE-REQUEST REUSE: {reuse['whole_request_reuse_fraction']*100:.2f}%")
    print(f"SECTION REUSE:       {reuse['section_reuse_fraction']*100:.2f}%")
    print(f"OUTPUT EQUIVALENCE:  {'PASS' if equivalent else 'FAIL'}")
    print(f"CONTROL CPU:         {ctl:.6f}s")
    print(f"WHOLE_CACHE CPU:     {whole:.6f}s")
    print(f"COMPONENT_CACHE CPU: {comp:.6f}s")
    print(f"EDEN CPU:            {eden:.6f}s")
    print(f"EDEN CPU reduction vs CONTROL:     {result['eden_cpu_reduction_vs_control_pct']:.2f}%")
    print(f"EDEN CPU reduction vs WHOLE_CACHE: {result['eden_cpu_reduction_vs_whole_cache_pct']:.2f}%")
    print(f"EDEN CPU delta vs COMPONENT_CACHE: {result['eden_cpu_delta_vs_component_cache_pct']:+.2f}%")
    print(f"Paired EDEN-CONTROL CPU:           {statistics.mean(paired_ec):+.4f} ms/request")
    print(f"Paired EDEN-WHOLE_CACHE CPU:       {statistics.mean(paired_ew):+.4f} ms/request")
    print(f"Paired EDEN-COMPONENT_CACHE CPU:   {statistics.mean(paired_es):+.4f} ms/request")
    print(f"TRACE COMMITMENT:  {result['trace_commitment']}")
    print(f"REPORT COMMITMENT: {result['report_commitment']}")
    print(f"SAVED: {path}")

    if not equivalent:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
