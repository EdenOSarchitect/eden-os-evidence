#!/usr/bin/env python3
import copy, importlib.util, unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("azure_application_001", HERE / "azure_application_001.py")
app = importlib.util.module_from_spec(spec); spec.loader.exec_module(app)

class ApplicationTests(unittest.TestCase):
    def test_request_stream_has_exact_realized_reuse(self):
        stream = app.request_stream(100, .50, 7)
        self.assertEqual(len(stream), 100)
        self.assertEqual(len(set(stream)), 50)
        self.assertEqual(stream, app.request_stream(100, .50, 7))

    def test_record_binds_every_assurance_field(self):
        record = app.make_record(9, 100, app.work(9, 100))
        self.assertTrue(app.verify_record(record, 9, 100))
        for field in ("input_commitment", "output_commitment", "policy",
                      "policy_commitment", "provenance", "value", "record_commitment"):
            changed = copy.deepcopy(record)
            changed[field] = "tampered" if field != "value" else changed[field] + 1
            with self.subTest(field=field):
                self.assertFalse(app.verify_record(changed, 9, 100))

    def test_modes_are_equivalent_and_accounted(self):
        stream = app.request_stream(40, .50, 11)
        arms = {mode: app.run_arm(mode, stream, 200, 8) for mode in app.MODES}
        comparison = app.compare(arms)
        self.assertTrue(comparison["output_equivalence"])
        self.assertTrue(comparison["execution_accounting_valid"])
        self.assertEqual(arms["CONTROL"]["full_executions"], 40)
        for mode in ("CACHE", "EDEN"):
            self.assertEqual(arms[mode]["full_executions"], 20)
            self.assertEqual(arms[mode]["reuse_hits"], 20)
            self.assertEqual(arms[mode]["executions_avoided_vs_control"], 20)
        self.assertEqual(arms["EDEN"]["verification_attempts"], 40)
        self.assertEqual(arms["EDEN"]["verification_hit_attempts"], 20)
        self.assertEqual(arms["EDEN"]["verification_passes"], 40)
        self.assertEqual(arms["EDEN"]["verification_failures"], 0)
        self.assertEqual(
            arms["CONTROL"]["application_payload_bytes"],
            arms["EDEN"]["application_payload_bytes"],
        )

    def test_explicit_order_validation(self):
        self.assertEqual(app.parse_order("EDEN,CONTROL,CACHE", 1),
                         ["EDEN", "CONTROL", "CACHE"])
        with self.assertRaises(ValueError):
            app.parse_order("CONTROL,CACHE,CACHE", 1)

if __name__ == "__main__": unittest.main()
