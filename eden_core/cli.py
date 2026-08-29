#!/usr/bin/env python3
"""Command-line launcher and control surface for EDEN OS."""
from __future__ import annotations

import argparse
import json
import os
import platform
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


def process_cmdline(pid: int | None) -> str:
    if not pid:
        return ""
    try:
        raw = Path(f"/proc/{pid}/cmdline").read_bytes()
        return raw.replace(b"\x00", b" ").decode("utf-8", errors="replace").strip()
    except Exception:
        return ""


def is_eden_core_process(pid: int | None) -> bool:
    """Return True only when pid is a live EDEN Core serve process."""
    if not is_alive(pid):
        return False
    cmdline = process_cmdline(pid)
    return "eden_core.cli" in cmdline and "serve" in cmdline


def clear_stale_pid() -> None:
    pid = read_pid()
    if pid and not is_eden_core_process(pid):
        pid_path().unlink(missing_ok=True)


def banner() -> None:
    print("=" * 58)
    print(" EDEN OS :: LAUNCHER")
    print(" Evidence-bound integrated runtime")
    print("=" * 58)


def preflight() -> tuple[bool, list[tuple[str, bool, str]]]:
    root = repo_root()
    checks: list[tuple[str, bool, str]] = []
    checks.append(("Python", sys.version_info >= (3, 10), platform.python_version()))
    checks.append(("Repository", (root / "eden_core").is_dir(), str(root)))
    checks.append(("Marble", (root / "marble").is_dir(), "marble/"))
    checks.append(("Chrysalis", (root / "chrysalis").is_dir(), "chrysalis/"))
    checks.append(("Refinery", (root / "eden-refinery").is_dir(), "eden-refinery/"))
    checks.append(("ChronoNav", (root / "chrononav").is_dir(), "chrononav/"))
    try:
        probe = runtime_dir() / ".write-test"
        probe.write_text("eden", encoding="utf-8")
        probe.unlink(missing_ok=True)
        writable = True
    except OSError:
        writable = False
    checks.append(("Runtime state", writable, str(runtime_dir())))

    critical = {"Python", "Repository", "Runtime state"}
    ok = all(passed for name, passed, _ in checks if name in critical)
    return ok, checks


def doctor(args) -> int:
    ok, checks = preflight()
    print("EDEN OS PREFLIGHT")
    print("=" * 58)
    for name, passed, detail in checks:
        print(f"{'PASS' if passed else 'WARN':<5} {name:<16} {detail}")
    print("=" * 58)
    print("READY" if ok else "BLOCKED: fix failed launch-critical checks")
    return 0 if ok else 2


def start(args) -> int:
    pid = read_pid()
    if is_eden_core_process(pid):
        print(f"EDEN CORE already running pid={pid}")
        return 0
    clear_stale_pid()

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
    if proc.poll() is not None:
        pid_path().unlink(missing_ok=True)
        print(f"EDEN CORE failed to remain running. See {log_path()}")
        return 1
    print(f"EDEN CORE started pid={proc.pid}; health endpoint not ready yet. See {log_path()}")
    return 0


def stop(args) -> int:
    pid = read_pid()
    if not pid:
        print("EDEN CORE is not running")
        return 0
    if not is_alive(pid):
        pid_path().unlink(missing_ok=True)
        print("EDEN CORE is not running; stale PID file removed")
        return 0
    if not is_eden_core_process(pid):
        cmdline = process_cmdline(pid) or "<unavailable>"
        pid_path().unlink(missing_ok=True)
        print("REFUSED: stored PID does not belong to EDEN Core. No process was terminated.")
        print(f"PID={pid} cmdline={cmdline}")
        return 2

    os.kill(pid, signal.SIGTERM)
    for _ in range(30):
        time.sleep(0.1)
        if not is_alive(pid):
            break
    if is_alive(pid):
        print(f"EDEN CORE pid={pid} did not stop after SIGTERM; process left running")
        return 1
    pid_path().unlink(missing_ok=True)
    print(f"EDEN CORE stopped pid={pid}")
    return 0


def status(args) -> int:
    pid = read_pid()
    try:
        with urlopen(f"http://{args.host}:{args.port}/telemetry", timeout=1.0) as r:
            t = json.loads(r.read().decode())
        print("EDEN OS")
        print("=" * 58)
        print(f"State            {t['status']}")
        print(f"Version          {t['version']}")
        print(f"PID              {t['host']['pid']}")
        print(f"Uptime           {t['uptime_seconds']:.1f}s")
        print(f"Marbles minted   {t['counters']['marbles_minted']}")
        print(f"Marbles verified {t['counters']['marbles_verified']}")
        print(f"Marbles void     {t['counters']['marbles_void']}")
        print(f"Chrysalis evals  {t['counters'].get('chrysalis_evaluations', 0)}")
        print(f"Evidence JSON    {t['evidence']['json_artifacts']}")
        print()
        for name, comp in t["components"].items():
            print(f"{name:<16} {comp['state']}")
        return 0
    except Exception:
        if pid and is_alive(pid) and not is_eden_core_process(pid):
            print(f"EDEN CORE OFFLINE; stale/unrelated PID={pid} detected")
            return 2
        print(f"EDEN CORE OFFLINE pid={pid if pid else '-'}")
        return 1


def launch(args) -> int:
    banner()
    ok, checks = preflight()
    for name, passed, detail in checks:
        print(f"{'OK' if passed else '--':<3} {name:<16} {detail}")
    if not ok:
        print("\nLaunch blocked by a critical preflight check. Run: eden doctor")
        return 2
    print("\nStarting integrated runtime...")
    code = start(args)
    if code != 0:
        return code
    print()
    return status(args)


def restart(args) -> int:
    code = stop(args)
    if code != 0:
        return code
    return launch(args)


def logs(args) -> int:
    path = log_path()
    if not path.exists():
        print(f"No EDEN log yet: {path}")
        return 0
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    for line in lines[-args.lines:]:
        print(line)
    return 0


def serve(args) -> int:
    core = EdenCore(repo_root=repo_root(), state_dir=runtime_dir())
    core.serve(args.host, args.port)
    return 0


def add_network_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", default=DEFAULT_PORT, type=int)


def main() -> int:
    p = argparse.ArgumentParser(
        prog="eden",
        description="EDEN OS launcher and integrated runtime control",
        epilog="Run `eden` with no command to launch EDEN OS.",
    )
    sub = p.add_subparsers(dest="command")

    for name, help_text in (
        ("launch", "boot EDEN OS and show integrated status"),
        ("start", "start EDEN Core in the background"),
        ("stop", "stop EDEN Core safely"),
        ("status", "show live runtime and component state"),
        ("restart", "restart EDEN OS"),
        ("serve", "run EDEN Core in the foreground"),
    ):
        s = sub.add_parser(name, help=help_text)
        add_network_args(s)

    sub.add_parser("doctor", help="run launch preflight checks")
    l = sub.add_parser("logs", help="show recent EDEN Core logs")
    l.add_argument("--lines", type=int, default=80)

    args = p.parse_args()
    command = args.command or "launch"
    if args.command is None:
        args.host = DEFAULT_HOST
        args.port = DEFAULT_PORT

    handlers = {
        "launch": launch,
        "start": start,
        "stop": stop,
        "status": status,
        "restart": restart,
        "serve": serve,
        "doctor": doctor,
        "logs": logs,
    }
    return handlers[command](args)


if __name__ == "__main__":
    raise SystemExit(main())
