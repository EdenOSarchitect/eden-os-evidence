#!/usr/bin/env python3
"""Operational assurance CLI for EDEN Marble v2."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

try:
    from .assurance import (
        append_log, load_head, make_timestamp_anchor, persist_head, sign_hmac,
        verifier_bundle, verify_hmac, verify_log,
    )
except ImportError:
    from assurance import (
        append_log, load_head, make_timestamp_anchor, persist_head, sign_hmac,
        verifier_bundle, verify_hmac, verify_log,
    )


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def dump(value):
    print(json.dumps(value, indent=2, sort_keys=True))


def secret_from_env(name: str) -> bytes:
    value = os.environ.get(name)
    if not value:
        raise SystemExit(f"missing secret environment variable: {name}")
    return value.encode("utf-8")


def main() -> int:
    p = argparse.ArgumentParser(description="EDEN Marble v2 assurance operations")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("sign")
    s.add_argument("marble")
    s.add_argument("--key-id", required=True)
    s.add_argument("--key-env", default="EDEN_MARBLE_SIGNING_KEY")

    vs = sub.add_parser("verify-signature")
    vs.add_argument("marble")
    vs.add_argument("signature")
    vs.add_argument("--key-id", required=True)
    vs.add_argument("--key-env", default="EDEN_MARBLE_SIGNING_KEY")

    a = sub.add_parser("timestamp-anchor")
    a.add_argument("marble")
    a.add_argument("--authority", default="LOCAL_SOFTWARE")
    a.add_argument("--external-ref")

    la = sub.add_parser("log-append")
    la.add_argument("marble")
    la.add_argument("log")

    lv = sub.add_parser("log-verify")
    lv.add_argument("log")

    ph = sub.add_parser("head-update")
    ph.add_argument("marble")
    ph.add_argument("head")

    hs = sub.add_parser("head-show")
    hs.add_argument("head")

    b = sub.add_parser("bundle")
    b.add_argument("marble")

    args = p.parse_args()

    if args.cmd == "sign":
        m = load(args.marble)
        dump(sign_hmac(m["marble_id"], secret_from_env(args.key_env), args.key_id))
        return 0
    if args.cmd == "verify-signature":
        m, sig = load(args.marble), load(args.signature)
        result = verify_hmac(m["marble_id"], sig, {args.key_id: secret_from_env(args.key_env)})
        dump(result)
        return 0 if result["signature_verified"] else 1
    if args.cmd == "timestamp-anchor":
        m = load(args.marble)
        dump(make_timestamp_anchor(m["marble_id"], authority=args.authority, external_ref=args.external_ref))
        return 0
    if args.cmd == "log-append":
        m = load(args.marble)
        dump(append_log(args.log, m["marble_id"]))
        return 0
    if args.cmd == "log-verify":
        entries = [json.loads(line) for line in Path(args.log).read_text(encoding="utf-8").splitlines() if line.strip()]
        result = verify_log(entries)
        dump(result)
        return 0 if result["transparency_log_verified"] else 1
    if args.cmd == "head-update":
        m = load(args.marble)
        sequence = int(m.get("provenance", {}).get("sequence"))
        dump(persist_head(args.head, m["marble_id"], sequence))
        return 0
    if args.cmd == "head-show":
        dump(load_head(args.head))
        return 0
    if args.cmd == "bundle":
        dump(verifier_bundle(load(args.marble)))
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
