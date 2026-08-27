#!/usr/bin/env python3
"""EDEN Marble v2 reference implementation.

MARBLE-LIFE-001
Dependency-light canonical minting, verification, lineage and evidence-boundary
checks. Cryptographic integrity proves integrity of the committed record; it does
not independently prove the truth of scientific claims recorded inside it.

Marble v2 is intended to be long-lived. Optional ``assurance`` data is excluded
from the scientific event identity so signatures, timestamp/log anchors, device
attestation evidence and external reproduction records can accrue without
renaming the underlying event.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Set

try:
    from .assurance import verify_attestation_record, verify_resource_provenance, verify_timestamp_anchor
except ImportError:  # direct script execution
    from assurance import verify_attestation_record, verify_resource_provenance, verify_timestamp_anchor

SCHEMA = "eden.marble.v2"
DOMAIN = "EDEN-MARBLE-V2\x00"
KINDS = {"OBSERVATION", "DECISION", "EXECUTION", "ASSERTION", "VERIFICATION", "ACCOUNTING", "REFUTATION"}
EVIDENCE_CLASSES = {"IMPLEMENTED", "MEASURED", "SIMULATED", "MODELLED", "PROPOSED", "INDEPENDENTLY_VALIDATED"}


def canonical_bytes(value: Any) -> bytes:
    """RFC-8785-inspired deterministic JSON for the constrained Marble schema."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def committed_core(marble: Mapping[str, Any]) -> Dict[str, Any]:
    core = copy.deepcopy(dict(marble))
    for mutable_envelope in ("marble_id", "signature", "verification", "assurance"):
        core.pop(mutable_envelope, None)
    return core


def compute_id(marble: Mapping[str, Any]) -> str:
    digest = hashlib.sha256(DOMAIN.encode("utf-8") + canonical_bytes(committed_core(marble))).hexdigest()
    return f"sha256:{digest}"


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def mint(core: Mapping[str, Any]) -> Dict[str, Any]:
    m = copy.deepcopy(dict(core))
    m.setdefault("schema", SCHEMA)
    m.setdefault("timestamp", utcnow())
    validate_structure(m, require_id=False)
    m["marble_id"] = compute_id(m)
    return m


def _require(obj: Mapping[str, Any], names: Iterable[str], where: str = "marble") -> None:
    missing = [n for n in names if n not in obj]
    if missing:
        raise ValueError(f"{where}: missing required fields: {', '.join(missing)}")


def validate_structure(m: Mapping[str, Any], require_id: bool = True) -> None:
    required = ["schema", "kind", "subject", "parents", "actor", "policy", "input", "output", "resources", "quality", "evidence", "truth", "provenance", "timestamp"]
    if require_id:
        required.append("marble_id")
    _require(m, required)
    if m["schema"] != SCHEMA:
        raise ValueError("unexpected schema")
    if m["kind"] not in KINDS:
        raise ValueError("invalid kind")
    if not isinstance(m["parents"], list) or not all(isinstance(x, str) and x.startswith("sha256:") for x in m["parents"]):
        raise ValueError("parents must be sha256 identifiers")
    if not isinstance(m["resources"], dict):
        raise ValueError("resources must be an object")
    if not isinstance(m["evidence"], dict):
        raise ValueError("evidence must be an object")
    ev_class = m["evidence"].get("class")
    if ev_class not in EVIDENCE_CLASSES:
        raise ValueError("invalid evidence class")
    if not isinstance(m["truth"], dict):
        raise ValueError("truth must be an object")
    if not isinstance(m["truth"].get("claims", []), list) or not isinstance(m["truth"].get("not_claimed", []), list):
        raise ValueError("truth claims must be arrays")
    if m["kind"] == "REFUTATION" and not m["subject"].get("target_marble_id"):
        raise ValueError("refutation requires subject.target_marble_id")
    if "assurance" in m and not isinstance(m["assurance"], dict):
        raise ValueError("assurance must be an object")


