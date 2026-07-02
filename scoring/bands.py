"""Shared risk-band mapping (score 0-100 -> label + color).

Single source of truth used by the PDF report, the public web index, and the
admin, so a "High" band always looks the same everywhere.
"""

# (min_score_inclusive, label, hex_color)
BANDS = [
    (80, "Severe", "#b00020"),
    (60, "High", "#e2711d"),
    (40, "Elevated", "#e0a800"),
    (20, "Moderate", "#2a9d8f"),
    (0, "Low", "#2a7d2a"),
]

UNKNOWN = ("Unknown", "#888888")


def band(score) -> tuple[str, str]:
    """Return (label, color) for a numeric score, or UNKNOWN if score is None."""
    if score is None:
        return UNKNOWN
    for threshold, label, color in BANDS:
        if score >= threshold:
            return label, color
    return BANDS[-1][1], BANDS[-1][2]
