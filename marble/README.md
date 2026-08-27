# MARBLE-LIFE-001 — EDEN Marble v2

Marble v2 turns the EDEN evidence object from a terminal receipt into an immutable event in an evidence/accountability graph.

## Design goals

A Marble commits to its trusted core, including kind, subject, lineage, actor, policy, inputs, outputs, resources, quality, evidence class, truth boundary, provenance and timestamp.

The identifier is domain-separated:

```text
marble_id = SHA256("EDEN-MARBLE-V2\\0" || canonical_json(committed_core))
```

`marble_id`, detached `signature`, and derived `verification` output are excluded from the committed core. Any mutation to a committed field therefore changes the identifier.

Cryptographic integrity proves integrity of the committed record. It does not independently prove that a scientific, physical, commercial or identity claim is true.

## First-class event kinds

- `OBSERVATION` — bytes, telemetry, sensor/provider output or another observation entered the evidence graph.
- `DECISION` — a policy/scheduler/refinery/authorization decision was made.
- `EXECUTION` — an action actually occurred.
- `ASSERTION` — a conclusion was derived from evidence.
- `VERIFICATION` — verification results were produced.
- `ACCOUNTING` — resources/value/cost were accounted.
- `REFUTATION` — a later record challenges or supersedes an earlier claim without mutating history.

## Verification is multi-state

A Marble is not reduced to one overloaded `VALID` bit. The reference verifier reports separate states for:

```text
structurally_valid
integrity_verified
provenance_verified
policy_verified
evidence_verified
attestation
independent_replication
```

A committed `MEASURED` label is not by itself enough for `evidence_verified`; named instrumentation is required by the v2 reference verifier. `INDEPENDENTLY_VALIDATED` additionally requires an external reproduction reference.

## Lineage

`parents` links Marbles into a DAG. `verify_lineage()` rejects missing parent references and cycles within the supplied graph.

Derived records do not automatically inherit a parent's evidence class. For example, a model derived from measured input remains `MODELLED` unless its own output meets the conditions for another evidence class.

## CRV accounting

`verify_crv(allocation, observed)` checks measured resource usage against delegated limits. This is the first reference primitive for connecting EDEN's multidimensional resource vector to Marble accountability.

## CLI

Mint from a core JSON object:

```bash
python marble/marble.py mint core.json > marble.json
```

Verify one Marble:

```bash
python marble/marble.py verify marble.json
```

Verify a supplied lineage set:

```bash
python marble/marble.py lineage parent.json child.json
```

Run regression tests:

```bash
python -m unittest discover -s marble/tests -p 'test_*.py' -v
```

## Current boundary

This is a reference software implementation. It does not yet provide detached signing, hardware-backed device identity, timestamp authority, remote attestation, transparency-log anchoring, or independent validation. Those are intended higher assurance layers rather than claims of MARBLE-LIFE-001.
