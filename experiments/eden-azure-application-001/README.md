# EDEN-AZURE-APPLICATION-001

A real local HTTP service benchmark intended to run on an Azure VM. It compares the same request stream across CONTROL (full execution), CACHE (minimal exact cache), and EDEN (exact reuse plus committed integrity metadata).

## Primary question

Does EDEN improve useful HTTP application capacity and reduce host process work, while preserving outputs, and how close is it to a conventional cache comparator?

## Quick smoke run

```bash
python -u experiments/eden-azure-application-001/azure_application_001.py --requests 60 --iterations 500 --reuse 0.5 --concurrency 4 --environment TEST_HOST
```

## Azure VM pilot

```bash
python -u experiments/eden-azure-application-001/azure_application_001.py \
  --requests 3000 \
  --iterations 30000 \
  --reuse 0.50 \
  --concurrency 8 \
  --environment AZURE_VM
```

If the VM's effective hourly price is known, add `--vm-hour-cost PRICE` to calculate a MODELLED cost per million successful outputs. This is not the same as measured Azure invoice savings.

An Azure Monitor/billing export may be attached with `--external-evidence path/to/file.json`. The report hashes that file but does not automatically reinterpret its contents.

## Metrics

CPU seconds, wall seconds, p50/p95/p99 HTTP latency, successful requests/sec, successful outputs/VM-hour, max RSS, request/response bytes, full executions, reuse hits, and semantic output equivalence.

## Truth boundary

The harness measures host/application behavior. It does not by itself measure Azure datacentre energy or prove Azure invoice savings. Actual billing/resource claims require Azure-native telemetry or billing evidence over the same test windows. The deterministic application is a real HTTP execution path but remains a controlled benchmark, not yet a third-party production workload.
