# EDEN Core v0.1

EDEN Core turns the evidence repository into a continuously running local runtime while keeping the experiment files as reproducible evidence.

## What is live in v0.1

- Persistent local process
- `eden start`, `eden status`, `eden stop`
- `/health`, `/telemetry`, `/evidence`
- `/marbles/mint`, `/marbles/verify`
- Uses the repository's existing Marble v2 implementation
- Runtime state under `.eden-core/`
- Evidence artifacts remain in their existing repository locations and are never rewritten by EDEN Core

## Component truth state

EDEN Core intentionally distinguishes implemented modules from research/documentation:

- Marble: **ACTIVE** — callable Marble v2 implementation
- Refinery: **AVAILABLE** — current repository benchmark/tools
- ChronoNav: **DOCUMENTED** — no callable module detected in this repository revision
- Chrysalis: **NOT_WIRED** — no callable module detected
- Telemetry: **ACTIVE**
- Evidence store: **ACTIVE**

This prevents the runtime status page from turning architectural names into unsupported implementation claims.

## Termux quick start

```bash
cd ~/eden-os-evidence
git checkout eden-core-v0.1
chmod +x bin/eden
./bin/eden start
./bin/eden status
```

Health:

```bash
curl -s http://127.0.0.1:8766/health
```

Telemetry:

```bash
curl -s http://127.0.0.1:8766/telemetry
```

Stop:

```bash
./bin/eden stop
```

## Always-on Termux

After confirming the foreground runtime works, keep Android from suspending Termux:

```bash
termux-wake-lock
./bin/eden start
```

For Termux:Boot, create `~/.termux/boot/start-eden`:

```bash
#!/data/data/com.termux/files/usr/bin/bash
termux-wake-lock
cd "$HOME/eden-os-evidence"
./bin/eden start
```

## Evidence preservation

EDEN Core treats existing experiment JSON as immutable evidence inputs. It scans the repository for JSON artifacts to report evidence-store health, but does not modify them. Runtime state is stored separately in `.eden-core/state.json`.

## Marble API

Minting expects a Marble v2 core matching the existing schema:

```bash
curl -s -X POST http://127.0.0.1:8766/marbles/mint \
  -H 'Content-Type: application/json' \
  --data-binary @marble/fixtures/marble_execution_core.json
```

Verification accepts a complete Marble v2 JSON object:

```bash
curl -s -X POST http://127.0.0.1:8766/marbles/verify \
  -H 'Content-Type: application/json' \
  --data-binary @marble.json
```

Cryptographic integrity establishes integrity of the committed Marble record; it does not by itself prove the truth of a scientific or economic claim recorded inside that Marble.
