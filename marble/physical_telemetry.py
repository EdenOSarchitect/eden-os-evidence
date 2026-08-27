#!/usr/bin/env python3
"""Adapt physical-device evidence into the stable Marble v2 telemetry envelope.

The adapter currently supports EDEN-RF-EST-001 handset Wi-Fi observations. It
verifies the source evidence hash before conversion. Real captures retain
MEASURED; CI fixtures must declare fixture_only=true and are forced to SIMULATED.
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


def adapt_rf(source: Mapping[str, Any], *, sequence: int = 0) -> Dict[str, Any]:
    if source.get("experiment") != "EDEN-RF-EST-001":
        raise ValueError("unsupported physical evidence experiment")
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
    fixture_only = source.get("fixture_only") is True
    evidence_class = "SIMULATED" if fixture_only else "MEASURED"
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


def main() -> int:
    p = argparse.ArgumentParser(description="Adapt EDEN physical telemetry into Marble v2 telemetry envelope")
    p.add_argument("source")
    p.add_argument("--output", required=True)
    p.add_argument("--sequence", type=int, default=0)
    args = p.parse_args()
    source = json.loads(Path(args.source).read_text(encoding="utf-8"))
    telemetry = adapt_rf(source, sequence=args.sequence)
    Path(args.output).write_text(json.dumps(telemetry, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"output": args.output, "telemetry_id": telemetry["telemetry_id"], "evidence_class": telemetry["evidence_class"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
