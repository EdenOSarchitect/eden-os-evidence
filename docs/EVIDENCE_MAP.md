# Evidence map

Use the linked procedure and its generated report when quoting a number. A result is scoped to its environment and workload. An open PR is work in review, not a merged result.

| Question | Runnable source | Comparator | Measurement or status | Limit |
| --- | --- | --- | --- | --- |
| Does exact reuse avoid repeated local computation? | [CPU avoidance](../experiments/eden-cpu-avoidance-001/cpu_avoidance.py) | Full recomputation | Host process CPU and wall time; generated JSON includes reuse sweep, repeats and output equality | No conventional-cache arm or cloud/energy measurement |
| What does verified exact reuse cost against a conventional cache? | [Three-arm quickstart](QUICKSTART.md) | Full recomputation and exact cache | Local synthetic process CPU, wall time, throughput, latency and execution counts | Small illustrative verifier, not integrated EDEN; no production claim |
| How does integrated evidence/control overhead compare at an equal cache boundary? | [Azure fair A/B](../experiments/azure-fair-ab-001/README.md) | Conventional exact cache | Mock mode runnable locally; provider mode requires credentials | Mock is simulated; provider execution must supply its own report and provenance |
| Does selective downlink help? | [SAT-001](../sat-001/README.md) | Simulation baselines described there | Deterministic simulated workload | No spacecraft flight or physical RF result |
| Does ChronoNav reduce electricity? | [ChronoNav](../chrononav/README.md) | Device/simulation comparators described there | Worker-time proxy and scheduler simulations | Worker-seconds are not joules |

Further Azure HTTP, interleaved analytics, structured reuse and semantic compression experiments are [open for review](https://github.com/EdenOSarchitect/eden-os-evidence/pulls). For an independent reproduction, attach the command, commit, hardware, Python version, output report, and any neutral or negative outcome. See [CONTRIBUTING](../CONTRIBUTING.md).
