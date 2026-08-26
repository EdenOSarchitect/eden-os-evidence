# EDEN OS — Current State

**Snapshot date:** 2026-08-26

This document is a claim-controlled snapshot of the current EDEN OS architecture and evidence state. It separates implemented software, measured results, simulations/models, and proposals. Claim strength must not exceed evidence strength.

## Canonical refinery flow

EDEN currently uses the following conceptual processing chain:

`SENSE -> DECOMPOSE -> MEASURE -> KEEP/VOID -> REGENERATE -> NAVIGATE (ChronoNav) -> VSURF -> TRANSMIT -> RECOMPOSE -> VERIFY`

Refinery classes are:

- `KEEP`
- `STRUCTURE`
- `DETAIL`
- `RESIDUAL`
- `VOID`

Evidence labels used across the project include `IMPLEMENTED`, `MEASURED`, `SIMULATED`, `MODELLED`, `PROPOSED`, `UNSUPPORTED`, and `INDEPENDENTLY VALIDATED` where applicable.

## Major implemented / evidenced components

### EDEN Refinery

The repository contains reproducibility and claim-control artifacts for EDEN's refinery architecture. Current evidence does not justify describing EDEN as universally more efficient than conventional systems.

### ChronoNav

ChronoNav is EDEN's scheduling/navigation layer.

- AB-003: synthetic multi-scheduler experiment across 1,000 trials. ChronoNav V2 reported mean true utility 1434.23 under that simulation.
- AB-004: frozen-policy blind validation across 10,000 randomized synthetic trials. ChronoNav V2 reported mean realised utility 1847.21 versus 1681.36 for TRUE_VALUE_GREEDY.
- MC-002: physical Android compute-resource proxy experiment. A reported 40-job run recorded an 85.0% deadline hit rate for ChronoNav versus 87.5% for Always-8 while using 52.333 versus 90.232 worker-seconds. Worker-seconds are not joules.

AB-003 and AB-004 are simulation evidence. MC-002 is device execution evidence but does not establish electrical-energy savings.

### SAT-001 / orbital scheduling

`sat-001/` contains deterministic selective-downlink simulations and related reproducibility artifacts. It does not establish deployment on a satellite, flight heritage, or measured RF improvement.

### AURA / RF work

AURA-related handset work has included local responder software, orbital geometry, Doppler/FSPL modelling, and device-side telemetry experiments. Local loopback responder measurements must not be represented as physical RF measurements. Orbital geometry based on external ephemeris is model-derived unless independently measured.

### Azure refinery / LLM workloads

`azure-refinery/` contains an Azure LLM benchmark harness and Termux bootstrap support. Historical cost examples and counterfactuals remain models unless backed by an executed provider workload with captured billing/token/latency evidence.

### Shadow Controller

The Shadow Controller is intended to compare baseline provider execution with EDEN treatment/counterfactuals while retaining provenance and value/accountability evidence. A local Termux Shadow Controller run is present in repository history.

### Manifold authenticated ingress

The repository contains an authenticated decrypt gate and documented encrypted Manifold ingress flow. Incoming authenticated frames can be associated with ingestion Marbles before downstream observation. This establishes software/artifact state, not third-party deployment.

### Marble / provenance layer

Marbles are EDEN provenance/accountability records. They should distinguish integrity evidence from truth evidence: a valid hash proves integrity of what was committed, not the physical or scientific truth of the underlying claim.

A known v1 verification boundary is documented separately in `MARBLE_V1_VERIFICATION_BOUNDARY.md`.

### GPT cognitive provider integration

EDEN now defines a provider-layer cognitive handoff contract for GPT-class models. The contract treats provider inputs as workload envelopes and outputs as structured evidence suitable for refinery, Shadow Controller, Marble and accountability processing. Hidden chain-of-thought is not part of the evidence contract; auditable rationale, assumptions, inputs, outputs, tests and counterfactual summaries are used instead.

See `GPT_COGNITIVE_PROVIDER_HANDOFF.md`.

## Physical-device observations recorded during EDEN development

Reported Android/Termux work has included multicore scheduling, local responder execution, bandwidth telemetry and a device joule-meter experiment. Measurements must remain scoped to the exact workload and sensor path used; they cannot be generalized into EDEN-wide energy, RF, network or cloud savings without a controlled comparison.

## Current public claim boundaries

EDEN does **not** currently establish all of the following:

- deployment on a satellite or third-party operational infrastructure;
- independently validated universal efficiency gains;
- measured physical RF improvement attributable to EDEN;
- general electrical-energy savings from ChronoNav;
- production-grade reliability across cloud/provider workloads;
- commercial customer validation;
- correctness of labels that are not cryptographically bound and re-derived by the verifier.

## High-value next validation steps

1. Power-instrumented ChronoNav replication across multiple physical devices and strong baselines.
2. Executed provider-side LLM A/B runs with immutable capture of token counts, latency, cost and workload identity.
3. Marble v2 verification that binds and re-derives evidence/provenance/kind/count fields rather than trusting mutable labels.
4. Independent third-party reproduction of the strongest EDEN results.
5. End-to-end Shadow Controller run that produces a verifiable baseline, treatment, counterfactual, delta and Marble in one reproducible package.

## Status

EDEN remains a lab-stage, pre-revenue R&D system. The repository is an evidence and reproducibility surface; it should be read as a controlled record of what has been implemented, measured, simulated, modelled or proposed rather than as proof of every broader EDEN hypothesis.
