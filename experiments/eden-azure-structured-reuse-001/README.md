# EDEN-AZURE-STRUCTURED-REUSE-001

Purpose: test whether EDEN can exploit reusable structure below the whole-request level on an Azure VM while avoiding the sequential-arm bias found in earlier whole-arm benchmarks.

Each logical request is unique, so a conventional whole-request cache should have approximately zero reuse. Requests are composed of reusable JSON sections drawn from a larger trace. Four arms are executed for every request in randomized order within one process:

- CONTROL: recompute every section.
- WHOLE_CACHE: exact whole-request cache.
- COMPONENT_CACHE: conventional exact cache at section granularity. This is the strongest caching comparator.
- EDEN: section commitment/reuse plus per-request evidence records.

The trace determines the observed whole-request and section reuse fractions. There is no user-supplied reuse percentage.

The key scientific comparison is EDEN versus COMPONENT_CACHE. EDEN is expected to be slightly more expensive because it performs commitment/evidence work. If EDEN unexpectedly beats COMPONENT_CACHE materially, investigate the harness rather than treating it as a headline result.

Run on the Azure VM:

```bash
python3 -u experiments/eden-azure-structured-reuse-001/azure_structured_reuse_001.py \
  --requests 1200 \
  --rounds 120 \
  --environment AZURE_VM
```

For a quicker smoke test:

```bash
python3 -u experiments/eden-azure-structured-reuse-001/azure_structured_reuse_001.py \
  --requests 200 \
  --rounds 30 \
  --environment AZURE_VM_SMOKE
```

Evidence boundary: measured host/process CPU and wall timing only. This experiment does not establish Azure datacentre energy savings, Azure invoice savings, or that EDEN is fundamentally non-caching technology. It tests whether EDEN can coordinate auditable reuse below whole-request granularity while preserving outputs.
