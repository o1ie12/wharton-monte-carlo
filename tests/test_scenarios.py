"""Round 3: reinvestment-risk sizing scenarios and STRIPS rungs."""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from mcsim import scenarios
from mcsim.config import load_config
from mcsim.model import load_ladder, make_timeline, run_monte_carlo, rung_payouts, value_per_bond_at_bill

PAR_CURVE = "data/treasury_par_curve_2026-10-09.csv"


@pytest.fixture(scope="module")
def base():
    return load_config()


# Sizing rule: minimum whole number of bonds ------------------------------------

@pytest.mark.parametrize("rate", [0.04, 0.03, 0.02, 0.0])
def test_sizing_quantity_is_the_minimum_that_meets_the_bill(base, rate):
    a = base.override({"ladder.sizing_reinvest_rate": rate})
    official, sized = load_ladder(base), load_ladder(a)
    for k in np.flatnonzero(official.is_bond):
        per_bond = value_per_bond_at_bill(base, official, k, rate)
        q = sized.quantity[k]
        assert q * per_bond >= 50_000, (k + 1, q, per_bond)
        assert (q - 1) * per_bond < 50_000, (k + 1, q, per_bond)          # one fewer bond fails
    # Only the Treasury coupon-bond rungs change; iBonds rows keep their sheet quantities.
    assert np.array_equal(sized.quantity[~official.is_bond], official.quantity[~official.is_bond])
    assert np.allclose(sized.sheet_cost, sized.quantity * sized.unit_cost)


def test_sized_rungs_pay_the_bill_when_tbills_earn_the_sizing_rate(base):
    """End to end through the simulation: T-bills fixed at the sizing rate (no volatility),
    every resized bond rung delivers at least $50,000 by its bill date."""
    for rate in (0.04, 0.02, 0.0):
        a = base.override({"ladder.sizing_reinvest_rate": rate, "tbills.mean": rate, "tbills.mean_by_year": {},
                           "tbills.sd": 0.0,
                           "tbills.floor": 0.0})
        res = run_monte_carlo(a, n=2)
        ladder = load_ladder(a)
        assert (res.rung_payout[:, ladder.is_bond] >= 50_000 - 1e-6).all()


def test_principal_held_at_the_sizing_rate_until_jan_1(base):
    """A bond that matures well before its Jan 1 bill (bill 6: Feb 15 2037 -> Jan 1 2038) has its
    principal held at the reinvestment rate for the gap."""
    ladder = load_ladder(base)
    k = 5
    mat, bill = ladder.maturity[k], pd.Timestamp(year=ladder.bill_years[k], month=1, day=1)
    assert (bill - mat).days > 60
    coupons = len(ladder.flows(pd.Timestamp("2027-01-01"), "cashflows")[k].dates)
    v0, v4 = value_per_bond_at_bill(base, ladder, k, 0.0), value_per_bond_at_bill(base, ladder, k, 0.04)
    assert v0 == pytest.approx(1000 + 1000 * ladder.coupon[k] / 2 * coupons)    # face + coupons, no interest
    gap_year = (pd.Timestamp(year=mat.year + 1, month=1, day=1) - mat).days / (366 if mat.is_leap_year else 365)
    assert v4 - v0 > 1000 * 0.04 * gap_year                                     # includes interest on principal


# STRIPS ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def strips_assumptions(base, tmp_path_factory):
    path = tmp_path_factory.mktemp("f") / "ladder_F.csv"
    scenarios.build_strips_sheet(base, PAR_CURVE, path)
    return base.override({"ladder.csv_path": str(path)})


def test_strips_rung_pays_exactly_face_at_maturity_and_nothing_before(strips_assumptions):
    a = strips_assumptions
    ladder = load_ladder(a)
    assert ladder.is_strips[5:].all() and not ladder.is_bond.any()
    settle = pd.Timestamp(a["plan.ladder_purchase_date"])
    for k in np.flatnonzero(ladder.is_strips):
        f = ladder.flows(settle, "cashflows")[k]
        assert f.dates == (ladder.maturity[k],)              # a single payment, at maturity
        assert f.amounts.tolist() == [50_000.0]              # exactly face; no coupons
        assert ladder.coupon[k] == 0.0
    # At 0% T-bills the rung delivers exactly face by the bill date.
    zero = a.override({"tbills.mean": 0.0, "tbills.mean_by_year": {}, "tbills.sd": 0.0,
                       "ladder.ibonds_error_sd_per_year": 0.0})
    res = run_monte_carlo(zero, n=2)
    assert np.allclose(res.rung_payout[:, ladder.is_strips], 50_000.0)


