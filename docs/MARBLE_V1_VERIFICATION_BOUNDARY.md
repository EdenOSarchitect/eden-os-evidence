# Marble v1 Verification Boundary

**Snapshot date:** 2026-08-26

This note records a known trust boundary in the current v1 Marble verification design.

## v1 identity binding

The v1 identity formula is:

```text
identity = sha256(runId | inputCommitment | outputCommitment | policyVersion | timestamp)
```

This binds the listed identity inputs. It does **not** by itself bind every descriptive field that may appear elsewhere in a Marble.

## Observed verification behavior

The current v1 handoff records the following expected behavior for validation/reproduction:

1. Clean Marble -> identity formula matches.
2. Tamper `policyVersion` or the outer `sha256` -> verifier should return `VOID`.
3. Tamper only mutable descriptive fields such as `evidence`, `provenance`, or `kind` -> v1 may still report `VALID` because those fields are not all re-derived/bound by the v1 verifier.
4. v1 mint leaves/counts are RAW-centric and should not be treated as a policy-aware semantic proof.
5. A policy-aware v2 pack must not be assumed to exist unless the actual implementation/artifact is present and verified.

## Security / evidence consequence

A v1 `VALID` result proves the committed v1 identity relationship that the verifier actually checks. It must not be interpreted as proof that every label, evidence descriptor, provenance string, kind field, or count in the surrounding object is authentic.

In particular, labels such as `MEASURED`, `AOK CLEARED`, or equivalent high-trust classifications must be treated as **untrusted metadata** unless the verifier cryptographically binds and/or independently re-derives the fields supporting those labels.

## Required v2 direction

A stronger Marble verifier should bind or re-derive at minimum:

- evidence class;
- provenance;
- kind/type;
- semantic/count fields used in downstream policy;
- verifier/policy version;
- input/output commitments;
- workload/run identity;
- any status label that can escalate trust or authorization.

The verification result should make the checked field set explicit, so downstream systems can distinguish `IDENTITY_VALID` from stronger statements such as `EVIDENCE_FIELDS_BOUND` or `POLICY_REDERIVED`.

## Claim status

This is a **documented verification boundary / validation requirement**. It should remain visible until a v2 implementation is committed, reproduced, and shown to reject the relevant label-escalation tampering cases.
