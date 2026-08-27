# EDEN OS Evidence

Public, claim-controlled reproducibility artifacts for EDEN OS.

**Current snapshot:** 2026-08-27  
**System status:** lab-stage / pre-revenue / not yet independently validated as a complete stack.

## What EDEN OS is exploring

EDEN OS is an experimental evidence-controlled architecture for refining, scheduling, transmitting, verifying and accounting for computational/information workloads.

Canonical conceptual flow:

`SENSE -> DECOMPOSE -> MEASURE -> KEEP/VOID -> REGENERATE -> NAVIGATE (ChronoNav) -> VSURF -> TRANSMIT -> RECOMPOSE -> VERIFY`

Refinery classes: `KEEP`, `STRUCTURE`, `DETAIL`, `RESIDUAL`, `VOID`.

## Experimental interpretation

EDEN treats experiments as evidence-producing procedures. An experiment does not become a failed experiment because its hypothesis is unsupported, a benchmark is neutral, a component regresses, or an expected effect is absent. Those are valid experimental outcomes.

Research reports should therefore distinguish:

- **positive outcome** — the tested hypothesis is supported under the recorded conditions;
- **neutral outcome** — no material difference is established under the recorded conditions;
- **negative / falsifying outcome** — the tested hypothesis is not supported, or a comparator performs better;
- **inconclusive outcome** — instrumentation, sample size, environment, or evidence quality is insufficient for the intended inference;
- **execution issue** — the intended procedure did not run as specified, such as absent credentials, missing hardware access, or an interrupted process.

Negative, neutral and inconclusive outcomes are preserved rather than hidden. They refine the hypothesis and define the next experiment. An execution issue must not be promoted into a scientific result.

## Evidence classes

This repository uses explicit evidence classes:

- **IMPLEMENTED** — software or artifact exists and can be inspected.
- **MEASURED** — a quantity was measured in an executed workload or on physical hardware; the exact measured quantity must be named.
- **SIMULATED** — result comes from a synthetic environment.
- **MODELLED** — value follows from a model/physics/economic calculation rather than direct measurement.
- **PROPOSED** — architecture, experiment, deployment or commercial hypothesis not yet demonstrated.
- **INDEPENDENTLY VALIDATED** — reproduced by an external party outside the creator's environment.

Claim strength must not exceed evidence strength. Hashes and Merkle commitments prove integrity/inclusion of committed records; they do not prove that a scientific or physical claim is true.

## Current EDEN surfaces

### ChronoNav

`chrononav/` records scheduler evidence and its boundaries.

- **MC-002 — MEASURED physical-device compute-resource proxy:** on a reported 40-job run on an 8-core Android handset, ChronoNav recorded an 85.0% deadline hit rate versus 87.5% for Always-8, while using 52.333 versus 90.232 worker-seconds (about 42% lower worker-time). Worker-seconds are not joules; electrical-energy savings were not measured. The result is not independently validated.
- **AB-004 — SIMULATED:** a frozen ChronoNav V2 policy was reported across 10,000 randomized synthetic trials with mean realised utility 1847.21 versus 1681.36 for TRUE_VALUE_GREEDY. This is scheduler simulation evidence, not physical RF, spacecraft, energy, or customer-performance evidence.

### SAT-001

`sat-001/` contains deterministic selective-downlink simulations. These results are **SIMULATED / REPRODUCIBLE**, not flight evidence. Modelled energy/economic quantities remain modelled and unavailable real-world measurements remain null.

### EDEN Refinery

`eden-refinery/` contains the verifiable EDEN Refinery LLM benchmark harness, retry/URL hardening, workflow support and a safe Termux bootstrap. Azure OpenAI is currently supported as a provider configuration; it is not the name of the refinery itself. Historical counterfactual cost examples must remain labelled as models until backed by captured provider workload/billing evidence.

### Shadow Controller

Repository history includes a local Termux Shadow Controller run. The intended evidence flow is:

`baseline -> EDEN treatment -> counterfactual -> delta -> evidence -> Marble -> accountability`

### Manifold / neural ingress

`neural-interface/` now includes the merged MANIFOLD-AUTH-001 hardening: source/session/sequence/version metadata are bound into AES-256-GCM authenticated data, replay and out-of-order frames are rejected, and provenance-chain/replay-state ambiguity fails closed. The dedicated Manifold security regression job and SAT-001 reproducibility job passed on the PR head before merge. This establishes tested software behavior, not production Neuralink or other third-party deployment, device attestation, physiological interpretation, penetration-test assurance, or formal cryptographic verification.

### Marble / accountability

Marbles are provenance/accountability records. A current v1 trust boundary is documented in [`docs/MARBLE_V1_VERIFICATION_BOUNDARY.md`](docs/MARBLE_V1_VERIFICATION_BOUNDARY.md): v1 identity verification does not automatically make every surrounding evidence/provenance/kind/count label trustworthy.

### GPT cognitive provider contract

[`docs/GPT_COGNITIVE_PROVIDER_HANDOFF.md`](docs/GPT_COGNITIVE_PROVIDER_HANDOFF.md) defines the EDEN provider-layer handoff for GPT-class cognitive engines: workload envelopes, structured evidence, void-compatible outputs, physics measurement status and Shadow Controller integration. Hidden chain-of-thought is not used as an evidence artifact; auditable rationale, assumptions, tests and counterfactual summaries are used instead.

### Full current-state snapshot

See [`docs/CURRENT_STATE_2026-08-26.md`](docs/CURRENT_STATE_2026-08-26.md) for the consolidated architecture/evidence status.

## Truth boundaries

This repository does **not** currently establish:

- EDEN deployment on a satellite or third-party operational infrastructure;
- physical RF/bandwidth improvement attributable to EDEN;
- general electrical-energy savings from the ChronoNav MC-002 worker-time result;
- a universal EDEN-wide efficiency advantage;
- production-grade cloud/provider reliability across the full stack;
- commercial customer validation;
- independent third-party validation of the complete EDEN benchmark stack;
- authenticity of Marble metadata fields that a verifier neither binds nor re-derives.

## Next evidence steps

Highest-value next steps are:

1. power-instrumented ChronoNav replication against maximum-compute and strong adaptive baselines on multiple devices;
2. executed provider-side LLM A/B workloads with immutable token, latency, cost and workload evidence;
3. Marble v2 verification that binds/re-derives evidence, provenance, kind and policy-relevant counts;
4. independent third-party reproduction of the strongest results;
5. a complete reproducible Shadow Controller baseline/treatment/counterfactual/Marble run;
6. physical RF observation and transport A/B experiments that keep RF observation, RF control and RF efficiency as separate claims.

Record task quality, deadlines, wall time, worker-time, actual joules where applicable, thermal/frequency state, software/hardware identifiers and full provenance.

CI is intended to keep deterministic artifacts reproducible and to prevent simulated/modelled results from being silently reclassified as measured physical evidence.
