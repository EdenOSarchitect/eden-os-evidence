#!/usr/bin/env python3
"""EDEN Manifold authenticated decrypt gate with ingestion Marble minting.

Accepts newline-delimited AES-256-GCM Manifold v2 frames on stdin, verifies that
source/session/sequence/version metadata is cryptographically bound into AEAD,
rejects replayed/out-of-order frames, fails closed on provenance-chain damage,
mints a provenance Marble for every successful ingestion, and emits a trusted
local handoff for open_connector.py.

The Marble stores hashes/metadata only; plaintext is not embedded in the Marble.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

MANIFOLD = "EDEN-MANIFOLD-NI-001"
PROTOCOL_VERSION = 2
ALGORITHM = "AES-256-GCM"


class EvidenceStateError(RuntimeError):
    """Raised when local provenance/replay state cannot be trusted."""


def canonical(obj: object) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")


def build_aad(*, source: str, session_id: str, sequence: int) -> bytes:
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


def decode_b64(value: Any, field: str) -> bytes:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be base64 text")
    try:
        return base64.b64decode(value, validate=True)
    except Exception as exc:
        raise ValueError(f"invalid base64 in {field}") from exc


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


def valid_sha256(value: Any) -> bool:
    if not isinstance(value, str) or len(value) != 64:
        return False
    try:
        int(value, 16)
    except ValueError:
        return False
    return True


def last_logged_marble_sha(log_path: str) -> str | None:
    path = Path(log_path)
    if not path.exists():
        return None
    last = None
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                last = line
    if last is None:
        return None
    try:
        obj = json.loads(last)
        value = obj["marble_sha256"]
    except Exception as exc:
        raise EvidenceStateError("Marble log tail is unreadable; refusing to continue chain") from exc
    if not valid_sha256(value):
        raise EvidenceStateError("Marble log tail has invalid marble_sha256")
    return value


def load_prev(head_path: str, log_path: str) -> str | None:
    """Load and cross-check chain head; any ambiguous state fails closed."""
    head = Path(head_path)
    log_tail = last_logged_marble_sha(log_path)

    if not head.exists():
        if log_tail is not None:
            raise EvidenceStateError("Marble head missing while log contains evidence")
        return None

    try:
        obj = json.loads(head.read_text(encoding="utf-8"))
        value = obj["marble_sha256"]
    except Exception as exc:
        raise EvidenceStateError("Marble head is unreadable; refusing to start a new chain") from exc

    if not valid_sha256(value):
        raise EvidenceStateError("Marble head has invalid marble_sha256")
    if log_tail is None:
        raise EvidenceStateError("Marble head exists but Marble log is empty/missing")
    if not hmac.compare_digest(value, log_tail):
        raise EvidenceStateError("Marble head does not match Marble log tail")
    return value


def load_replay_state(path: str) -> dict[str, int]:
    p = Path(path)
    if not p.exists():
        return {}
    try:
        obj = json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:
        raise EvidenceStateError("Replay state is unreadable; refusing untracked ingestion") from exc
    if not isinstance(obj, dict):
        raise EvidenceStateError("Replay state must be a JSON object")
    out: dict[str, int] = {}
    for key, value in obj.items():
        if not isinstance(key, str) or not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise EvidenceStateError("Replay state contains invalid entry")
        out[key] = value
    return out


def replay_key(source: str, session_id: str) -> str:
    return hashlib.sha256(canonical({"source": source, "session_id": session_id})).hexdigest()


def assert_fresh_sequence(state: dict[str, int], source: str, session_id: str, sequence: int) -> str:
    key = replay_key(source, session_id)
    previous = state.get(key)
    if previous is not None and sequence <= previous:
        raise ValueError("replay_or_out_of_order_sequence")
    return key


def atomic_write_json(path: str, obj: object) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(obj, handle, sort_keys=True)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


def mint_marble(
    frame: dict[str, Any], raw: bytes, keyid: str, prev_sha: str | None, aad: bytes
) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    ct = decode_b64(frame["ciphertext_b64"], "ciphertext_b64")
    nonce = decode_b64(frame["nonce_b64"], "nonce_b64")
    core = {
        "marble_version": "1.1",
        "marble_type": "MANIFOLD_INGESTION",
        "manifold": MANIFOLD,
        "protocol_version": PROTOCOL_VERSION,
        "timestamp_utc": now,
        "authenticated_metadata": {
            "source_label": frame["source"],
            "session_id": frame["session_id"],
            "sequence": frame["sequence"],
        },
        "crypto": {
            "algorithm": ALGORITHM,
            "key_id": keyid,
            "aad_sha256": hashlib.sha256(aad).hexdigest(),
            "nonce_sha256": hashlib.sha256(nonce).hexdigest(),
            "ciphertext_sha256": hashlib.sha256(ct).hexdigest(),
            "authentication": "VERIFIED",
        },
        "ingestion": {
            "plaintext_sha256": hashlib.sha256(raw).hexdigest(),
            "plaintext_bytes": len(raw),
            "plaintext_stored_in_marble": False,
        },
        "chain": {"prev_marble_sha256": prev_sha},
        "evidence_class": "OBSERVED_INPUT",
        "truth_boundary": (
            "This Marble proves successful authentication/decryption of the supplied Manifold v2 frame "
            "under the configured local key and cryptographically binds the sender-supplied source label, "
            "session and sequence to the payload. It does not independently prove the real-world device/vendor "
            "identity or physiological meaning of the payload."
        ),
    }
    marble_sha = hashlib.sha256(canonical(core)).hexdigest()
    marble = dict(core)
    marble["marble_id"] = "EDEN-MANIFOLD-MARBLE-" + marble_sha[:20]
    marble["marble_sha256"] = marble_sha
    return marble


def append_marble(path: str, marble: dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(marble, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def write_head(path: str, marble: dict[str, Any]) -> None:
    atomic_write_json(path, {"marble_id": marble["marble_id"], "marble_sha256": marble["marble_sha256"]})


def verify_frame(frame: dict[str, Any], aes: AESGCM, replay_state: dict[str, int]) -> tuple[bytes, bytes, str]:
    if frame.get("manifold") != MANIFOLD:
        raise ValueError("unsupported manifold frame")
    if frame.get("alg") != ALGORITHM:
        raise ValueError("unsupported algorithm")
    if frame.get("version") != PROTOCOL_VERSION:
        raise ValueError("unsupported protocol version")

    source = frame.get("source")
    session_id = frame.get("session_id")
    sequence = frame.get("sequence")
    expected_aad = build_aad(source=source, session_id=session_id, sequence=sequence)
    supplied_aad = decode_b64(frame.get("aad_b64"), "aad_b64")
    if not hmac.compare_digest(supplied_aad, expected_aad):
        raise ValueError("authenticated metadata mismatch")

    nonce = decode_b64(frame.get("nonce_b64"), "nonce_b64")
    if len(nonce) != 12:
        raise ValueError("AES-GCM nonce must be 12 bytes")
    ciphertext = decode_b64(frame.get("ciphertext_b64"), "ciphertext_b64")

    # Authenticate/decrypt before consulting replay freshness so malformed tags do
    # not mutate any state or disclose acceptance of forged metadata.
    raw = aes.decrypt(nonce, ciphertext, expected_aad)
    key = assert_fresh_sequence(replay_state, source, session_id, sequence)
    return raw, expected_aad, key


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--key-file", required=True)
    ap.add_argument("--marble-log", default="neural-interface/results/manifold_ingestion_marbles.jsonl")
    ap.add_argument("--head-file", default="neural-interface/results/manifold_head.json")
    ap.add_argument("--replay-state", default="neural-interface/results/manifold_replay_state.json")
    args = ap.parse_args()

    key = load_key(args.key_file)
    aes = AESGCM(key)
    kid = key_id(key)

    try:
        prev_sha = load_prev(args.head_file, args.marble_log)
        replay_state = load_replay_state(args.replay_state)
    except EvidenceStateError as exc:
        print(json.dumps({"manifold_verified": False, "error": "EvidenceStateError", "detail": str(exc)}), file=sys.stderr)
        raise SystemExit(2)

    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            parsed = json.loads(line)
            if not isinstance(parsed, dict):
                raise ValueError("frame must be a JSON object")
            frame: dict[str, Any] = parsed
            raw, aad, state_key = verify_frame(frame, aes, replay_state)

            marble = mint_marble(frame, raw, kid, prev_sha, aad)
            append_marble(args.marble_log, marble)
            write_head(args.head_file, marble)

            # Persist replay acceptance only after the evidence chain has been
            # durably advanced. A crash can fail closed rather than silently
            # accepting an untracked replay.
            replay_state[state_key] = frame["sequence"]
            atomic_write_json(args.replay_state, replay_state)
            prev_sha = marble["marble_sha256"]

            handoff = {
                "manifold_verified": True,
                "manifold": MANIFOLD,
                "protocol_version": PROTOCOL_VERSION,
                "source": frame["source"],
                "session_id": frame["session_id"],
                "sequence": frame["sequence"],
                "payload_sha256": hashlib.sha256(raw).hexdigest(),
                "payload_b64": base64.b64encode(raw).decode("ascii"),
                "ingestion_marble_id": marble["marble_id"],
                "ingestion_marble_sha256": marble["marble_sha256"],
            }
            print(json.dumps(handoff, separators=(",", ":")), flush=True)
        except (KeyError, TypeError, ValueError, json.JSONDecodeError, InvalidTag) as exc:
            print(
                json.dumps({"manifold_verified": False, "error": type(exc).__name__, "detail": str(exc)}),
                file=sys.stderr,
                flush=True,
            )


if __name__ == "__main__":
    main()
