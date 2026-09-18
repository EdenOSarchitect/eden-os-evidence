#!/usr/bin/env python3
import argparse
import hashlib
import json
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
        commitment = sha256_obj({"kind": "section", "payload": s, "policy": "structured-reuse-v1", "rounds": rounds})
        reused = commitment in store
        if not reused:
            value = heavy_section(s, rounds)
            store[commitment] = {"output": value, "output_commitment": sha256_obj(value)}
        record = store[commitment]
        if sha256_obj(record["output"]) != record["output_commitment"]:
            raise ValueError("EDEN stored section output commitment mismatch")
        parts.append(record["output"])
        used.append({"commitment": commitment, "output_commitment": record["output_commitment"], "reused": reused})
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


def run_trial(trace, rounds, seed):
    rng = random.Random(seed ^ 0xED3A)

    whole_cache = {}
    component_cache = {}
    eden_store = {}
    eden_evidence = []

    arms = ["CONTROL", "WHOLE_CACHE", "COMPONENT_CACHE", "EDEN"]
    cpu = {a: 0 for a in arms}
    wall = {a: 0 for a in arms}
    lat_cpu = {a: [] for a in arms}
    lat_wall = {a: [] for a in arms}
    outputs = {a: [] for a in arms}

    for index, req in enumerate(trace):
        # Each consecutive block puts every arm in every timing position once.
        if index % len(arms) == 0:
            base_order = arms[:]
            rng.shuffle(base_order)
        offset = index % len(arms)
        order = base_order[offset:] + base_order[:offset]
        for arm in order:
            c0, w0 = cpu_now(), wall_now()
            if arm == "CONTROL":
                out = run_control(req, rounds)
            elif arm == "WHOLE_CACHE":
                out = run_whole_cache(req, rounds, whole_cache)
            elif arm == "COMPONENT_CACHE":
                out = run_component_cache(req, rounds, component_cache)
            else:
                out = run_eden(req, rounds, eden_store, eden_evidence)
            c1, w1 = cpu_now(), wall_now()
            dc, dw = c1 - c0, w1 - w0
            cpu[arm] += dc
            wall[arm] += dw
            lat_cpu[arm].append(dc / 1e6)
            lat_wall[arm].append(dw / 1e6)
            outputs[arm].append(out)

    equivalent = outputs["CONTROL"] == outputs["WHOLE_CACHE"] == outputs["COMPONENT_CACHE"] == outputs["EDEN"]
    if not equivalent:
        raise ValueError("Output equivalence failed")
    paired_cpu = {arm: statistics.mean(e - c for e, c in zip(lat_cpu["EDEN"], lat_cpu[arm])) for arm in arms if arm != "EDEN"}
    paired_wall = {arm: statistics.mean(e - c for e, c in zip(lat_wall["EDEN"], lat_wall[arm])) for arm in arms if arm != "EDEN"}

    cpu_s = {k: v / 1e9 for k, v in cpu.items()}
    wall_s = {k: v / 1e9 for k, v in wall.items()}
    ctl = cpu_s["CONTROL"]
    whole = cpu_s["WHOLE_CACHE"]
    comp = cpu_s["COMPONENT_CACHE"]
    eden = cpu_s["EDEN"]

    return {
        "cpu_seconds": cpu_s,
        "wall_seconds": wall_s,
        "paired_cpu_ms_per_request": paired_cpu,
        "paired_wall_ms_per_request": paired_wall,
        "eden_cpu_delta_vs_component_cache_pct": (eden / comp - 1) * 100 if comp else None,
        "eden_wall_delta_vs_component_cache_pct": (wall_s["EDEN"] / wall_s["COMPONENT_CACHE"] - 1) * 100 if wall_s["COMPONENT_CACHE"] else None,
        "output_equivalence": equivalent,
        "output_commitment": sha256_obj(outputs["EDEN"]),
        "eden_evidence_events": len(eden_evidence),
        "verified_section_hits": sum(sum(c["reused"] for c in event["components"]) for event in eden_evidence),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--requests", type=int, default=1200)
    ap.add_argument("--rounds", type=int, default=120)
    ap.add_argument("--seed", type=int, default=20260901)
    ap.add_argument("--trials", type=int, default=3)
    ap.add_argument("--environment", default="LOCAL_UNVERIFIED")
    args = ap.parse_args()
    if args.requests < 1 or args.rounds < 1 or args.trials < 1:
        ap.error("requests, rounds, and trials must be positive")
    trace, reuse = build_trace(args.requests, args.seed)
    trials = [run_trial(trace, args.rounds, args.seed + i) for i in range(args.trials)]
    if len({trial["output_commitment"] for trial in trials}) != 1:
        raise ValueError("Output changed between trials")
    cpu_deltas = [t["eden_cpu_delta_vs_component_cache_pct"] for t in trials]
    wall_deltas = [t["eden_wall_delta_vs_component_cache_pct"] for t in trials]
    result = {
        "run_id": str(uuid.uuid4()),
        "experiment": RUN,
        "environment_label": args.environment,
        "configuration": vars(args),
        "trace_commitment": sha256_obj(trace),
        "reuse": reuse,
        "primary_comparator": "COMPONENT_CACHE",
        "trials": trials,
        "summary": {
            "eden_cpu_delta_vs_component_cache_pct_mean": statistics.mean(cpu_deltas),
            "eden_cpu_delta_vs_component_cache_pct_stdev": statistics.stdev(cpu_deltas) if len(cpu_deltas) > 1 else None,
            "eden_wall_delta_vs_component_cache_pct_mean": statistics.mean(wall_deltas),
            "eden_wall_delta_vs_component_cache_pct_stdev": statistics.stdev(wall_deltas) if len(wall_deltas) > 1 else None,
            "verified_section_hits_per_trial": [t["verified_section_hits"] for t in trials],
        },
        "truth_boundary": {
            "evidence_class": "MEASURED_HOST_PROCESS_CPU_AND_WALL",
            "claims": "Host/process workload behavior on the executing VM only.",
            "environment_label_is_self_reported": True,
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
    print(f"OUTPUT EQUIVALENCE:  {'PASS' if all(t['output_equivalence'] for t in trials) else 'FAIL'}")
    print(f"TRIALS:              {len(trials)}")
    for i, trial in enumerate(trials, 1):
        print(f"Trial {i}: CONTROL {trial['cpu_seconds']['CONTROL']:.6f}s; WHOLE_CACHE {trial['cpu_seconds']['WHOLE_CACHE']:.6f}s; COMPONENT_CACHE {trial['cpu_seconds']['COMPONENT_CACHE']:.6f}s; EDEN {trial['cpu_seconds']['EDEN']:.6f}s CPU; verified hits {trial['verified_section_hits']}")
        print(f"  EDEN vs COMPONENT_CACHE: CPU {trial['eden_cpu_delta_vs_component_cache_pct']:+.2f}%; wall {trial['eden_wall_delta_vs_component_cache_pct']:+.2f}%")
    print(f"EDEN vs COMPONENT_CACHE mean CPU delta:  {statistics.mean(cpu_deltas):+.2f}%")
    print(f"EDEN vs COMPONENT_CACHE mean wall delta: {statistics.mean(wall_deltas):+.2f}%")
    print(f"TRACE COMMITMENT:  {result['trace_commitment']}")
    print(f"REPORT COMMITMENT: {result['report_commitment']}")
    print(f"SAVED: {path}")

if __name__ == "__main__":
    main()
