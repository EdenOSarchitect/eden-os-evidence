#!/usr/bin/env python3
"""Synthetic EDEN-SAT-001 selective-downlink simulation (not flight evidence)."""

from __future__ import annotations

import hashlib
import json
import math
import random
import statistics
from pathlib import Path

SEED = 20260811
MISSIONS = 200
SCENES_PER_MISSION = 10_000
USEFUL_PREVALENCE = 0.35
SCENE_BYTES_MIN = 40_000_000
SCENE_BYTES_MAX = 120_000_000
ENERGY_J_PER_DOWNLINK_BYTE = 2.5e-6  # explicit engineering assumption
SELECTOR_ENERGY_J_PER_SCENE = 18.0   # explicit hardware-proxy assumption
DOWNLINK_VALUE_USD_PER_GB = 0.02     # scenario input, not an observed price
SELECTOR_COST_USD_PER_MISSION = 1.50 # scenario input, not an observed cost
FLIGHT_AVAILABILITY = 0.9995         # assumed, not flight-measured
BASELINE_LATENCY_MS = 42.0
SELECTOR_OVERHEAD_MS = 7.5
QUALITY_GATE = 0.99
ENSEMBLE_MEMBERS = 3


def percentile(values: list[float], q: float) -> float:
    values = sorted(values)
    k = (len(values) - 1) * q
    lo, hi = math.floor(k), math.ceil(k)
    return values[lo] if lo == hi else values[lo] * (hi - k) + values[hi] * (k - lo)


def score(rng: random.Random, useful: bool) -> float:
    # Synthetic ensemble proxy; not fitted to or measured on CloudSEN12.
    dist = (7.0, 2.1) if useful else (2.0, 6.5)
    return statistics.fmean(rng.betavariate(*dist) for _ in range(ENSEMBLE_MEMBERS))


def select_threshold(rng: random.Random, n: int = 100_000) -> float:
    validation = [(rng.random() < USEFUL_PREVALENCE) for _ in range(n)]
    scored = [(label, score(rng, label)) for label in validation]
    useful_scores = [s for label, s in scored if label]
    candidates = [percentile(useful_scores, q / 1000) for q in range(1, 10)]
    eligible: list[tuple[float, float]] = []
    for threshold in candidates:
        tp = tn = fp = fn = 0
        for label, value in scored:
            keep = value >= threshold
            tp += int(label and keep); fn += int(label and not keep)
            tn += int(not label and not keep); fp += int(not label and keep)
        recall = tp / (tp + fn)
        accuracy = (tp + tn) / n
        if recall >= 0.992:  # validation safety margin above the 0.99 test gate
            eligible.append((accuracy, threshold))
    if not eligible:
        raise RuntimeError("no validation threshold satisfies recall margin")
    return max(eligible)[1]


def run_mission(rng: random.Random, threshold: float) -> dict[str, float]:
    tp = tn = fp = fn = 0
    total_bytes = kept_bytes = safely_avoided = unsafe_avoided = 0
    for _ in range(SCENES_PER_MISSION):
        useful = rng.random() < USEFUL_PREVALENCE
        keep = score(rng, useful) >= threshold
        size = rng.randint(SCENE_BYTES_MIN, SCENE_BYTES_MAX)
        total_bytes += size
        if keep:
            kept_bytes += size
            if useful: tp += 1
            else: fp += 1
        elif useful:
            fn += 1
            unsafe_avoided += size
        else:
            tn += 1
            safely_avoided += size
    recall = tp / (tp + fn)
    precision = tp / (tp + fp)
    specificity = tn / (tn + fp)
    accuracy = (tp + tn) / SCENES_PER_MISSION
    f1 = 2 * precision * recall / (precision + recall)
    avoided = safely_avoided + unsafe_avoided
    gross_energy = avoided * ENERGY_J_PER_DOWNLINK_BYTE
    selector_energy = SCENES_PER_MISSION * SELECTOR_ENERGY_J_PER_SCENE
    net_energy = gross_energy - selector_energy
    gross_value = avoided / 1_000_000_000 * DOWNLINK_VALUE_USD_PER_GB
    return {
        "recall": recall,
        "precision": precision,
        "specificity": specificity,
        "accuracy": accuracy,
        "f1": f1,
        "false_discard_rate_useful": fn / (tp + fn),
        "downlink_reduction_fraction": avoided / total_bytes,
        "safe_downlink_reduction_fraction": safely_avoided / total_bytes,
        "unsafe_avoided_fraction": unsafe_avoided / total_bytes,
        "baseline_bytes": total_bytes,
        "downlinked_bytes": kept_bytes,
        "safely_avoided_bytes": safely_avoided,
        "unsafe_avoided_bytes": unsafe_avoided,
        "modeled_gross_energy_avoided_j": gross_energy,
        "modeled_selector_energy_j": selector_energy,
        "modeled_net_energy_avoided_j": net_energy,
        "modeled_gross_economic_value_usd": gross_value,
        "modeled_net_economic_value_usd": gross_value - SELECTOR_COST_USD_PER_MISSION,
        "modeled_flight_adjusted_recall": recall * FLIGHT_AVAILABILITY,
        "modeled_latency_ms": BASELINE_LATENCY_MS + SELECTOR_OVERHEAD_MS,
        "gate_pass": recall >= QUALITY_GATE,
    }


