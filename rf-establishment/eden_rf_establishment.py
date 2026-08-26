import json
import subprocess
import hashlib
import datetime
import os
import sys

OUT = os.path.expanduser("~/eden-rf/results/EDEN_RF_EST_001.json")

def utcnow():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()

print("======================================")
print(" EDEN RF ESTABLISHMENT EXPERIMENT")
print(" EDEN-RF-EST-001")
print("======================================")
print()
print("Objective:")
print("Establish physical RF reception using handset radio")
print("and record observed RSSI + carrier frequency.")
print()

try:
    raw = subprocess.check_output(
        ["termux-wifi-scaninfo"],
        stderr=subprocess.STDOUT,
        timeout=30
    ).decode()
except Exception as e:
    print("RF SCAN FAILED")
    print(e)
    print()
    print("Make sure:")
    print("  1. Termux:API Android app is installed")
    print("  2. Nearby devices / location permission is granted")
    print("  3. Wi-Fi is enabled")
    sys.exit(1)

try:
    aps = json.loads(raw)
except Exception:
    print("Could not parse scan data:")
    print(raw)
    sys.exit(1)

if not isinstance(aps, list) or not aps:
    print("NO RF SOURCES OBSERVED")
    sys.exit(2)

valid = [
    ap for ap in aps
    if isinstance(ap, dict)
    and isinstance(ap.get("level"), (int, float))
]

if not valid:
    print("RF sources returned, but RSSI was not exposed.")
    sys.exit(3)

valid.sort(key=lambda x: x["level"], reverse=True)
observations = []

for ap in valid:
    bssid = str(ap.get("bssid", "UNKNOWN"))
    bssid_commitment = hashlib.sha256(bssid.encode()).hexdigest()
    observations.append({
        "rssi_dbm": ap.get("level"),
        "frequency_mhz": ap.get("frequency_mhz", ap.get("frequency")),
        "channel_bandwidth_mhz": ap.get("channel_bandwidth_mhz", ap.get("channelBandwidth")),
        "bssid_sha256": bssid_commitment
    })

strongest = observations[0]

evidence = {
    "experiment": "EDEN-RF-EST-001",
    "system": "EDEN",
    "evidence_class": "OBSERVED_INPUT",
    "claim": {
        "rf_reception_established": True,
        "rssi_measured": True,
        "external_rf_source_observed": True,
        "not_claimed": [
            "RF transmission",
            "decoded payload ownership",
            "raw IQ capture",
            "SDR functionality",
            "antenna gain",
            "transmit power",
            "source distance"
        ]
    },
    "sensor": {
        "type": "ANDROID_WIFI_RADIO",
        "measurement": "RSSI",
        "unit": "dBm"
    },
    "strongest_observation": strongest,
    "number_of_rf_sources": len(observations),
    "observations": observations,
    "timestamp_utc": utcnow()
}

canonical = json.dumps(evidence, sort_keys=True, separators=(",", ":")).encode()
evidence["evidence_sha256"] = hashlib.sha256(canonical).hexdigest()

with open(OUT, "w") as f:
    json.dump(evidence, f, indent=2)

print("RF ESTABLISHMENT: PASS")
print()
print("External RF sources:", len(observations))
print("Strongest RSSI:", strongest["rssi_dbm"], "dBm")
print("Frequency:", strongest["frequency_mhz"], "MHz")
print()
print("EVIDENCE CLASS: OBSERVED_INPUT")
print("RF SIGNAL: MEASURED")
print("RSSI: MEASURED")
print("SIMULATION: NO")
print("LOCAL LOOPBACK: NO")
print()
print("Evidence SHA-256:")
print(evidence["evidence_sha256"])
print()
print("Saved:")
print(OUT)
print()
print("=== EDEN RF ESTABLISHMENT COMPLETE ===")
