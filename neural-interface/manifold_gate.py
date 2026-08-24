#!/usr/bin/env python3
"""EDEN Manifold authenticated decrypt gate with ingestion Marble minting.

Accepts newline-delimited AES-256-GCM Manifold frames on stdin, authenticates and
decrypts them locally, mints a provenance Marble for every successful ingestion,
and emits a trusted local handoff for open_connector.py.

The Marble stores hashes/metadata only; plaintext is not embedded in the Marble.
"""
import argparse, base64, hashlib, json, os, sys
from datetime import datetime, timezone
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

AAD = b"EDEN-MANIFOLD-NI-v1"
MANIFOLD = "EDEN-MANIFOLD-NI-001"


def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()


def load_key(path: str) -> bytes:
    raw = open(path, "rb").read().strip()
    try:
        key = base64.b64decode(raw, validate=True)
    except Exception:
        key = raw
    if len(key) != 32:
        raise SystemExit("Manifold key must be exactly 32 bytes (raw) or base64-encoded 32 bytes.")
    return key


def key_id(key: bytes) -> str:
    return "sha256:" + hashlib.sha256(key).hexdigest()[:16]


def load_prev(path: str):
    if not path or not os.path.exists(path):
        return None
    try:
        return json.load(open(path))["marble_sha256"]
    except Exception:
        return None


def mint_marble(frame, raw: bytes, keyid: str, prev_sha):
    now = datetime.now(timezone.utc).isoformat()
    ct = base64.b64decode(frame["ciphertext_b64"])
    nonce = base64.b64decode(frame["nonce_b64"])
    core = {
        "marble_version": "1.0",
        "marble_type": "MANIFOLD_INGESTION",
        "manifold": MANIFOLD,
        "timestamp_utc": now,
        "source_label": frame.get("source", "unknown"),
        "crypto": {
            "algorithm": "AES-256-GCM",
            "key_id": keyid,
            "aad_sha256": hashlib.sha256(AAD).hexdigest(),
            "nonce_sha256": hashlib.sha256(nonce).hexdigest(),
            "ciphertext_sha256": hashlib.sha256(ct).hexdigest(),
            "authentication": "VERIFIED"
        },
        "ingestion": {
            "plaintext_sha256": hashlib.sha256(raw).hexdigest(),
            "plaintext_bytes": len(raw),
            "plaintext_stored_in_marble": False
        },
        "chain": {"prev_marble_sha256": prev_sha},
        "evidence_class": "OBSERVED_INPUT",
        "truth_boundary": (
            "This Marble proves successful authentication/decryption of the supplied Manifold frame "
            "under the configured local key and binds hashes to the ingested bytes. It does not prove "
            "the external device/vendor identity or physiological meaning of the payload."
        )
    }
    marble_sha = hashlib.sha256(canonical(core)).hexdigest()
    marble = dict(core)
    marble["marble_id"] = "EDEN-MANIFOLD-MARBLE-" + marble_sha[:20]
    marble["marble_sha256"] = marble_sha
    return marble


def append_marble(path: str, marble: dict):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(marble, sort_keys=True) + "\n")


def write_head(path: str, marble: dict):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"marble_id": marble["marble_id"], "marble_sha256": marble["marble_sha256"]}, f)
    os.replace(tmp, path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--key-file", required=True)
    ap.add_argument("--marble-log", default="neural-interface/results/manifold_ingestion_marbles.jsonl")
    ap.add_argument("--head-file", default="neural-interface/results/manifold_head.json")
    args = ap.parse_args()

    key = load_key(args.key_file)
    aes = AESGCM(key)
    kid = key_id(key)
    prev_sha = load_prev(args.head_file)

    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            frame = json.loads(line)
            if frame.get("manifold") != MANIFOLD or frame.get("alg") != "AES-256-GCM":
                raise ValueError("unsupported manifold frame")
            if base64.b64decode(frame["aad_b64"]) != AAD:
                raise ValueError("AAD mismatch")
            nonce = base64.b64decode(frame["nonce_b64"])
            ct = base64.b64decode(frame["ciphertext_b64"])
            raw = aes.decrypt(nonce, ct, AAD)

            marble = mint_marble(frame, raw, kid, prev_sha)
            append_marble(args.marble_log, marble)
            write_head(args.head_file, marble)
            prev_sha = marble["marble_sha256"]

            handoff = {
                "manifold_verified": True,
                "manifold": MANIFOLD,
                "source": frame.get("source", "unknown"),
                "payload_sha256": hashlib.sha256(raw).hexdigest(),
                "payload_b64": base64.b64encode(raw).decode(),
                "ingestion_marble_id": marble["marble_id"],
                "ingestion_marble_sha256": marble["marble_sha256"]
            }
            print(json.dumps(handoff, separators=(",", ":")), flush=True)
        except (KeyError, ValueError, json.JSONDecodeError, InvalidTag) as e:
            print(json.dumps({"manifold_verified": False, "error": type(e).__name__}), file=sys.stderr, flush=True)


if __name__ == "__main__":
    main()
