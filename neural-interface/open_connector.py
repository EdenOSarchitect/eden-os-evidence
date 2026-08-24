#!/usr/bin/env python3
"""EDEN open neural-interface connector.

Observation-only ingress. It does not generate synthetic neural data and does not
claim a Neuralink connection. It accepts newline-delimited JSON from stdin or a
user-specified local TCP endpoint, hashes each raw observation, and emits a
provenance envelope without interpreting physiological meaning.
"""
import argparse, hashlib, json, socket, sys
from datetime import datetime, timezone


def envelope(raw: bytes, source: str):
    return {
        "connector": "EDEN-NI-OPEN-001",
        "mode": "OBSERVE_ONLY",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "source": source,
        "payload_sha256": hashlib.sha256(raw).hexdigest(),
        "payload_bytes": len(raw),
        "evidence_class": "OBSERVED_INPUT",
        "truth_boundary": (
            "Records bytes presented to this connector only. Source/vendor/device identity "
            "is not independently authenticated by EDEN. No physiological or medical inference is made."
        ),
    }


def consume(stream, source):
    for raw in stream:
        if not raw.strip():
            continue
        meta = envelope(raw.rstrip(b"\r\n"), source)
        print(json.dumps(meta, sort_keys=True), flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--listen", help="Optional local bind HOST:PORT. Omit to observe stdin.")
    args = ap.parse_args()
    if not args.listen:
        consume(sys.stdin.buffer, "stdin")
        return
    host, port = args.listen.rsplit(":", 1)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((host, int(port)))
        s.listen(1)
        print(json.dumps({"connector":"EDEN-NI-OPEN-001","status":"LISTENING","bind":args.listen,"mode":"OBSERVE_ONLY"}), flush=True)
        while True:
            conn, addr = s.accept()
            with conn, conn.makefile("rb") as f:
                consume(f, f"tcp:{addr[0]}:{addr[1]}")

if __name__ == "__main__":
    main()
