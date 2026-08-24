#!/usr/bin/env python3
"""EDEN Manifold ingress encryptor.

Reads newline-delimited plaintext bytes from stdin and emits authenticated
AES-256-GCM frames. This is intended to run at the data source or as close to it
as possible, before transport to the EDEN observation stack.
"""
import argparse, base64, json, os, sys
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
    ap.add_argument("--source", default="external-source")
    args = ap.parse_args()
    aes = AESGCM(load_key(args.key_file))

    for raw in sys.stdin.buffer:
        raw = raw.rstrip(b"\r\n")
        if not raw:
            continue
        nonce = os.urandom(12)
        ct = aes.encrypt(nonce, raw, AAD)
        frame = {
            "manifold": "EDEN-MANIFOLD-NI-001",
            "version": 1,
            "source": args.source,
            "alg": "AES-256-GCM",
            "aad_b64": base64.b64encode(AAD).decode(),
            "nonce_b64": base64.b64encode(nonce).decode(),
            "ciphertext_b64": base64.b64encode(ct).decode(),
        }
        print(json.dumps(frame, separators=(",", ":")), flush=True)


if __name__ == "__main__":
    main()
