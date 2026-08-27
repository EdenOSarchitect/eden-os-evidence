# EDEN OS Current State — 2026-08-27

This document is a claim-controlled snapshot of the public EDEN evidence repository.

## Research interpretation

EDEN treats an experiment as an evidence-producing procedure. A result may support a hypothesis, show no material difference, contradict a hypothesis, expose a boundary condition, or be inconclusive. Those are experimental outcomes, not failed experiments.

An **execution issue** is different: the intended procedure did not run as specified because of conditions such as unavailable credentials, unavailable hardware, interrupted execution, or invalid configuration. Execution issues do not count as scientific results.

## Canonical evidence classes

- **IMPLEMENTED** — inspectable software/artifact exists.
- **MEASURED** — the named quantity was directly measured in an executed workload or physical observation.
- **SIMULATED** — the result comes from a synthetic environment.
- **MODELLED** — the value is calculated from assumptions/model inputs rather than directly measured.
- **PROPOSED** — architecture/deployment/hypothesis not yet demonstrated.
- **INDEPENDENTLY VALIDATED** — reproduced by an external party outside the creator environment.

## Manifold / Providence

MANIFOLD-AUTH-001 is merged into `main`.

Implemented properties include:

- AES-256-GCM authenticated encryption;
- source/session/sequence/version/algorithm/manifold metadata bound into canonical AEAD associated data;
- rejection of tampered authenticated metadata;
- replay and out-of-order rejection per source/session;
- persisted replay state;
- fail-closed handling of corrupt replay state;
- provenance-head/log-tail cross-checking;
- fail-closed handling of missing/corrupt/mismatched evidence-chain state;
- authenticated metadata recorded in ingestion Marbles.

CI evidence: the `manifold-auth-001` regression job and `sat001-reproducibility` job both completed successfully on the PR head, and the post-merge `main` evidence-ci run completed successfully.

Boundary: authenticated sender-supplied source metadata does not independently establish real-world hardware/vendor identity. Device identity requires a separate attestation/credential mechanism.

## Azure / EDEN Refinery

Azure integration/execution was successfully established in the initial provider work.

A later GitHub Actions attempt to run a larger 1,000-request benchmark did not execute the measured request phase because the CI environment did not contain the required Azure credentials. That later event is an **execution issue**, not evidence that Azure integration failed.

Current classification:

- Azure provider integration: **IMPLEMENTED / previously executed**.
- large 1,000-request provider benchmark: **NOT COMPLETED**.
- large-scale Azure resource/cost superiority attributable to EDEN: **NOT YET ESTABLISHED**.
- counterfactual Shadow Controller percentages remain counterfactual unless backed by captured provider-side workload/billing evidence.

## ChronoNav

MC-002 remains the strongest physical-device scheduler/resource observation presently documented:

- 40 jobs;
- ChronoNav deadline hit rate: 85.0%;
- Always-8 deadline hit rate: 87.5%;
- ChronoNav worker-time: 52.333 worker-seconds;
- Always-8 worker-time: 90.232 worker-seconds;
- approximately 42% lower worker-time with one additional missed deadline.

Classification: **MEASURED physical-device compute-resource proxy**.

Boundary: worker-seconds are not electrical joules. Direct electrical-energy comparison still requires a power/battery-instrumented run.

AB-004 remains **SIMULATED** scheduler evidence over 10,000 randomized trials.

## EDEN Refinery / Keep-Void / Chrysalis

Refinery and Keep/Void components exist in implemented/prototype form. Gross information reduction must not automatically be treated as net resource saving.

A net resource evaluation should charge:

`baseline - active - metadata - recovery - regeneration - orchestration`

while independently reporting task quality.

Chrysalis remains experimental until its regeneration/refinement advantage is demonstrated against a credible comparator after its own resource cost is included.

## RF / communications

EDEN-RF-EST-001 is an **IMPLEMENTED handset RF-observation experiment** designed to record Android Wi-Fi observations such as RSSI and carrier frequency with claim-controlled evidence.

The experiment implementation is distinct from an executed observation artifact.

Three claim levels remain separate:

1. physical RF observation;
2. EDEN-controlled RF transmission;
3. RF efficiency/capacity improvement attributable to EDEN.

An executed Wi-Fi RSSI observation can establish level 1 only. It does not establish levels 2 or 3.

Bluetooth remains a standards-compliant transport candidate beneath EDEN application/resource control. No EDEN-specific Bluetooth efficiency result is currently established.

## SAT-001 / orbital compute

SAT-001 deterministic simulations are implemented and reproducible in CI.

Classification: **SIMULATED / REPRODUCIBLE**.

They do not establish satellite deployment, flight performance, physical RF improvement, hardware-energy saving, operator validation, or realized economic saving.

## EDEN-FIRST / CRV

The architecture remains focused on separating proposed action from authorized execution and on attaching bounded resource/authority contracts.

The stronger research target is multidimensional resource enforcement across fields such as authority, tokens, CPU/GPU, memory, bytes, storage, joules, latency and money, with Providence recording actual consumption against allocation.

Physical robot enforcement remains a future validation step.

## BCI / neural interface

The neural-interface work currently establishes secure software ingress/provenance behavior, not physiological decoding or device integration.

MANIFOLD-AUTH-001 is now canonical and CI-tested, but real neural hardware identity, physiological interpretation, clinical utility and BCI efficiency remain separate future evidence questions.

## Evidence CI

Evidence CI is now observed functioning, not merely present as configuration.

Verified successful jobs include:

- `manifold-auth-001` security regression suite;
- `sat001-reproducibility` deterministic rerun and truth-boundary checks.

The main branch post-merge run for MANIFOLD-AUTH-001 completed successfully.

## Next evidence steps

1. Direct battery/power-instrumented ChronoNav comparison against a strong adaptive scheduler.
2. Provider-side Azure A/B workload with immutable task, token, latency, quality and billing evidence.
3. Execute and preserve EDEN-RF-EST-001 physical handset observations.
4. Move from RF observation to controlled transport A/B tests with bytes, latency, quality, retransmission and joules.
5. Continue Marble verification hardening so policy-relevant evidence/provenance fields are bound or re-derived.
6. Independent external reproduction of the strongest measured results.

## Current overall position

EDEN has implemented and measured components, reproducible simulations, a functioning claim-controlled CI path, and an increasingly integrated evidence architecture. The remaining work is to extend direct physical/provider measurement across the full stack and obtain independent reproduction.
