# EDEN OS Launcher

The EDEN OS launcher turns the existing EDEN Core runtime into a single front door for boot, diagnostics, status, logs, restart, and shutdown.

## Termux quick start

From the repository root:

```bash
chmod +x bin/eden
./bin/eden
```

Running `./bin/eden` with no arguments now performs launch preflight checks, starts EDEN Core in the background, waits for the local health endpoint, then prints integrated runtime status.

## Commands

```bash
./bin/eden                 # launch EDEN OS
./bin/eden launch          # explicit launch
./bin/eden doctor          # environment/component preflight
./bin/eden status          # live runtime + component state
./bin/eden logs            # last 80 log lines
./bin/eden logs --lines 200
./bin/eden restart         # safe stop + relaunch
./bin/eden stop            # safe shutdown
./bin/eden serve           # foreground runtime
```

The default local runtime endpoint remains `127.0.0.1:8766`. Commands that use the runtime endpoint accept `--host` and `--port`.

## Launcher model

The launcher does not replace the evidence repository or rewrite historical experiments. It orchestrates the existing integrated runtime and reports the state already exposed by EDEN Core: Refinery, ChronoNav, Chrysalis, Marble, assurance, telemetry, and the evidence store.

Preflight treats Python, the EDEN repository, and a writable runtime-state directory as launch-critical. Optional component directories are reported as warnings so the launcher can still expose partial/development installations without falsely claiming those components are present.

PID handling preserves the existing safety boundary: EDEN will only terminate a PID when `/proc/<pid>/cmdline` identifies it as the EDEN Core serve process. A stale PID that belongs to another process is removed from EDEN state, but that process is not terminated.

Runtime state and logs are stored under `.eden-core/` by default. Override this with `EDEN_CORE_STATE_DIR`. Override repository discovery with `EDEN_REPO_ROOT`.
