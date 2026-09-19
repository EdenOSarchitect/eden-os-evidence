#!/usr/bin/env python3
import json
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPT = Path(__file__).with_name("azure_live_004.py")


def test_mock_paired_replay() -> None:
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "run"
        subprocess.run([
            sys.executable,
            str(SCRIPT),
            "--provider", "mock",
            "--unique-tasks", "2",
            "--repeats", "2",
            "--output-dir", str(out),
        ], check=True, stdout=subprocess.DEVNULL)

        manifest = json.loads((out / "manifest.json").read_text())
        assert manifest["experiment"] == "AZURE-LIVE-004"
        assert manifest["provider_class"] == "SIMULATED_MOCK_PROVIDER"
        assert manifest["provider_calls_total"] == 2
        assert manifest["provider_calls_during_replay"] == 0
        assert manifest["capture_quality_pass_rate"] == 1.0
        assert manifest["replay"]["control_quality_pass_rate"] == 1.0
        assert manifest["replay"]["eden_quality_pass_rate"] == 1.0
        assert manifest["replay"]["identical_output_hash_all_pairs"] is True
        assert manifest["replay"]["eden_integrity_verified_all"] is True
        assert manifest["replay"]["pairs"] == 4


if __name__ == "__main__":
    test_mock_paired_replay()
    print("PASS AZURE-LIVE-004 mock paired replay")
