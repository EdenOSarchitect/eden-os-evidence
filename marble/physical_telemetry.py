#!/usr/bin/env python3
"""Adapt physical-device evidence into the stable Marble v2 telemetry envelope.

Supported physical evidence profiles:
- EDEN-RF-EST-001 handset Wi-Fi observations
- EDEN-PHYSICAL-COMPUTE-001 Android/Termux process + memory telemetry

The adapter verifies the source evidence hash before conversion. Real captures
retain MEASURED; CI fixtures must declare fixture_only=true and are forced to
SIMULATED. No unavailable quantity is synthesized.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, Mapping

POLICY_TEXT = b"EDEN-PHYSICAL-INGRESS-001: preserve source evidence class; bind source hash; require named physical instrumentation"
POLICY_HASH = "sha256:" + hashlib.sha256(POLICY_TEXT).hexdigest()


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def verify_source_hash(source: Mapping[str, Any]) -> str:
    expected = source.get("evidence_sha256")
    if not isinstance(expected, str) or not expected:
        raise ValueError("physical source lacks evidence_sha256")
    core = dict(source)
    core.pop("evidence_sha256", None)
    actual = hashlib.sha256(canonical_bytes(core)).hexdigest()
    if actual != expected:
        raise ValueError("physical source evidence_sha256 mismatch")
    return "sha256:" + actual


def _physical_evidence_class(source: Mapping[str, Any]) -> tuple[str, bool]:
    fixture_only = source.get("fixture_only") is True
    if fixture_only:
        return "SIMULATED", True
    if source.get("evidence_class") not in (None, "MEASURED"):
        raise ValueError("real physical source must retain MEASURED evidence class")
    return "MEASURED", False


def adapt_rf(source: Mapping[str, Any], *, sequence: int = 0) -> Dict[str, Any]:
    if source.get("experiment") != "EDEN-RF-EST-001":
        raise ValueError("unsupported RF evidence experiment")
    claim = source.get("claim") or {}
    sensor = source.get("sensor") or {}
    strongest = source.get("strongest_observation") or {}
    if claim.get("rssi_measured") is not True:
        raise ValueError("source does not record measured RSSI")
    if sensor.get("type") != "ANDROID_WIFI_RADIO":
        raise ValueError("unexpected physical sensor type")
    if not isinstance(strongest.get("rssi_dbm"), (int, float)):
        raise ValueError("strongest RSSI missing")
    if not isinstance(sequence, int) or sequence < 0:
        raise ValueError("sequence must be non-negative")

    source_hash = verify_source_hash(source)
    evidence_class, fixture_only = _physical_evidence_class(source)
    timestamp = str(source.get("timestamp_utc"))
    telemetry_id = f"{source['experiment']}:{timestamp}"

    observations: Dict[str, Any] = {
        "rssi_dbm": strongest["rssi_dbm"],
        "frequency_mhz": strongest.get("frequency_mhz"),
        "rf_sources_count": source.get("number_of_rf_sources"),
    }
    observation_instrumentation = {
        "rssi_dbm": {"instrument": "ANDROID_WIFI_RADIO", "unit": "dBm", "method": "termux-wifi-scaninfo"},
        "frequency_mhz": {"instrument": "ANDROID_WIFI_RADIO", "unit": "MHz", "method": "termux-wifi-scaninfo"},
        "rf_sources_count": {"instrument": "ANDROID_WIFI_RADIO", "unit": "count", "method": "termux-wifi-scaninfo"},
    }

    return {
        "telemetry_id": telemetry_id,
        "source": "ANDROID_WIFI_RADIO",
        "timestamp": timestamp,
        "evidence_class": evidence_class,
        "workload": {
            "workload_id": source["experiment"],
            "experiment_id": source["experiment"],
            "device_id": "ANDROID-HANDSET-UNATTESTED",
            "attestation": "UNATTESTED",
            "input_bytes": None,
            "output_bytes": None,
        },
        "measurements": {
            "tokens_in": None, "tokens_out": None, "cpu_seconds": None, "gpu_seconds": None,
            "memory_peak_bytes": None, "network_bytes": None, "storage_bytes": None,
            "joules": None, "wall_time_ms": None, "cost": None, "deadline_met": None,
        },
        "instrumentation": {},
        "observations": observations,
        "observation_instrumentation": observation_instrumentation,
        "source_evidence": {
            "experiment": source["experiment"],
            "commitment": source_hash,
            "physical_capture": not fixture_only,
            "fixture_only": fixture_only,
        },
        "quality": {},
        "policy": {"policy_id": "EDEN-PHYSICAL-INGRESS-001", "policy_hash": POLICY_HASH},
        "claims": [
            "physical RF observation captured" if not fixture_only else "physical RF adapter structure exercised",
            "RSSI observation bound into Marble evidence",
        ],
        "not_claimed": list(claim.get("not_claimed") or []) + (["real physical capture"] if fixture_only else ["hardware-backed device identity"]),
        "provenance": {"sequence": sequence, "previous": None},
    }


def adapt_compute(source: Mapping[str, Any], *, sequence: int = 0) -> Dict[str, Any]:
    if source.get("experiment") != "EDEN-PHYSICAL-COMPUTE-001":
        raise ValueError("unsupported compute evidence experiment")
    if source.get("device_execution") != "ANDROID_TERMUX":
        raise ValueError("unexpected compute execution environment")
    if source.get("physical_capture") is not True and source.get("fixture_only") is not True:
        raise ValueError("physical compute source lacks physical_capture=true")
    if not isinstance(sequence, int) or sequence < 0:
        raise ValueError("sequence must be non-negative")

    m = source.get("measurements") or {}
    instr = source.get("instrumentation") or {}
    workload = source.get("workload") or {}
    for key in ("wall_time_ms", "cpu_time_ms", "max_rss_kb"):
        if not isinstance(m.get(key), (int, float)):
            raise ValueError(f"compute source missing numeric {key}")
    for key in ("wall_time_ms", "cpu_time_ms", "max_rss_kb", "memory"):
        if not instr.get(key):
            raise ValueError(f"compute source missing instrumentation for {key}")

    source_hash = verify_source_hash(source)
    evidence_class, fixture_only = _physical_evidence_class(source)
    timestamp = str(source.get("timestamp_utc"))
    telemetry_id = f"{source['experiment']}:{timestamp}"

    resources = {
        "tokens_in": None,
        "tokens_out": None,
        "cpu_seconds": float(m["cpu_time_ms"]) / 1000.0,
        "gpu_seconds": None,
        "memory_peak_bytes": int(float(m["max_rss_kb"]) * 1024),
        "network_bytes": None,
        "storage_bytes": None,
        "joules": None,
        "wall_time_ms": float(m["wall_time_ms"]),
        "cost": None,
        "deadline_met": None,
    }
    instrumentation = {
        "cpu_seconds": {"instrument": str(instr["cpu_time_ms"]), "unit": "s", "method": "process CPU time converted ms->s"},
        "memory_peak_bytes": {"instrument": str(instr["max_rss_kb"]), "unit": "bytes", "method": "ru_maxrss converted KiB->bytes"},
        "wall_time_ms": {"instrument": str(instr["wall_time_ms"]), "unit": "ms", "method": "monotonic wall-clock interval"},
    }

    observations = {
        "minor_faults": m.get("minor_faults"),
        "major_faults": m.get("major_faults"),
        "memory_before_kb": m.get("memory_before_kb", m.get("mem_before_kb")),
        "memory_after_kb": m.get("memory_after_kb", m.get("mem_after_kb")),
        "deterministic_result": workload.get("result"),
        "iterations": workload.get("iterations"),
    }
    observation_instrumentation = {
        "minor_faults": {"instrument": "resource.getrusage", "unit": "count", "method": "delta ru_minflt"},
        "major_faults": {"instrument": "resource.getrusage", "unit": "count", "method": "delta ru_majflt"},
        "memory_before_kb": {"instrument": str(instr["memory"]), "unit": "kB", "method": "pre-workload /proc/meminfo snapshot"},
        "memory_after_kb": {"instrument": str(instr["memory"]), "unit": "kB", "method": "post-workload /proc/meminfo snapshot"},
        "deterministic_result": {"instrument": "PYTHON_INTEGER_LOOP", "unit": "uint32", "method": "deterministic workload terminal state"},
        "iterations": {"instrument": "PYTHON_INTEGER_LOOP", "unit": "count", "method": "configured loop count"},
    }

    return {
        "telemetry_id": telemetry_id,
        "source": "ANDROID_TERMUX",
        "timestamp": timestamp,
        "evidence_class": evidence_class,
        "workload": {
            "workload_id": source["experiment"],
            "experiment_id": source["experiment"],
            "device_id": "ANDROID-HANDSET-UNATTESTED",
            "attestation": "UNATTESTED",
            "input_bytes": None,
            "output_bytes": None,
            "workload_type": workload.get("type"),
        },
        "measurements": resources,
        "instrumentation": instrumentation,
        "observations": observations,
        "observation_instrumentation": observation_instrumentation,
        "source_evidence": {
            "experiment": source["experiment"],
            "commitment": source_hash,
            "physical_capture": not fixture_only,
            "fixture_only": fixture_only,
        },
        "quality": {},
        "policy": {"policy_id": "EDEN-PHYSICAL-INGRESS-001", "policy_hash": POLICY_HASH},
        "claims": [
            "physical handset workload executed" if not fixture_only else "physical compute adapter structure exercised",
            "wall time measured",
            "process CPU time measured",
            "peak process RSS measured",
            "memory snapshots bound into Marble evidence",
        ],
        "not_claimed": list(source.get("not_claimed") or []) + (["real physical capture"] if fixture_only else ["hardware-backed device identity"]),
        "provenance": {"sequence": sequence, "previous": None},
    }


def adapt(source: Mapping[str, Any], *, sequence: int = 0) -> Dict[str, Any]:
    experiment = source.get("experiment")
    if experiment == "EDEN-RF-EST-001":
        return adapt_rf(source, sequence=sequence)
    if experiment == "EDEN-PHYSICAL-COMPUTE-001":
        return adapt_compute(source, sequence=sequence)
    raise ValueError(f"unsupported physical evidence experiment: {experiment}")


def main() -> int:
    p = argparse.ArgumentParser(description="Adapt EDEN physical telemetry into Marble v2 telemetry envelope")
    p.add_argument("source")
    p.add_argument("--output", required=True)
    p.add_argument("--sequence", type=int, default=0)
    args = p.parse_args()
    source = json.loads(Path(args.source).read_text(encoding="utf-8"))
    telemetry = adapt(source, sequence=args.sequence)
    Path(args.output).write_text(json.dumps(telemetry, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"output": args.output, "telemetry_id": telemetry["telemetry_id"], "evidence_class": telemetry["evidence_class"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
