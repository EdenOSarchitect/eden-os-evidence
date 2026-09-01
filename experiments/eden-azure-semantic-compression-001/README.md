# EDEN-AZURE-SEMANTIC-COMPRESSION-001

Purpose: measure how much byte reduction an EDEN semantic representation achieves at a predeclared semantic-quality threshold on an Azure VM.

The benchmark generates deterministic telemetry records, then compares:

1. Raw canonical JSON.
2. Conventional zlib compression of raw JSON.
3. `EDEN_TASK_SEMANTIC`: dictionary-coded task-relevant fields; source-only trace/span/sdk/schema/message fields are omitted.
4. `EDEN_MESSAGE_PRESERVING`: same structured representation while retaining message text.

The quality threshold defaults to **1.0**, meaning exact equality on the full predeclared analytics query suite is required. This avoids calling a representation successful merely because it is smaller.

Important truth boundary: `semantic_reduction_pct` is reduction relative to the source bytes while preserving the declared application semantics. It is not lossless source compression and cannot be compared directly to gzip/zlib as though the outputs had identical fidelity. `compressed_bytes_zlib` is provided separately as a conventional byte-compression comparator.

## Azure VM run

```bash
cd ~/eden-os-evidence
git fetch origin eden-azure-semantic-compression-001
git restore --source=origin/eden-azure-semantic-compression-001 --worktree experiments/eden-azure-semantic-compression-001
python3 -u experiments/eden-azure-semantic-compression-001/azure_semantic_compression_001.py \
  --records 100000 \
  --quality-threshold 1.0 \
  --environment AZURE_VM
```

For a larger follow-up after the 100k run completes successfully:

```bash
python3 -u experiments/eden-azure-semantic-compression-001/azure_semantic_compression_001.py \
  --records 1000000 \
  --quality-threshold 1.0 \
  --environment AZURE_VM
```

Headline fields: raw bytes, conventional zlib reduction, EDEN semantic reduction, EDEN+zlib reduction, exact semantic quality, threshold PASS/FAIL, pack/unpack CPU, trace commitment, and report commitment.
