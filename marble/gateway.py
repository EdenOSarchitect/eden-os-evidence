#!/usr/bin/env python3
"""EDEN Marble v2 off-ramp gateway.

A Marble must pass v2 integrity verification and a destination policy before it
can leave the local runtime. The first implemented off-ramp is HTTPS webhook
POST, with dry-run support for reproducible testing.

Integrity proves commitment consistency; it does not prove the external truth
of claims inside a Marble and it does not create a payment obligation.
"""
from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import socket
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

from .marble import canonical_bytes, verify_integrity

GATEWAY_SCHEMA = "eden.marble.gateway.v1"
DEFAULT_TIMEOUT_SECONDS = 10.0


@dataclass(frozen=True)
class DestinationPolicy:
    """Policy applied after Marble verification and before transmission."""

    require_integrity: bool = True
    require_policy: bool = True
    require_provenance: bool = True
    require_evidence: bool = True
    require_https: bool = True
    allow_private_networks: bool = False


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def evaluate_policy(verification: Mapping[str, Any], policy: DestinationPolicy) -> Dict[str, Any]:
    checks = {
        "integrity": (not policy.require_integrity) or verification.get("integrity_verified") is True,
        "policy": (not policy.require_policy) or verification.get("policy_verified") is True,
        "provenance": (not policy.require_provenance) or verification.get("provenance_verified") is True,
        "evidence": (not policy.require_evidence) or verification.get("evidence_verified") is True,
    }
    return {
        "allowed": all(checks.values()),
        "checks": checks,
        "verification_errors": list(verification.get("errors", [])),
    }


def _host_is_private_or_local(hostname: str) -> bool:
    if hostname.lower() == "localhost":
        return True
    try:
        addresses = {item[4][0] for item in socket.getaddrinfo(hostname, None)}
    except socket.gaierror:
        return False
    for addr in addresses:
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            continue
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            return True
    return False


def validate_destination(url: str, policy: DestinationPolicy) -> Dict[str, Any]:
    parsed = urllib.parse.urlparse(url)
    errors = []
    if parsed.scheme not in {"https", "http"}:
        errors.append("destination must use http or https")
    if policy.require_https and parsed.scheme != "https":
        errors.append("destination policy requires https")
    if not parsed.hostname:
        errors.append("destination hostname is missing")
    if parsed.username or parsed.password:
        errors.append("credentials in destination URL are not allowed")
    if parsed.hostname and not policy.allow_private_networks and _host_is_private_or_local(parsed.hostname):
        errors.append("private, loopback, link-local, or reserved destinations are not allowed")
    return {"allowed": not errors, "errors": errors}


def build_envelope(marble: Mapping[str, Any], verification: Mapping[str, Any], destination: str) -> Dict[str, Any]:
    envelope = {
        "schema": GATEWAY_SCHEMA,
        "gateway_timestamp": utcnow(),
        "destination": destination,
        "marble_id": marble.get("marble_id"),
        "verification": dict(verification),
        "marble": dict(marble),
    }
    envelope["envelope_sha256"] = hashlib.sha256(canonical_bytes(envelope)).hexdigest()
    return envelope


def route_marble(
    marble: Mapping[str, Any],
    destination: str,
    *,
    policy: Optional[DestinationPolicy] = None,
    dry_run: bool = False,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
) -> Dict[str, Any]:
    policy = policy or DestinationPolicy()
    verification = verify_integrity(marble)
    policy_result = evaluate_policy(verification, policy)
    destination_result = validate_destination(destination, policy)

    result: Dict[str, Any] = {
        "schema": GATEWAY_SCHEMA,
        "marble_id": marble.get("marble_id"),
        "verification": verification,
        "policy": policy_result,
        "destination_policy": destination_result,
        "transmitted": False,
        "dry_run": dry_run,
    }
    if not policy_result["allowed"]:
        result["status"] = "BLOCKED_VERIFICATION_OR_POLICY"
        return result
    if not destination_result["allowed"]:
        result["status"] = "BLOCKED_DESTINATION"
        return result

    envelope = build_envelope(marble, verification, destination)
    result["envelope_sha256"] = envelope["envelope_sha256"]
    if dry_run:
        result["status"] = "AUTHORIZED_DRY_RUN"
        result["envelope"] = envelope
        return result

    body = canonical_bytes(envelope)
    req = urllib.request.Request(
        destination,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "User-Agent": "EDEN-Marble-Gateway/1",
            "X-EDEN-Marble-ID": str(marble.get("marble_id", "")),
            "X-EDEN-Envelope-SHA256": envelope["envelope_sha256"],
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_seconds) as response:
            response_body = response.read(4096).decode("utf-8", errors="replace")
            result.update(
                {
                    "status": "TRANSMITTED",
                    "transmitted": True,
                    "http_status": response.status,
                    "response_excerpt": response_body,
                }
            )
    except urllib.error.HTTPError as exc:
        result.update({"status": "REMOTE_HTTP_ERROR", "http_status": exc.code, "error": str(exc)})
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        result.update({"status": "TRANSPORT_ERROR", "error": str(exc)})
    return result


def _load(path: str) -> Dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Marble input must be a JSON object")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify, authorize, and route an EDEN Marble v2 off-ramp")
    parser.add_argument("input", help="path to Marble v2 JSON")
    parser.add_argument("destination", help="HTTPS webhook URL")
    parser.add_argument("--dry-run", action="store_true", help="authorize and build the envelope without transmitting")
    parser.add_argument("--allow-private-network", action="store_true", help="allow loopback/private destinations for controlled local tests")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_SECONDS)
    args = parser.parse_args()

    policy = DestinationPolicy(allow_private_networks=args.allow_private_network)
    try:
        result = route_marble(
            _load(args.input),
            args.destination,
            policy=policy,
            dry_run=args.dry_run,
            timeout_seconds=args.timeout,
        )
    except Exception as exc:
        print(json.dumps({"status": "GATEWAY_ERROR", "error": str(exc)}, indent=2, sort_keys=True))
        return 2

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] in {"AUTHORIZED_DRY_RUN", "TRANSMITTED"} else 1


if __name__ == "__main__":
    sys.exit(main())