def test_strips_sheet_is_labelled_estimate_and_prices_from_the_curve(strips_assumptions):
    ladder = load_ladder(strips_assumptions)
    rows = ladder.table[ladder.is_strips]
    assert rows["data_status"].str.startswith(scenarios.STRIPS_NOTE).all()
    assert len(ladder.unverified) == 5                      # flagged like any ESTIMATE row
    curve_date, par = scenarios.load_par_curve(PAR_CURVE)
    for k in np.flatnonzero(ladder.is_strips):
        price, spot = scenarios.strips_quote(curve_date, par, ladder.maturity[k])
        assert ladder.table["price"][k] == pytest.approx(price, abs=1e-4)
        assert ladder.yields[k] == pytest.approx(spot, abs=1e-6)


def test_bootstrap_reprices_par_bonds_at_100():
    _, par = scenarios.load_par_curve(PAR_CURVE)
    t, spot = scenarios.bootstrap_spot_rates(par)
    for n in (4, 20, 30):                                   # 2, 10 and 15 years
        c = float(np.interp(t[n - 1], sorted(par), [par[x] for x in sorted(par)]))
        df = (1 + spot[:n] / 2) ** (-2 * t[:n])
        assert (c / 2 * 100 * df).sum() + 100 * df[-1] == pytest.approx(100, abs=1e-9)
    flat_t, flat = scenarios.bootstrap_spot_rates({0.5: 0.05, 30: 0.05})
    assert np.allclose(flat, 0.05)                          # flat par curve -> flat spot curve


# Budget check ------------------------------------------------------------------------

def test_budget_check_flags_scenarios_over_budget(base):
    budget = base["scenarios.budget"] - base["scenarios.cash_reserve"] - base["scenarios.fees"]
    assert scenarios.budget_check(base, budget)["fits_budget"]                 # exactly fits
    over = scenarios.budget_check(base, budget + 1)
    assert not over["fits_budget"] and over["over_budget_by"] == pytest.approx(1)
    assert scenarios.budget_check(base, 293_324.0)["sgov_buffer"] == pytest.approx(300_000 - 293_324 - 700)
    md = scenarios.sizing_markdown(base, [
        {"key": "A", "label": "A", "estimate": False, "n_sims": 1, "quantities_6_10": [1] * 5, "extra_cost": 0.0,
         "ladder_cost": 310_000.0, **scenarios.budget_check(base, 310_000.0), "ladder_alone": 0.5,
         "coverage_median": 1, "coverage_p10": 1, "coverage_worst": 1, "topup_median": 0, "topup_p90": 0,
         "all_paid_with_backstop": 1, "all_paid_without_backstop": 1, "facility_median": 1,
         "range_low": 1, "range_high": 2, "worst_stress_shortfall": 0, "worst_stress_backstop_left": 0,
         "vg_all_paid_with_backstop": 1, "vg_all_paid_without_backstop": 1, "vg_facility_median": 1,
         "vg_facility_p10": 1, "vg_range_low": 1, "vg_range_high": 2},
    ], any_1_5_short=0.25, curve_date=None)
    assert "**NO** (over by $10,700)" in md


# Scenario A = official -----------------------------------------------------------------

def test_scenario_a_reproduces_official_outputs_exactly(base):
    m = json.loads((base.base_dir / "outputs" / "metrics.json").read_text())
    spec = scenarios.scenario_specs(base)[0]
    assert spec["key"] == "A" and spec["overrides"] == {}
    same_run = base.override({"simulation.n_sims": m["n_sims"]})    # official (100k) or --final (500k) run
    row = scenarios.run_sizing_scenario(same_run, spec, float(load_ladder(base).sheet_cost.sum()))
    assert row["n_sims"] == m["n_sims"]
    for key in ["all_paid_with_backstop", "all_paid_without_backstop", "coverage_median", "topup_median",
                "facility_median", "range_low", "range_high"]:
        assert row[key] == m[key], key
    assert row["worst_stress_shortfall"] == m["worst_unpaid"]
    assert row["worst_stress_backstop_left"] == m["worst_backstop_left"]
    assert row["extra_cost"] == 0.0


