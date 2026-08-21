# ChronoNav evidence

ChronoNav is EDEN's resource-aware scheduling / state-navigation research layer. This directory records results with strict evidence boundaries.

## MC-002 — physical-device workload

**Classification:** MEASURED (compute-resource proxy), NOT independently validated.

Reported configuration and outcome:

- device class: 8-core Android handset;
- workload: 40 jobs;
- ChronoNav deadline hit rate: **85.0%**;
- Always-8 deadline hit rate: **87.5%**;
- ChronoNav worker-time: **52.333 worker-seconds**;
- Always-8 worker-time: **90.232 worker-seconds**;
- relative worker-time reduction vs Always-8: approximately **42.0%**;
- deadline difference: ChronoNav missed one additional deadline across the 40 jobs.

### Boundary

Worker-seconds are a compute-resource proxy. They are **not electrical joules**. MC-002 does not establish a 42% energy saving. Raw power-meter evidence is not currently published here, and the result has not been independently reproduced.

## AB-004 — frozen scheduler randomized validation

**Classification:** SIMULATED.

Reported 10,000 randomized synthetic trials:

- ChronoNav V2 mean realised utility: **1847.21**;
- TRUE_VALUE_GREEDY mean realised utility: **1681.36**;
- ChronoNav trial wins: **6204**;
- reported mean uplift: approximately **+9.9%** vs TRUE_VALUE_GREEDY and **+11.3%** vs UTILITY_PER_BYTE.

### Boundary

AB-004 is synthetic scheduler validation. It is not physical RF, satellite, electrical-energy, customer, or independently validated evidence.

## Next experiment: MC-003

Freeze the policy and reproduce MC-002 with direct power instrumentation on at least two physical platforms. Compare:

1. Always-max compute;
2. a strong conventional adaptive scheduler;
3. ChronoNav.

Measure deadline hit rate, task quality, wall time, worker-time, actual joules, temperature, frequency/throttling state, and scheduler overhead. Preserve hardware IDs, runtime versions, seeds/configuration and evidence hashes.
