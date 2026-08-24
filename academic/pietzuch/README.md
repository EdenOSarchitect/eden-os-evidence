# Pietzuch / Imperial — EDEN Distributed Provenance + Scheduling Experiment

Status: PROPOSED / REPRODUCIBLE HARNESS. Not independently validated.

## Research question
Can EDEN preserve verifiable provenance across distributed task execution while maintaining useful scheduling performance and bounded verification overhead?

## Baselines
1. Unsigned/uncommitted execution
2. Hash-only provenance
3. Merkle commitment per batch
4. EDEN value-aware scheduling + Merkle provenance

## Controlled variables
Task count, node count, batch size, failure rate, tamper rate, network delay and workload skew.

## Primary metrics
Task throughput, useful-task completion, provenance bytes, verification latency, tamper-detection rate, false-accept rate and scheduler overhead.

## Falsification criteria
EDEN fails if integrity guarantees are weaker than the baseline, tampering is not reliably detected, or provenance/scheduling overhead erases the useful-work advantage.

## External runner identity
Set `EDEN_RUNNER_ID` and `EDEN_RUN_TOKEN` to non-secret run labels and preserve the raw JSON and environment metadata. External execution is not automatically INDEPENDENTLY VALIDATED; attribution and methodology must be reviewable.

Termux/Linux:
```bash
export EDEN_RUNNER_ID="imperial-systems-lab"
export EDEN_RUN_TOKEN="pietzuch-dist-001"
python3 academic/pietzuch/run_experiment.py > results/pietzuch-dist-001.json
```
