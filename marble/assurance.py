#!/usr/bin/env python3
"""Assurance primitives for EDEN Marble v2.

This module deliberately keeps the schema at ``eden.marble.v2`` while adding
optional assurance envelopes. It provides software-verifiable signatures,
append-only transparency-log chaining, persistent provenance-head state,
resource measurement provenance, and attestation/timestamp verification hooks.

Important truth boundary: software verification of an attestation/timestamp
record does not by itself prove hardware-backed identity or trusted third-party
time. Those stronger states require an external verifier/authority reference.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional

SIGN_DOMAIN = b"EDEN-MARBLE-V2-SIGN\x00"
LOG_DOMAIN = b"EDEN-MARBLE-V2-LOG\x00"
HEAD_DOMAIN = b"EDEN-MARBLE-V2-HEAD\x00"


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_id(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def signature_payload(marble_id: str) -> bytes:
    return SIGN_DOMAIN + marble_id.encode("utf-8")


def sign_hmac(marble_id: str, key: bytes, key_id: str, *, signed_at: Optional[str] = None) -> Dict[str, Any]:
    if not key or not key_id:
        raise ValueError("non-empty key and key_id required")
    mac = hmac.new(key, signature_payload(marble_id), hashlib.sha256).hexdigest()
    return {
        "scheme": "HMAC-SHA256",
        "key_id": key_id,
        "signed_at": signed_at or utcnow(),
        "signature": mac,
        "scope": "marble_id",
    }


def verify_hmac(marble_id: str, envelope: Mapping[str, Any], keyring: Mapping[str, bytes]) -> Dict[str, Any]:
    result = {"signature_verified": False, "errors": []}
    if envelope.get("scheme") != "HMAC-SHA256" or envelope.get("scope") != "marble_id":
        result["errors"].append("unsupported signature envelope")
        return result
    key_id = envelope.get("key_id")
    if key_id not in keyring:
        result["errors"].append("unknown key_id")
        return result
    expected = hmac.new(keyring[key_id], signature_payload(marble_id), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(str(envelope.get("signature", "")), expected):
        result["errors"].append("signature mismatch")
        return result
    result["signature_verified"] = True
    return result


def make_timestamp_anchor(marble_id: str, *, authority: str = "LOCAL_SOFTWARE", external_ref: Optional[str] = None, at: Optional[str] = None) -> Dict[str, Any]:
    observed_at = at or utcnow()
    token = sha256_id(canonical_bytes({"marble_id": marble_id, "observed_at": observed_at, "authority": authority, "external_ref": external_ref}))
    return {
        "authority": authority,
        "observed_at": observed_at,
        "external_ref": external_ref,
        "token": token,
    }


def verify_timestamp_anchor(marble_id: str, anchor: Mapping[str, Any]) -> Dict[str, Any]:
    result = {"timestamp_anchor_verified": False, "trust": "LOCAL_ONLY", "errors": []}
    required = ["authority", "observed_at", "token"]
    if any(not anchor.get(k) for k in required):
        result["errors"].append("timestamp anchor incomplete")
        return result
    expected = make_timestamp_anchor(
        marble_id,
        authority=str(anchor["authority"]),
        external_ref=anchor.get("external_ref"),
        at=str(anchor["observed_at"]),
    )["token"]
    if expected != anchor.get("token"):
        result["errors"].append("timestamp token mismatch")
        return result
    result["timestamp_anchor_verified"] = True
    if anchor.get("external_ref") and anchor.get("authority") != "LOCAL_SOFTWARE":
        result["trust"] = "EXTERNAL_REFERENCE_RECORDED"
    return result


def make_attestation_record(*, subject: str, credential_hash: str, verifier: str = "LOCAL_SOFTWARE", evidence_ref: Optional[str] = None, hardware_backed: bool = False) -> Dict[str, Any]:
    return {
        "subject": subject,
        "credential_hash": credential_hash,
        "verifier": verifier,
        "evidence_ref": evidence_ref,
        "hardware_backed": bool(hardware_backed),
        "verified": True,
    }


def verify_attestation_record(record: Mapping[str, Any]) -> Dict[str, Any]:
    result = {"attestation_verified": False, "assurance": "UNATTESTED", "errors": []}
    if record.get("verified") is not True or not record.get("subject") or not record.get("credential_hash") or not record.get("verifier"):
        result["errors"].append("attestation record incomplete")
        return result
    result["attestation_verified"] = True
    if record.get("hardware_backed") is True:
        if record.get("evidence_ref") and record.get("verifier") != "LOCAL_SOFTWARE":
            result["assurance"] = "HARDWARE_ATTESTATION_REFERENCE_RECORDED"
        else:
            result["assurance"] = "HARDWARE_CLAIM_UNVERIFIED"
            result["errors"].append("hardware-backed claim lacks external verifier evidence")
    else:
        result["assurance"] = "SOFTWARE_CREDENTIAL_VERIFIED"
    return result


def measurement_digest(measurement: Mapping[str, Any]) -> str:
    return sha256_id(canonical_bytes(dict(measurement)))


def verify_resource_provenance(resources: Mapping[str, Any], evidence: Mapping[str, Any]) -> Dict[str, Any]:
    result = {"resource_provenance_verified": True, "verified_resources": [], "unproven_resources": [], "errors": []}
    provenance = evidence.get("resource_provenance", {})
    if not isinstance(provenance, dict):
        provenance = {}
    for name, value in resources.items():
        if value is None:
            continue
        p = provenance.get(name)
        if not isinstance(p, dict):
            result["unproven_resources"].append(name)
            continue
        if not p.get("instrument") or not p.get("measurement_ref"):
            result["unproven_resources"].append(name)
            continue
        result["verified_resources"].append(name)
    if result["unproven_resources"]:
        result["resource_provenance_verified"] = False
        result["errors"].append("non-null resource values lack measurement provenance")
    return result


def _entry_payload(index: int, marble_id: str, previous_entry_hash: Optional[str], timestamp: str) -> Dict[str, Any]:
    return {"index": index, "marble_id": marble_id, "previous_entry_hash": previous_entry_hash, "timestamp": timestamp}


def make_log_entry(index: int, marble_id: str, previous_entry_hash: Optional[str], *, timestamp: Optional[str] = None) -> Dict[str, Any]:
    payload = _entry_payload(index, marble_id, previous_entry_hash, timestamp or utcnow())
    entry_hash = sha256_id(LOG_DOMAIN + canonical_bytes(payload))
    return {**payload, "entry_hash": entry_hash}


def verify_log(entries: Iterable[Mapping[str, Any]]) -> Dict[str, Any]:
    items = list(entries)
    errors = []
    previous = None
    for expected_index, entry in enumerate(items):
        if entry.get("index") != expected_index:
            errors.append(f"entry {expected_index}: index mismatch")
        if entry.get("previous_entry_hash") != previous:
            errors.append(f"entry {expected_index}: previous hash mismatch")
        payload = _entry_payload(expected_index, str(entry.get("marble_id")), previous, str(entry.get("timestamp")))
        expected_hash = sha256_id(LOG_DOMAIN + canonical_bytes(payload))
        if entry.get("entry_hash") != expected_hash:
            errors.append(f"entry {expected_index}: entry hash mismatch")
        previous = entry.get("entry_hash")
    return {"transparency_log_verified": not errors, "entries": len(items), "head": previous, "errors": errors}


def append_log(path: str, marble_id: str) -> Dict[str, Any]:
    p = Path(path)
    entries = []
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            if line.strip():
                entries.append(json.loads(line))
        check = verify_log(entries)
        if not check["transparency_log_verified"]:
            raise ValueError("existing transparency log is corrupt")
    previous = entries[-1]["entry_hash"] if entries else None
    entry = make_log_entry(len(entries), marble_id, previous)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, sort_keys=True, separators=(",", ":")) + "\n")
        fh.flush()
        os.fsync(fh.fileno())
    return entry


def provenance_head_record(marble_id: str, sequence: int, previous_head: Optional[str]) -> Dict[str, Any]:
    payload = {"marble_id": marble_id, "sequence": sequence, "previous_head": previous_head}
    return {**payload, "head_hash": sha256_id(HEAD_DOMAIN + canonical_bytes(payload))}


def load_head(path: str) -> Optional[Dict[str, Any]]:
    p = Path(path)
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ValueError("provenance head is corrupt") from exc
    payload = {"marble_id": data.get("marble_id"), "sequence": data.get("sequence"), "previous_head": data.get("previous_head")}
    if data.get("head_hash") != sha256_id(HEAD_DOMAIN + canonical_bytes(payload)):
        raise ValueError("provenance head hash mismatch")
    return data


def persist_head(path: str, marble_id: str, sequence: int) -> Dict[str, Any]:
    current = load_head(path)
    if current is not None and sequence <= int(current["sequence"]):
        raise ValueError("provenance sequence must increase")
    record = provenance_head_record(marble_id, sequence, current.get("head_hash") if current else None)
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=p.name + ".", dir=str(p.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(record, fh, sort_keys=True, separators=(",", ":"))
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_name, p)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)
    return record


def verifier_bundle(marble: Mapping[str, Any]) -> Dict[str, Any]:
    """Portable data-only envelope for independently implemented verifiers."""
    return {
        "profile": "eden.marble.v2.independent-verifier",
        "schema": marble.get("schema"),
        "marble_id": marble.get("marble_id"),
        "canonicalization": "UTF-8 JSON; sort_keys; separators=(',', ':'); no NaN",
        "identity_domain": "EDEN-MARBLE-V2\\x00",
        "hash": "SHA-256",
        "committed_core_excludes": ["marble_id", "signature", "verification", "assurance"],
        "marble": dict(marble),
    }
