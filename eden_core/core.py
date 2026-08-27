#!/usr/bin/env python3
"""EDEN Core v0.2.

Persistent, dependency-light runtime for the EDEN evidence repository.
The runtime exposes local health/telemetry endpoints, preserves experiment
artifacts, and uses the existing Marble v2 reference implementation for mint
and verification. Components retain explicit evidence/truth boundaries.
"""
from __future__ import annotations

import json
import os
import platform
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict

from chrysalis import evaluate as chrysalis_evaluate
from marble import mint, verify_integrity

VERSION = "0.2.0"


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class EdenCore:
    def __init__(self, repo_root: Path | None = None, state_dir: Path | None = None) -> None:
        self.repo_root = Path(repo_root or Path.cwd()).resolve()
        self.state_dir = Path(
            state_dir
            or os.environ.get("EDEN_CORE_STATE_DIR", self.repo_root / ".eden-core")
        ).resolve()
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.started_monotonic = time.monotonic()
        self.started_at = utcnow()
        self._lock = threading.Lock()
        self._counters = {
            "marbles_minted": 0,
            "marbles_verified": 0,
            "marbles_void": 0,
            "chrysalis_evaluations": 0,
        }

    @property
    def state_path(self) -> Path:
        return self.state_dir / "state.json"

    def component_state(self) -> Dict[str, Dict[str, str]]:
        return {
            "refinery": {
                "state": "AVAILABLE" if (self.repo_root / "eden-refinery").exists() else "MISSING",
                "implementation": "BENCHMARK/TOOLS",
            },
            "chrononav": {
                "state": "DOCUMENTED" if (self.repo_root / "chrononav" / "README.md").exists() else "MISSING",
                "implementation": "DOCUMENTATION_ONLY",
            },
            "chrysalis": {
                "state": "ACTIVE",
                "implementation": "EXPERIMENTAL_NET_RESOURCE_EVALUATOR",
            },
            "marble": {
                "state": "ACTIVE",
                "implementation": "marble.marble v2",
            },
            "assurance": {
                "state": "ACTIVE",
                "implementation": "MARBLE_INTEGRITY_BOUNDARIES",
            },
            "telemetry": {"state": "ACTIVE", "implementation": "EDEN_CORE_STD_LIB"},
            "evidence_store": {
                "state": "ACTIVE",
                "implementation": "REPOSITORY_JSON_ARTIFACTS",
            },
        }

    def evidence_summary(self) -> Dict[str, Any]:
        candidates = []
        for folder in ("marble", "energy", "validation-builds", "eden-refinery", "chrysalis"):
            root = self.repo_root / folder
            if root.exists():
                candidates.extend(root.rglob("*.json"))
        files = [p for p in candidates if ".eden-core" not in p.parts]
        total_bytes = sum(p.stat().st_size for p in files if p.is_file())
        newest = None
        if files:
            p = max(files, key=lambda x: x.stat().st_mtime)
            newest = str(p.relative_to(self.repo_root))
        return {
            "json_artifacts": len(files),
            "bytes": total_bytes,
            "newest": newest,
        }

    def telemetry(self) -> Dict[str, Any]:
        with self._lock:
            counters = dict(self._counters)
        return {
            "system": "EDEN CORE",
            "version": VERSION,
            "status": "ONLINE",
            "started_at": self.started_at,
            "uptime_seconds": round(time.monotonic() - self.started_monotonic, 3),
            "timestamp_utc": utcnow(),
            "host": {
                "platform": platform.platform(),
                "python": platform.python_version(),
                "pid": os.getpid(),
            },
            "components": self.component_state(),
            "counters": counters,
            "evidence": self.evidence_summary(),
        }

    def health(self) -> Dict[str, Any]:
        t = self.telemetry()
        return {
            "status": "ok",
            "system": t["system"],
            "version": t["version"],
            "uptime_seconds": t["uptime_seconds"],
            "marble": t["components"]["marble"]["state"],
            "chrysalis": t["components"]["chrysalis"]["state"],
            "evidence_store": t["components"]["evidence_store"]["state"],
        }

    def persist_state(self) -> Dict[str, Any]:
        state = self.telemetry()
        tmp = self.state_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")
        tmp.replace(self.state_path)
        return state

    def mint_marble(self, core: Dict[str, Any]) -> Dict[str, Any]:
        result = mint(core)
        with self._lock:
            self._counters["marbles_minted"] += 1
        self.persist_state()
        return result

    def verify_marble(self, marble: Dict[str, Any]) -> Dict[str, Any]:
        result = verify_integrity(marble)
        with self._lock:
            self._counters["marbles_verified"] += 1
            if not result.get("integrity_verified"):
                self._counters["marbles_void"] += 1
        self.persist_state()
        return result

    def evaluate_chrysalis(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        result = chrysalis_evaluate(payload)
        with self._lock:
            self._counters["chrysalis_evaluations"] += 1
        self.persist_state()
        return result

    def handler_class(self):
        core = self

        class Handler(BaseHTTPRequestHandler):
            server_version = f"EDEN-Core/{VERSION}"

            def _write(self, status: int, payload: Any) -> None:
                body = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _json_body(self) -> Dict[str, Any]:
                length = int(self.headers.get("Content-Length", "0"))
                raw = self.rfile.read(length) if length else b"{}"
                value = json.loads(raw.decode("utf-8"))
                if not isinstance(value, dict):
                    raise ValueError("JSON body must be an object")
                return value

            def do_GET(self) -> None:  # noqa: N802
                if self.path == "/health":
                    self._write(200, core.health())
                elif self.path == "/telemetry":
                    self._write(200, core.telemetry())
                elif self.path == "/evidence":
                    self._write(200, core.evidence_summary())
                elif self.path == "/":
                    self._write(200, {
                        "system": "EDEN CORE",
                        "version": VERSION,
                        "endpoints": [
                            "/health",
                            "/telemetry",
                            "/evidence",
                            "/chrysalis/evaluate",
                            "/marbles/mint",
                            "/marbles/verify",
                        ],
                    })
                else:
                    self._write(404, {"error": "not_found"})

            def do_POST(self) -> None:  # noqa: N802
                try:
                    payload = self._json_body()
                    if self.path == "/marbles/mint":
                        self._write(200, core.mint_marble(payload))
                    elif self.path == "/marbles/verify":
                        self._write(200, core.verify_marble(payload))
                    elif self.path == "/chrysalis/evaluate":
                        self._write(200, core.evaluate_chrysalis(payload))
                    else:
                        self._write(404, {"error": "not_found"})
                except Exception as exc:
                    self._write(400, {"error": type(exc).__name__, "message": str(exc)})

            def log_message(self, fmt: str, *args: Any) -> None:
                return

        return Handler

    def serve(self, host: str = "127.0.0.1", port: int = 8766) -> None:
        self.persist_state()
        server = ThreadingHTTPServer((host, port), self.handler_class())
        print(f"EDEN CORE {VERSION} ONLINE http://{host}:{port}", flush=True)
        try:
            server.serve_forever(poll_interval=0.5)
        finally:
            server.server_close()
            self.persist_state()
