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

RUN_ID = "EDEN-CORE-AB-002"
CORE = os.getenv("EDEN_CORE_URL", "http://127.0.0.1:8766")
TRIALS = int(os.getenv("EDEN_AB_TRIALS", "4"))
ITERATIONS = int(os.getenv("EDEN_AB_ITERATIONS", "4000000"))
WINDOW_S = float(os.getenv("EDEN_AB_WINDOW_SECONDS", "10"))
SAMPLE_S = float(os.getenv("EDEN_POWER_SAMPLE_SECONDS", "0.25"))
COOLDOWN_S = float(os.getenv("EDEN_COOLDOWN_SECONDS", "5"))
OUT = Path("experiments/eden-core-ab-002/results")
OUT.mkdir(parents=True, exist_ok=True)
CACHE = OUT / "reuse-cache.json"

ARMS = ("BASELINE_RECOMPUTE", "BASELINE_REUSE_NO_EDEN", "EDEN_REUSE")


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
    raw = subprocess.check_output(
        ["termux-battery-status"],
        stderr=subprocess.DEVNULL,
        timeout=3,
    )
    d = json.loads(raw)
    voltage_v = float(d["voltage"]) / 1000.0
    current_a = abs(float(d["current"])) / 1_000_000.0
    if not 2.5 <= voltage_v <= 5.0:
        raise RuntimeError(f"implausible battery voltage {voltage_v} V")
    if current_a > 20.0:
        raise RuntimeError(f"implausible battery current {current_a} A")
    return {
        "t": time.perf_counter(),
        "voltage_v": voltage_v,
        "current_a": current_a,
        "power_w": voltage_v * current_a,
        "temperature_c": d.get("temperature"),
        "status": d.get("status"),
        "plugged": d.get("plugged"),
        "raw_voltage_mv": d.get("voltage"),
        "raw_current_ua": d.get("current"),
        "raw_current_average_ua": d.get("current_average"),
        "source": "termux-battery-status",
    }


def sampler(stop, samples, errors):
    while not stop.is_set():
        try:
            samples.append(battery_sample())
        except Exception as exc:
            errors.append(f"{type(exc).__name__}: {exc}")
        stop.wait(SAMPLE_S)


def integrate_joules(samples):
    if len(samples) < 2:
        return None
    total = 0.0
    for a, b in zip(samples, samples[1:]):
        dt = b["t"] - a["t"]
        total += ((a["power_w"] + b["power_w"]) / 2.0) * dt
    return total


def workload(n):
    x = 0x12345678
    for k in range(n):
        x = ((x << 5) ^ (x >> 3) ^ k ^ 0x9E3779B9) & 0xFFFFFFFF
    return x


def measured_window(fn):
    samples = []
    errors = []
    pre = battery_sample()
    if pre.get("status") != "DISCHARGING":
        raise SystemExit("STOP: phone must remain UNPLUGGED / DISCHARGING")
    samples.append(pre)

    stop = threading.Event()
    th = threading.Thread(target=sampler, args=(stop, samples, errors), daemon=True)
    c0 = time.process_time()
    w0 = time.perf_counter()
    th.start()
    try:
        result = fn(WINDOW_S)
    finally:
        w1 = time.perf_counter()
        c1 = time.process_time()
        stop.set()
        th.join(timeout=3)
        samples.append(battery_sample())

    span = samples[-1]["t"] - samples[0]["t"] if len(samples) >= 2 else 0.0
    est_j = integrate_joules(samples)
    return {
        "result": result,
        "wall_seconds": w1 - w0,
        "cpu_seconds": c1 - c0,
        "max_rss_kb": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        "estimated_joules": est_j,
        "battery_samples": samples,
        "battery_sample_count": len(samples),
        "measurement_span_seconds": span,
        "sampler_errors": errors,
        "energy_source": "termux-battery-status",
        "energy_resolution_ok": len(samples) >= 10 and span >= 2.0,
    }


def cache_key():
    return sha({"workload": "integer-v1", "iterations": ITERATIONS})


