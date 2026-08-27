#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RF_OUT="${RF_OUT:-$HOME/eden-rf/results/EDEN_RF_EST_001.json}"
OUT_DIR="${OUT_DIR:-$HOME/eden-rf/results/marble-e2e}"
KEY_ID="${EDEN_MARBLE_KEY_ID:-handset-local}"

if [[ -z "${EDEN_MARBLE_SIGNING_KEY:-}" ]]; then
  echo "EDEN_MARBLE_SIGNING_KEY is required for the signed physical E2E path" >&2
  exit 2
fi

mkdir -p "$OUT_DIR"

python "$ROOT/rf-establishment/eden_rf_establishment.py"

python "$ROOT/marble/physical_telemetry.py" \
  "$RF_OUT" \
  --output "$OUT_DIR/physical-telemetry.json"

python "$ROOT/marble/telemetry_e2e.py" run \
  "$OUT_DIR/physical-telemetry.json" \
  --output "$OUT_DIR/EDEN-MARBLE-PHYSICAL-E2E-001.json" \
  --log "$OUT_DIR/providence.jsonl" \
  --head "$OUT_DIR/provenance-head.json" \
  --key-id "$KEY_ID"

python "$ROOT/marble/telemetry_e2e.py" verify \
  "$OUT_DIR/EDEN-MARBLE-PHYSICAL-E2E-001.json"

python - "$OUT_DIR/EDEN-MARBLE-PHYSICAL-E2E-001.json" <<'PY'
import json, sys
p=sys.argv[1]
a=json.load(open(p, encoding='utf-8'))
if a['marble']['evidence']['class'] != 'MEASURED':
    raise SystemExit('physical capture did not retain MEASURED evidence class')
if a['marble']['input']['source_evidence'].get('physical_capture') is not True:
    raise SystemExit('physical source flag missing')
if a.get('e2e_verified') is not True:
    raise SystemExit('physical Marble E2E verification failed')
print('PHYSICAL TELEMETRY -> VERIFIED MARBLE E2E: PASS')
print('artifact_id:', a['artifact_id'])
print('marble_id:', a['marble']['marble_id'])
print('RSSI dBm:', a['marble']['evidence']['observations'].get('rssi_dbm'))
print('frequency MHz:', a['marble']['evidence']['observations'].get('frequency_mhz'))
PY
