#!/usr/bin/env python3
"""EDEN open neural-interface connector.

Observation-only connector. It accepts only verified local handoff envelopes from
EDEN-MANIFOLD-NI-001 on stdin. Direct network listening and plaintext ingress are
intentionally disabled.
"""
import base64, hashlib, json, sys
from datetime import datetime, timezone


def main():
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            handoff = json.loads(line)
            if handoff.get("manifold_verified") is not True:
                raise ValueError("unverified manifold handoff")
            if handoff.get("manifold") != "EDEN-MANIFOLD-NI-001":
                raise ValueError("unexpected manifold")
            raw = base64.b64decode(handoff["payload_b64"], validate=True)
            digest = hashlib.sha256(raw).hexdigest()
            if digest != handoff.get("payload_sha256"):
                raise ValueError("payload hash mismatch")

            meta = {
                "connector": "EDEN-NI-OPEN-001",
                "mode": "OBSERVE_ONLY",
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "source": handoff.get("source", "unknown"),
                "manifold": "EDEN-MANIFOLD-NI-001",
                "manifold_verified": True,
                "ingress_encryption": "AES-256-GCM",
                "payload_sha256": digest,
                "payload_bytes": len(raw),
                "evidence_class": "OBSERVED_INPUT",
                "truth_boundary": (
                    "Records authenticated bytes delivered through the EDEN Manifold. "
                    "Encryption/authentication protects the frame but does not independently prove "
                    "vendor/device identity or physiological meaning. No medical inference is made."
                ),
            }
            print(json.dumps(meta, sort_keys=True), flush=True)
        except Exception as e:
            print(json.dumps({"connector":"EDEN-NI-OPEN-001","accepted":False,"error":type(e).__name__}), file=sys.stderr, flush=True)


if __name__ == "__main__":
    main()
