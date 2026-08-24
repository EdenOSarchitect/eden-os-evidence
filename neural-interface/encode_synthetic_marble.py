#!/usr/bin/env python3
import argparse, hashlib, json, math, platform, random
from datetime import datetime, timezone

TRUTH = "Synthetic neural-interface data only; not physiological evidence, medical telemetry, or a Neuralink device measurement."


def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=20260824)
    ap.add_argument("--channels", type=int, default=8)
    ap.add_argument("--sample-rate", type=int, default=1000)
    ap.add_argument("--window-ms", type=int, default=100)
    ap.add_argument("--prev", default=None)
    ap.add_argument("--output", default="neural-interface/results/neuralink-style-marble.json")
    args = ap.parse_args()

    rng = random.Random(args.seed)
    n = int(args.sample_rate * args.window_ms / 1000)
    samples = []
    for c in range(args.channels):
        phase = rng.random() * math.tau
        for i in range(n):
            t = i / args.sample_rate
            x = 7000 * math.sin(math.tau * (8 + c) * t + phase) + rng.gauss(0, 1200)
            samples.append(max(-32768, min(32767, int(round(x)))))

    signal = {
        "sample_rate_hz": args.sample_rate,
        "channels": args.channels,
        "window_ms": args.window_ms,
        "encoding": "synthetic-normalized-int16",
        "samples": samples,
    }
    payload_sha = hashlib.sha256(canonical(signal)).hexdigest()
    marble = {
        "marble_id": f"EDEN-NI-{args.seed}-{payload_sha[:12]}",
        "evidence_class": "SIMULATED",
        "source": {
            "device_class": "neural-interface-synthetic",
            "device_connected": False,
            "vendor_claim": "NO_LIVE_NEURALINK_CONNECTION"
        },
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "signal": signal,
        "provenance": {
            "payload_sha256": payload_sha,
            "prev_marble_sha256": args.prev,
            "truth_boundary": TRUTH
        },
        "run_environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "seed": args.seed
        }
    }
    import os
    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w") as f:
        json.dump(marble, f, indent=2)
    print(json.dumps({"marble_id": marble["marble_id"], "payload_sha256": payload_sha, "output": args.output, "evidence_class": "SIMULATED"}, indent=2))

if __name__ == "__main__":
    main()
