# Tafazolli / Surrey — EDEN 6G + NTN Orchestration Experiment

Status: PROPOSED / REPRODUCIBLE HARNESS. Not independently validated.

Research question: can an information-aware orchestration policy improve application utility under changing terrestrial/non-terrestrial network conditions without unacceptable control overhead?

Baselines: FIFO, earliest-deadline-first, throughput-first greedy, and EDEN value-aware scheduling.

Controlled variables: capacity, latency, loss, jitter, handover events, contact-window duration, compute budget and utility-estimation error.

Primary metrics: delivered application utility, deadline success, useful reconstruction at cutoff, bytes transmitted, control overhead, scheduler CPU time and failure rate.

Falsification: EDEN fails if its advantage disappears against strong baselines, reverses under modest utility-estimation error, or orchestration overhead consumes the measured gain.

External runners should set `EDEN_RUNNER_ID` and `EDEN_RUN_TOKEN` to non-secret labels and preserve the generated JSON plus hardware/software metadata. A run is not INDEPENDENTLY VALIDATED until the external party and environment are attributable.

Termux/Linux:
```bash
export EDEN_RUNNER_ID="surrey-ics-lab"
export EDEN_RUN_TOKEN="tafazolli-ntn-001"
python3 academic/tafazolli/run_experiment.py > results/tafazolli-ntn-001.json
```

Truth boundary: this harness does not establish physical RF, 6G or satellite performance. Physical claims require instrumented external infrastructure.
