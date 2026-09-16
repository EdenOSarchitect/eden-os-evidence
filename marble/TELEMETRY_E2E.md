# EDEN-MARBLE-E2E-001 — Full Telemetry → Verified Marble

This is the acceptance path for the long-lived `eden.marble.v2` infrastructure.

```text
RAW TELEMETRY
    ↓ SHA-256 commitment
NORMALIZE MEASUREMENTS
    ↓ per-resource instrumentation + measurement_ref
EXECUTION MARBLE v2
    ↓ whole-core event identity
PRIMARY VERIFIER
    ↓
INDEPENDENT IDENTITY VERIFIER
    ↓
CRV ENFORCEMENT
    ↓
TIMESTAMP ANCHOR
    ↓
DETACHED SIGNATURE
    ↓
PERSISTENT PROVENANCE HEAD
    ↓
APPEND-ONLY TRANSPARENCY LOG
    ↓
VERIFIED E2E ARTIFACT
```

## Input contract

A telemetry envelope identifies its source, evidence class, workload, policy, provenance sequence, measurements and instrumentation. Every non-null resource measurement must have an instrument record. The E2E pipeline does not promote evidence classes: a CI/synthetic input remains `SIMULATED`; a model remains `MODELLED`; a physical/provider measurement may be `MEASURED` only when the supplied evidence and instrumentation justify that label.

The current normalized resource surface is:

- `tokens_in`
- `tokens_out`
- `cpu_seconds`
- `gpu_seconds`
- `memory_peak_bytes`
- `network_bytes`
- `storage_bytes`
- `joules`
- `wall_time_ms`
- `cost`
- `deadline_met`

Additional resource surfaces can be added inside v2 without changing the event model.

## Output artifact

`telemetry_e2e.py run` emits one JSON object with profile `eden.marble.v2.telemetry-e2e`. It contains:

- raw telemetry SHA-256 commitment and byte count;
- normalized telemetry;
- the minted EXECUTION Marble;
- primary verification result;
- independent identity-verifier result;
- resource provenance verification;
- CRV verification;
- detached signature verification when signing is enabled;
- timestamp anchor;
- persistent provenance-head record when requested;
- transparency-log entry and chain verification when requested;
- a domain-separated `artifact_id` over the complete E2E output;
- `e2e_verified` acceptance state;
- `scientific_truth_implied: false`.

## Acceptance rule

`e2e_verified` is true only when all applicable gates pass:

```text
structurally_valid
AND integrity_verified
AND provenance_verified
AND policy_verified
AND evidence_verified
AND resource_provenance_verified
AND timestamp_anchor_verified
AND independent_identity_verified
AND CRV_within_delegation
AND transparency_log_verified
AND signature_not_failed
```

A signed CI run additionally requires the detached signature to verify.

## Fail-closed cases

The regression suite exercises at least:

- Marble/resource tampering;
- E2E artifact tampering;
- missing instrumentation for non-null resource telemetry;
- CRV resource-budget violation;
- wrong signing key / wrong Marble identity;
- timestamp-anchor mutation;
- transparency-log mutation;
- provenance replay/regression;
- corrupt persisted provenance state;
- attempted self-promotion of a local record into hardware-backed attestation.

## CI artifact

The `marble-life-001` workflow runs the full pipeline against `marble/fixtures/full-telemetry-ci.json` and publishes an Actions artifact named:

```text
EDEN-MARBLE-E2E-001
```

The artifact contains:

```text
EDEN-MARBLE-E2E-001.json
providence.jsonl
provenance-head.json
```

The CI fixture is explicitly `SIMULATED`; its joules, cost and other resource values are synthetic test telemetry and are not physical/provider measurements. CI therefore proves the software evidence pipeline and verification behavior, not those external physical/economic claims.

## Local run

```bash
export EDEN_MARBLE_SIGNING_KEY='replace-with-secret'
mkdir -p artifacts/marble-e2e state

python marble/telemetry_e2e.py run \
  telemetry.json \
  --output artifacts/marble-e2e/EDEN-MARBLE-E2E-001.json \
  --log artifacts/marble-e2e/providence.jsonl \
  --head state/provenance-head.json \
  --key-id local-2026

python marble/telemetry_e2e.py verify \
  artifacts/marble-e2e/EDEN-MARBLE-E2E-001.json
```

This E2E contract is intended to accept telemetry from Refinery, ChronoNav, CRV execution, RF/transport, Manifold ingress, provider workloads and future device integrations while retaining the same Marble v2 evidence fabric.
