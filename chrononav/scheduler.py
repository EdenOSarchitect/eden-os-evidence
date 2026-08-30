"""Dependency-light callable ChronoNav reference scheduler.

This module implements the policy boundary already used in EDEN research:
select the lowest worker count predicted to meet a deadline, otherwise select
the fastest available configuration. Predictions are caller-supplied/modelled;
selection itself is deterministic and does not establish physical energy gain.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable


def choose_workers(predicted_seconds: Dict[int, float], deadline_seconds: float) -> int:
    if not predicted_seconds:
        raise ValueError("predicted_seconds must not be empty")
    if deadline_seconds <= 0:
        raise ValueError("deadline_seconds must be > 0")
    clean = {int(k): float(v) for k, v in predicted_seconds.items()}
    if any(k <= 0 or v <= 0 for k, v in clean.items()):
        raise ValueError("worker counts and predicted seconds must be > 0")
    meeting = sorted(k for k, v in clean.items() if v <= deadline_seconds)
    if meeting:
        return meeting[0]
    return min(clean, key=lambda k: (clean[k], k))


def schedule(payload: Dict[str, Any]) -> Dict[str, Any]:
    profiles = payload.get("predicted_seconds")
    if not isinstance(profiles, dict):
        raise ValueError("predicted_seconds must be an object mapping workers to seconds")
    deadline = float(payload.get("deadline_seconds", 0))
    clean = {int(k): float(v) for k, v in profiles.items()}
    selected = choose_workers(clean, deadline)
    return {
        "schema": "eden.chrononav.reference.v1",
        "status": "SELECTED",
        "selected_workers": selected,
        "predicted_seconds": clean[selected],
        "deadline_seconds": deadline,
        "deadline_predicted_met": clean[selected] <= deadline,
        "policy": "minimum_workers_meeting_deadline_else_fastest",
        "evidence": {
            "class": "IMPLEMENTED",
            "prediction_provenance": payload.get("prediction_provenance", "CALLER_SUPPLIED"),
            "physically_measured": False,
        },
        "truth": {
            "claims": ["deterministic scheduler policy executed"],
            "not_claimed": ["physical energy saving", "independent validation"],
        },
    }