def summarize(rows: list[dict[str, float]], key: str) -> dict[str, float]:
    vals = [float(r[key]) for r in rows]
    return {
        "mean": statistics.fmean(vals),
        "p05": percentile(vals, 0.05),
        "p50": percentile(vals, 0.50),
        "p95": percentile(vals, 0.95),
    }


def main() -> None:
    rng = random.Random(SEED)
    threshold = select_threshold(rng)
    rows = [run_mission(rng, threshold) for _ in range(MISSIONS)]
    metric_keys = [
        "recall", "precision", "specificity", "accuracy", "f1",
        "false_discard_rate_useful", "downlink_reduction_fraction",
        "safe_downlink_reduction_fraction", "unsafe_avoided_fraction",
        "baseline_bytes", "downlinked_bytes", "safely_avoided_bytes",
        "unsafe_avoided_bytes", "modeled_gross_energy_avoided_j",
        "modeled_selector_energy_j", "modeled_net_energy_avoided_j",
        "modeled_gross_economic_value_usd", "modeled_net_economic_value_usd",
        "modeled_flight_adjusted_recall", "modeled_latency_ms",
    ]
    result = {
        "experiment": "EDEN-SAT-001-SIM-002",
        "classification": "SIMULATED_SYNTHETIC_NOT_FLIGHT_EVIDENCE",
        "seed": SEED,
        "missions": MISSIONS,
        "scenes_per_mission": SCENES_PER_MISSION,
        "total_test_scenes": MISSIONS * SCENES_PER_MISSION,
        "assumptions": {
            "useful_prevalence": USEFUL_PREVALENCE,
            "useful_score_distribution": "Beta(7.0, 2.1)",
            "non_useful_score_distribution": "Beta(2.0, 6.5)",
            "scene_bytes_uniform": [SCENE_BYTES_MIN, SCENE_BYTES_MAX],
            "energy_j_per_downlink_byte": ENERGY_J_PER_DOWNLINK_BYTE,
            "selector_energy_j_per_scene": SELECTOR_ENERGY_J_PER_SCENE,
            "downlink_value_usd_per_gb": DOWNLINK_VALUE_USD_PER_GB,
            "selector_cost_usd_per_mission": SELECTOR_COST_USD_PER_MISSION,
            "flight_availability": FLIGHT_AVAILABILITY,
            "ensemble_members": ENSEMBLE_MEMBERS,
            "baseline_latency_ms": BASELINE_LATENCY_MS,
            "selector_overhead_ms": SELECTOR_OVERHEAD_MS,
        },
        "selected_threshold": threshold,
        "quality_gate_recall": QUALITY_GATE,
        "mission_gate_pass_rate": sum(bool(r["gate_pass"]) for r in rows) / MISSIONS,
        "metrics": {k: summarize(rows, k) for k in metric_keys},
        "measurement_register": {
            "cloudsen12_performance": {
                "status": "NOT_MEASURED",
                "dataset_manifest_sha256": None,
                "test_split_sha256": None,
                "measured_accuracy": None,
                "measured_recall": None
            },
            "flight_performance": {
                "status": "SIMULATED_ONLY",
                "measured_missions": 0,
                "assumed_availability": FLIGHT_AVAILABILITY
            },
            "hardware_energy_savings": {
                "status": "MODELED_ONLY",
                "power_meter_trace_sha256": None,
                "hardware_model": None
            },
            "economic_savings": {
                "status": "MODELED_ONLY",
                "invoice_or_ledger_evidence_sha256": None,
                "currency": "USD"
            }
        },
        "claim_boundaries": {
            "cloudsen12_measured": False,
            "real_satellite_measured": False,
            "real_energy_savings_proven": False,
            "realized_economic_savings_proven": False,
        },
    }
    canonical = json.dumps(result, indent=2, sort_keys=True) + "\n"
    result["result_payload_sha256"] = hashlib.sha256(canonical.encode()).hexdigest()
    out = Path(__file__).with_name("RESULTS.json")
    out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
