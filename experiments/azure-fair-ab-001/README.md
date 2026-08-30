# AZURE-FAIR-AB-001

A provider-scale A/B harness for comparing a conventional Azure service boundary with the same boundary plus EDEN Core evidence/control overhead.

## Question

Does EDEN reduce total Azure resource consumption or cost for a defined reusable workload after EDEN's own overhead is included, without violating the required quality/latency envelope?

This harness is deliberately structured so that the first fair comparison can also return a neutral or negative result. It does **not** assume EDEN should beat a conventional exact cache.

## Identical outer service boundary

Both arms use the same local HTTP route:

```text
POST /evaluate
```

Both receive the same JSON request shape, same workload sequence, same Azure deployment, same maximum output setting, and the same exact SHA-256 cache algorithm with independent per-arm cache state.

### CONTROL

```text
HTTP
 -> JSON deserialisation
 -> exact SHA-256 cache lookup
 -> Azure OpenAI on cache miss
 -> quality check
 -> response
```

### EDEN

```text
HTTP
 -> JSON deserialisation
 -> same exact SHA-256 cache lookup
 -> Azure OpenAI on cache miss
 -> quality check
 -> EDEN Core integrated path
      Refinery
      -> ChronoNav reference scheduler
      -> Chrysalis evaluator
      -> Marble v2 mint
      -> Marble integrity verification
 -> response
```

This first benchmark therefore answers a narrow question: **what does the EDEN evidence/control layer cost relative to a conventional cache when both avoid exactly the same Azure calls?**

It is not yet a semantic-reuse benchmark. A later experiment can add a semantic reuse policy after this exact-cache baseline is established.

## What is measured

Per request the harness records:

- request UID and task index;
- input/output SHA-256 commitments;
- cache hit/miss;
- whether Azure was called;
- Azure deployment;
- Azure response ID where present;
- selected Azure/APIM request headers where exposed;
- provider-reported input/output token usage on provider calls;
- provider-call latency observed by the service;
- local service wall time;
- local service CPU time;
- deterministic task-quality result;
- EDEN Marble ID and integrity result in the EDEN arm;
- a SHA-256 commitment over each service record.

The manifest reports means/p50/p95 where appropriate and the direct EDEN-minus-CONTROL deltas.

## Cost evidence

There are two distinct cost paths.

### Token-price model

Optional:

```bash
--input-price-per-1m  <price>
--output-price-per-1m <price>
```

This produces:

```text
MODELLED_FROM_PROVIDER_REPORTED_USAGE
```

It is not called Azure billing.

### Azure billing export

Optional:

```bash
--billing-json /path/to/billing-evidence.json
```

The supplied file is preserved by SHA-256 in the benchmark manifest. The harness does not independently attest the Azure origin of the export; provenance should therefore be supplied with the file.

For a strong provider review, run CONTROL and EDEN in separable Azure billing scopes/tags/time windows so billing can be attributed without inference.

## Energy

This harness does not invent an Azure energy figure.

If Azure or a hardware/telemetry provider exposes a defensible energy measurement, preserve it as a separate evidence source with instrumentation/provenance and bind it into the result later.

## Deterministic quality task

Every generated prompt asks the provider for strict JSON containing a known task index and checksum. The quality checker independently verifies:

- index;
- checksum;
- allowed EDEN classification;
- <=12-word summary.

This is intentionally simple. Provider-scale follow-up should use a real application task and a frozen quality metric.

## Workload reuse distribution

Example:

```bash
--requests 1000 --unique-tasks 250
```

creates 1,000 requests per arm with 250 unique exact prompts and a target 75% duplicate/reuse fraction.

Each arm starts with an independent empty cache and receives the same request sequence. Arm order is shuffled per workload item to reduce time-of-run bias.

## CI / no-cost run

The harness includes a deterministic mock provider for CI. Mock results are classified as simulation and cannot be represented as Azure measurement.

```bash
python experiments/azure-fair-ab-001/azure_fair_ab.py \
  --provider mock \
  --requests 20 \
  --unique-tasks 5 \
  --output-dir /tmp/azure-fair-ab
```

Run tests:

```bash
python -m unittest experiments/azure-fair-ab-001/test_azure_fair_ab.py
```

## Real Azure run

Required environment variables:

```bash
export AZURE_OPENAI_ENDPOINT='https://...'
export AZURE_OPENAI_API_KEY='...'
export AZURE_OPENAI_DEPLOYMENT='...'
```

Start small because this performs paid provider calls on cache misses in **both** arms:

```bash
python experiments/azure-fair-ab-001/azure_fair_ab.py \
  --provider azure \
  --requests 40 \
  --unique-tasks 10 \
  --output-dir experiments/azure-fair-ab-001/results/AZURE-FAIR-AB-001-RUN-001
```

Then scale only when budget is approved.

A 1,000-request / 250-unique-task run causes approximately 250 Azure calls for CONTROL and 250 for EDEN, assuming no provider errors and exact-cache behavior as designed. That is about 500 paid provider calls, not 2,000.

## Output

```text
results/<run>/
  control-records.jsonl
  eden-records.jsonl
  service-events.jsonl
  manifest.json
  state/
```

The manifest includes SHA-256 commitments for the record files and for itself.

## Interpretation

The fair initial hypothesis is not "EDEN must be faster than a cache."

With identical exact-cache behavior, provider-call count and provider token consumption should normally be approximately equal between CONTROL and EDEN. The useful result is then the measured incremental cost of EDEN's evidence/control layer.

A future EDEN semantic/reuse policy only has a resource advantage if the additional Azure work it avoids exceeds this measured EDEN overhead while maintaining the frozen quality requirement.

Conceptually:

```text
net_EDEN_value
=
avoided_Azure_work
-
measured_EDEN_overhead
```

subject to:

```text
quality_EDEN >= required_quality
```

## Claim boundary

This experiment can support claims about the exact workload, Azure deployment, service implementation and run whose evidence is preserved.

It does not by itself establish:

- universal Azure savings;
- Azure energy reduction;
- hyperscale production reliability;
- semantic equivalence beyond the frozen quality task;
- independent validation.
