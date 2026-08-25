#!/usr/bin/env python3
"""EDEN Manifold ingress encryptor.

Reads newline-delimited plaintext bytes from stdin and emits AES-256-GCM frames.
Protocol v2 cryptographically binds the declared source, session, sequence,
protocol version, manifold identifier, and algorithm into AEAD associated data.

The source label is authenticated as sender-supplied metadata. Authentication of
that label does not independently establish the real-world device identity.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import uuid

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

MANIFOLD = "EDEN-MANIFOLD-NI-001"
PROTOCOL_VERSION = 2
ALGORITHM = "AES-256-GCM"


def canonical(obj: object) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")


def build_aad(*, source: str, session_id: str, sequence: int) -> bytes:
    """Return canonical authenticated metadata for a Manifold v2 frame."""
    if not source:
        raise ValueError("source must be non-empty")
    if not session_id:
        raise ValueError("session_id must be non-empty")
    if not isinstance(sequence, int) or isinstance(sequence, bool) or sequence < 0:
        raise ValueError("sequence must be a non-negative integer")
    return canonical(
        {
            "alg": ALGORITHM,
            "manifold": MANIFOLD,
            "protocol_version": PROTOCOL_VERSION,
            "sequence": sequence,
            "session_id": session_id,
            "source": source,
        }
    )


def load_key(path: str) -> bytes:
    raw = open(path, "rb").read().strip()
    try:
        key = base64.b64decode(raw, validate=True)
    except Exception:
        key = raw
    if len(key) != 32:
        raise SystemExit("Manifold key must be exactly 32 bytes (raw) or base64-encoded 32 bytes.")
    return key


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--key-file", required=True)
    ap.add_argument("--source", default="external-source")
    ap.add_argument(
        "--session-id",
        default=None,
        help="Authenticated session identifier. Defaults to a fresh random UUID.",
    )
    ap.add_argument(
        "--start-sequence",
        type=int,
        default=0,
        help="First authenticated sequence number emitted in this process.",
    )
    args = ap.parse_args()

    session_id = args.session_id or str(uuid.uuid4())
    if args.start_sequence < 0:
        raise SystemExit("--start-sequence must be non-negative")

    aes = AESGCM(load_key(args.key_file))
    sequence = args.start_sequence

    for raw in sys.stdin.buffer:
        raw = raw.rstrip(b"\r\n")
        if not raw:
            continue

        aad = build_aad(source=args.source, session_id=session_id, sequence=sequence)
        nonce = os.urandom(12)
        ciphertext = aes.encrypt(nonce, raw, aad)
        frame = {
            "manifold": MANIFOLD,
            "version": PROTOCOL_VERSION,
            "source": args.source,
            "session_id": session_id,
            "sequence": sequence,
            "alg": ALGORITHM,
            "aad_b64": base64.b64encode(aad).decode("ascii"),
            "nonce_b64": base64.b64encode(nonce).decode("ascii"),
            "ciphertext_b64": base64.b64encode(ciphertext).decode("ascii"),
        }
        print(json.dumps(frame, separators=(",", ":")), flush=True)
        sequence += 1


if __name__ == "__main__":
    main()
