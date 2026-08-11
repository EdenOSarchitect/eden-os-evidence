# EDEN-SAT-001 synthetic simulation

This package estimates previously unmeasured EDEN-SAT-001 quantities using an
explicitly synthetic, deterministic Monte Carlo model. It is not CloudSEN12
evidence, hardware-in-the-loop evidence, flight evidence, or proof of energy or
economic savings.

Run:

```bash
python3 run_simulation.py
```

`RESULTS.json` records assumptions, uncertainty across simulated missions,
quality-gate pass rate, classification metrics, byte effects, modeled energy,
latency, and strict claim boundaries.

SIM-002 uses a three-member synthetic ensemble and selects its threshold on a
separate validation sample, maximising validation accuracy subject to a 99.2%
recall safety margin. It also hard-codes a measurement register for CloudSEN12,
flight, hardware-energy and economic evidence. Empty evidence fields remain
`null`; modeled values cannot populate measured fields.
