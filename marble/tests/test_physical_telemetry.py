import copy
import json
import tempfile
import unittest
from pathlib import Path

from marble.physical_telemetry import adapt_rf
from marble.telemetry_e2e import run_e2e


class PhysicalTelemetryTests(unittest.TestCase):
    def setUp(self):
        self.fixture = Path("marble/fixtures/physical-rf-ci.json")

    def test_ci_fixture_is_forced_to_simulated(self):
        source = json.loads(self.fixture.read_text(encoding="utf-8"))
        telemetry = adapt_rf(source)
        self.assertEqual(telemetry["evidence_class"], "SIMULATED")
        self.assertTrue(telemetry["source_evidence"]["fixture_only"])
        self.assertIn("rssi_dbm", telemetry["observations"])

    def test_physical_shaped_telemetry_uses_same_e2e_chain(self):
        source = json.loads(self.fixture.read_text(encoding="utf-8"))
        telemetry = adapt_rf(source)
        with tempfile.TemporaryDirectory() as td:
            telemetry_path = Path(td) / "telemetry.json"
            log_path = Path(td) / "providence.jsonl"
            head_path = Path(td) / "head.json"
            telemetry_path.write_text(json.dumps(telemetry, sort_keys=True), encoding="utf-8")
            artifact = run_e2e(
                str(telemetry_path),
                log_path=str(log_path),
                head_path=str(head_path),
                signing_key=b"physical-adapter-ci-key",
                key_id="physical-ci",
            )
            self.assertTrue(artifact["e2e_verified"])
            self.assertEqual(artifact["marble"]["evidence"]["class"], "SIMULATED")
            self.assertEqual(artifact["marble"]["evidence"]["observations"]["rssi_dbm"], -47)
            self.assertIn("rssi_dbm", artifact["marble"]["evidence"]["observation_provenance"])
            self.assertTrue(artifact["verification"]["independent"]["identity_verified"])

    def test_source_hash_tamper_is_rejected(self):
        source = json.loads(self.fixture.read_text(encoding="utf-8"))
        source["strongest_observation"]["rssi_dbm"] = -10
        with self.assertRaises(ValueError):
            adapt_rf(source)

    def test_real_source_would_retain_measured_after_valid_hash(self):
        source = json.loads(self.fixture.read_text(encoding="utf-8"))
        source.pop("fixture_only", None)
        source.pop("evidence_sha256")
        import hashlib
        core = json.dumps(source, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")
        source["evidence_sha256"] = hashlib.sha256(core).hexdigest()
        telemetry = adapt_rf(source)
        self.assertEqual(telemetry["evidence_class"], "MEASURED")
        self.assertFalse(telemetry["source_evidence"]["physical_capture"] is False)


if __name__ == "__main__":
    unittest.main()
