#!/usr/bin/env python3

import json
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPT = Path(__file__).with_name("azure_capacity_002.py")

with tempfile.TemporaryDirectory() as td:
    outdir = Path(td)
    cmd = [
        sys.executable,
        str(SCRIPT),
        "--outputs", "24",
        "--iterations", "200",
        "--reuse", "0", "0.5",
        "--progress-every", "0",
        "--environment", "TEST_HOST",
        "--output-dir", str(outdir),
    ]
    subprocess.run(cmd, check=True)
    reports = list(outdir.glob("EDEN-AZURE-CAPACITY-002-*.json"))
    assert len(reports) == 1, reports
    report = json.loads(reports[0].read_text())

assert report["experiment"] == "EDEN-AZURE-CAPACITY-002"
assert len(report["results"]) == 2
for sweep in report["results"]:
    assert sweep["comparison"]["all_outputs_equivalent"] is True
    assert set(sweep["arms"]) == {"CONTROL", "CACHE", "EDEN", "EDEN_NOREUSE"}
    assert sweep["arms"]["EDEN"]["evidence_chain_commitment"].startswith("sha256:")
    assert sweep["arms"]["EDEN_NOREUSE"]["evidence_chain_commitment"].startswith("sha256:")

half = report["results"][1]
assert half["reuse_target_fraction"] == 0.5
assert half["arms"]["CACHE"]["reuse_hits"] == 12
assert half["arms"]["EDEN"]["reuse_hits"] == 12
assert half["arms"]["EDEN_NOREUSE"]["reuse_hits"] == 0
assert half["comparison"]["cache_executions_avoided"] == 12
assert half["comparison"]["eden_executions_avoided"] == 12
assert report["report_commitment"].startswith("sha256:")

print("PASS EDEN-AZURE-CAPACITY-002 smoke test")
