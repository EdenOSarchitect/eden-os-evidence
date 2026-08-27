import tempfile
import unittest
from pathlib import Path

from eden_core.core import EdenCore


class EdenCoreTests(unittest.TestCase):
    def test_health_and_evidence_store(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "marble").mkdir()
            (root / "marble" / "evidence.json").write_text("{}")
            core = EdenCore(repo_root=root, state_dir=root / ".eden-core")
            health = core.health()
            self.assertEqual(health["status"], "ok")
            self.assertEqual(core.evidence_summary()["json_artifacts"], 1)

    def test_marble_mint_and_verify_use_reference_module(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            core = EdenCore(repo_root=root, state_dir=root / ".eden-core")
            payload = {
                "kind": "EXECUTION",
                "subject": {"name": "core-test"},
                "parents": [],
                "actor": {"id": "test", "attestation": "UNATTESTED"},
                "policy": {"policy_id": "TEST", "policy_hash": "sha256:test"},
                "input": {"sha256": "sha256:input"},
                "output": {"sha256": "sha256:output"},
                "resources": {"cpu_seconds": 1.0},
                "quality": {"status": "PASS"},
                "evidence": {"class": "IMPLEMENTED", "instrumentation": []},
                "truth": {"claims": [], "not_claimed": []},
                "provenance": {"sequence": 0},
            }
            marble = core.mint_marble(payload)
            result = core.verify_marble(marble)
            self.assertTrue(result["integrity_verified"])
            telemetry = core.telemetry()
            self.assertEqual(telemetry["counters"]["marbles_minted"], 1)
            self.assertEqual(telemetry["counters"]["marbles_verified"], 1)
            self.assertEqual(telemetry["counters"]["marbles_void"], 0)


if __name__ == "__main__":
    unittest.main()
