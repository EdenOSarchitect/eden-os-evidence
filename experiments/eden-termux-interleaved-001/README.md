# EDEN-TERMUX-INTERLEAVED-001

Bias-control benchmark for Android/Termux. Each request is executed through CONTROL, CACHE and EDEN in a deterministic random order inside one process. This is designed to reduce sequential-arm warm-up/order bias.

Run:

```bash
python -u experiments/eden-termux-interleaved-001/termux_interleaved.py \
  --requests 600 \
  --iterations 30000 \
  --reuse 0 0.50
```

Interpretation:

- At 0% reuse, EDEN performs the full workload plus evidence/integrity work. If EDEN reports lower thread CPU than CONTROL, the run is flagged `INVESTIGATE_NEGATIVE_DELTA` rather than treated as an efficiency result.
- At 50% reuse, compare EDEN to both CONTROL and conventional CACHE using paired per-request deltas.
- Output equivalence must pass.
- The benchmark measures same-process thread CPU and wall time. It does not measure joules, GPU performance, Azure billing, or datacentre energy.
