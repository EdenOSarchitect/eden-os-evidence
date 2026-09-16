import copy

from marble.gateway import DestinationPolicy, evaluate_policy, route_marble
from marble.marble import mint, verify_integrity


def sample_core():
    return {
        "schema": "eden.marble.v2",
        "kind": "EXECUTION",
        "subject": {"type": "TEST", "name": "gateway"},
        "parents": [],
        "actor": {"id": "test-runner"},
        "policy": {"policy_id": "gateway-test", "policy_hash": "sha256:test-policy"},
        "input": {"commitment": "sha256:input"},
        "output": {"commitment": "sha256:output"},
        "resources": {"cpu_ms": 1},
        "quality": {"score": 1.0},
        "evidence": {"class": "MEASURED", "instrumentation": ["pytest"]},
        "truth": {"claims": ["gateway test"], "not_claimed": []},
        "provenance": {"sequence": 1, "source": "unit-test"},
        "timestamp": "2026-08-28T00:00:00Z",
    }


def test_valid_v2_marble_authorizes_https_dry_run(monkeypatch):
    monkeypatch.setattr("marble.gateway._host_is_private_or_local", lambda hostname: False)
    marble = mint(sample_core())
    result = route_marble(marble, "https://example.com/eden", dry_run=True)
    assert result["status"] == "AUTHORIZED_DRY_RUN"
    assert result["transmitted"] is False
    assert result["policy"]["allowed"] is True
    assert result["envelope"]["marble_id"] == marble["marble_id"]
    assert len(result["envelope_sha256"]) == 64


def test_tampered_committed_evidence_is_blocked(monkeypatch):
    monkeypatch.setattr("marble.gateway._host_is_private_or_local", lambda hostname: False)
    marble = mint(sample_core())
    tampered = copy.deepcopy(marble)
    tampered["evidence"]["class"] = "INDEPENDENTLY_VALIDATED"
    result = route_marble(tampered, "https://example.com/eden", dry_run=True)
    assert result["status"] == "BLOCKED_VERIFICATION_OR_POLICY"
    assert result["verification"]["integrity_verified"] is False
    assert result["transmitted"] is False


def test_measured_without_instrumentation_is_blocked(monkeypatch):
    monkeypatch.setattr("marble.gateway._host_is_private_or_local", lambda hostname: False)
    core = sample_core()
    core["evidence"]["instrumentation"] = []
    marble = mint(core)
    verification = verify_integrity(marble)
    assert verification["integrity_verified"] is True
    assert verification["evidence_verified"] is False
    result = route_marble(marble, "https://example.com/eden", dry_run=True)
    assert result["status"] == "BLOCKED_VERIFICATION_OR_POLICY"


def test_http_destination_is_blocked(monkeypatch):
    monkeypatch.setattr("marble.gateway._host_is_private_or_local", lambda hostname: False)
    marble = mint(sample_core())
    result = route_marble(marble, "http://example.com/eden", dry_run=True)
    assert result["status"] == "BLOCKED_DESTINATION"


def test_private_destination_is_blocked_by_default():
    marble = mint(sample_core())
    result = route_marble(marble, "https://127.0.0.1:8765/eden", dry_run=True)
    assert result["status"] == "BLOCKED_DESTINATION"


def test_private_destination_can_be_explicitly_enabled():
    marble = mint(sample_core())
    policy = DestinationPolicy(allow_private_networks=True)
    result = route_marble(marble, "https://127.0.0.1:8765/eden", policy=policy, dry_run=True)
    assert result["status"] == "AUTHORIZED_DRY_RUN"


def test_policy_can_report_individual_boundary_checks():
    verification = {
        "integrity_verified": True,
        "policy_verified": True,
        "provenance_verified": False,
        "evidence_verified": True,
        "errors": ["invalid provenance sequence"],
    }
    result = evaluate_policy(verification, DestinationPolicy())
    assert result["allowed"] is False
    assert result["checks"]["provenance"] is False
