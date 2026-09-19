# EDEN-AZURE-CAPACITY-002

Purpose: compare full recomputation, a minimal conventional exact cache, EDEN exact reuse with evidence commitments, and EDEN with reuse disabled on the same host.

The experiment asks a narrower question than EDEN-AZURE-CAPACITY-001: what compute/capacity benefit remains after comparing EDEN with an ordinary exact cache, and what local assurance overhead does EDEN add?

## Arms

- `CONTROL`: recomputes every request.
- `CACHE`: minimal in-process exact cache keyed by `(seed, iterations)`.
- `EDEN`: exact reuse keyed by a canonical workload commitment, verifies cached values, and emits per-request evidence commitments into an evidence-chain commitment.
- `EDEN_NOREUSE`: runs the full workload every request while still emitting the EDEN evidence path. This estimates non-reuse EDEN overhead against CONTROL.

All arms receive the same deterministic request sequence for each reuse point. Arm order is deterministically randomized per sweep point to reduce fixed-order bias.

## Fast Azure VM flagship

```bash
cd ~/eden-os-evidence
git fetch origin
git checkout eden-azure-capacity-002
git pull origin eden-azure-capacity-002

python -u experiments/eden-azure-capacity-002/azure_capacity_002.py \
  --outputs 5000 \
  --iterations 30000 \
  --reuse 0 0.25 0.50 0.75 \
  --environment AZURE_VM
```

This performs 4 reuse points × 4 arms. Start with this shorter sweep before attempting 10k/20k outputs.

## Metrics

For each arm/reuse point the report records host process CPU time, wall time, mean/p50/p95 local request latency, outputs per second, outputs per VM-hour, outputs per CPU-second, full executions, reuse hits, output commitment, process maximum RSS at arm end, and EDEN evidence-chain commitment where applicable.

Derived comparisons include:

- CONTROL → CACHE CPU reduction
- CONTROL → EDEN CPU reduction
- CONTROL → EDEN wall reduction
- CONTROL → EDEN capacity gain
- EDEN_NOREUSE minus CONTROL CPU/wall overhead
- EDEN minus CACHE CPU/wall assurance premium
- executions avoided by CACHE and EDEN

## Interpretation

A strong result does not require EDEN to beat a minimal cache in raw lookup speed. The commercially relevant question is whether EDEN remains close enough to conventional cache performance while adding verifiable evidence/provenance/resource-accounting behavior, and whether workloads with expensive repeated execution still produce a material net reduction after EDEN overhead.

`CACHE` is deliberately a minimal in-process comparator. It is not equivalent to Redis, Memcached, CDN caching, database query caching, or a production distributed cache. A later experiment should compare equivalent HTTP/service boundaries.

## Truth boundary

Evidence class: `MEASURED_HOST_PROCESS_CPU_WALL_AND_WORKLOAD_CAPACITY` when run on the stated host.

The experiment does not establish Azure datacentre energy savings, Azure billing reduction, general cloud efficiency superiority, superiority over all production cache systems, or independent validation. `outputs_per_vm_hour` is workload throughput measured on the tested VM, not a claim that EDEN changes physical VM specifications.
