"""Population lookup + demand-pressure normalization (no network)."""
from integrations.demographics import demand_pressure, population_for


def test_population_lookup():
    assert population_for("04013") == 4_420_568  # Maricopa (Phoenix)
    assert population_for("41065") == 26_670     # Wasco (The Dalles)
    assert population_for("99999") is None
    assert population_for("") is None


def test_demand_pressure_normalization():
    assert demand_pressure(5_000_000) == 1.0     # saturates at the cap
    assert demand_pressure(10_000_000) == 1.0    # clamped
    assert demand_pressure(0) == 0.0
    assert demand_pressure(None) == 0.0
    # big metro high, tiny county near zero, and monotonic in between
    assert demand_pressure(4_420_568) > 0.8      # Phoenix
    assert demand_pressure(26_670) < 0.02        # The Dalles
    assert demand_pressure(2_613_539) > demand_pressure(420_959)  # Dallas > Loudoun
