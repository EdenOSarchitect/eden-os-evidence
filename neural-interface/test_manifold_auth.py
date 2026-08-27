#!/usr/bin/env python3
"""MANIFOLD-AUTH-001 security regression tests.

These tests verify protocol behavior only. They do not establish external neural
device identity, physiological meaning, or independent security validation.
"""
from __future__ import annotations

import base64
import importlib.util
import json
import tempfile
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

HERE = Path(__file__).resolve().parent


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


enc = load_module("manifold_encrypt", HERE / "manifold_encrypt.py")
gate = load_module("manifold_gate", HERE / "manifold_gate.py")
KEY = bytes(range(32))


def make_frame(*, source="device-A", session_id="session-001", sequence=0, payload=b"neural-bytes"):
    aes = AESGCM(KEY)
    aad = enc.build_aad(source=source, session_id=session_id, sequence=sequence)
    nonce = bytes(range(12))
    ciphertext = aes.encrypt(nonce, payload, aad)
    return {
        "manifold": enc.MANIFOLD,
        "version": enc.PROTOCOL_VERSION,
        "source": source,
        "session_id": session_id,
        "sequence": sequence,
        "alg": enc.ALGORITHM,
        "aad_b64": base64.b64encode(aad).decode("ascii"),
        "nonce_b64": base64.b64encode(nonce).decode("ascii"),
        "ciphertext_b64": base64.b64encode(ciphertext).decode("ascii"),
    }


def expect_reject(frame, state=None):
    aes = AESGCM(KEY)
    try:
        gate.verify_frame(frame, aes, state or {})
    except (ValueError, InvalidTag, TypeError, KeyError):
        return
    raise AssertionError("tampered frame was accepted")


def test_valid_frame():
    frame = make_frame()
    raw, aad, state_key = gate.verify_frame(frame, AESGCM(KEY), {})
    assert raw == b"neural-bytes"
    assert aad == enc.build_aad(source="device-A", session_id="session-001", sequence=0)
    assert isinstance(state_key, str) and len(state_key) == 64


def test_source_tamper_rejected():
    frame = make_frame()
    frame["source"] = "device-B"
    expect_reject(frame)


def test_session_tamper_rejected():
    frame = make_frame()
    frame["session_id"] = "session-evil"
    expect_reject(frame)


def test_sequence_tamper_rejected():
    frame = make_frame(sequence=5)
    frame["sequence"] = 6
    expect_reject(frame)


def test_version_tamper_rejected():
    frame = make_frame()
    frame["version"] = 1
    expect_reject(frame)


def test_aad_tamper_rejected():
    frame = make_frame()
    aad = bytearray(base64.b64decode(frame["aad_b64"]))
    aad[-1] ^= 1
    frame["aad_b64"] = base64.b64encode(bytes(aad)).decode("ascii")
    expect_reject(frame)


def test_nonce_tamper_rejected():
    frame = make_frame()
    nonce = bytearray(base64.b64decode(frame["nonce_b64"]))
    nonce[0] ^= 1
    frame["nonce_b64"] = base64.b64encode(bytes(nonce)).decode("ascii")
    expect_reject(frame)


def test_ciphertext_tamper_rejected():
    frame = make_frame()
    ciphertext = bytearray(base64.b64decode(frame["ciphertext_b64"]))
    ciphertext[0] ^= 1
    frame["ciphertext_b64"] = base64.b64encode(bytes(ciphertext)).decode("ascii")
    expect_reject(frame)


def test_replay_and_out_of_order_rejected():
    frame = make_frame(sequence=7)
    _, _, key = gate.verify_frame(frame, AESGCM(KEY), {})
    state = {key: 7}
    expect_reject(frame, state)
    older = make_frame(sequence=6)
    expect_reject(older, state)
    newer = make_frame(sequence=8)
    raw, _, _ = gate.verify_frame(newer, AESGCM(KEY), state)
    assert raw == b"neural-bytes"


def test_corrupt_head_fails_closed():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        log = root / "marbles.jsonl"
        head = root / "head.json"
        log.write_text(json.dumps({"marble_sha256": "a" * 64}) + "\n", encoding="utf-8")
        head.write_text("{not-json", encoding="utf-8")
        try:
            gate.load_prev(str(head), str(log))
        except gate.EvidenceStateError:
            pass
        else:
            raise AssertionError("corrupt head did not fail closed")


def test_missing_head_with_existing_log_fails_closed():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        log = root / "marbles.jsonl"
        head = root / "missing-head.json"
        log.write_text(json.dumps({"marble_sha256": "b" * 64}) + "\n", encoding="utf-8")
        try:
            gate.load_prev(str(head), str(log))
        except gate.EvidenceStateError:
            pass
        else:
            raise AssertionError("missing head with existing log did not fail closed")


def test_head_log_mismatch_fails_closed():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        log = root / "marbles.jsonl"
        head = root / "head.json"
        log.write_text(json.dumps({"marble_sha256": "c" * 64}) + "\n", encoding="utf-8")
        head.write_text(json.dumps({"marble_sha256": "d" * 64}), encoding="utf-8")
        try:
            gate.load_prev(str(head), str(log))
        except gate.EvidenceStateError:
            pass
        else:
            raise AssertionError("head/log mismatch did not fail closed")


def test_corrupt_replay_state_fails_closed():
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "replay.json"
        path.write_text("[]", encoding="utf-8")
        try:
            gate.load_replay_state(str(path))
        except gate.EvidenceStateError:
            pass
        else:
            raise AssertionError("invalid replay state did not fail closed")


def run_all():
    tests = [value for name, value in sorted(globals().items()) if name.startswith("test_") and callable(value)]
    for test in tests:
        test()
        print("PASS", test.__name__)
    print(f"MANIFOLD-AUTH-001: {len(tests)}/{len(tests)} tests passed")


if __name__ == "__main__":
    run_all()
