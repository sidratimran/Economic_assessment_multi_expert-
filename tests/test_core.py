"""Fast unit tests for the core logic (no network)."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from asiapulse.agents.grounding import verify  # noqa: E402
from asiapulse.models.backtest import confidence  # noqa: E402
from asiapulse.models.forecast import forecast_series  # noqa: E402
from asiapulse.models.risk import evaluate_flags, risk_label, score_row  # noqa: E402
from asiapulse.models.scenario import Levers, simulate  # noqa: E402


def test_risk_label_thresholds_are_single_source():
    assert risk_label(70) == "High"
    assert risk_label(55) == "Elevated"
    assert risk_label(45) == "Moderate"
    assert risk_label(10) == "Low"
    assert risk_label(np.nan) == "Unrated"


def test_flags_fire_on_absolute_thresholds_only():
    keys = {f["key"] for f in evaluate_flags({"inflation": 12.0, "reserves_months": 2.0, "internet": 80.0})}
    assert {"high_inflation", "low_reserves"} <= keys
    assert "digital_divide" not in keys


def test_contraction_supersedes_weak_growth():
    keys = {f["key"] for f in evaluate_flags({"gdp_cagr_fc": -1.0})}
    assert "contraction" in keys and "weak_growth" not in keys


def test_score_row_direction():
    ref = pd.DataFrame({"unemp": [2, 4, 6, 8, 10]})
    worse = score_row({"unemp": 10}, ref)["pillar_labour"]
    better = score_row({"unemp": 2}, ref)["pillar_labour"]
    assert worse > better


def test_confidence_labels():
    assert confidence("gdp_real", 3) == "Very High"
    assert confidence("gdp_real", 40) == "Very Low"
    assert confidence("unemp", 0.5) == "Very High"


def test_forecast_bounds_and_interval():
    s = pd.Series(np.linspace(5, 6, 20), index=range(2005, 2025))
    f = forecast_series(s, "unemp", 2030)
    assert f.year.tolist() == list(range(2025, 2031))
    assert (f.lo <= f.value).all() and (f.value <= f.hi).all()
    assert (f.lo >= 0).all()
    # intervals widen with horizon
    assert (np.diff(f.hi - f.lo) > 0).all()


def test_forecast_needs_history():
    assert forecast_series(pd.Series([1.0, 2.0], index=[2023, 2024]), "gdp_real", 2030) is None


def _sim(**kw):
    years = pd.Index(range(2026, 2036))
    gdp = pd.Series(100 * 1.04 ** np.arange(1, 11), index=years)
    unemp = pd.Series(6.0, index=years)
    ctx = {"gdp_last": 100.0, "okun_beta": -0.3, "gov_debt": 60.0, "inflation_5y_median": 4.0,
           "primary_balance": 0.0, "implied_interest_rate": 5.0, "emp_ratio": 55.0, "unemp": 6.0, "internet": 50.0}
    return simulate(gdp, unemp, ctx, Levers(**kw))


def test_scenario_zero_levers_equals_baseline():
    path, summ = _sim()
    assert np.allclose(path.growth_base, path.growth_scen)
    assert summ["gdp_end_diff_pct"] == pytest.approx(0, abs=1e-9)


def test_scenario_directions():
    _, neg = _sim(demand_shock_pp=-2)
    assert neg["gdp_end_diff_pct"] < 0 and neg["peak_unemp_diff_pp"] > 0
    _, cons = _sim(fiscal_consolidation_pp=2)
    assert cons["debt_end_scen"] < cons["debt_end_base"]
    _, dig = _sim(digital_adoption_pp=20)
    assert dig["gdp_end_diff_pct"] > 0


def test_digital_adoption_capped_at_100_percent():
    _, a = _sim(digital_adoption_pp=50)
    _, b = _sim(digital_adoption_pp=80)  # internet starts at 50%, so both cap at +50 pp
    assert a["gdp_end_diff_pct"] == pytest.approx(b["gdp_end_diff_pct"])


def test_grounding_flags_invented_numbers():
    tools = [{"gdp_growth": 3.54, "unemp": 8.08}]
    ok = verify("Growth is 3.5% and unemployment 8.1% in 2035.", tools)
    assert ok["checked"] == 2 and ok["verified"] == 2
    bad = verify("Growth is 7.9%.", tools)
    assert bad["unverified"] == ["7.9"]
