# EDEN OS Evidence

Public, claim-controlled reproducibility artifacts for EDEN OS.

## Evidence classes

This repository uses five explicit evidence classes:

- **IMPLEMENTED** — software or artifact exists and can be inspected.
- **MEASURED** — a quantity was measured in an executed workload or on physical hardware; the exact measured quantity must be named.
- **SIMULATED** — result comes from a synthetic/modelled environment.
- **PROPOSED** — architecture, experiment, deployment or commercial hypothesis not yet demonstrated.
- **INDEPENDENTLY VALIDATED** — reproduced by an external party outside the creator's environment.

Claim strength must not exceed evidence strength. Hashes and Merkle commitments prove integrity/inclusion of committed records; they do not prove that a scientific or physical claim is true.

## Current evidence

### SAT-001

`sat-001/` contains deterministic selective-downlink simulations. These results are **SIMULATED / REPRODUCIBLE**, not flight evidence. Modelled energy/economic quantities remain modelled and unavailable real-world measurements remain null.

### ChronoNav

`chrononav/` records current scheduler evidence and its boundaries.

- **MC-002 — MEASURED physical-device compute-resource proxy:** on a reported 40-job run on an 8-core Android handset, ChronoNav recorded an 85.0% deadline hit rate versus 87.5% for Always-8, while using 52.333 versus 90.232 worker-seconds (about 42% lower worker-time). Worker-seconds are not joules; electrical-energy savings were not measured. The result is not independently validated.
- **AB-004 — SIMULATED:** a frozen ChronoNav V2 policy was reported across 10,000 randomized synthetic trials with mean realised utility 1847.21 versus 1681.36 for TRUE_VALUE_GREEDY. This is scheduler simulation evidence, not physical RF, spacecraft, energy, or customer-performance evidence.

## Truth boundaries

This repository does **not** currently establish:

- EDEN deployment on a satellite or third-party operational infrastructure;
- physical RF/bandwidth improvement from EDEN;
- electrical-energy savings from the ChronoNav MC-002 worker-time result;
- a universal EDEN-wide efficiency advantage;
- independent third-party validation of the current EDEN benchmark stack.

## Validation direction

The next high-value validation is a power-instrumented ChronoNav replication against both maximum-compute and strong adaptive conventional baselines, ideally on more than one physical device. Record task quality, deadlines, wall time, worker-time, actual joules, thermal/frequency state, software/hardware identifiers, and full provenance.

CI is intended to keep deterministic SAT-001 outputs reproducible and to prevent simulated/modelled results from being silently reclassified as measured physical evidence.
