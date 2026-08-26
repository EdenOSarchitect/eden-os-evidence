# EDEN OS Evidence

Public, claim-controlled reproducibility artifacts for EDEN OS.

**Current snapshot:** 2026-08-26  
**System status:** lab-stage / pre-revenue / not yet independently validated as a complete stack.

## What EDEN OS is exploring

EDEN OS is an experimental evidence-controlled architecture for refining, scheduling, transmitting, verifying and accounting for computational/information workloads.

Canonical conceptual flow:

`SENSE -> DECOMPOSE -> MEASURE -> KEEP/VOID -> REGENERATE -> NAVIGATE (ChronoNav) -> VSURF -> TRANSMIT -> RECOMPOSE -> VERIFY`

Refinery classes: `KEEP`, `STRUCTURE`, `DETAIL`, `RESIDUAL`, `VOID`.

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

### Azure refinery

`azure-refinery/` contains a verifiable Azure LLM refinery benchmark harness, retry/URL hardening, workflow support and a safe Termux bootstrap. Historical counterfactual cost examples must remain labelled as models until backed by captured provider workload/billing evidence.

### Shadow Controller

Repository history includes a local Termux Shadow Controller run. The intended evidence flow is:

`baseline -> EDEN treatment -> counterfactual -> delta -> evidence -> Marble -> accountability`

### Manifold / neural ingress

`neural-interface/` includes an authenticated decrypt gate, encrypted Manifold ingress documentation and ingestion-Marble handling. This establishes software/artifact state, not a claim of production Neuralink or other third-party deployment.

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

## Validation direction

Highest-value next steps are:

1. power-instrumented ChronoNav replication against maximum-compute and strong adaptive baselines on multiple devices;
2. executed provider-side LLM A/B workloads with immutable token, latency, cost and workload evidence;
3. Marble v2 verification that binds/re-derives evidence, provenance, kind and policy-relevant counts;
4. independent third-party reproduction of the strongest results;
5. a complete reproducible Shadow Controller baseline/treatment/counterfactual/Marble run.

Record task quality, deadlines, wall time, worker-time, actual joules where applicable, thermal/frequency state, software/hardware identifiers and full provenance.

CI is intended to keep deterministic artifacts reproducible and to prevent simulated/modelled results from being silently reclassified as measured physical evidence.