def prewarm_cache():
    key = cache_key()
    out = workload(ITERATIONS)
    CACHE.write_text(json.dumps({key: out}, sort_keys=True))
    return key, out


def read_cached(key):
    return int(json.loads(CACHE.read_text())[key])


def arm_recompute(window_s):
    deadline = time.perf_counter() + window_s
    count = 0
    out = None
    while time.perf_counter() < deadline:
        out = workload(ITERATIONS)
        count += 1
    return {"requests": count, "output": out}


def arm_reuse_no_eden(window_s, key):
    cache = json.loads(CACHE.read_text())
    out = int(cache[key])
    deadline = time.perf_counter() + window_s
    count = 0
    last = None
    while time.perf_counter() < deadline:
        last = out
        count += 1
    return {"requests": count, "output": last}


def arm_eden_reuse(window_s, key, trial_idx):
    cache = json.loads(CACHE.read_text())
    out = int(cache[key])
    deadline = time.perf_counter() + window_s
    count = 0
    integrity_ok = True
    while time.perf_counter() < deadline:
        count += 1
        payload = {
            "run_id": f"{RUN_ID}-EDEN-{trial_idx:03d}-{count:06d}",
            "refinery": {
                "input": {"key": key, "iterations": ITERATIONS},
                "output": {"result": out},
                "classification": "KEEP",
            },
            "chrononav": {
                "predicted_seconds": {"1": 1.20, "2": 0.82, "4": 0.55, "8": 0.40},
                "deadline_seconds": 0.90,
                "prediction_provenance": "FIXED_EXPERIMENT_PROFILE",
            },
            "chrysalis": {
                "baseline": {"quality": 1.0, "total": float(ITERATIONS)},
                "policy": {"minimum_quality": 1.0, "minimum_net_reduction_fraction": 0.01},
                "candidates": [{
                    "id": "cached-exact-result",
                    "quality": 1.0,
                    "active": 1.0,
                    "metadata": 1.0,
                    "recovery": 0.0,
                    "regeneration": 0.0,
                    "orchestration": 1.0,
                }],
            },
            "quality": {"status": "PASS", "exact_output_match_required": True},
            "instrumentation": [
                RUN_ID,
                "python.process_time",
                "python.perf_counter",
                "resource.getrusage",
                "termux-battery-status",
            ],
            "observed_resources": {},
        }
        pipeline = post_json("/pipeline/run", payload)
        integrity_ok = integrity_ok and bool(pipeline.get("verification", {}).get("integrity_verified"))
    return {"requests": count, "output": out, "all_integrity_verified": integrity_ok}


def mean(rows, field):
    vals = [r[field] for r in rows if r.get(field) is not None]
    return statistics.mean(vals) if vals else None


def pct_reduction(a, b):
    return None if a in (None, 0) or b is None else (a - b) / a * 100.0


