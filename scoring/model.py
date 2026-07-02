"""Water-risk scoring model.

Turns normalized measurements into a single 0-100 risk score plus the
component sub-scores that fed it. Deterministic and unit-testable — this is
the credibility core of the product, so it must NOT depend on an LLM.

The weighting below is a defensible first pass; tune with real calibration
data. Higher score = higher water-supply risk.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# Component weights must sum to 1.0.
WEIGHTS = {
    "streamflow_deficit": 0.45,  # low flow vs historical median -> higher risk
    "drought_index": 0.30,       # U.S. Drought Monitor severity -> higher risk
    "withdrawal_pressure": 0.25, # high withdrawal/stress -> higher risk
}


@dataclass
class ScoreInputs:
    """Normalized 0-1 stress indicators (1 = maximum stress)."""

    streamflow_deficit: float = 0.0
    drought_index: float = 0.0
    withdrawal_pressure: float = 0.0
    notes: list[str] = field(default_factory=list)


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def compute_score(inputs: ScoreInputs) -> dict:
    """Return {'score': float 0-100, 'components': {...}}."""
    components = {
        "streamflow_deficit": _clamp01(inputs.streamflow_deficit),
        "drought_index": _clamp01(inputs.drought_index),
        "withdrawal_pressure": _clamp01(inputs.withdrawal_pressure),
    }
    weighted = sum(components[k] * WEIGHTS[k] for k in WEIGHTS)
    return {
        "score": round(weighted * 100.0, 2),
        "components": {k: round(v * 100.0, 1) for k, v in components.items()},
        "weights": WEIGHTS,
        "notes": inputs.notes,
    }


def streamflow_deficit(current_cfs: float, baseline_cfs: float) -> float:
    """1.0 when flow is at/below zero relative to baseline, 0.0 at/above baseline."""
    if baseline_cfs <= 0:
        return 0.0
    ratio = current_cfs / baseline_cfs
    return _clamp01(1.0 - ratio)
