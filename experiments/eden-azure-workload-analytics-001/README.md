# EDEN-AZURE-WORKLOAD-ANALYTICS-001

A second Azure VM workload using deterministic JSON event analytics with request-level interleaving across CONTROL, CACHE and EDEN.

The trace contains a naturally generated duplicate pattern and the experiment reports the **observed exact reuse fraction** rather than accepting a reuse percentage as an input.

Each logical request is executed through all three arms in a randomized order inside the same process. This is intended to reduce sequential-arm warm-up and host-drift bias.

## Run

```bash
python -u experiments/eden-azure-workload-analytics-001/azure_workload_analytics_001.py \
  --requests 2500 \
  --rounds 80 \
  --environment AZURE_VM
```

## Measures

- observed exact duplicate/reuse fraction
- paired process CPU timing
- paired wall timing
- CONTROL vs CACHE vs EDEN
- cache/EDEN reuse hits
- exact output equivalence
- trace commitment
- report commitment

## Interpretation boundary

This is an application-like analytics workload on an Azure VM, not a claim of Azure billing reduction, datacentre energy reduction, or production-workload generality. The primary comparison is EDEN vs a conventional exact cache under paired request-level interleaving.
