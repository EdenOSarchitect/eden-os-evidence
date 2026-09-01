#!/usr/bin/env python3
"""Full telemetry -> verified EDEN Marble v2 E2E artifact.

MARBLE-LIFE-001 acceptance path.

Consumes one telemetry envelope, commits the raw input, normalizes resource and
physical observations, mints an EXECUTION Marble, performs primary + independent
identity verification, verifies measurement provenance, optionally enforces CRV
limits, attaches a timestamp anchor, optionally signs the Marble, persists
provenance head state, appends a transparency-log entry, and emits one immutable
E2E result artifact.

The pipeline never upgrades evidence class. Physical, simulated and modelled
sources retain their supplied evidence class and truth boundary.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

try:
    from .assurance import append_log, canonical_bytes, make_timestamp_anchor, persist_head, sign_hmac, verify_hmac, verify_log
    from .independent_verify import verify as independent_verify
    from .marble import assurance_profile, mint, verify_crv, verify_integrity
except ImportError:
    from assurance import append_log, canonical_bytes, make_timestamp_anchor, persist_head, sign_hmac, verify_hmac, verify_log
    from independent_verify import verify as independent_verify
    from marble import assurance_profile, mint, verify_crv, verify_integrity

ARTIFACT_DOMAIN = b"EDEN-MARBLE-E2E-001\x00"
RESOURCE_KEYS = (
    "tokens_in", "tokens_out", "cpu_seconds", "gpu_seconds",
    "memory_peak_bytes", "network_bytes", "storage_bytes", "joules",
    "wall_time_ms", "cost", "deadline_met",
)


def sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _require(mapping: Mapping[str, Any], names, where: str) -> None:
    missing = [n for n in names if n not in mapping]
    if missing:
        raise ValueError(f"{where}: missing {', '.join(missing)}")


def _normalize_measurement_group(values: Mapping[str, Any], instruments: Mapping[str, Any], *, telemetry_id: str, source: str, timestamp: str, group: str) -> tuple[Dict[str, Any], Dict[str, Any]]:
    normalized: Dict[str, Any] = {}
    provenance: Dict[str, Any] = {}
    for key, value in values.items():
        normalized[key] = value
        if value is None:
            continue
        instrument = instruments.get(key)
        if not isinstance(instrument, dict) or not instrument.get("instrument"):
            raise ValueError(f"non-null {group} {key} lacks instrumentation")
        measurement = {
            "telemetry_id": telemetry_id,
            "group": group,
            "measurement": key,
            "value": value,
            "unit": instrument.get("unit"),
            "instrument": instrument["instrument"],
            "method": instrument.get("method"),
            "source": source,
            "timestamp": timestamp,
        }
        provenance[key] = {
            "instrument": instrument["instrument"],
            "measurement_ref": sha256(canonical_bytes(measurement)),
            "unit": instrument.get("unit"),
            "method": instrument.get("method"),
        }
    return normalized, provenance


def normalize_telemetry(t: Mapping[str, Any]) -> Dict[str, Any]:
    _require(t, ["telemetry_id", "source", "timestamp", "evidence_class", "workload", "measurements", "instrumentation"], "telemetry")
    workload = t["workload"]
    measurements = t["measurements"]
    instruments = t["instrumentation"]
    if not isinstance(workload, dict) or not isinstance(measurements, dict) or not isinstance(instruments, dict):
        raise ValueError("workload, measurements and instrumentation must be objects")

    resource_values = {key: measurements.get(key) for key in RESOURCE_KEYS}
    resources, resource_provenance = _normalize_measurement_group(
        resource_values, instruments,
        telemetry_id=str(t["telemetry_id"]), source=str(t["source"]), timestamp=str(t["timestamp"]), group="resource",
    )

    observations_in = t.get("observations") or {}
    observation_instruments = t.get("observation_instrumentation") or {}
    if not isinstance(observations_in, dict) or not isinstance(observation_instruments, dict):
        raise ValueError("observations and observation_instrumentation must be objects")
    observations, observation_provenance = _normalize_measurement_group(
        observations_in, observation_instruments,
        telemetry_id=str(t["telemetry_id"]), source=str(t["source"]), timestamp=str(t["timestamp"]), group="observation",
    )

    return {
        "telemetry_id": str(t["telemetry_id"]),
        "source": str(t["source"]),
        "timestamp": str(t["timestamp"]),
        "evidence_class": str(t["evidence_class"]),
        "workload": dict(workload),
        "resources": resources,
        "resource_provenance": resource_provenance,
        "observations": observations,
        "observation_provenance": observation_provenance,
        "source_evidence": dict(t.get("source_evidence") or {}),
        "quality": dict(t.get("quality") or {}),
        "policy": dict(t.get("policy") or {}),
        "crv_allocation": dict(t.get("crv_allocation") or {}),
        "claims": list(t.get("claims") or []),
        "not_claimed": list(t.get("not_claimed") or []),
        "provenance": dict(t.get("provenance") or {}),
    }


def build_core(normalized: Mapping[str, Any], raw_commitment: str) -> Dict[str, Any]:
    workload = normalized["workload"]
    policy = normalized["policy"]
    if not policy.get("policy_id") or not policy.get("policy_hash"):
        raise ValueError("policy_id and policy_hash required")
    seq = normalized["provenance"].get("sequence")
    if not isinstance(seq, int) or seq < 0:
        raise ValueError("provenance.sequence must be a non-negative integer")

    output_commitment = workload.get("output_commitment") or sha256(canonical_bytes({
        "telemetry_id": normalized["telemetry_id"],
        "resources": normalized["resources"],
        "observations": normalized["observations"],
        "quality": normalized["quality"],
    }))
    all_instruments = {
        p["instrument"] for p in list(normalized["resource_provenance"].values()) + list(normalized["observation_provenance"].values())
    }

    return {
        "schema": "eden.marble.v2",
        "kind": "EXECUTION",
        "subject": {
            "telemetry_id": normalized["telemetry_id"],
            "workload_id": workload.get("workload_id"),
            "experiment_id": workload.get("experiment_id"),
        },
        "parents": list(workload.get("parents") or []),
        "actor": {
            "source": normalized["source"],
            "device_id": workload.get("device_id"),
            "attestation": workload.get("attestation", "UNATTESTED"),
        },
        "policy": {"policy_id": policy["policy_id"], "policy_hash": policy["policy_hash"]},
        "input": {
            "commitment": raw_commitment,
            "bytes": workload.get("input_bytes"),
            "source_evidence": dict(normalized["source_evidence"]),
        },
        "output": {"commitment": output_commitment, "bytes": workload.get("output_bytes")},
        "resources": dict(normalized["resources"]),
        "quality": dict(normalized["quality"]),
        "evidence": {
            "class": normalized["evidence_class"],
            "instrumentation": sorted(all_instruments),
            "resource_provenance": dict(normalized["resource_provenance"]),
            "observations": dict(normalized["observations"]),
            "observation_provenance": dict(normalized["observation_provenance"]),
        },
        "truth": {"claims": list(normalized["claims"]), "not_claimed": list(normalized["not_claimed"])},
        "provenance": {"sequence": seq, "previous": normalized["provenance"].get("previous")},
        "timestamp": normalized["timestamp"],
    }


def artifact_id(artifact: Mapping[str, Any]) -> str:
    core = dict(artifact)
    core.pop("artifact_id", None)
    return sha256(ARTIFACT_DOMAIN + canonical_bytes(core))


def run_e2e(telemetry_path: str, *, log_path: Optional[str] = None, head_path: Optional[str] = None, signing_key: Optional[bytes] = None, key_id: Optional[str] = None) -> Dict[str, Any]:
    path = Path(telemetry_path)
    raw_bytes = path.read_bytes()
    telemetry = json.loads(raw_bytes.decode("utf-8"))
    normalized = normalize_telemetry(telemetry)
    raw_commitment = sha256(raw_bytes)
    marble = mint(build_core(normalized, raw_commitment))

    timestamp_anchor = make_timestamp_anchor(marble["marble_id"])
    marble["assurance"] = {"timestamp_anchor": timestamp_anchor}
    primary = verify_integrity(marble)
    independent = independent_verify(marble)
    crv = verify_crv(normalized["crv_allocation"], marble["resources"]) if normalized["crv_allocation"] else {"within_delegation": True, "violations": []}

    signature = None
    signature_verification = {"signature_verified": None, "errors": []}
    if signing_key is not None:
        if not key_id:
            raise ValueError("key_id required when signing_key is supplied")
        signature = sign_hmac(marble["marble_id"], signing_key, key_id)
        signature_verification = verify_hmac(marble["marble_id"], signature, {key_id: signing_key})

    persisted_head = persist_head(head_path, marble["marble_id"], int(marble["provenance"]["sequence"])) if head_path else None
    log_entry = None
    log_verification = {"transparency_log_verified": True, "entries": 0, "head": None, "errors": []}
    if log_path:
        log_entry = append_log(log_path, marble["marble_id"])
        entries = [json.loads(line) for line in Path(log_path).read_text(encoding="utf-8").splitlines() if line.strip()]
        log_verification = verify_log(entries)

    signature_ok = signature_verification["signature_verified"] is not False
    e2e_verified = all([
        primary.get("structurally_valid"), primary.get("integrity_verified"), primary.get("provenance_verified"),
        primary.get("policy_verified"), primary.get("evidence_verified"), primary.get("resource_provenance_verified"),
        primary.get("timestamp_anchor_verified"), independent.get("identity_verified"), crv.get("within_delegation"),
        log_verification.get("transparency_log_verified"), signature_ok,
    ])

    artifact: Dict[str, Any] = {
        "profile": "eden.marble.v2.telemetry-e2e",
        "telemetry_source": {"path": str(path), "sha256": raw_commitment, "bytes": len(raw_bytes), "telemetry_id": normalized["telemetry_id"]},
        "normalized_telemetry": normalized,
        "marble": marble,
        "verification": {
            "primary": primary, "independent": independent, "assurance_profile": assurance_profile(marble, primary),
            "crv": crv, "signature": signature_verification, "transparency_log": log_verification,
        },
        "assurance_artifacts": {
            "signature": signature, "timestamp_anchor": timestamp_anchor,
            "provenance_head": persisted_head, "transparency_log_entry": log_entry,
        },
        "e2e_verified": bool(e2e_verified),
        "scientific_truth_implied": False,
    }
    artifact["artifact_id"] = artifact_id(artifact)
    return artifact


def verify_e2e_artifact(artifact: Mapping[str, Any]) -> Dict[str, Any]:
    errors = []
    expected_artifact_id = artifact_id(artifact)
    if artifact.get("artifact_id") != expected_artifact_id:
        errors.append("artifact_id mismatch")
    marble = artifact.get("marble") or {}
    primary = verify_integrity(marble)
    independent = independent_verify(marble)
    if not primary.get("integrity_verified"):
        errors.append("primary Marble integrity verification failed")
    if not independent.get("identity_verified"):
        errors.append("independent Marble identity verification failed")
    if artifact.get("telemetry_source", {}).get("sha256") != marble.get("input", {}).get("commitment"):
        errors.append("telemetry commitment does not match Marble input commitment")
    if artifact.get("e2e_verified") is not True:
        errors.append("artifact not marked e2e_verified")
    return {
        "profile": "eden.marble.v2.telemetry-e2e-verifier", "verified": not errors,
        "artifact_id": artifact.get("artifact_id"), "expected_artifact_id": expected_artifact_id,
        "errors": errors, "scientific_truth_implied": False,
    }


def main() -> int:
    p = argparse.ArgumentParser(description="Full telemetry -> verified EDEN Marble v2 E2E artifact")
    sub = p.add_subparsers(dest="cmd", required=True)
    run = sub.add_parser("run")
    run.add_argument("telemetry")
    run.add_argument("--output", required=True)
    run.add_argument("--log")
    run.add_argument("--head")
    run.add_argument("--signing-key-env", default="EDEN_MARBLE_SIGNING_KEY")
    run.add_argument("--key-id", default="local")
    run.add_argument("--unsigned", action="store_true")
    verify = sub.add_parser("verify")
    verify.add_argument("artifact")
    args = p.parse_args()

    if args.cmd == "run":
        key = None if args.unsigned else os.environ.get(args.signing_key_env)
        if not args.unsigned and not key:
            raise SystemExit(f"missing signing key env {args.signing_key_env}; use --unsigned only when intentionally testing unsigned mode")
        artifact = run_e2e(args.telemetry, log_path=args.log, head_path=args.head, signing_key=key.encode("utf-8") if key else None, key_id=args.key_id if key else None)
        Path(args.output).write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps({"artifact": args.output, "artifact_id": artifact["artifact_id"], "marble_id": artifact["marble"]["marble_id"], "e2e_verified": artifact["e2e_verified"]}, sort_keys=True))
        return 0 if artifact["e2e_verified"] else 1

    artifact = json.loads(Path(args.artifact).read_text(encoding="utf-8"))
    result = verify_e2e_artifact(artifact)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["verified"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
