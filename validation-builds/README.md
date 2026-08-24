# EDEN Independent Validation Builds

These packages are narrow, falsifiable research harnesses prepared for external academic evaluation.

## Evidence discipline

No build in this directory is labelled `INDEPENDENTLY VALIDATED` until an external party runs it outside the creator's environment and records the environment, method and results.

Synthetic/modelled harness outputs remain `SIMULATED`. A replay of a third-party measured link trace is not automatically a physical EDEN RF test. Electrical energy must be measured as joules before any energy-saving claim is made.

## Builds

- `vural_ntn.py` — value-aware NTN/network orchestration versus FIFO on identical synthetic traces.
- `macdonald_orbital_compute.py` — constrained spacecraft compute/downlink scheduling under synthetic power/contact windows.
- `vasile_chrononav.py` — ChronoNav-style multi-objective scheduling versus EDF and utility-greedy baselines.
- `evans_testbed_adapter.py` — satellite-network trace replay adapter; accepts external CSV traces and preserves the distinction between trace replay and live RF testing.
- `simeonidou_network.py` — information-aware programmable-network scheduling versus FIFO under synthetic capacity/loss/latency constraints.

## Run

All builds require only Python 3 standard library.

```bash
python validation-builds/vural_ntn.py
python validation-builds/macdonald_orbital_compute.py
python validation-builds/vasile_chrononav.py
python validation-builds/evans_testbed_adapter.py
python validation-builds/simeonidou_network.py
```

Each program writes JSON to stdout and states its evidence class and falsification/pass boundary.

## External validation record

External evaluators should record:

- commit SHA;
- exact command and seed;
- OS, Python version, hardware and relevant network/testbed identifiers;
- raw output;
- baseline definitions;
- any code/configuration changes;
- whether the result was reproduced, partially reproduced, not reproduced, or methodologically insufficient.

Negative results must be retained.
