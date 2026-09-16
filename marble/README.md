# MARBLE-LIFE-001 — EDEN Marble v2

Marble v2 turns the EDEN evidence object from a terminal receipt into an immutable event in an evidence/accountability graph. The design goal is for `eden.marble.v2` to be a long-lived format rather than requiring a Marble v3 for each new assurance capability.

## Stable event identity

A Marble commits to its trusted scientific/execution core, including kind, subject, lineage, actor, policy, inputs, outputs, resources, quality, evidence class, truth boundary, provenance and timestamp.

```text
marble_id = SHA256("EDEN-MARBLE-V2\\0" || canonical_json(committed_core))
```

`marble_id`, detached `signature`, derived `verification`, and the optional `assurance` envelope are excluded from the event identity. This is intentional: signatures can rotate, timestamp/log anchors can accrue, and external attestation/reproduction evidence can arrive later without changing the identity of the original event.

Mutation of a committed scientific/execution field still changes the Marble identifier.

Cryptographic integrity proves integrity of the committed record. It does not independently prove that a scientific, physical, commercial or identity claim is true.

## First-class event kinds

- `OBSERVATION` — bytes, telemetry, sensor/provider output or another observation entered the evidence graph.
- `DECISION` — a policy/scheduler/refinery/authorization decision was made.
- `EXECUTION` — an action actually occurred.
- `ASSERTION` — a conclusion was derived from evidence.
- `VERIFICATION` — verification results were produced.
- `ACCOUNTING` — resources/value/cost were accounted.
- `REFUTATION` — a later record challenges or supersedes an earlier claim without mutating history.

## Multi-state verification

A Marble is not reduced to one overloaded `VALID` bit. The reference verifier reports separate states for event integrity, provenance, policy, evidence class, per-resource measurement provenance, timestamp anchoring, attestation and independent reproduction.

A committed `MEASURED` label is not enough by itself; named instrumentation is required. Non-null resource values can additionally carry `evidence.resource_provenance.<resource>` records containing their instrument and measurement reference. `INDEPENDENTLY_VALIDATED` additionally requires an external reproduction reference.

## Assurance envelope

Optional assurance can be added to an already-minted v2 Marble without changing `marble_id`.

Implemented reference primitives include:

- HMAC-SHA256 detached software signing with explicit `key_id` and key rotation support through a keyring;
- software timestamp anchors with explicit truth distinction between `LOCAL_SOFTWARE` and an external authority reference;
- append-only JSONL transparency-log chaining with index, previous-entry hash and fail-closed verification;
- atomically persisted provenance-head state with monotonic sequence enforcement and corruption detection;
- device/source attestation records with explicit separation between software credentials and externally evidenced hardware-backed attestation;
- per-resource measurement provenance;
- portable verifier bundles;
- a second identity verifier implementation that does not import the primary Marble verifier.

The reference HMAC signer is an immediately runnable software mechanism. Production deployments can add asymmetric/HSM/KMS signatures as additional assurance schemes without changing the `eden.marble.v2` event format.

## Attestation truth boundary

A local record cannot promote itself to hardware-backed identity. If `hardware_backed=true`, the reference verifier only records the stronger state when an external verifier and evidence reference are present. This still records an attestation reference; validation of the external attestation evidence remains the responsibility of the corresponding verifier/integration.

The same principle applies to timestamping: local anchoring proves deterministic binding to a local observation record, not trusted third-party time.

## Lineage and persistent provenance

`parents` links Marbles into a DAG. `verify_lineage()` rejects missing parent references and cycles within the supplied graph.

For process-to-process continuity, `assurance.persist_head()` stores a hash-protected provenance head atomically. Sequence replay/regression and corrupt state fail closed.

Derived records do not automatically inherit a parent's evidence class.

## Transparency anchoring

`assurance.append_log()` creates an append-only hash chain over Marble identities. Before appending it verifies the existing chain and refuses to extend a corrupted log. `verify_log()` independently checks ordering, previous-entry links and entry hashes.

The local log is not presented as a public transparency service. A deployment can publish or externally anchor its log head without changing Marble v2.

## CRV accounting

`verify_crv(allocation, observed)` checks measured resource usage against delegated limits. CRV results can be recorded as VERIFICATION or ACCOUNTING Marbles so allocation, execution and post-execution resource accounting remain separate events.

## Independent verifier path

`marble/independent_verify.py` intentionally does not import the primary `marble.py` implementation. CI requires both implementations to compute the same identity for the fixture. This is implementation diversity, not independent third-party validation.

## CLI

Mint and verify:

```bash
python marble/marble.py mint core.json > marble.json
python marble/marble.py verify marble.json
python marble/marble.py assurance marble.json
```

Independent identity verification:

```bash
python marble/independent_verify.py marble.json
```

Detached software signature using an environment-held key:

```bash
export EDEN_MARBLE_SIGNING_KEY='replace-with-secret'
python marble/assure.py sign marble.json --key-id local-2026 > signature.json
python marble/assure.py verify-signature marble.json signature.json --key-id local-2026
```

Timestamp and transparency operations:

```bash
python marble/assure.py timestamp-anchor marble.json > timestamp.json
python marble/assure.py log-append marble.json providence.jsonl
python marble/assure.py log-verify providence.jsonl
```

Persistent provenance head:

```bash
python marble/assure.py head-update marble.json state/provenance-head.json
python marble/assure.py head-show state/provenance-head.json
```

Portable independent-verifier bundle:

```bash
python marble/assure.py bundle marble.json > marble-verifier-bundle.json
```

Run regression tests:

```bash
python -m unittest discover -s marble/tests -p 'test_*.py' -v
```

## Long-lived v2 boundary

MARBLE-LIFE-001 now includes the software infrastructure needed for signatures, evolving assurance, persistent provenance, transparency chaining, measurement provenance and attestation integration while retaining `eden.marble.v2`.

What cannot be created by repository code alone remains explicitly external: possession of real hardware-rooted device credentials, a third-party timestamp authority response, HSM/KMS custody, or an external party's independent reproduction. Marble v2 has slots and verification boundaries for those artifacts without falsely claiming they already exist.
