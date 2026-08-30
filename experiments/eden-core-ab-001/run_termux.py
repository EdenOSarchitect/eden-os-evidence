#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
import random
import resource
import statistics
import subprocess
import threading
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

RUN_ID = "EDEN-CORE-AB-001"
CORE = os.getenv("EDEN_CORE_URL", "http://127.0.0.1:8766")
TRIALS = int(os.getenv("EDEN_AB_TRIALS", "6"))
ITERATIONS = int(os.getenv("EDEN_AB_ITERATIONS", "4000000"))
SAMPLE_S = float(os.getenv("EDEN_POWER_SAMPLE_SECONDS", "0.25"))
COOLDOWN_S = float(os.getenv("EDEN_COOLDOWN_SECONDS", "5"))
OUT = Path("experiments/eden-core-ab-001/results")
OUT.mkdir(parents=True, exist_ok=True)
CACHE = OUT / "reuse-cache.json"


def utcnow():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def canon(v):
    return json.dumps(v, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def sha(v):
    data = v if isinstance(v, (bytes, bytearray)) else canon(v)
    return "sha256:" + hashlib.sha256(data).hexdigest()


def get_json(path):
    with urllib.request.urlopen(CORE + path, timeout=5) as r:
        return json.loads(r.read().decode())


def post_json(path, payload):
    req = urllib.request.Request(
        CORE + path,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode())


def battery_sample():
    """Read the same Termux battery telemetry path used by EDEN_PHYSICAL_ENERGY_015."""
    try:
        raw = subprocess.check_output(
            ["termux-battery-status"],
            stderr=subprocess.DEVNULL,
            timeout=3,
        )
        d = json.loads(raw)
        voltage_v = float(d["voltage"]) / 1000.0
        current_a = abs(float(d["current"])) / 1_000_000.0
        return {
            "t": time.perf_counter(),
            "available": True,
            "voltage_v": voltage_v,
            "current_a": current_a,
            "power_w": voltage_v * current_a,
            "temperature_c": d.get("temperature"),
            "status": d.get("status"),
            "plugged": d.get("plugged"),
            "source": "termux-battery-status",
        }
    except Exception as exc:
        return {
            "t": time.perf_counter(),
            "available": False,
            "source": "termux-battery-status",
            "error": f"{type(exc).__name__}: {exc}",
        }


def sampler(stop, samples):
    while not stop.is_set():
        s = battery_sample()
        if s.get("available"):
            samples.append(s)
        stop.wait(SAMPLE_S)


def joules(samples):
    good = [s for s in samples if s.get("power_w") is not None]
    if len(good) < 2:
        return None
    total = 0.0
    for a, b in zip(good, good[1:]):
        total += ((a["power_w"] + b["power_w"]) / 2.0) * (b["t"] - a["t"])
    return total


def workload(n):
    x = 0x12345678
    for k in range(n):
        x = ((x << 5) ^ (x >> 3) ^ k ^ 0x9E3779B9) & 0xFFFFFFFF
    return x


def measured(fn):
    # Take explicit boundary samples so short EDEN/reuse runs still have
    # at least two physical battery observations when the Termux API works.
    samples = []
    pre = battery_sample()
    if pre.get("available"):
        samples.append(pre)

    stop = threading.Event()
    th = threading.Thread(target=sampler, args=(stop, samples), daemon=True)
    c0 = time.process_time()
    w0 = time.perf_counter()
    th.start()
    try:
        result = fn()
    finally:
        w1 = time.perf_counter()
        c1 = time.process_time()
        stop.set()
        th.join(timeout=3)
        post = battery_sample()
        if post.get("available"):
            samples.append(post)

    return {
        "result": result,
        "wall_seconds": w1 - w0,
        "cpu_seconds": c1 - c0,
        "max_rss_kb": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        "estimated_joules": joules(samples),
        "battery_samples": samples,
        "energy_source": "termux-battery-status",
    }


def load_cache():
    try:
        return json.loads(CACHE.read_text())
    except Exception:
        return {}


def save_cache(c):
    CACHE.write_text(json.dumps(c, sort_keys=True))


def baseline(idx):
    m = measured(lambda: workload(ITERATIONS))
    out = m.pop("result")
    return {"trial": idx, "mode": "BASELINE", "output": out, "output_commitment": sha(str(out).encode()), **m}


def eden(idx):
    cache = load_cache()
    key = sha({"workload": "integer-v1", "iterations": ITERATIONS})
    reused = key in cache

    def run():
        if key in cache:
            out = int(cache[key])
        else:
            out = workload(ITERATIONS)
            cache[key] = out
            save_cache(cache)
        payload = {
            "run_id": f"{RUN_ID}-EDEN-{idx:03d}",
            "refinery": {"input": {"key": key, "iterations": ITERATIONS}, "output": {"result": out}, "classification": "KEEP"},
            "chrononav": {"predicted_seconds": {"1": 1.20, "2": 0.82, "4": 0.55, "8": 0.40}, "deadline_seconds": 0.90, "prediction_provenance": "FIXED_EXPERIMENT_PROFILE"},
            "chrysalis": {
                "baseline": {"quality": 1.0, "total": float(ITERATIONS)},
                "policy": {"minimum_quality": 1.0, "minimum_net_reduction_fraction": 0.01},
                "candidates": [{"id": "cached-exact-result" if reused else "fresh-computation", "quality": 1.0, "active": 1.0 if reused else float(ITERATIONS), "metadata": 1.0, "recovery": 0.0, "regeneration": 0.0, "orchestration": 1.0}],
            },
            "quality": {"status": "PASS", "exact_output_match_required": True},
            "instrumentation": ["EDEN-CORE-AB-001", "python.process_time", "python.perf_counter", "resource.getrusage", "termux-battery-status"],
            "observed_resources": {},
        }
        return out, post_json("/pipeline/run", payload)

    m = measured(run)
    out, pipeline = m.pop("result")
    return {
        "trial": idx,
        "mode": "EDEN",
        "output": out,
        "output_commitment": sha(str(out).encode()),
        "avoided_recomputation": reused,
        "integrity_verified": bool(pipeline.get("verification", {}).get("integrity_verified")),
        "pipeline": pipeline,
        **m,
    }


def avg(xs):
    xs = [x for x in xs if x is not None]
    return statistics.mean(xs) if xs else None


def reduction(a, b):
    return None if a in (None, 0) or b is None else (a - b) / a * 100.0


def main():
    health = get_json("/health")
    if health.get("version") != "0.3.0":
        raise SystemExit(f"EDEN Core 0.3.0 required; running {health.get('version')}")

    probe = battery_sample()
    if not probe.get("available"):
        raise SystemExit(f"Battery telemetry unavailable: {probe.get('error', 'unknown error')}")
    print(
        f"Battery probe: {probe['power_w']:.3f} W | "
        f"{probe['voltage_v']:.3f} V | {probe['current_a']:.3f} A | "
        f"{probe.get('status')}"
    )
    if probe.get("status") != "DISCHARGING":
        raise SystemExit("STOP: unplug phone; physical energy trials require DISCHARGING state")

    print("EDEN-CORE-AB-001", health)
    workload(min(200000, ITERATIONS))
    time.sleep(2)
    if CACHE.exists():
        CACHE.unlink()
    seq = [(m, i) for i in range(1, TRIALS + 1) for m in ("BASELINE", "EDEN")]
    random.Random(20260830).shuffle(seq)
    rows = []
    for mode, idx in seq:
        print(f"[{mode}] {idx}/{TRIALS}")
        row = baseline(idx) if mode == "BASELINE" else eden(idx)
        row.update({"run_id": RUN_ID, "timestamp": utcnow(), "iterations": ITERATIONS})
        rows.append(row)
        (OUT / f"{RUN_ID}_{mode}_{idx:03d}.json").write_text(json.dumps(row, indent=2, sort_keys=True))
        print(f" wall={row['wall_seconds']:.4f}s cpu={row['cpu_seconds']:.4f}s J={row['estimated_joules']}")
        time.sleep(COOLDOWN_S)

    b = [r for r in rows if r["mode"] == "BASELINE"]
    e = [r for r in rows if r["mode"] == "EDEN"]
    bmj = avg([r["estimated_joules"] for r in b])
    emj = avg([r["estimated_joules"] for r in e])
    bcpu = avg([r["cpu_seconds"] for r in b])
    ecpu = avg([r["cpu_seconds"] for r in e])
    bw = avg([r["wall_seconds"] for r in b])
    ew = avg([r["wall_seconds"] for r in e])
    equivalent = {r["output_commitment"] for r in b} == {r["output_commitment"] for r in e}

    summary = {
        "run_id": RUN_ID,
        "classification": "MEASURED_ON_DEVICE" if bmj is not None and emj is not None else "MEASURED_COMPUTE_ENERGY_UNAVAILABLE",
        "equivalent_output": equivalent,
        "all_eden_marbles_integrity_verified": all(r.get("integrity_verified") for r in e),
        "baseline_mean_estimated_joules": bmj,
        "eden_mean_estimated_joules": emj,
        "estimated_energy_reduction_pct": reduction(bmj, emj),
        "baseline_mean_cpu_seconds": bcpu,
        "eden_mean_cpu_seconds": ecpu,
        "cpu_reduction_pct": reduction(bcpu, ecpu),
        "baseline_mean_wall_seconds": bw,
        "eden_mean_wall_seconds": ew,
        "wall_reduction_pct": reduction(bw, ew),
        "energy_boundary": "Termux battery voltage/current integration; on-device estimate, not external power meter",
        "energy_source": "termux-battery-status",
        "independent_validation": False,
    }
    p = OUT / f"{RUN_ID}_SUMMARY.json"
    p.write_text(json.dumps(summary, indent=2, sort_keys=True))
    print("\nFINAL RESULTS")
    print(json.dumps(summary, indent=2, sort_keys=True))
    print("SAVED", p)


if __name__ == "__main__":
    main()
