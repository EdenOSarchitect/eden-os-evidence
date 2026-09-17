# Five-minute EDEN comparison

Requires Python 3.9+; no account, provider key or package install.

From the repository root:

```bash
python3 experiments/quickstart.py
```

The command prints JSON for three arms over 60 synthetic requests and 30 unique inputs. `CONTROL` recomputes each request. `CACHE` stores exact results keyed by a SHA-256 digest of the input. `EDEN` uses the same exact reuse and checks an input/output commitment on every hit. Each arm receives the identical ordered input stream, starting with an empty cache. Output hashes must agree or the command exits with an error.

Try a different workload:

```bash
python3 experiments/quickstart.py --requests 100 --unique 25 --iterations 10000
```

`unique` changes the exact reuse rate. `iterations` changes the cost of a full execution. Compare `cpu_s`, `wall_s`, `throughput_req_s`, `p50_latency_ms` and `avoided_executions` across arms. Timing varies by machine; run repeated trials for any performance claim. This demo illustrates a narrow verification mechanism, not the integrated EDEN stack. The commitment detects changes to stored output bytes under this local threat model; it does not independently prove a provider response is correct. Conventional exact caching can outperform it.

For a longer CPU-only reuse sweep, run the existing [CPU avoidance experiment](../experiments/eden-cpu-avoidance-001/cpu_avoidance.py):

```bash
python3 experiments/eden-cpu-avoidance-001/cpu_avoidance.py --requests 100 --iterations 5000 --repeats 3 --reuse 0.0 0.5 0.9 --output /tmp/eden-cpu-report.json
```

That older experiment has only CONTROL and EDEN arms, so do not use it to claim EDEN beats a conventional cache. Neither experiment measures cloud provider internals, electricity, billing, production workloads, or universal savings.
