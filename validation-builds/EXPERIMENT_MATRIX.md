# Academic Experiment Matrix

| Research lead | Build | Primary hypothesis | Baselines | Current evidence class | Next physical/independent step |
|---|---|---|---|---|---|
| Dr Serdar Vural, Surrey | `vural_ntn.py` | Information-value-aware ordering can improve delivered application value under constrained NTN-like capacity/loss windows | FIFO on identical trace | SIMULATED | Independent execution; then SDN/NTN testbed integration if warranted |
| Prof Malcolm Macdonald, Strathclyde | `macdonald_orbital_compute.py` | Joint resource/value scheduling can improve mission-value return under constrained compute/power/contact windows | FIFO on identical synthetic constraints | SIMULATED | Replace model constraints with measured/representative spacecraft compute, power and contact data |
| Prof Massimiliano Vasile, Strathclyde | `vasile_chrononav.py` | ChronoNav-style multi-objective scheduling can outperform EDF and utility-greedy under a declared objective | EDF; utility-greedy | SIMULATED | Formalise objective/constraints; test across randomized regimes and physical energy instrumentation |
| Prof Barry Evans, Surrey | `evans_testbed_adapter.py` | Value-aware transmission can improve application utility under measured network traces and ultimately controlled NTN conditions | FIFO on same trace | SIMULATED by default; MEASURED-TRACE-INPUT when external trace supplied | Integrate with live satellite/network testbed I/O; measure latency, loss, throughput, application utility and overhead |
| Prof Dimitra Simeonidou, Bristol | `simeonidou_network.py` | Information-aware scheduling can improve application utility under constrained programmable-network conditions | FIFO on identical trace | SIMULATED | Independent programmable-network experiment against stronger scheduling/congestion-control baselines |

## Rules

1. A positive simulation is not physical validation.
2. External trace replay is not a live RF experiment.
3. Energy-proxy values are not joules.
4. Every evaluation must retain negative results.
5. Independent evaluators may modify or replace the EDEN policy and baselines, but changes must be recorded.
6. A result becomes `INDEPENDENTLY VALIDATED` only after an external party executes the experiment outside the creator's environment and documents the result.
