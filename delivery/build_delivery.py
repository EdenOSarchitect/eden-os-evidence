#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import subprocess
import tarfile
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "delivery" / "out"
OUT.mkdir(parents=True, exist_ok=True)

INCLUDE_DIRS = [
    "chrononav",
    "chrysalis",
    "eden-refinery",
    "eden_core",
    "experiments",
    "marble",
    "neural-interface",
    "rf-establishment",
    "sat-001",
    "energy",
    "gpu",
    "docs",
    "academic",
]

EXCLUDE_PARTS = {"__pycache__", ".git", ".eden-core", "node_modules"}


def utcnow():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def git(args):
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def collect_files():
    files = []
    for name in INCLUDE_DIRS:
        root = ROOT / name
        if not root.exists():
            continue
        for p in root.rglob("*"):
            if not p.is_file():
                continue
            rel = p.relative_to(ROOT)
            if any(part in EXCLUDE_PARTS for part in rel.parts):
                continue
            files.append(p)
    for p in [ROOT / "README.md", ROOT / "bin" / "eden"]:
        if p.exists():
            files.append(p)
    return sorted(set(files), key=lambda p: str(p.relative_to(ROOT)))


def classify_json(path: Path):
    try:
        data = json.loads(path.read_text())
    except Exception:
        return None
    if isinstance(data, dict):
        for key in ("classification", "evidence_class"):
            if key in data:
                return data[key]
        ev = data.get("evidence")
        if isinstance(ev, dict):
            return ev.get("class")
    return None


def run_tests():
    cmd = [
        "python", "-m", "unittest",
        "eden_core.tests.test_core",
        "eden_core.tests.test_launcher_integration",
        "chrononav.tests.test_scheduler",
        "chrysalis.tests.test_chrysalis",
        "-v",
    ]
    proc = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True)
    return {
        "command": " ".join(cmd),
        "returncode": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "passed": proc.returncode == 0,
    }


def build(run_tests_first=True):
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    bundle_dir = OUT / f"EDEN-DELIVERY-{stamp}"
    bundle_dir.mkdir(parents=True, exist_ok=False)

    test_result = run_tests() if run_tests_first else {"passed": None, "skipped": True}
    files = collect_files()
    manifest_files = []
    classifications = {}

    for p in files:
        rel = p.relative_to(ROOT)
        digest = sha256_file(p)
        entry = {
            "path": str(rel),
            "bytes": p.stat().st_size,
            "sha256": digest,
        }
        if p.suffix.lower() == ".json":
            c = classify_json(p)
            if c is not None:
                entry["classification"] = c
                classifications[str(c)] = classifications.get(str(c), 0) + 1
        manifest_files.append(entry)

    head = git(["rev-parse", "HEAD"])
    branch = git(["branch", "--show-current"])
    dirty = bool(git(["status", "--porcelain"]))

    manifest = {
        "schema": "eden.delivery.v1",
        "created_at": utcnow(),
        "repository": "EdenOSarchitect/eden-os-evidence",
        "git": {"commit": head, "branch": branch, "working_tree_dirty": dirty},
        "runtime": {"required_core": "0.3.0"},
        "verification": {
            "software_tests": test_result,
            "independent_validation": False,
            "claim_boundary": "Package integrity and repository tests do not independently validate scientific or physical performance claims.",
        },
        "evidence_class_counts": classifications,
        "files": manifest_files,
    }

    manifest_path = bundle_dir / "MANIFEST.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True))

    sums_path = bundle_dir / "SHA256SUMS"
    sums_path.write_text("".join(f"{x['sha256']}  {x['path']}\n" for x in manifest_files))

    status = {
        "system": "EDEN OS",
        "delivery_status": "PACKAGED",
        "software_test_gate": "PASS" if test_result.get("passed") else ("SKIPPED" if test_result.get("skipped") else "NOT_CLEARED"),
        "integrity_manifest": "SHA256",
        "authentication": "HMAC-SHA256" if os.getenv("EDEN_DELIVERY_SIGNING_KEY") else "UNSIGNED",
        "independent_validation": False,
        "physical_measurements": "included where present in repository/worktree; retain each artifact's own evidence boundary",
    }
    (bundle_dir / "DELIVERY_STATUS.json").write_text(json.dumps(status, indent=2, sort_keys=True))

    key = os.getenv("EDEN_DELIVERY_SIGNING_KEY")
    if key:
        sig = hmac.new(key.encode(), manifest_path.read_bytes(), hashlib.sha256).hexdigest()
        (bundle_dir / "MANIFEST.hmac-sha256").write_text(sig + "\n")

    archive = OUT / f"EDEN-DELIVERY-{stamp}.tar.gz"
    with tarfile.open(archive, "w:gz") as tf:
        tf.add(bundle_dir, arcname=bundle_dir.name)
        for p in files:
            tf.add(p, arcname=str(Path(bundle_dir.name) / "repository" / p.relative_to(ROOT)))

    archive_sha = sha256_file(archive)
    (OUT / f"{archive.name}.sha256").write_text(f"{archive_sha}  {archive.name}\n")

    print("=" * 72)
    print(" EDEN DELIVERY PACKAGE")
    print("=" * 72)
    print(f"Archive: {archive}")
    print(f"SHA256:  {archive_sha}")
    print(f"Tests:   {status['software_test_gate']}")
    print(f"Auth:    {status['authentication']}")
    print(f"Commit:  {head}")
    print("Independent validation: NO")
    return 0 if test_result.get("passed") or test_result.get("skipped") else 2


def main():
    ap = argparse.ArgumentParser(description="Build one integrity-bound EDEN delivery package from all current components and evidence artifacts.")
    ap.add_argument("--skip-tests", action="store_true", help="Package without running the software verification gate")
    args = ap.parse_args()
    raise SystemExit(build(not args.skip_tests))


if __name__ == "__main__":
    main()