def main():
    health = get_json("/health")
    if health.get("version") != "0.3.0":
        raise SystemExit(f"EDEN Core 0.3.0 required; running {health.get('version')}")

    probe = battery_sample()
    print(
        f"Battery probe: {probe['power_w']:.3f} W | {probe['voltage_v']:.3f} V | "
        f"{probe['current_a']:.3f} A | {probe.get('status')} | {probe.get('temperature_c')} C"
    )
    if probe.get("status") != "DISCHARGING":
        raise SystemExit("STOP: unplug phone; physical energy trials require DISCHARGING state")

    print(f"{RUN_ID}: three-arm fixed-window efficiency test")
    print(f"Window: {WINDOW_S:.1f}s per arm | trials: {TRIALS} | iterations/request: {ITERATIONS}")

    key, expected = prewarm_cache()
    expected_commitment = sha(str(expected).encode())
    print("Cache prewarmed before measured trials.")

    seq = [(arm, i) for i in range(1, TRIALS + 1) for arm in ARMS]
    random.Random(20260830).shuffle(seq)
    rows = []

    for arm, idx in seq:
        print(f"[{arm}] {idx}/{TRIALS}")
        if arm == "BASELINE_RECOMPUTE":
            m = measured_window(arm_recompute)
        elif arm == "BASELINE_REUSE_NO_EDEN":
            m = measured_window(lambda seconds: arm_reuse_no_eden(seconds, key))
        else:
            m = measured_window(lambda seconds: arm_eden_reuse(seconds, key, idx))

        result = m.pop("result")
        requests = int(result["requests"])
        output_commitment = sha(str(result["output"]).encode())
        row = {
            "run_id": RUN_ID,
            "timestamp": utcnow(),
            "trial": idx,
            "arm": arm,
            "iterations_per_request": ITERATIONS,
            "window_seconds": WINDOW_S,
            "requests": requests,
            "output_commitment": output_commitment,
            "equivalent_output": output_commitment == expected_commitment,
            "all_integrity_verified": result.get("all_integrity_verified"),
            **m,
        }
        row["requests_per_second"] = requests / row["wall_seconds"] if row["wall_seconds"] else None
        row["joules_per_request"] = row["estimated_joules"] / requests if row["estimated_joules"] is not None and requests else None
        row["cpu_seconds_per_request"] = row["cpu_seconds"] / requests if requests else None
        rows.append(row)
        path = OUT / f"{RUN_ID}_{arm}_{idx:03d}.json"
        path.write_text(json.dumps(row, indent=2, sort_keys=True))
        print(
            f" requests={requests} wall={row['wall_seconds']:.3f}s "
            f"J={row['estimated_joules']:.4f} J/request={row['joules_per_request']:.8f} "
            f"samples={row['battery_sample_count']}"
        )
        time.sleep(COOLDOWN_S)

    grouped = {arm: [r for r in rows if r["arm"] == arm] for arm in ARMS}
    for arm, rs in grouped.items():
        if not all(r["equivalent_output"] for r in rs):
            raise SystemExit(f"STOP: output equivalence failed in {arm}")

    a_jpr = mean(grouped["BASELINE_RECOMPUTE"], "joules_per_request")
    b_jpr = mean(grouped["BASELINE_REUSE_NO_EDEN"], "joules_per_request")
    c_jpr = mean(grouped["EDEN_REUSE"], "joules_per_request")

    summary = {
        "run_id": RUN_ID,
        "classification": "MEASURED_ON_DEVICE",
        "design": "three-arm fixed-duration throughput-normalized comparison",
        "arms": {
            arm: {
                "mean_estimated_joules": mean(grouped[arm], "estimated_joules"),
                "mean_joules_per_request": mean(grouped[arm], "joules_per_request"),
                "mean_requests_per_second": mean(grouped[arm], "requests_per_second"),
                "mean_cpu_seconds_per_request": mean(grouped[arm], "cpu_seconds_per_request"),
                "all_energy_resolution_ok": all(r["energy_resolution_ok"] for r in grouped[arm]),
                "all_outputs_equivalent": all(r["equivalent_output"] for r in grouped[arm]),
            }
            for arm in ARMS
        },
        "gross_reuse_energy_reduction_pct_per_request": pct_reduction(a_jpr, b_jpr),
        "eden_net_energy_reduction_pct_per_request_vs_recompute": pct_reduction(a_jpr, c_jpr),
        "eden_overhead_pct_vs_plain_reuse_per_request": None if b_jpr in (None, 0) or c_jpr is None else (c_jpr - b_jpr) / b_jpr * 100.0,
        "all_eden_marbles_integrity_verified": all(
            r.get("all_integrity_verified") is True for r in grouped["EDEN_REUSE"]
        ),
        "cache_prewarmed_before_measurement": True,
        "equivalent_output_required": True,
        "energy_source": "termux-battery-status",
        "energy_boundary": "Termux battery voltage/current integration; on-device estimate, not external power meter",
        "normalization": "joules and CPU seconds per completed equivalent logical request during equal-duration windows",
        "independent_validation": False,
    }

    p = OUT / f"{RUN_ID}_SUMMARY.json"
    p.write_text(json.dumps(summary, indent=2, sort_keys=True))
    print("\nFINAL RESULTS")
    print(json.dumps(summary, indent=2, sort_keys=True))
    print("SAVED", p)


if __name__ == "__main__":
    main()
