#!/usr/bin/env python3
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
MODULE_PATH = HERE / "azure_fair_ab.py"
spec = importlib.util.spec_from_file_location("azure_fair_ab", MODULE_PATH)
mod = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(mod)


class AzureFairABTests(unittest.TestCase):
    def test_quality_checker_accepts_expected_payload(self):
        idx = 7
        exp = mod.expected_for(idx)
        text = json.dumps({
            "index": idx,
            "checksum": exp["checksum"],
            "classification": "KEEP",
            "summary": "ok",
        })
        result = mod.quality_check(text, idx)
        self.assertTrue(result["pass"])
        self.assertEqual(result["score"], 1.0)

    def test_same_exact_cache_key_for_same_request(self):
        prompt = mod.prompt_for(3)
        a = mod.exact_cache_key(prompt, "deployment", 96)
        b = mod.exact_cache_key(prompt, "deployment", 96)
        self.assertEqual(a, b)

    def test_mock_run_has_identical_provider_call_count_and_quality(self):
        with tempfile.TemporaryDirectory() as td:
            args = mod.parse_args([
                "--provider", "mock",
                "--requests", "12",
                "--unique-tasks", "4",
                "--seed", "1234",
                "--output-dir", td,
            ])
            manifest = mod.run(args)
            control = manifest["summaries"]["control"]
            eden = manifest["summaries"]["eden"]
            self.assertEqual(control["provider_calls"], 4)
            self.assertEqual(eden["provider_calls"], 4)
            self.assertEqual(control["cache_hits"], 8)
            self.assertEqual(eden["cache_hits"], 8)
            self.assertEqual(control["quality_pass_rate"], 1.0)
            self.assertEqual(eden["quality_pass_rate"], 1.0)
            self.assertEqual(manifest["comparison"]["provider_call_delta"], 0)
            self.assertEqual(manifest["comparison"]["provider_input_token_delta"], 0)
            self.assertEqual(manifest["comparison"]["provider_output_token_delta"], 0)
            self.assertEqual(manifest["provider_class"], "SIMULATED_MOCK_PROVIDER")
            self.assertIn("Azure energy consumption", manifest["truth_boundary"]["not_claimed"])
            self.assertTrue((Path(td) / "manifest.json").exists())
            self.assertTrue((Path(td) / "eden-records.jsonl").exists())

            eden_records = [json.loads(line) for line in (Path(td) / "eden-records.jsonl").read_text().splitlines()]
            self.assertEqual(len(eden_records), 12)
            for record in eden_records:
                self.assertIsNotNone(record["eden"])
                self.assertTrue(record["eden"]["integrity_verified"])
                self.assertTrue(record["record_sha256"].startswith("sha256:"))

    def test_token_price_is_modelled_not_billing(self):
        with tempfile.TemporaryDirectory() as td:
            args = mod.parse_args([
                "--provider", "mock",
                "--requests", "4",
                "--unique-tasks", "2",
                "--output-dir", td,
                "--input-price-per-1m", "1.25",
                "--output-price-per-1m", "5.0",
            ])
            manifest = mod.run(args)
            for arm in ("control", "eden"):
                summary = manifest["summaries"][arm]
                self.assertIsNotNone(summary["modeled_token_cost"])
                self.assertEqual(summary["modeled_token_cost_class"], "MODELLED_FROM_PROVIDER_REPORTED_USAGE")
            self.assertEqual(manifest["billing"]["status"], "NOT_SUPPLIED")

    def test_external_billing_file_is_hashed_and_not_auto_attested(self):
        with tempfile.TemporaryDirectory() as td:
            billing = Path(td) / "billing.json"
            billing.write_text(json.dumps({"control": {"amount": 1.0}, "eden": {"amount": 0.9}}))
            args = mod.parse_args([
                "--provider", "mock",
                "--requests", "4",
                "--unique-tasks", "2",
                "--output-dir", str(Path(td) / "out"),
                "--billing-json", str(billing),
            ])
            manifest = mod.run(args)
            self.assertEqual(manifest["billing"]["status"], "SUPPLIED_EXTERNAL_EVIDENCE")
            self.assertTrue(manifest["billing"]["file_sha256"].startswith("sha256:"))
            self.assertIn("must be established", manifest["billing"]["truth_boundary"])


if __name__ == "__main__":
    unittest.main()
