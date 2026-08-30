import json
import os
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from urllib.request import Request, urlopen


REPO_ROOT = Path(__file__).resolve().parents[2]
HOST = "127.0.0.1"
PORT = 18766
BASE = f"http://{HOST}:{PORT}"


def get_json(path: str):
    with urlopen(BASE + path, timeout=2.0) as response:
        return json.loads(response.read().decode("utf-8"))


def post_json(path: str, payload):
    request = Request(
        BASE + path,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=2.0) as response:
        return json.loads(response.read().decode("utf-8"))


class LauncherIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.state_dir = Path(self.tempdir.name) / "state"
        self.env = {
            **os.environ,
            "EDEN_REPO_ROOT": str(REPO_ROOT),
            "EDEN_CORE_STATE_DIR": str(self.state_dir),
        }

    def tearDown(self):
        self.run_eden("stop", check=False)
        self.tempdir.cleanup()

    def run_eden(self, command: str, check: bool = True):
        args = ["bash", "bin/eden", command]
        if command in {"launch", "start", "stop", "status", "restart"}:
            args += ["--host", HOST, "--port", str(PORT)]
        return subprocess.run(
            args,
            cwd=REPO_ROOT,
            env=self.env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=20,
            check=check,
        )

    def wait_health(self):
        deadline = time.time() + 5
        while time.time() < deadline:
            try:
                health = get_json("/health")
                if health.get("status") == "ok":
                    return health
            except Exception:
                time.sleep(0.1)
        self.fail("EDEN Core /health did not become ready")

    def test_full_launcher_lifecycle_and_runtime_surfaces(self):
        doctor = self.run_eden("doctor")
        self.assertIn("READY", doctor.stdout)

        launch = self.run_eden("launch")
        self.assertIn("EDEN CORE ONLINE", launch.stdout)
        health = self.wait_health()
        self.assertEqual(health["marble"], "ACTIVE")
        self.assertEqual(health["chrysalis"], "ACTIVE")

        telemetry = get_json("/telemetry")
        self.assertEqual(telemetry["status"], "ONLINE")
        self.assertEqual(telemetry["components"]["marble"]["state"], "ACTIVE")
        self.assertEqual(telemetry["components"]["chrysalis"]["state"], "ACTIVE")

        chrysalis = post_json("/chrysalis/evaluate", {
            "baseline": {"quality": 1.0, "total": 100},
            "policy": {
                "minimum_quality": 0.995,
                "minimum_net_reduction_fraction": 0.10,
            },
            "candidates": [{
                "id": "integration-candidate",
                "quality": 0.999,
                "active": 70,
                "metadata": 2,
                "recovery": 1,
                "regeneration": 3,
                "orchestration": 2,
            }],
        })
        self.assertEqual(chrysalis["status"], "SELECTED")

        marble_core = {
            "kind": "EXECUTION",
            "subject": {"name": "eden-core-integration"},
            "parents": [],
            "actor": {"id": "github-actions", "attestation": "UNATTESTED"},
            "policy": {"policy_id": "EDEN-CORE-CI", "policy_hash": "sha256:ci"},
            "input": {"sha256": "sha256:integration-input"},
            "output": {"sha256": "sha256:integration-output"},
            "resources": {"cpu_seconds": 0.0},
            "quality": {"status": "PASS"},
            "evidence": {
                "class": "IMPLEMENTED",
                "instrumentation": ["eden-core-integration-ci"],
            },
            "truth": {
                "claims": ["launcher/runtime integration executed"],
                "not_claimed": ["physical energy advantage"],
            },
            "provenance": {"sequence": 0},
        }
        marble = post_json("/marbles/mint", marble_core)
        verified = post_json("/marbles/verify", marble)
        self.assertTrue(verified["integrity_verified"])

        state_path = self.state_dir / "state.json"
        self.assertTrue(state_path.exists())
        before_restart = json.loads(state_path.read_text(encoding="utf-8"))
        self.assertGreaterEqual(before_restart["counters"]["marbles_minted"], 1)
        self.assertGreaterEqual(before_restart["counters"]["chrysalis_evaluations"], 1)

        restart = self.run_eden("restart")
        self.assertIn("EDEN CORE ONLINE", restart.stdout)
        self.wait_health()

        stop = self.run_eden("stop")
        self.assertIn("EDEN CORE stopped", stop.stdout)

    def test_stale_pid_is_removed_without_killing_unrelated_process(self):
        self.state_dir.mkdir(parents=True, exist_ok=True)
        sleeper = subprocess.Popen(["sleep", "10"])
        try:
            (self.state_dir / "eden-core.pid").write_text(str(sleeper.pid), encoding="utf-8")
            result = self.run_eden("stop", check=False)
            self.assertEqual(result.returncode, 2)
            self.assertIn("REFUSED", result.stdout)
            self.assertIsNone(sleeper.poll())
            self.assertFalse((self.state_dir / "eden-core.pid").exists())
        finally:
            sleeper.terminate()
            sleeper.wait(timeout=5)


if __name__ == "__main__":
    unittest.main()