def verify_integrity(m: Mapping[str, Any]) -> Dict[str, Any]:
    checks: Dict[str, Any] = {
        "schema": SCHEMA,
        "structurally_valid": False,
        "integrity_verified": False,
        "provenance_verified": False,
        "policy_verified": False,
        "evidence_verified": False,
        "resource_provenance_verified": False,
        "timestamp_anchor_verified": False,
        "attestation": "UNATTESTED",
        "independent_replication": "NOT_PERFORMED",
        "errors": [],
    }
    try:
        validate_structure(m, require_id=True)
        checks["structurally_valid"] = True
    except Exception as exc:
        checks["errors"].append(str(exc))
        return checks

    expected = compute_id(m)
    if m.get("marble_id") != expected:
        checks["errors"].append("marble_id mismatch")
        return checks
    checks["integrity_verified"] = True

    provenance = m.get("provenance", {})
    seq = provenance.get("sequence")
    if isinstance(seq, int) and seq >= 0:
        checks["provenance_verified"] = True
    else:
        checks["errors"].append("invalid provenance sequence")

    policy = m.get("policy", {})
    if policy.get("policy_id") and policy.get("policy_hash"):
        checks["policy_verified"] = True
    else:
        checks["errors"].append("policy commitment incomplete")

    evidence = m.get("evidence", {})
    ev_class = evidence.get("class")
    instrumentation = evidence.get("instrumentation", [])
    if ev_class == "MEASURED":
        if isinstance(instrumentation, list) and len(instrumentation) > 0:
            checks["evidence_verified"] = True
        else:
            checks["errors"].append("MEASURED evidence lacks instrumentation")
    elif ev_class == "INDEPENDENTLY_VALIDATED":
        ref = evidence.get("independent_reproduction")
        if ref:
            checks["evidence_verified"] = True
            checks["independent_replication"] = "RECORDED"
        else:
            checks["errors"].append("independent validation lacks reproduction reference")
    else:
        checks["evidence_verified"] = True

    rp = verify_resource_provenance(m.get("resources", {}), evidence)
    checks["resource_provenance_verified"] = rp["resource_provenance_verified"]
    checks["verified_resources"] = rp["verified_resources"]
    checks["unproven_resources"] = rp["unproven_resources"]
    # Resource provenance is reported separately so old v2 Marbles remain valid;
    # assurance profiles may require it before accepting resource claims.

    assurance = m.get("assurance", {})
    timestamp_anchor = assurance.get("timestamp_anchor") if isinstance(assurance, dict) else None
    if isinstance(timestamp_anchor, dict):
        tv = verify_timestamp_anchor(str(m["marble_id"]), timestamp_anchor)
        checks["timestamp_anchor_verified"] = tv["timestamp_anchor_verified"]
        checks["timestamp_trust"] = tv["trust"]
        checks["errors"].extend(tv["errors"])

    att = assurance.get("attestation") if isinstance(assurance, dict) else None
    if att is None:
        att = m.get("actor", {}).get("attestation")
    if isinstance(att, dict):
        av = verify_attestation_record(att)
        checks["attestation"] = av["assurance"]
        if not av["attestation_verified"]:
            checks["errors"].extend(av["errors"])
    elif isinstance(att, str):
        checks["attestation"] = att
    return checks


def verify_lineage(marbles: Iterable[Mapping[str, Any]]) -> Dict[str, Any]:
    items = list(marbles)
    by_id = {m.get("marble_id"): m for m in items if m.get("marble_id")}
    errors: List[str] = []
    for m in items:
        mid = m.get("marble_id", "<missing>")
        for parent in m.get("parents", []):
            if parent not in by_id:
                errors.append(f"{mid}: missing parent {parent}")

    visiting: Set[str] = set()
    visited: Set[str] = set()

    def dfs(mid: str) -> None:
        if mid in visiting:
            errors.append(f"cycle detected at {mid}")
            return
        if mid in visited or mid not in by_id:
            return
        visiting.add(mid)
        for parent in by_id[mid].get("parents", []):
            dfs(parent)
        visiting.remove(mid)
        visited.add(mid)

    for mid in list(by_id):
        dfs(mid)
    return {"lineage_verified": len(errors) == 0, "marbles": len(items), "errors": errors}


def verify_crv(allocation: Mapping[str, Any], observed: Mapping[str, Any]) -> Dict[str, Any]:
    violations = []
    for key, limit in allocation.items():
        actual = observed.get(key)
        if limit is None or actual is None:
            continue
        if not isinstance(limit, (int, float)) or not isinstance(actual, (int, float)):
            violations.append({"resource": key, "reason": "non-numeric"})
        elif actual > limit:
            violations.append({"resource": key, "limit": limit, "observed": actual})
    return {"within_delegation": not violations, "violations": violations}


def assurance_profile(m: Mapping[str, Any], verification: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    """Summarise v2 assurance without collapsing distinct guarantees into VALID."""
    v = dict(verification or verify_integrity(m))
    return {
        "profile": "eden.marble.v2.assurance",
        "marble_id": m.get("marble_id"),
        "event_integrity": "VERIFIED" if v.get("integrity_verified") else "UNVERIFIED",
        "lineage_state": "LOCAL_SEQUENCE_VERIFIED" if v.get("provenance_verified") else "UNVERIFIED",
        "policy_state": "COMMITMENT_RECORDED" if v.get("policy_verified") else "UNVERIFIED",
        "evidence_state": "VERIFIED_TO_RECORDED_CLASS" if v.get("evidence_verified") else "UNVERIFIED",
        "resource_measurement_state": "PROVENANCE_COMPLETE" if v.get("resource_provenance_verified") else "PARTIAL_OR_UNPROVEN",
        "timestamp_state": v.get("timestamp_trust", "NOT_ANCHORED"),
        "attestation_state": v.get("attestation", "UNATTESTED"),
        "independent_replication": v.get("independent_replication", "NOT_PERFORMED"),
        "scientific_truth_implied": False,
    }


def load_json(path: str) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main() -> int:
    p = argparse.ArgumentParser(description="EDEN Marble v2 reference tool")
    sub = p.add_subparsers(dest="cmd", required=True)
    pm = sub.add_parser("mint")
    pm.add_argument("input")
    pv = sub.add_parser("verify")
    pv.add_argument("input")
    pa = sub.add_parser("assurance")
    pa.add_argument("input")
    pl = sub.add_parser("lineage")
    pl.add_argument("inputs", nargs="+")
    args = p.parse_args()

    if args.cmd == "mint":
        print(json.dumps(mint(load_json(args.input)), indent=2, sort_keys=True))
        return 0
    if args.cmd == "verify":
        result = verify_integrity(load_json(args.input))
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result["integrity_verified"] else 1
    if args.cmd == "assurance":
        m = load_json(args.input)
        print(json.dumps(assurance_profile(m), indent=2, sort_keys=True))
        return 0
    result = verify_lineage(load_json(x) for x in args.inputs)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["lineage_verified"] else 1


if __name__ == "__main__":
    sys.exit(main())
