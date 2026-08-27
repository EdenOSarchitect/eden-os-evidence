#!/usr/bin/env python3
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("eden_marble_fixture", ROOT / "marble.py")
marble = importlib.util.module_from_spec(spec)
spec.loader.exec_module(marble)


class FixtureTests(unittest.TestCase):
    def test_example_fixture_mints_and_verifies(self):
        core = json.loads((ROOT / "fixtures" / "example-execution-core.json").read_text(encoding="utf-8"))
        minted = marble.mint(core)
        result = marble.verify_integrity(minted)
        self.assertTrue(result["integrity_verified"])
        self.assertTrue(result["evidence_verified"])
        self.assertEqual(minted["kind"], "EXECUTION")


if __name__ == "__main__":
    unittest.main()
