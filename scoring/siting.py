"""Data-center siting suitability model.

Turns three 0-100 favorability sub-scores (water headroom, power availability,
physical-hazard safety) into a single 0-100 SUITABILITY score plus a letter
grade. Deterministic and unit-testable — like the water-risk model, this is a
credibility core and must NOT depend on an LLM.

Direction convention: every leg and the composite are "higher = better for
siting." That's the opposite of the water-RISK model (where higher = worse),
so the two are never confused.

Default weighting reflects today's reality: power (interconnection) is the #1
binding constraint, water is the emerging #2 and our differentiator, hazard is
a modifier. Override via env NEMO_SITING_WEIGHTS if you recalibrate.
"""
from __future__ import annotations

from dataclasses import dataclass

# Component weights must sum to 1.0.
WEIGHTS = {
    "power": 0.40,   # interconnection queue / time-to-energize — the hard gate
    "water": 0.35,   # cooling-water headroom — our differentiated leg
    "hazard": 0.25,  # natural-hazard safety — insurance + cooling-load modifier
}

# (min_score_inclusive, grade_label, hex_color). Higher score = better site.
GRADES = [
    (80, "Prime", "#1d6b3a"),
    (65, "Strong", "#2a9d8f"),
    (50, "Viable", "#e0a800"),
    (35, "Marginal", "#e2711d"),
    (0, "Challenged", "#b00020"),
]


def _clamp0_100(x: float) -> float:
    return max(0.0, min(100.0, float(x)))


def grade_for(score) -> tuple[str, str]:
    """Return (label, color) for a 0-100 suitability score, UNKNOWN if None."""
    if score is None:
        return ("Unknown", "#888888")
    for threshold, label, color in GRADES:
        if score >= threshold:
            return label, color
    return GRADES[-1][1], GRADES[-1][2]


@dataclass
class SitingInputs:
    """0-100 favorability sub-scores (100 = most favorable for siting)."""

    water: float = 0.0
    power: float = 0.0
    hazard: float = 0.0


def compute_suitability(inputs: SitingInputs, weights: dict | None = None) -> dict:
    """Return {'score', 'grade', 'color', 'components', 'weights'}.

    `score` is 0-100 where higher = more suitable for a new data center.
    """
    w = weights or WEIGHTS
    components = {
        "water": _clamp0_100(inputs.water),
        "power": _clamp0_100(inputs.power),
        "hazard": _clamp0_100(inputs.hazard),
    }
    total_w = sum(w[k] for k in components) or 1.0
    score = sum(components[k] * w[k] for k in components) / total_w
    score = round(score, 2)
    label, color = grade_for(score)
    return {
        "score": score,
        "grade": label,
        "color": color,
        "components": {k: round(v, 1) for k, v in components.items()},
        "weights": dict(w),
    }
