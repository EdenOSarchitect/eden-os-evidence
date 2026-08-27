#!/usr/bin/env python3
"""EDEN Chrysalis experimental adaptive resource evaluator.

Chrysalis does not claim resource savings by label. It evaluates candidate
strategies against a supplied baseline, charges active + metadata + recovery +
regeneration + orchestration costs, enforces a quality floor, and selects the
lowest-net-cost qualifying candidate. Inputs are caller-supplied observations;
this module does not independently establish that they were physically measured.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, Mapping

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


def net_resource_cost(record: Mapping[str, Any]) -> float:
    """Return fully charged resource cost for one baseline/candidate record."""
    if "total" in record:
        return _number(record["total"], "total")
    return sum(_number(record.get(field, 0.0), field) for field in RESOURCE_FIELDS)


def evaluate(payload: Mapping[str, Any]) -> Dict[str, Any]:
    """Evaluate baseline and adaptive candidates under a frozen quality gate.

    Expected payload:
      baseline: {quality, total} OR {quality, active, metadata, recovery,
                 regeneration, orchestration}
      candidates: [{id, quality, ...cost fields...}, ...]
      policy: {minimum_quality, minimum_net_reduction_fraction?}

    The result is an experimental decision record. It does not convert supplied
    metrics into MEASURED evidence; provenance/measurement classification belongs
    to the caller and Marble layer.
    """
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
    if baseline_cost <= 0:
        raise ValueError("baseline net resource cost must be > 0")

    evaluated = []
    for index, candidate in enumerate(candidates):
        if not isinstance(candidate, Mapping):
            raise ValueError(f"candidate[{index}] must be an object")
        candidate_id = str(candidate.get("id", f"candidate-{index}"))
        quality = _number(candidate.get("quality"), f"{candidate_id}.quality")
        cost = net_resource_cost(candidate)
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
        })

    qualifying = [item for item in evaluated if item["qualifies"]]
    selected = min(qualifying, key=lambda item: (item["net_resource_cost"], -item["quality"], item["id"])) if qualifying else None

    return {
        "system": "EDEN_CHRYSALIS",
        "status": "SELECTED" if selected else "NO_QUALIFYING_CANDIDATE",
        "classification": "EXPERIMENTAL_IMPLEMENTATION",
        "baseline": {
            "quality": baseline_quality,
            "net_resource_cost": baseline_cost,
        },
        "policy": {
            "minimum_quality": minimum_quality,
            "minimum_net_reduction_fraction": minimum_reduction,
        },
        "candidates": evaluated,
        "selected": selected,
        "truth_boundary": (
            "Selection is computed from supplied metrics. Chrysalis does not "
            "independently prove that resource or quality observations are measured."
        ),
    }
