import copy
import json
import tempfile
import unittest
from pathlib import Path

from marble.assurance import (
    append_log,
    load_head,
    make_attestation_record,
    make_timestamp_anchor,
    persist_head,
    sign_hmac,
    verify_attestation_record,
    verify_hmac,
    verify_log,
    verify_resource_provenance,
    verify_timestamp_anchor,
)
from marble.independent_verify import verify as independent_verify
from marble.marble import assurance_profile, mint, verify_integrity


def core():
    return {
        "schema": "eden.marble.v2",
        "kind": "EXECUTION",
        "subject": {"workload_id": "WL-ASSURANCE-001"},
        "parents": [],
        "actor": {"source": "TEST", "attestation": "UNATTESTED"},
        "policy": {"policy_id": "P-1", "policy_hash": "sha256:policy"},
        "input": {"commitment": "sha256:input", "bytes": 100},
        "output": {"commitment": "sha256:output", "bytes": 40},
        "resources": {"wall_time_ms": 12.5, "network_bytes": 40, "joules": None},
        "quality": {"metric": "test", "value": 1.0},
        "evidence": {
            "class": "MEASURED",
            "instrumentation": ["CLOCK_MONOTONIC"],
            "resource_provenance": {
                "wall_time_ms": {"instrument": "CLOCK_MONOTONIC", "measurement_ref": "sha256:wall"},
                "network_bytes": {"instrument": "BYTE_COUNTER", "measurement_ref": "sha256:bytes"},
            },
        },
        "truth": {"claims": ["wall time measured"], "not_claimed": ["hardware identity"]},
        "provenance": {"sequence": 1, "previous": None},
        "timestamp": "2026-08-27T08:00:00Z",
    }


class AssuranceV2Tests(unittest.TestCase):
    def test_assurance_can_accrue_without_changing_event_identity(self):
        m = mint(core())
        original = m["marble_id"]
        m["assurance"] = {"timestamp_anchor": make_timestamp_anchor(original)}
        self.assertEqual(m["marble_id"], original)
        self.assertTrue(verify_integrity(m)["integrity_verified"])
        self.assertTrue(independent_verify(m)["identity_verified"])

    def test_hmac_signature_detects_wrong_key_and_wrong_id(self):
        m = mint(core())
        env = sign_hmac(m["marble_id"], b"secret", "test-key")
        self.assertTrue(verify_hmac(m["marble_id"], env, {"test-key": b"secret"})["signature_verified"])
        self.assertFalse(verify_hmac(m["marble_id"], env, {"test-key": b"wrong"})["signature_verified"])
        self.assertFalse(verify_hmac("sha256:" + "0" * 64, env, {"test-key": b"secret"})["signature_verified"])

    def test_timestamp_anchor_tamper_is_rejected(self):
        m = mint(core())
        anchor = make_timestamp_anchor(m["marble_id"], at="2026-08-27T08:01:00Z")
        self.assertTrue(verify_timestamp_anchor(m["marble_id"], anchor)["timestamp_anchor_verified"])
        bad = dict(anchor)
        bad["observed_at"] = "2026-08-27T08:02:00Z"
        self.assertFalse(verify_timestamp_anchor(m["marble_id"], bad)["timestamp_anchor_verified"])

    def test_resource_provenance_requires_each_non_null_resource(self):
        m = mint(core())
        good = verify_resource_provenance(m["resources"], m["evidence"])
        self.assertTrue(good["resource_provenance_verified"])
        bad_evidence = copy.deepcopy(m["evidence"])
        del bad_evidence["resource_provenance"]["network_bytes"]
        bad = verify_resource_provenance(m["resources"], bad_evidence)
        self.assertFalse(bad["resource_provenance_verified"])
        self.assertIn("network_bytes", bad["unproven_resources"])

    def test_hardware_attestation_cannot_self_promote(self):
        local = make_attestation_record(
            subject="device:test",
            credential_hash="sha256:credential",
            verifier="LOCAL_SOFTWARE",
            hardware_backed=True,
        )
        local_v = verify_attestation_record(local)
        self.assertEqual(local_v["assurance"], "HARDWARE_CLAIM_UNVERIFIED")
        external = make_attestation_record(
            subject="device:test",
            credential_hash="sha256:credential",
            verifier="EXTERNAL_TPM_VERIFIER",
            evidence_ref="https://example.invalid/attestation/1",
            hardware_backed=True,
        )
        self.assertEqual(verify_attestation_record(external)["assurance"], "HARDWARE_ATTESTATION_REFERENCE_RECORDED")

    def test_transparency_log_hash_chain_and_tamper(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "log.jsonl"
            a = mint(core())
            bcore = core()
            bcore["provenance"] = {"sequence": 2, "previous": a["marble_id"]}
            b = mint(bcore)
            append_log(str(path), a["marble_id"])
            append_log(str(path), b["marble_id"])
            entries = [json.loads(x) for x in path.read_text().splitlines()]
            self.assertTrue(verify_log(entries)["transparency_log_verified"])
            entries[1]["marble_id"] = "sha256:" + "f" * 64
            self.assertFalse(verify_log(entries)["transparency_log_verified"])

    def test_persistent_head_fails_closed_on_corruption_and_replay(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "head.json"
            a = mint(core())
            persist_head(str(path), a["marble_id"], 1)
            self.assertEqual(load_head(str(path))["sequence"], 1)
            with self.assertRaises(ValueError):
                persist_head(str(path), a["marble_id"], 1)
            path.write_text('{"corrupt":true}', encoding="utf-8")
            with self.assertRaises(ValueError):
                load_head(str(path))

    def test_assurance_profile_never_implies_scientific_truth(self):
        m = mint(core())
        p = assurance_profile(m)
        self.assertFalse(p["scientific_truth_implied"])
        self.assertEqual(p["resource_measurement_state"], "PROVENANCE_COMPLETE")


if __name__ == "__main__":
    unittest.main()
