import importlib.util
import unittest
from pathlib import Path


spec = importlib.util.spec_from_file_location(
    "structured_reuse", Path(__file__).with_name("azure_structured_reuse_001.py")
)
benchmark = importlib.util.module_from_spec(spec)
spec.loader.exec_module(benchmark)


class StructuredReuseTests(unittest.TestCase):
    def test_tampered_hit_is_rejected(self):
        req = benchmark.build_trace(1, 42)[0][0]
        store, evidence = {}, []
        benchmark.run_eden(req, 5, store, evidence)
        first = next(iter(store.values()))
        first["output"]["score"] ^= 1
        with self.assertRaisesRegex(ValueError, "commitment mismatch"):
            benchmark.run_eden(req, 5, store, evidence)

    def test_rounds_are_part_of_reuse_policy(self):
        req = benchmark.build_trace(1, 42)[0][0]
        store, evidence = {}, []
        benchmark.run_eden(req, 5, store, evidence)
        before = len(store)
        benchmark.run_eden(req, 6, store, evidence)
        self.assertGreater(len(store), before)

    def test_repeated_trials_preserve_outputs_and_hit_count(self):
        trace, reuse = benchmark.build_trace(12, 42)
        first = benchmark.run_trial(trace, 5, 42)
        second = benchmark.run_trial(trace, 5, 43)
        expected = reuse["total_sections"] - reuse["unique_sections"]
        self.assertEqual(first["output_commitment"], second["output_commitment"])
        self.assertEqual(first["verified_section_hits"], expected)
        self.assertEqual(second["verified_section_hits"], expected)
        self.assertTrue(first["output_equivalence"])


if __name__ == "__main__":
    unittest.main()
