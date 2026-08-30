#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "delivery" / "out"
RESULTS.mkdir(parents=True, exist_ok=True)


def utcnow():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def run(name, cmd, required=True, env=None):
    print(f"\n=== {name} ===")
    proc = subprocess.run(cmd, cwd=ROOT, text=True, env=env)
    return {
        "name": name,
        "command": " ".join(cmd),
        "required": required,
        "returncode": proc.returncode,
        "status": "PASS" if proc.returncode == 0 else "NOT_COMPLETED",
    }


def exists(path):
    return (ROOT / path).exists()


def main():
    ap = argparse.ArgumentParser(description="Run the consolidated EDEN verification/experiment suite.")
    ap.add_argument("--handset", action="store_true", help="Also run physical Termux handset experiments AB-001 and AB-002")
    ap.add_argument("--package", action="store_true", help="Build delivery archive after the run")
    args = ap.parse_args()

    records = []
    records.append(run(
        "Core + ChronoNav + Chrysalis unit/integration gate",
        [sys.executable, "-m", "unittest",
         "eden_core.tests.test_core",
         "eden_core.tests.test_launcher_integration",
         "chrononav.tests.test_scheduler",
         "chrysalis.tests.test_chrysalis", "-v"],
    ))

    # Historical experiments remain preserved as immutable evidence artifacts.
    # Only known deterministic/reproducible runners are invoked automatically.
    optional = [
        ("SAT-001 reproducibility", "sat-001", [sys.executable, "sat-001/reproduce.py"]),
    ]
    for name, path, cmd in optional:
        if exists(path) and exists(cmd[1]) if len(cmd) > 1 else False:
            records.append(run(name, cmd, required=False))
        else:
            records.append({"name": name, "required": False, "status": "PRESERVED_NOT_RERUN", "reason": "runner not present at expected path"})

    if args.handset:
        probe = subprocess.run(["termux-battery-status"], cwd=ROOT, text=True, capture_output=True)
        if probe.returncode != 0:
            records.append({"name": "Physical handset suite", "required": False, "status": "NOT_COMPLETED", "reason": "termux-battery-status unavailable"})
        else:
            try:
                battery = json.loads(probe.stdout)
            except Exception:
                battery = {}
            if battery.get("status") != "DISCHARGING":
                records.append({"name": "Physical handset suite", "required": False, "status": "NOT_COMPLETED", "reason": "handset must be unplugged / DISCHARGING"})
            else:
                subprocess.run(["bash", "bin/eden", "restart"], cwd=ROOT)
                for exp in ("eden-core-ab-001", "eden-core-ab-002"):
                    script = ROOT / "experiments" / exp / "run_termux.py"
                    if script.exists():
                        records.append(run(exp.upper(), [sys.executable, str(script.relative_to(ROOT))], required=False))
                    else:
                        records.append({"name": exp.upper(), "required": False, "status": "PRESERVED_NOT_RERUN", "reason": "runner missing"})

    required_ok = all(r.get("status") == "PASS" for r in records if r.get("required"))
    report = {
        "schema": "eden.experiment-suite.v1",
        "created_at": utcnow(),
        "required_gate": "PASS" if required_ok else "NOT_CLEARED",
        "records": records,
        "truth_boundary": {
            "independent_validation": False,
            "physical_claims": "Only physical runs that actually execute and retain their raw measurement artifacts are MEASURED; preserved or skipped experiments are not upgraded.",
            "integrity": "Hash/signature verification establishes integrity/authenticity under the stated mechanism, not scientific truth.",
        },
    }
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = RESULTS / f"EDEN-EXPERIMENT-SUITE-{stamp}.json"
    out.write_text(json.dumps(report, indent=2, sort_keys=True))
    print(f"\nSuite report: {out}")

    if args.package:
        package = subprocess.run([sys.executable, "delivery/build_delivery.py"], cwd=ROOT)
        if package.returncode != 0:
            return package.returncode
    return 0 if required_ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
