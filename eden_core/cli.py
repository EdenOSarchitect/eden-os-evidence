#!/usr/bin/env python3
"""Command-line control for EDEN Core."""
from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import urlopen

from .core import EdenCore

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8766


def repo_root() -> Path:
    return Path(os.environ.get("EDEN_REPO_ROOT", Path.cwd())).resolve()


def runtime_dir() -> Path:
    path = Path(os.environ.get("EDEN_CORE_STATE_DIR", repo_root() / ".eden-core"))
    path.mkdir(parents=True, exist_ok=True)
    return path


def pid_path() -> Path:
    return runtime_dir() / "eden-core.pid"


def log_path() -> Path:
    return runtime_dir() / "eden-core.log"


def read_pid() -> int | None:
    try:
        return int(pid_path().read_text().strip())
    except Exception:
        return None


def is_alive(pid: int | None) -> bool:
    if not pid:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def start(args) -> int:
    pid = read_pid()
    if is_alive(pid):
        print(f"EDEN CORE already running pid={pid}")
        return 0
    log = open(log_path(), "ab", buffering=0)
    cmd = [sys.executable, "-m", "eden_core.cli", "serve", "--host", args.host, "--port", str(args.port)]
    proc = subprocess.Popen(
        cmd,
        cwd=str(repo_root()),
        stdout=log,
        stderr=subprocess.STDOUT,
        start_new_session=True,
        env={**os.environ, "EDEN_REPO_ROOT": str(repo_root()), "EDEN_CORE_STATE_DIR": str(runtime_dir())},
    )
    pid_path().write_text(str(proc.pid))
    for _ in range(30):
        time.sleep(0.1)
        try:
            with urlopen(f"http://{args.host}:{args.port}/health", timeout=0.5) as r:
                if r.status == 200:
                    print(f"EDEN CORE ONLINE pid={proc.pid} http://{args.host}:{args.port}")
                    return 0
        except Exception:
            pass
    print(f"EDEN CORE started pid={proc.pid}; health endpoint not ready yet. See {log_path()}")
    return 0


def stop(args) -> int:
    pid = read_pid()
    if not is_alive(pid):
        print("EDEN CORE is not running")
        pid_path().unlink(missing_ok=True)
        return 0
    os.kill(pid, signal.SIGTERM)
    for _ in range(30):
        time.sleep(0.1)
        if not is_alive(pid):
            break
    pid_path().unlink(missing_ok=True)
    print("EDEN CORE stopped")
    return 0


def status(args) -> int:
    pid = read_pid()
    try:
        with urlopen(f"http://{args.host}:{args.port}/telemetry", timeout=1.0) as r:
            t = json.loads(r.read().decode())
        print("EDEN CORE")
        print("=" * 48)
        print(f"State            {t['status']}")
        print(f"PID              {t['host']['pid']}")
        print(f"Uptime           {t['uptime_seconds']:.1f}s")
        print(f"Marbles minted   {t['counters']['marbles_minted']}")
        print(f"Marbles verified {t['counters']['marbles_verified']}")
        print(f"Marbles void     {t['counters']['marbles_void']}")
        print(f"Evidence JSON    {t['evidence']['json_artifacts']}")
        print()
        for name, comp in t["components"].items():
            print(f"{name:<16} {comp['state']}")
        return 0
    except Exception:
        print(f"EDEN CORE OFFLINE pid={pid if pid else '-'}")
        return 1


def serve(args) -> int:
    core = EdenCore(repo_root=repo_root(), state_dir=runtime_dir())
    core.serve(args.host, args.port)
    return 0


def main() -> int:
    p = argparse.ArgumentParser(prog="eden", description="EDEN Core control")
    sub = p.add_subparsers(dest="command", required=True)
    for name in ("start", "stop", "status", "serve"):
        s = sub.add_parser(name)
        s.add_argument("--host", default=DEFAULT_HOST)
        s.add_argument("--port", default=DEFAULT_PORT, type=int)
    args = p.parse_args()
    return {"start": start, "stop": stop, "status": status, "serve": serve}[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
