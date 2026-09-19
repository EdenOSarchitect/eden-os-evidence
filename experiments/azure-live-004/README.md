# AZURE-LIVE-004

Paired identical-provider-response overhead experiment.

## Question

What local CPU/wall overhead does the integrated EDEN path add when CONTROL and EDEN receive the exact same already-captured provider output?

## Method

1. Capture each unique Azure response once using structured outputs.
2. Require the capture to pass the frozen quality gate.
3. Replay the exact same captured output bytes through CONTROL and EDEN.
4. Randomize CONTROL/EDEN order within each replay pair.
5. Make **zero provider calls during replay timing**.
6. Measure paired local CPU and wall-time deltas.
7. EDEN executes Refinery -> ChronoNav -> Chrysalis -> Marble v2 -> verification.

This experiment isolates EDEN local orchestration/evidence overhead from Azure generation latency and reasoning-token variability.

## Live Azure run

The harness reads Azure credentials only from environment variables:

- `AZURE_OPENAI_ENDPOINT`
- `AZURE_OPENAI_API_KEY`
- `AZURE_OPENAI_DEPLOYMENT`

Example:

```bash
python experiments/azure-live-004/azure_live_004.py \
  --provider azure \
  --unique-tasks 2 \
  --repeats 20 \
  --max-output-tokens 512 \
  --output-dir experiments/azure-live-004/results/AZURE-LIVE-004
```

With two unique tasks, the capture phase should make exactly two Azure provider calls. The 40 paired replays then make no additional provider calls.

## Free mock check

```bash
python experiments/azure-live-004/azure_live_004.py \
  --provider mock \
  --unique-tasks 2 \
  --repeats 3 \
  --output-dir experiments/azure-live-004/results/MOCK-004
```

## Evidence outputs

- `captures.jsonl` — provider capture provenance, provider-reported usage and quality.
- `replay-records.jsonl` — paired CONTROL/EDEN local timing and EDEN verification records.
- `manifest.json` — summary metrics and SHA-256 commitments.

## Truth boundary

This experiment can support a measured claim about **local EDEN overhead on this device/workload**. It does not by itself establish Azure energy savings, Azure billing savings, provider latency improvement, general efficiency superiority, or independent validation.
