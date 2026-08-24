# Tafazolli / Surrey — EDEN 6G + NTN Orchestration Experiment

Status: PROPOSED / REPRODUCIBLE HARNESS. Not independently validated.

## Research question
Can an information-aware orchestration policy improve application utility under changing terrestrial/non-terrestrial network conditions without unacceptable control overhead?

## Baselines
1. FIFO
2. Earliest-deadline-first
3. Throughput-first greedy
4. EDEN value-aware policy

## Controlled variables
Capacity, latency, loss, jitter, handover events, contact-window duration, compute budget and utility-estimation error.

## Primary metrics
Delivered application utility, deadline success, useful reconstruction at cutoff, bytes transmitted, control overhead, scheduler CPU time, fairness and failure rate.

## Falsification criteria
EDEN is not better if its benefit disappears against strong baselines, reverses when utility estimates are perturbed, or its orchestration overhead consumes the measured gain.

## External-run identity
Independent runners should set `EDEN_RUNNER_ID` and `EDEN_RUN_TOKEN` to non-secret labels identifying the lab/run, and preserve the generated JSON result plus software/hardware metadata. A run is not classified INDEPENDENTLY VALIDATED until the external party and environment are independently attributable.

## Suggested Termux/Linux command
```bash
export EDEN_RUNNER_ID="surrey-ics-lab"
export EDEN_RUN_TOKEN="tafazolli-ntn-001"
python3 academic/tafazolli/run_experiment.py --seed 20260824 --trials 1000 --output results/tafazolli-ntn-001.json
```

## Truth boundary
This harness does not establish physical RF, 6G or satellite performance. Trace replay remains replay. Physical claims require instrumented external infrastructure.
