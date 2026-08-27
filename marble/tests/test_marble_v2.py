#!/usr/bin/env python3
import copy
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("eden_marble", ROOT / "marble.py")
marble = importlib.util.module_from_spec(spec)
spec.loader.exec_module(marble)


def core(kind="EXECUTION"):
    return {
        "schema": "eden.marble.v2",
        "kind": kind,
        "subject": {"workload_id": "WL-001", "experiment_id": "MARBLE-LIFE-001"},
        "parents": [],
        "actor": {"source": "EDEN-TEST", "attestation": "UNATTESTED"},
        "policy": {"policy_id": "TEST-001", "policy_hash": "sha256:policy"},
        "input": {"commitment": "sha256:input", "bytes": 1000},
        "output": {"commitment": "sha256:output", "bytes": 400},
        "resources": {"cpu_seconds": 1.25, "network_bytes": 400, "joules": None},
        "quality": {"metric": "task_score", "value": 0.98, "baseline": 0.99},
        "evidence": {"class": "MEASURED", "instrumentation": ["CLOCK_MONOTONIC"]},
        "truth": {"claims": ["wall time measured"], "not_claimed": ["energy reduction"]},
        "provenance": {"previous": None, "sequence": 0},
        "timestamp": "2026-08-27T08:00:00Z"
    }


class MarbleV2Tests(unittest.TestCase):
    def test_mint_and_verify(self):
        m = marble.mint(core())
        r = marble.verify_integrity(m)
        self.assertTrue(r["integrity_verified"])
        self.assertTrue(r["evidence_verified"])
        self.assertEqual(r["attestation"], "UNATTESTED")

    def test_committed_field_tamper_rejected(self):
        mutations = [
            ("kind", "ASSERTION"),
            ("subject", {"workload_id": "FORGED"}),
            ("actor", {"source": "FORGED", "attestation": "UNATTESTED"}),
            ("policy", {"policy_id": "FORGED", "policy_hash": "sha256:forged"}),
            ("input", {"commitment": "sha256:forged"}),
            ("output", {"commitment": "sha256:forged"}),
            ("resources", {"cpu_seconds": 0.0001}),
            ("quality", {"metric": "task_score", "value": 1.0}),
            ("evidence", {"class": "INDEPENDENTLY_VALIDATED", "independent_reproduction": "fake"}),
            ("truth", {"claims": ["forged"], "not_claimed": []}),
            ("provenance", {"previous": None, "sequence": 99}),
            ("timestamp", "2099-01-01T00:00:00Z"),
        ]
        original = marble.mint(core())
        for field, value in mutations:
            with self.subTest(field=field):
                tampered = copy.deepcopy(original)
                tampered[field] = value
                self.assertFalse(marble.verify_integrity(tampered)["integrity_verified"])

    def test_measured_label_requires_instrumentation(self):
        c = core()
        c["evidence"] = {"class": "MEASURED", "instrumentation": []}
        m = marble.mint(c)
        r = marble.verify_integrity(m)
        self.assertTrue(r["integrity_verified"])
        self.assertFalse(r["evidence_verified"])

    def test_independent_validation_requires_reference(self):
        c = core()
        c["evidence"] = {"class": "INDEPENDENTLY_VALIDATED"}
        m = marble.mint(c)
        r = marble.verify_integrity(m)
        self.assertFalse(r["evidence_verified"])

    def test_lineage(self):
        parent = marble.mint(core("OBSERVATION"))
        child_core = core("EXECUTION")
        child_core["parents"] = [parent["marble_id"]]
        child_core["provenance"] = {"previous": parent["marble_id"], "sequence": 1}
        child = marble.mint(child_core)
        self.assertTrue(marble.verify_lineage([parent, child])["lineage_verified"])
        self.assertFalse(marble.verify_lineage([child])["lineage_verified"])

    def test_cycle_rejected(self):
        a = marble.mint(core("OBSERVATION"))
        bcore = core("DECISION")
        bcore["parents"] = [a["marble_id"]]
        bcore["provenance"] = {"previous": a["marble_id"], "sequence": 1}
        b = marble.mint(bcore)
        # Construct a deliberately malformed graph by changing parent links and
        # recomputing IDs. A two-node cryptographic cycle cannot be fixed-point
        # constructed naturally, so verify_lineage's DFS is separately exercised
        # using synthetic identifiers.
        fake_a = copy.deepcopy(a)
        fake_b = copy.deepcopy(b)
        fake_a["marble_id"] = "sha256:" + "a" * 64
        fake_b["marble_id"] = "sha256:" + "b" * 64
        fake_a["parents"] = [fake_b["marble_id"]]
        fake_b["parents"] = [fake_a["marble_id"]]
        self.assertFalse(marble.verify_lineage([fake_a, fake_b])["lineage_verified"])

    def test_crv(self):
        ok = marble.verify_crv({"cpu": 4, "memory": 1024, "cost": 0.2}, {"cpu": 3, "memory": 900, "cost": 0.13})
        self.assertTrue(ok["within_delegation"])
        bad = marble.verify_crv({"cpu": 4}, {"cpu": 8})
        self.assertFalse(bad["within_delegation"])

    def test_refutation_requires_target(self):
        c = core("REFUTATION")
        with self.assertRaises(ValueError):
            marble.mint(c)


if __name__ == "__main__":
    unittest.main()
