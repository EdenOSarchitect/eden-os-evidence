# EDEN-AZURE-APPLICATION-001

Pilot-oriented local HTTP benchmark comparing:

- **CONTROL** — every request performs the deterministic workload.
- **CACHE** — conventional exact-key in-memory caching, with no assurance record.
- **EDEN** — exact reuse with a record binding the input, semantic output, policy,
  provenance and complete record; every result is verified before use.

All modes use the same request stream, response schema, HTTP endpoint and fresh
child-process boundary. The child contains both the load generator and service,
so CPU and RSS are whole-harness process measurements. Response-body equality
keeps application payload bytes comparable.

## CI smoke check

```bash
python -m unittest experiments/eden-azure-application-001/test_azure_application_001.py
python experiments/eden-azure-application-001/azure_application_001.py \
  --requests 60 --iterations 500 --reuse 0.50 --concurrency 4 \
  --environment CI_LOCAL --output-dir /tmp/eden-azure-application
```

## Azure pilot runbook

Use a dedicated, otherwise-idle Linux VM. Record the VM SKU, region, image,
Python version and effective hourly price. Disable unrelated scheduled work and
do not change VM sizing or power state during the run.

1. Clone the exact PR commit and confirm a clean tree:

   ```bash
   git clone https://github.com/EdenOSarchitect/eden-os-evidence.git
   cd eden-os-evidence
   git fetch origin pull/19/head:pr-19
   git checkout pr-19
   git status --short
   git rev-parse HEAD
   ```

2. Run tests and a short smoke check:

   ```bash
   python3 -m unittest experiments/eden-azure-application-001/test_azure_application_001.py
   python3 experiments/eden-azure-application-001/azure_application_001.py \
     --requests 60 --iterations 500 --reuse 0.50 --concurrency 4 \
     --environment AZURE_VM_SMOKE --output-dir /tmp/eden-app-smoke
   ```

3. Allow the VM to return to idle, then run the single long primary trial:

   ```bash
   mkdir -p experiments/eden-azure-application-001/results
   python3 -u experiments/eden-azure-application-001/azure_application_001.py \
     --requests 10000 --iterations 30000 --reuse 0.50 --concurrency 8 \
     --seed 260907 --environment AZURE_VM \
     --output-dir experiments/eden-azure-application-001/results
   ```

   The seed deterministically randomizes request order and arm order, both of
   which are committed in the report. For an exact rerun, copy the recorded
   order into `--arm-order CONTROL,CACHE,EDEN` (using the actual order).

4. Optionally attach an Azure Monitor or billing export and a known VM price:

   ```bash
   python3 -u experiments/eden-azure-application-001/azure_application_001.py \
     --requests 10000 --iterations 30000 --reuse 0.50 --concurrency 8 \
     --seed 260907 --environment AZURE_VM \
     --vm-hour-cost 0.00 --external-evidence azure-monitor-export.json
   ```

   Replace `0.00` with the effective price. The export is only byte-counted and
   hashed: the harness does not interpret or time-align it.

5. Preserve the JSON result, terminal output, commit SHA, VM metadata and
   external evidence together. A pilot reviewer should rerun from the recorded
   commit and configuration.

## Acceptance checks

A credible successful run must show:

- identical semantic output commitments across all three arms;
- zero failed requests and zero EDEN verification failures;
- CONTROL full executions equal requests;
- CACHE and EDEN full executions equal unique requests;
- executions avoided equal realized repeated requests;
- equal application request/response body bytes across arms;
- fresh-process RSS scope and the complete truth boundary in the report.

## Evidence interpretation

The primary comparison is EDEN versus CONTROL. CACHE versus CONTROL establishes
the value of conventional reuse. EDEN versus CACHE isolates the overhead of
binding and verifying assurance metadata.

This is a controlled, real local HTTP application path—not a third-party
production workload. One long run per arm is operationally simple, but cannot
support confidence intervals or statistical significance and remains exposed
to time/order drift. It measures child-process CPU, wall time, lifetime peak
RSS, client-observed loopback latency, throughput, application body bytes,
execution counts and integrity outcomes. It does not measure Azure platform
CPU, network transit, energy, carbon, or invoices. A user-supplied
`--environment AZURE_VM` label is not accepted as proof; the stronger Azure
evidence class requires the Linux DMI vendor signal to identify Microsoft.
