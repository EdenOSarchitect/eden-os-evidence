#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SOURCE="${1:-$HOME/eden-physical/results/EDEN_PHYSICAL_COMPUTE_001.json}"
OUT_DIR="${OUT_DIR:-$HOME/eden-physical/results/marble-e2e}"
KEY_ID="${EDEN_MARBLE_KEY_ID:-handset-compute-local}"

if [[ ! -f "$SOURCE" ]]; then
  echo "physical compute evidence not found: $SOURCE" >&2
  exit 2
fi
if [[ -z "${EDEN_MARBLE_SIGNING_KEY:-}" ]]; then
  echo "EDEN_MARBLE_SIGNING_KEY is required for signed physical E2E" >&2
  exit 2
fi

mkdir -p "$OUT_DIR"

python "$ROOT/marble/physical_telemetry.py" \
  "$SOURCE" \
  --output "$OUT_DIR/physical-compute-telemetry.json"

python "$ROOT/marble/telemetry_e2e.py" run \
  "$OUT_DIR/physical-compute-telemetry.json" \
  --output "$OUT_DIR/EDEN-MARBLE-PHYSICAL-COMPUTE-E2E-001.json" \
  --log "$OUT_DIR/providence.jsonl" \
  --head "$OUT_DIR/provenance-head.json" \
  --key-id "$KEY_ID"

python "$ROOT/marble/telemetry_e2e.py" verify \
  "$OUT_DIR/EDEN-MARBLE-PHYSICAL-COMPUTE-E2E-001.json"

python - "$OUT_DIR/EDEN-MARBLE-PHYSICAL-COMPUTE-E2E-001.json" <<'PY'
import json, sys
p=sys.argv[1]
a=json.load(open(p, encoding='utf-8'))
if a['marble']['evidence']['class'] != 'MEASURED':
    raise SystemExit('physical compute did not retain MEASURED evidence class')
if a['marble']['input']['source_evidence'].get('physical_capture') is not True:
    raise SystemExit('physical source flag missing')
if a.get('e2e_verified') is not True:
    raise SystemExit('physical compute Marble E2E verification failed')
print('PHYSICAL COMPUTE -> VERIFIED MARBLE E2E: PASS')
print('artifact_id:', a['artifact_id'])
print('marble_id:', a['marble']['marble_id'])
print('wall_time_ms:', a['marble']['resources'].get('wall_time_ms'))
print('cpu_seconds:', a['marble']['resources'].get('cpu_seconds'))
print('memory_peak_bytes:', a['marble']['resources'].get('memory_peak_bytes'))
PY
