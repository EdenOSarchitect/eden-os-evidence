import copy
import json
import tempfile
import unittest
from pathlib import Path

from marble.telemetry_e2e import run_e2e, verify_e2e_artifact


class TelemetryE2ETests(unittest.TestCase):
    def setUp(self):
        self.fixture = Path("marble/fixtures/full-telemetry-ci.json")

    def test_full_telemetry_to_verified_marble_artifact(self):
        with tempfile.TemporaryDirectory() as td:
            log = Path(td) / "providence.jsonl"
            head = Path(td) / "head.json"
            artifact = run_e2e(
                str(self.fixture),
                log_path=str(log),
                head_path=str(head),
                signing_key=b"e2e-test-key",
                key_id="e2e-test",
            )
            self.assertTrue(artifact["e2e_verified"])
            self.assertTrue(artifact["verification"]["primary"]["integrity_verified"])
            self.assertTrue(artifact["verification"]["primary"]["resource_provenance_verified"])
            self.assertTrue(artifact["verification"]["independent"]["identity_verified"])
            self.assertTrue(artifact["verification"]["signature"]["signature_verified"])
            self.assertTrue(artifact["verification"]["transparency_log"]["transparency_log_verified"])
            self.assertTrue(artifact["verification"]["crv"]["within_delegation"])
            self.assertEqual(artifact["marble"]["evidence"]["class"], "SIMULATED")
            self.assertFalse(artifact["scientific_truth_implied"])
            self.assertTrue(verify_e2e_artifact(artifact)["verified"])

    def test_artifact_tamper_is_rejected(self):
        artifact = run_e2e(str(self.fixture), signing_key=b"e2e-test-key", key_id="e2e-test")
        tampered = copy.deepcopy(artifact)
        tampered["marble"]["resources"]["joules"] = 1.0
        result = verify_e2e_artifact(tampered)
        self.assertFalse(result["verified"])
        self.assertIn("artifact_id mismatch", result["errors"])
        self.assertIn("primary Marble integrity verification failed", result["errors"])

    def test_missing_instrumentation_fails_before_mint(self):
        source = json.loads(self.fixture.read_text(encoding="utf-8"))
        del source["instrumentation"]["network_bytes"]
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "bad.json"
            path.write_text(json.dumps(source), encoding="utf-8")
            with self.assertRaises(ValueError):
                run_e2e(str(path), signing_key=b"e2e-test-key", key_id="e2e-test")

    def test_crv_violation_prevents_e2e_verified(self):
        source = json.loads(self.fixture.read_text(encoding="utf-8"))
        source["crv_allocation"]["joules"] = 1.0
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "over-budget.json"
            path.write_text(json.dumps(source), encoding="utf-8")
            artifact = run_e2e(str(path), signing_key=b"e2e-test-key", key_id="e2e-test")
            self.assertFalse(artifact["e2e_verified"])
            self.assertFalse(artifact["verification"]["crv"]["within_delegation"])


if __name__ == "__main__":
    unittest.main()
