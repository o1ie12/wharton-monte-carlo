"""Round 5: growth-bucket mix scenarios."""
from __future__ import annotations

import json

import numpy as np
import pytest

from mcsim import analysis, growth
from mcsim.config import load_config
from mcsim.model import (MONTHS, draw_random, growth_mix, leveraged_monthly_returns, load_ladder,
                         monthly_log_returns, run_monte_carlo, simulate)


@pytest.fixture(scope="module")
def base():
    return load_config()


def spec(base, key):
    return next(s for s in base["growth_mix.scenarios"] if s["key"] == key)


# Required: G1 reproduces the official outputs exactly -----------------------------------

def test_g1_reproduces_official_outputs_exactly(base):
    m = json.loads((base.base_dir / "outputs" / "metrics.json").read_text())
    row = growth.run_growth_scenario(base, spec(base, "G1"), n=m["n_sims"], with_drawdown=False)
    for key in ["facility_median", "range_low", "range_high", "all_paid_with_backstop", "all_paid_without_backstop"]:
        assert row[key] == m[key], key


def test_g1_mix_is_bit_identical_to_official(base):
    official = run_monte_carlo(base, n=20_000)
    g1 = run_monte_carlo(growth.scenario_assumptions(base, spec(base, "G1")), n=20_000)
    assert np.array_equal(official.growth_path, g1.growth_path)
    assert np.array_equal(official.bill_paid, g1.bill_paid)
    assert np.array_equal(official.facility, g1.facility)


# Required: weights sum to 100% ------------------------------------------------------------

def test_every_scenario_mix_sums_to_100_percent(base):
    keys = [s["key"] for s in base["growth_mix.scenarios"]]
    assert keys == [f"G{i}" for i in range(1, 9)] + ["G2-V", "G3-V"]                # no G4-V by decision
    for s in base["growth_mix.scenarios"]:
        mix = growth_mix(growth.scenario_assumptions(base, s))           # validates names and weights
        assert sum(mix.values()) == pytest.approx(1.0, abs=1e-12), s["key"]
        assert all(w >= 0 for w in mix.values())
    assert dict(spec(base, "G1")["mix"]) == {"us": base["growth.us_weight"], "intl": base["growth.intl_weight"]}
    assert dict(spec(base, "G8")["mix"]) == dict(spec(base, "G1")["mix"]) and spec(base, "G8")["returns"] == "vanguard"
    for k in ("G2", "G3"):                           # the -V rows: same mix, Vanguard returns
        assert dict(spec(base, f"{k}-V")["mix"]) == dict(spec(base, k)["mix"])
        assert spec(base, f"{k}-V")["returns"] == "vanguard" and spec(base, k).get("returns", "official") == "official"
    with pytest.raises(ValueError):
        growth_mix(base.override({"growth_mix.mix": {"us": 0.6, "intl": 0.3}}))


# Required: leveraged fund, hand-worked month ----------------------------------------------

def test_leveraged_month_by_hand():
    """US +3.00% in the month, T-bills 4.00% a year, 2x, fee 0.89% a year:
    2 x 3.00% - (1.04^(1/12) - 1) - 0.89% / 12 = 6.00% - 0.32737% - 0.07417% = 5.59846%."""
    r = leveraged_monthly_returns(np.array([[[0.03]]]), np.array([[0.04]]), 2.0, 0.0089)
    by_hand = 0.06 - (1.04 ** (1 / 12) - 1) - 0.0089 / 12
    assert r[0, 0, 0] == pytest.approx(by_hand, abs=1e-15)
    assert r[0, 0, 0] == pytest.approx(0.0559846, abs=1e-7)
    # A -60% month would mean a -120% fund return: floored at -100% (wiped out).
    assert leveraged_monthly_returns(np.array([[[-0.60]]]), np.array([[0.04]]), 2.0, 0.0089)[0, 0, 0] == -1.0


