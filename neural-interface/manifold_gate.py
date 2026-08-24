#!/usr/bin/env python3
"""EDEN Manifold authenticated decrypt gate.

Accepts newline-delimited AES-256-GCM Manifold frames on stdin, verifies and
decrypts them, then emits a local trusted handoff envelope for open_connector.py.
No unauthenticated frame is forwarded.
"""
import argparse, base64, hashlib, json, sys
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

AAD = b"EDEN-MANIFOLD-NI-v1"


def load_key(path: str) -> bytes:
    raw = open(path, "rb").read().strip()
    try:
        key = base64.b64decode(raw, validate=True)
    except Exception:
        key = raw
    if len(key) != 32:
        raise SystemExit("Manifold key must be exactly 32 bytes (raw) or base64-encoded 32 bytes.")
    return key


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--key-file", required=True)
    args = ap.parse_args()
    aes = AESGCM(load_key(args.key_file))

    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            frame = json.loads(line)
            if frame.get("manifold") != "EDEN-MANIFOLD-NI-001" or frame.get("alg") != "AES-256-GCM":
                raise ValueError("unsupported manifold frame")
            if base64.b64decode(frame["aad_b64"]) != AAD:
                raise ValueError("AAD mismatch")
            nonce = base64.b64decode(frame["nonce_b64"])
            ct = base64.b64decode(frame["ciphertext_b64"])
            raw = aes.decrypt(nonce, ct, AAD)
            handoff = {
                "manifold_verified": True,
                "manifold": "EDEN-MANIFOLD-NI-001",
                "source": frame.get("source", "unknown"),
                "payload_sha256": hashlib.sha256(raw).hexdigest(),
                "payload_b64": base64.b64encode(raw).decode(),
            }
            print(json.dumps(handoff, separators=(",", ":")), flush=True)
        except (KeyError, ValueError, json.JSONDecodeError, InvalidTag) as e:
            print(json.dumps({"manifold_verified": False, "error": type(e).__name__}), file=sys.stderr, flush=True)


if __name__ == "__main__":
    main()