def test_scenarios_never_modify_official_ladder(base, tmp_path):
    path = base.path("ladder.csv_path")
    before = path.read_bytes()
    scenarios.build_strips_sheet(base, PAR_CURVE, tmp_path / "f.csv")
    load_ladder(base.override({"ladder.sizing_reinvest_rate": 0.0}))
    assert path.read_bytes() == before


# Round 4c: hardening options for scenario A ---------------------------------------------

def test_hardening_options_load_their_settings(base):
    """Each option changes only the rate rule's assumed rate and/or the backstop; everything
    else is the official config, and the official config itself is untouched."""
    expected = {"A0": (0.02, 10_000), "A1": (0.015, 10_000), "A2": (0.010, 10_000),
                "A3": (0.02, 12_500), "A4": (0.015, 12_500)}
    assert [o["key"] for o in scenarios.HARDENING_OPTIONS] == list(expected)
    official = load_config()
    for option in scenarios.HARDENING_OPTIONS:
        s = scenarios.option_assumptions(base, option, n=1_000)
        rate, backstop = expected[option["key"]]
        assert s["waterfall.rate_rule_rate"] == rate, option["key"]
        assert s["waterfall.backstop_amount"] == backstop, option["key"]
        assert s["waterfall.topup_rule"] == "rate_rule"
        assert s["simulation.n_sims"] == 1_000
        changed = {k for k in s.values if s[k] != official[k]}
        assert changed <= {"waterfall.rate_rule_rate", "waterfall.backstop_amount", "simulation.n_sims"}
    # Official = A2 since Oct 13 2026.
    assert official["waterfall.rate_rule_rate"] == 0.010 and official["waterfall.backstop_amount"] == 10_000


def test_hardening_option_a2_is_the_official_run(base):
    a2 = next(o for o in scenarios.HARDENING_OPTIONS if o["key"] == "A2")
    assert all(base[k] == v for k, v in a2["overrides"].items())
    row = scenarios.run_hardening_option(base, a2, n=20_000)
    res = run_monte_carlo(base, n=20_000)
    assert row["facility_median"] == float(np.median(res.facility))
    assert row["fail_with_backstop"] == int((~res.all_paid_with_backstop).sum())


def test_hardening_sentences_state_facts_without_a_pick():
    base = {"key": "A0", "label": "x", "n_sims": 10, "fail_with_backstop": 3, "facility_median": 100.0,
            "cushion_free_median": 50.0}
    rows = [base,
            {**base, "key": "A1", "fail_with_backstop": 0, "facility_median": 90.0, "cushion_free_median": 50.0},
            {**base, "key": "A3", "fail_with_backstop": 0, "facility_median": 100.0, "cushion_free_median": 45.0}]
    text = " ".join(scenarios.hardening_sentences(rows))
    assert "2 of 3 options pay every bill" in text and "A1 $90 and $50" in text and "A3 $100 and $45" in text
    assert "A0 3" in text                                                       # the failing option, as a fact
    for word in ("cheapest", "best", "recommend", "should"):
        assert word not in text.lower()


def test_hardening_seed_check_reports_backstop_room(base):
    rows = scenarios.hardening_seed_check(base, ["A2", "A4"], [int(base["simulation.seed"]), 1], n=5_000)
    assert [(r["key"], r["seed"]) for r in rows] == [("A2", 20270101), ("A2", 1), ("A4", 20270101), ("A4", 1)]
    for r in rows:
        assert r["spare"] == pytest.approx(r["backstop_amount"] - r["max_backstop_draw"])
        assert r["spare_share"] == pytest.approx(r["spare"] / r["backstop_amount"])
    a2 = rows[0]
    res = run_monte_carlo(base, n=5_000)                                        # A2 is the official run
    assert a2["max_backstop_draw"] == pytest.approx(float(res.backstop_used.max()))
    assert a2["cushion_free_median"] == pytest.approx(float(np.median(res.cushion_kept - res.backstop_start)))
    md = scenarios.hardening_seed_markdown(rows)
    assert "A2 vs A4" in md and "cheapest" not in md.lower()
