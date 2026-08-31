# EDEN Marble Off-Ramp Gateway

The Marble Gateway is the boundary between EDEN's internal Marble evidence fabric and an external system.

```text
EDEN Core -> Marble v2 -> VERIFY -> DESTINATION POLICY -> OFF-RAMP -> external system
```

## First implemented off-ramp

The initial implementation is an HTTPS webhook POST in `marble/gateway.py`.

A Marble is blocked unless all of the following required checks pass:

- Marble v2 structural and integrity verification
- committed policy verification
- provenance verification
- evidence-boundary verification
- destination policy validation
- HTTPS destination by default
- no loopback/private/link-local destination by default

The gateway sends a canonical JSON envelope containing the Marble, verification result, gateway timestamp, destination and a SHA-256 commitment over the envelope.

## Dry-run authorization

Use dry-run before connecting a real endpoint:

```bash
python -m marble.gateway marble/fixtures/example-execution-core.json https://example.com/eden --dry-run
```

The input must be a minted Marble v2 containing `marble_id`. A successful dry-run returns:

```text
status = AUTHORIZED_DRY_RUN
transmitted = false
```

No network request is made in dry-run mode.

## Live HTTPS route

```bash
python -m marble.gateway /path/to/minted-marble.json https://receiver.example/v1/marbles
```

A successful POST returns `status = TRANSMITTED` and records the HTTP status. The receiver also gets:

- `X-EDEN-Marble-ID`
- `X-EDEN-Envelope-SHA256`

## Local controlled testing

Private and loopback destinations are blocked by default. They may be explicitly enabled for a controlled test environment:

```bash
python -m marble.gateway /path/to/minted-marble.json https://127.0.0.1:8765/eden --allow-private-network
```

TLS is still required by the default destination policy.

## Security and truth boundary

The gateway authorizes transport of a committed record. It does not independently prove that scientific or commercial claims inside that record are true. `MEASURED` evidence must still satisfy the Marble verifier's instrumentation requirement, and `INDEPENDENTLY_VALIDATED` evidence must carry its reproduction reference.

An authorized Marble also does **not** by itself create a debt, invoice, entitlement, payment obligation or settlement instruction. Commercial settlement requires a separate agreement or policy layer.

## Planned adapters

The same verify/policy boundary can support later adapters without changing Marble identity:

- evidence/archive storage
- cloud/FinOps telemetry
- billing record generation
- audit and assurance export
- queues/event buses
- machine-action controllers
- settlement systems

All adapters should consume the same verified gateway envelope rather than implementing weaker per-adapter verification logic.
