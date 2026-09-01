#!/usr/bin/env python3
"""Independent-data-path verifier for EDEN Marble v2 identity.

This implementation intentionally does not import ``marble.marble``. It gives CI
and third parties a second implementation of the canonical identity rule so an
accidental bug in the primary verifier is less likely to self-confirm.
"""
from __future__ import annotations

import copy
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Mapping

SCHEMA = "eden.marble.v2"
DOMAIN = b"EDEN-MARBLE-V2\x00"
EXCLUDED = {"marble_id", "signature", "verification", "assurance"}


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def independent_compute_id(marble: Mapping[str, Any]) -> str:
    core = copy.deepcopy(dict(marble))
    for key in EXCLUDED:
        core.pop(key, None)
    return "sha256:" + hashlib.sha256(DOMAIN + canonical_bytes(core)).hexdigest()


def verify(marble: Mapping[str, Any]) -> dict:
    errors = []
    if marble.get("schema") != SCHEMA:
        errors.append("unexpected schema")
    expected = independent_compute_id(marble)
    if marble.get("marble_id") != expected:
        errors.append("marble_id mismatch")
    return {
        "profile": "eden.marble.v2.independent-verifier",
        "identity_verified": not errors,
        "expected_marble_id": expected,
        "errors": errors,
        "scientific_truth_implied": False,
    }


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: independent_verify.py MARBLE.json", file=sys.stderr)
        return 2
    marble = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    result = verify(marble)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["identity_verified"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
