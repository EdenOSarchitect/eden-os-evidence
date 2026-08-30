#!/usr/bin/env python3
"""EDEN Chrysalis experimental adaptive resource evaluator.

Chrysalis evaluates candidate strategies against a supplied baseline, charges
active + metadata + recovery + regeneration + orchestration costs, enforces a
quality floor, and selects the lowest-net-cost qualifying candidate.

Evidence truth boundary:
- caller-supplied observations may be evaluated without being treated as measured;
- a record that explicitly claims evidence.class == MEASURED must carry a
  measurement_provenance object with a Marble v2 reference and instrumentation;
- Chrysalis validates this provenance shape but does not independently establish
  that the referenced physical measurement is scientifically correct.
"""
from __future__ import annotations

from typing import Any, Dict, Mapping

RESOURCE_FIELDS = (
    "active",
    "metadata",
    "recovery",
    "regeneration",
    "orchestration",
)


def _number(value: Any, name: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError(f"{name} must be numeric")
    return float(value)


def _evidence(record: Mapping[str, Any], name: str) -> Dict[str, Any]:
    raw = record.get("evidence")
    if raw is None:
        return {
            "class": "SUPPLIED",
            "measurement_provenance": None,
            "physically_measured": False,
        }
    if not isinstance(raw, Mapping):
        raise ValueError(f"{name}.evidence must be an object")

    evidence_class = str(raw.get("class", "SUPPLIED")).upper()
    provenance = raw.get("measurement_provenance")

    if evidence_class == "MEASURED":
        if not isinstance(provenance, Mapping):
            raise ValueError(
                f"{name} claims MEASURED but measurement_provenance is missing"
            )
        marble_reference = provenance.get("marble_reference")
        instrumentation = provenance.get("instrumentation")
        if not isinstance(marble_reference, str) or not marble_reference.strip():
            raise ValueError(
                f"{name} MEASURED provenance requires marble_reference"
            )
        if not isinstance(instrumentation, list) or not instrumentation:
            raise ValueError(
                f"{name} MEASURED provenance requires non-empty instrumentation"
            )
        if not all(isinstance(item, str) and item.strip() for item in instrumentation):
            raise ValueError(
                f"{name} measurement instrumentation entries must be strings"
            )
        normalized_provenance = {
            "marble_reference": marble_reference,
            "instrumentation": list(instrumentation),
        }
        if "observed_at" in provenance:
            normalized_provenance["observed_at"] = provenance["observed_at"]
        return {
            "class": "MEASURED",
            "measurement_provenance": normalized_provenance,
            "physically_measured": True,
        }

    return {
        "class": evidence_class,
        "measurement_provenance": provenance if isinstance(provenance, Mapping) else None,
        "physically_measured": False,
    }


def net_resource_cost(record: Mapping[str, Any]) -> float:
    """Return fully charged resource cost for one baseline/candidate record."""
    if "total" in record:
        return _number(record["total"], "total")
    return sum(_number(record.get(field, 0.0), field) for field in RESOURCE_FIELDS)


def evaluate(payload: Mapping[str, Any]) -> Dict[str, Any]:
    """Evaluate baseline and adaptive candidates under a frozen quality gate."""
    if not isinstance(payload, Mapping):
        raise ValueError("payload must be an object")
    baseline = payload.get("baseline")
    candidates = payload.get("candidates")
    policy = payload.get("policy", {})
    if not isinstance(baseline, Mapping):
        raise ValueError("baseline must be an object")
    if not isinstance(candidates, list) or not candidates:
        raise ValueError("candidates must be a non-empty array")
    if not isinstance(policy, Mapping):
        raise ValueError("policy must be an object")

    minimum_quality = _number(policy.get("minimum_quality", 0.0), "minimum_quality")
    minimum_reduction = _number(
        policy.get("minimum_net_reduction_fraction", 0.0),
        "minimum_net_reduction_fraction",
    )
    if not 0.0 <= minimum_quality <= 1.0:
        raise ValueError("minimum_quality must be between 0 and 1")
    if minimum_reduction < 0.0:
        raise ValueError("minimum_net_reduction_fraction must be >= 0")

    baseline_quality = _number(baseline.get("quality"), "baseline.quality")
    baseline_cost = net_resource_cost(baseline)
    baseline_evidence = _evidence(baseline, "baseline")
    if baseline_cost <= 0:
        raise ValueError("baseline net resource cost must be > 0")

    evaluated = []
    for index, candidate in enumerate(candidates):
        if not isinstance(candidate, Mapping):
            raise ValueError(f"candidate[{index}] must be an object")
        candidate_id = str(candidate.get("id", f"candidate-{index}"))
        quality = _number(candidate.get("quality"), f"{candidate_id}.quality")
        cost = net_resource_cost(candidate)
        evidence = _evidence(candidate, candidate_id)
        reduction = (baseline_cost - cost) / baseline_cost
        quality_pass = quality >= minimum_quality
        resource_pass = reduction >= minimum_reduction
        qualifies = quality_pass and resource_pass
        evaluated.append({
            "id": candidate_id,
            "quality": quality,
            "net_resource_cost": cost,
            "net_reduction_fraction": reduction,
            "net_reduction_percent": reduction * 100.0,
            "quality_pass": quality_pass,
            "resource_pass": resource_pass,
            "qualifies": qualifies,
            "evidence": evidence,
        })

    qualifying = [item for item in evaluated if item["qualifies"]]
    selected = min(
        qualifying,
        key=lambda item: (item["net_resource_cost"], -item["quality"], item["id"]),
    ) if qualifying else None

    return {
        "system": "EDEN_CHRYSALIS",
        "status": "SELECTED" if selected else "NO_QUALIFYING_CANDIDATE",
        "classification": "EXPERIMENTAL_IMPLEMENTATION",
        "baseline": {
            "quality": baseline_quality,
            "net_resource_cost": baseline_cost,
            "evidence": baseline_evidence,
        },
        "policy": {
            "minimum_quality": minimum_quality,
            "minimum_net_reduction_fraction": minimum_reduction,
        },
        "candidates": evaluated,
        "selected": selected,
        "truth_boundary": (
            "Selection is computed from supplied metrics. MEASURED labels require "
            "explicit Marble-linked measurement provenance, but Chrysalis does not "
            "independently prove the scientific truth of that measurement."
        ),
    }