def test_leveraged_annual_return_compounds_its_months(base):
    a = growth.scenario_assumptions(base, spec(base, "G6"))
    ladder = load_ladder(a)
    d = draw_random(a, ladder, 2_000, seed=9)
    res = simulate(a, d, ladder)
    values = growth.monthly_bucket_values(a, d, 9, res.growth_contribution)
    jan = values[:, ::MONTHS]                                   # Jan 2028 ... Jan 2033
    assert np.allclose(jan, res.growth_path, rtol=1e-10)        # monthly walk == annual model


# Supporting checks ------------------------------------------------------------------------

def test_brownian_bridge_months_add_up_to_the_year():
    rng = np.random.default_rng(0)
    annual = rng.normal(0.05, 0.15, (100, 5))
    m = monthly_log_returns(annual, 0.15, rng.standard_normal((100, 5, 12)))
    assert np.allclose(m.sum(axis=-1), annual)
    e = np.random.default_rng(1).standard_normal((200_000, 1, 12))
    assert m.shape == (100, 5, 12)
    assert monthly_log_returns(np.zeros((200_000, 1)), 0.15, e).std() == pytest.approx(0.15 / np.sqrt(12) * np.sqrt(11 / 12), rel=0.01)


@pytest.mark.parametrize("key", ["G2", "G4", "G7"])
def test_monthly_walk_matches_annual_model(base, key):
    a = growth.scenario_assumptions(base, spec(base, key))
    ladder = load_ladder(a)
    d = draw_random(a, ladder, 2_000, seed=5)
    res = simulate(a, d, ladder)
    values = growth.monthly_bucket_values(a, d, 5, res.growth_contribution)
    assert (res.growth_contribution < 150_000).any()           # some paths start below $150k (ladder overrun)
    assert np.allclose(values[:, ::MONTHS], res.growth_path, rtol=1e-10)
    assert (growth.max_drawdown(values) >= 0).all() and (growth.max_drawdown(values) < 1).all()


def test_small_cap_moments_and_correlations(base):
    a = growth.scenario_assumptions(base, spec(base, "G4"))
    d = draw_random(a, load_ladder(a), 200_000, seed=2)
    sc = d.extra["small_cap"][:, 0]
    assert sc.mean() == pytest.approx(base["growth_mix.small_cap_mean"], abs=0.002)
    assert sc.std() == pytest.approx(base["growth_mix.small_cap_vol"], abs=0.003)
    assert np.corrcoef(d.us[:, 0], sc)[0, 1] == pytest.approx(0.90, abs=0.01)
    assert np.corrcoef(d.intl[:, 0], sc)[0, 1] == pytest.approx(0.77, abs=0.01)
    official = draw_random(base, load_ladder(base), 200_000, seed=2)       # official draws untouched
    assert np.array_equal(official.us, d.us) and np.array_equal(official.tbill, d.tbill)


def test_stress_tests_run_for_every_mix(base):
    official = analysis.run_stress_tests(base)
    for s in base["growth_mix.scenarios"]:
        st = analysis.run_stress_tests(growth.scenario_assumptions(base, s))
        assert len(st) == len(official) and st["facility_contribution"].notna().all()


def test_vanguard_rows_use_vanguard_returns_and_hold_only_us_and_intl(base):
    """G2-V/G3-V use the Vanguard pessimistic returns for US and international, same volatilities.
    No -V row holds small cap (Vanguard gives no small-cap figure)."""
    v = analysis.vanguard_overrides(base)
    for k in ("G2-V", "G3-V"):
        a = growth.scenario_assumptions(base, spec(base, k))
        assert a["growth.us_mean"] == pytest.approx(v["growth.us_mean"])
        assert a["growth.intl_mean"] == pytest.approx(v["growth.intl_mean"])
        assert a["growth.us_vol"] == base["growth.us_vol"] and a["growth.intl_vol"] == base["growth.intl_vol"]
    for s in base["growth_mix.scenarios"]:
        if s.get("returns") == "vanguard":
            assert set(s["mix"]) <= {"us", "intl"}, s["key"]
