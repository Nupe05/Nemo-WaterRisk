"""Pure unit tests for the scoring core (no Django/DB required)."""
from scoring.model import ScoreInputs, compute_score, streamflow_deficit


def test_zero_stress_scores_zero():
    result = compute_score(ScoreInputs())
    assert result["score"] == 0.0


def test_max_stress_scores_100():
    result = compute_score(
        ScoreInputs(streamflow_deficit=1.0, drought_index=1.0, withdrawal_pressure=1.0)
    )
    assert result["score"] == 100.0


def test_weights_sum_to_one():
    from scoring.model import WEIGHTS

    assert abs(sum(WEIGHTS.values()) - 1.0) < 1e-9


def test_streamflow_deficit_bounds():
    assert streamflow_deficit(0, 100) == 1.0      # no flow -> max deficit
    assert streamflow_deficit(100, 100) == 0.0    # at baseline -> no deficit
    assert streamflow_deficit(200, 100) == 0.0    # above baseline clamps to 0
    assert streamflow_deficit(50, 0) == 0.0       # guard against zero baseline


def test_components_are_reported():
    result = compute_score(ScoreInputs(streamflow_deficit=0.5))
    assert result["components"]["streamflow_deficit"] == 50.0
