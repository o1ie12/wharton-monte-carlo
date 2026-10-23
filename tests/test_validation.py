"""Validation tests for the Monte Carlo model.  Run:  python -m pytest -q"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from mcsim import analysis
from mcsim.config import load_config
from mcsim.model import ladder_costs, load_ladder, run_monte_carlo, sheet_date_costs


@pytest.fixture(scope="module")
def base():
    return load_config()


ZERO_VOL = {
    "ladder.yield_shift_mean": 0.0,
    "ladder.yield_shift_sd": 0.0,
    "ladder.ibonds_error_mean": 0.0,
    "ladder.ibonds_error_sd_per_year": 0.0,
    "ladder.ibonds_fee": 0.0,                 # hand calculations assume iBonds pay exactly their target
    "tbills.mean": 0.03,
    "tbills.mean_by_year": {},                # flat 3% T-bills in every year
    "tbills.sd": 0.0,
    "growth.us_mean": 0.08,
    "growth.us_vol": 0.0,
    "growth.intl_mean": 0.06,
    "growth.intl_vol": 0.0,
    "ladder.bond_payout_model": "face",
    "glide_path.enabled": True,
    "growth.rebalance_annually": True,
    "facility.give_pct": 0.75,
    "inflation.rate": 0.025,
    "inflation.rate_by_year": {},             # flat 2.5% inflation
    # Rate rule at the T-bill rate: with no volatility the rule equals perfect foresight.
    "waterfall.topup_rule": "rate_rule",
    "waterfall.rate_rule_rate": 0.03,
}


# 1. Zero volatility -> every path equals a hand calculation -------------------

def test_zero_volatility_matches_hand_calculation(base):
    a = base.override(ZERO_VOL)
    res = run_monte_carlo(a, n=20)

    # Ladder: PV of each $50k bill on Jan 1 2027 at the sheet YTM, semiannual compounding.
    sheet = pd.read_csv(a.path("ladder.csv_path"))
    years = (pd.to_datetime(sheet["maturity_date"]) - pd.Timestamp("2027-01-01")).dt.days / 365.25
    cost = float((50_000 / (1 + sheet["ytm"] / 2) ** (2 * years)).sum())
    shortfall = max(cost - 300_000, 0.0)
    buffer0 = max(300_000 - cost, 0.0)

    # Buffer: earns 3% a year; each rung pays exactly the $50k bill, so the buffer just compounds.
    min_buffer = buffer0 * 1.03 ** 6     # after the Jan 2033 bill
    final_buffer = buffer0 * 1.03 ** 15  # after the Jan 2042 bill

    # Growth: stocks earn 0.6*8% + 0.4*6% = 7.2% (rebalanced); T-bills earn 3%.
    v2028 = 150_000 - shortfall
    v2031 = v2028 * 1.072 ** 3
    stocks, bills = v2031 * 2 / 3, v2031 / 3            # Jan 2031: move 1/3 of stocks
    stocks, bills = stocks * 1.072, bills * 1.03
    stocks, bills = stocks / 2, bills + stocks / 2      # Jan 2032: move 1/2 of remaining stocks
    v2033 = stocks * 1.072 + bills * 1.03
    facility = 0.75 * v2033

    assert np.allclose(res.ladder_cost, cost, rtol=1e-12)
    assert np.allclose(res.buffer_start, buffer0, atol=1e-6)
    assert res.all_paid.all() and res.ladder_only_all_paid.all()
    assert np.allclose(res.topup, 0.0)
    assert np.allclose(res.min_buffer, min_buffer, atol=1e-6)
    assert np.allclose(res.final_buffer, final_buffer, atol=1e-6)
    assert np.allclose(res.value, v2033, rtol=1e-12)
    assert np.allclose(res.facility, facility, rtol=1e-12)
    assert np.allclose(res.facility_real, facility / 1.025 ** 6, rtol=1e-12)
    # Growth factor Jan 2028 -> Jan 2033, worked by hand.
    assert v2033 / v2028 == pytest.approx(1.3609669538775044, rel=1e-12)
    # Fan chart path starts at the contribution and ends at the 2033 value.
    assert np.allclose(res.growth_path[:, 0], v2028)
    assert np.allclose(res.growth_path[:, -1], v2033)


def test_zero_volatility_stress_normal_matches_monte_carlo(base):
    a = base.override(ZERO_VOL)
    stress = analysis.run_stress_tests(a).set_index("scenario")
    res = run_monte_carlo(a, n=5)
    assert stress.loc["normal", "facility_contribution"] == pytest.approx(res.facility[0], rel=1e-12)


# 2. 10,000 vs 50,000 runs: median within 1% ---------------------------------

def test_median_stable_10k_vs_50k(base):
    small = run_monte_carlo(base, n=10_000)
    large = run_monte_carlo(base, n=50_000)
    for name in ("facility", "value"):
        m10 = np.median(getattr(small, name))
        m50 = np.median(getattr(large, name))
        assert abs(m10 / m50 - 1) < 0.01, f"{name}: {m10:,.0f} vs {m50:,.0f}"


# 3. Ladder cost at zero yield shift matches ladder.csv -----------------------

@pytest.mark.parametrize("model", ["face", "cashflows"])
def test_ladder_cost_zero_shift_matches_sheet(base, model):
    """Priced on the sheet's own date, each rung matches its rung_cost within its sizing
    rounding plus a small slack: ETF rows within the accepted share tolerance of the
    sizing rule, bond rows within half a $1,000 bond. The cashflows model prices bonds
    from their actual coupons, so at its YTM each bond row reprices to its clean fill price
    plus textbook (actual/actual) accrued within the slack. rung_cost is the cash WInS took,
    which differs from that only by the accrued WInS charged (outputs/wins_fills.md)."""
    a = base.override({"ladder.bond_payout_model": model})
    ladder = load_ladder(a)
    cost = sheet_date_costs(ladder, a)          # each row on its own price_date
    slack = a["ladder.cost_check_slack"]
    rounding = np.where(ladder.is_treasury, 0.5, a["ladder.share_tolerance"]) * ladder.unit_cost
    diff = np.abs(cost - ladder.sheet_cost)
    if model == "face":
        # The face model prices a bond rung as a $50,000 zero, which is not what the sheet
        # buys (whole coupon bonds sized from the Jan 2027 purchase), so compare ETF rows only.
        etf = ~ladder.is_treasury
        assert (diff[etf] <= rounding[etf] + slack).all(), diff
        return
    assert (diff <= rounding + slack).all(), diff
    from mcsim.fills import textbook_accrued
    for k in np.flatnonzero(ladder.is_bond):                   # actual coupon cash flows: near exact
        dirty = ladder.table["price"][k] * 10 + textbook_accrued(ladder.coupon[k], ladder.maturity[k],
                                                                 ladder.price_dates[k])
        assert abs(cost[k] - ladder.quantity[k] * dirty) <= slack, (k + 1, cost[k], ladder.quantity[k] * dirty)
    assert abs(cost.sum() - ladder.sheet_cost.sum()) <= (rounding + slack).sum()


def test_etf_share_counts_within_tolerance_of_sizing_rule(base):
    """Sizing rule: the share count that grows to the bill amount at maturity at the row's
    YTM (semiannual compounding from its price_date). Counts may differ by at most
    ladder.share_tolerance shares."""
    ladder = load_ladder(base)
    tol = base["ladder.share_tolerance"]
    for k in np.flatnonzero(~ladder.is_bond):
        t = (ladder.maturity[k] - ladder.price_dates[k]).days / base["ladder.day_count_basis"]
        growth = (1 + ladder.yields[k] / 2) ** (2 * t)
        rule = round(ladder.bill_amount[k] / (ladder.unit_cost[k] * growth))
        assert abs(ladder.quantity[k] - rule) <= tol, (k + 1, ladder.quantity[k], rule)


# Supporting checks ------------------------------------------------------------

def test_sheet_quantities_reproduce_rung_cost(base):
    ladder = load_ladder(base)
    assert np.allclose(ladder.quantity * ladder.unit_cost, ladder.sheet_cost, atol=0.01)


def test_every_assumption_has_value_source_status(base):
    """Required: fails if any assumption in config.yaml lacks value, source or status."""
    import yaml

    def leaves(node, prefix=""):
        for key, child in node.items():
            if isinstance(child, dict) and any(f in child for f in ("value", "source", "status")):
                yield prefix + key, child
            elif isinstance(child, dict):
                yield from leaves(child, prefix + key + ".")
            else:
                yield prefix + key, {"value": child}           # a bare value is missing fields

    raw = yaml.safe_load(open(base.base_dir / "config.yaml"))
    found = list(leaves(raw))
    assert len(found) == len(base.values)
    for key, leaf in found:
        missing = [f for f in ("value", "source", "status") if f not in leaf]
        assert not missing, f"{key} is missing {missing}"
        assert leaf["status"] in ("sourced", "policy", "placeholder"), key
        assert str(leaf["source"]).strip(), key
        if leaf["status"] == "placeholder":
            assert leaf["source"] == "TODO", key


def test_loader_rejects_assumption_missing_a_field(tmp_path):
    from mcsim.config import load_config
    for bad in ('x:\n  value: 1\n  source: "a"\n',             # no status
                'x:\n  value: 1\n  status: sourced\n',          # no source
                'x:\n  source: "a"\n  status: sourced\n',       # no value
                'x:\n  value: 1\n  source: "a"\n  status: maybe\n'):
        p = tmp_path / "c.yaml"
        p.write_text(bad)
        with pytest.raises(ValueError):
            load_config(p)


def test_assumptions_table_flags_exactly_the_placeholders(base):
    table = analysis.assumptions_table(base)
    assert len(table) == len(base.values)
    flagged = set(table.loc[table["Status"] == "**PLACEHOLDER**", "Assumption"])
    assert flagged == set(base.placeholders())


def test_yield_drop_shortfall_comes_from_2028_contribution(base):
    stress = analysis.run_stress_tests(base).set_index("scenario")
    row = stress.loc["yields_down_1pt"]
    assert row["ladder_cost"] > base["plan.ladder_budget"]
    assert row["shortfall_from_2028"] == pytest.approx(row["ladder_cost"] - base["plan.ladder_budget"])
    assert row["growth_contribution"] == pytest.approx(150_000 - row["shortfall_from_2028"])
    assert row["buffer_jan_2027"] == 0.0


def test_topup_matches_hand_calculation(base):
    """iBonds rungs pay $40k (error -20%) for the 2033-2037 bills; Treasury rungs pay $50k.
    Ladder + buffer alone fall short, so the growth bucket tops up the reserve in Jan 2033."""
    a = base.override({**ZERO_VOL, "ladder.ibonds_error_mean": -0.20})
    res = run_monte_carlo(a, n=3)
    b2033 = res.buffer_start[0] * 1.03 ** 6
    # Reserve after bill k (k = 1..5) with top-up X: (b2033 + X) * 1.03**(k-1) - 10k * sum_{j<k} 1.03**j.
    # The binding bill is the 5th, so X = 10k * (1 + 1/1.03 + ... + 1/1.03**4) - b2033.
    topup = 10_000 * sum(1.03 ** -j for j in range(5)) - b2033

    assert not res.ladder_only_all_paid.any()
    assert np.allclose(res.topup_needed, topup, rtol=1e-10)   # perfect-foresight reference
    # Ladder alone: bill 1 gets $40k + the whole buffer, so it is short by 10k - b2033.
    assert np.allclose(res.ladder_only_shortfall[:, 0], 10_000 - b2033)
    assert np.allclose(res.topup_target, topup, rtol=1e-10)   # rate rule at 3% = T-bill rate
    assert np.allclose(res.topup, topup, rtol=1e-10)
    assert res.all_paid.all()                                 # whole portfolio pays everything
    assert np.allclose(res.min_buffer, 0.0, atol=1e-6)        # top-up is exactly enough, no more
    assert np.allclose(res.value, res.value_before_topup - topup)
    assert np.allclose(res.facility, 0.75 * (res.value_before_topup - topup))


def test_failure_when_growth_bucket_cannot_cover_topup(base):
    a = base.override({**ZERO_VOL, "ladder.ibonds_error_mean": -0.20, "plan.growth_contribution": 1_000})
    res = run_monte_carlo(a, n=3)
    assert res.rule_capped.all() and res.failed.all()
    assert not res.foresight_all_paid.any()
    assert not res.all_paid.any()
    assert np.allclose(res.topup, res.value_before_topup)     # everything moved to the reserve
    assert np.allclose(res.facility, 0.0)
    assert (res.unpaid > 0).all()


# Required: top-up is ~0 when T-bills earn the bond YTM -------------------------

def test_topup_near_zero_when_tbill_rate_equals_bond_ytm(base):
    """Zero volatility, cashflows model, T-bills earning the bonds' YTM, and no starting
    buffer (budget = Jan 2027 ladder cost): coupons reinvested at the YTM rebuild each
    rung's $50k, so no top-up is needed. The tolerance is one $1,000 bond, the sheet's
    rounding unit. Two points lower, reinvestment falls short and a top-up appears."""
    ladder = load_ladder(base)
    ytm = float(ladder.yields[ladder.is_bond].mean())
    a = base.override({**ZERO_VOL, "ladder.bond_payout_model": "cashflows", "tbills.mean": ytm})
    a = a.override({"plan.ladder_budget": float(ladder_costs(ladder, [0.0], a).sum())})
    res = run_monte_carlo(a, n=3)
    assert np.allclose(res.buffer_start, 0.0, atol=1e-6)
    assert (res.topup_needed < 1_000).all(), res.topup_needed
    assert res.all_paid.all()

    low = run_monte_carlo(a.override({"tbills.mean": ytm - 0.02}), n=3)
    assert (low.topup_needed > 5_000).all(), low.topup_needed


# Required: whole portfolio >= ladder only, in every run ----------------------

CONFIGS = [
    {},
    {"ladder.bond_payout_model": "face"},
    {"growth.us_vol": 0.30, "growth.intl_vol": 0.35},
    {"ladder.yield_shift_mean": -0.02},
    {"tbills.mean": 0.01, "tbills.mean_by_year": {}},
    {"plan.growth_contribution": 5_000},
]


@pytest.mark.parametrize("rule", ["rate_rule", "fixed_rule", "foresight"])
@pytest.mark.parametrize("overrides", CONFIGS)
@pytest.mark.parametrize("seed", [1, 2, 3])
def test_whole_portfolio_success_at_least_ladder_only(base, rule, overrides, seed):
    res = run_monte_carlo(base.override({**overrides, "waterfall.topup_rule": rule}), n=5_000, seed=seed)
    assert res.all_paid.mean() >= res.ladder_only_all_paid.mean()
    # Path by path: if ladder + buffer alone pay everything, so does the whole portfolio.
    assert not (res.ladder_only_all_paid & ~res.all_paid).any()


# Required: no-foresight success <= perfect-foresight success -----------------

@pytest.mark.parametrize("rule", ["rate_rule", "fixed_rule"])
@pytest.mark.parametrize("overrides", CONFIGS + [{"waterfall.rate_rule_rate": 0.06},
                                                 {"waterfall.fixed_rule_amount": 50_000}])
@pytest.mark.parametrize("seed", [1, 2, 3])
def test_no_foresight_success_at_most_perfect_foresight(base, rule, overrides, seed):
    res = run_monte_carlo(base.override({**overrides, "waterfall.topup_rule": rule}), n=5_000, seed=seed)
    assert res.all_paid.mean() <= res.foresight_all_paid.mean()
    # Path by path: a rule only succeeds where the exact top-up was affordable.
    assert not (res.all_paid & ~res.foresight_all_paid).any()
    # A path succeeds exactly when the rule moved at least the perfect-foresight amount.
    covered = res.topup >= res.topup_needed - 1e-6
    assert (res.all_paid == covered).all()


def test_rate_rule_excess_is_released_after_last_bill(base):
    """Zero volatility, T-bills at 3%. A 2% rate rule moves more than needed; the extra
    earns 3% from Jan 2033 to Jan 2042 (9 years) and is released after the last bill."""
    a3 = base.override({**ZERO_VOL, "ladder.ibonds_error_mean": -0.20})
    a2 = a3.override({"waterfall.rate_rule_rate": 0.02})
    r3, r2 = run_monte_carlo(a3, n=2), run_monte_carlo(a2, n=2)
    extra = r2.topup - r3.topup
    assert (extra > 0).all() and r2.all_paid.all()
    assert np.allclose(r3.excess_topup_final, 0.0, atol=1e-6)
    assert np.allclose(r2.excess_topup_final, extra * 1.03 ** 9)
    assert np.allclose(r2.final_buffer - r3.final_buffer, extra * 1.03 ** 9)
    assert np.allclose(r2.facility, r3.facility - 0.75 * extra)


def test_fixed_rule_moves_fixed_amount(base):
    a = base.override({"waterfall.topup_rule": "fixed_rule", "waterfall.fixed_rule_amount": 13_400})
    res = run_monte_carlo(a, n=2_000)
    assert np.allclose(res.topup, np.minimum(13_400, res.value_before_topup))
    assert (res.all_paid == (res.topup >= res.topup_needed - 1e-6)).all()


def test_low_rate_stress_reports_shortfall_and_rate_needed(base):
    stress = analysis.run_stress_tests(base).set_index("scenario")
    row = stress.loc["low_rates_2010s"]
    assert not row["all_bills_paid"]                      # 2% rule under-funds when T-bills earn 0.5%
    assert row["unpaid_bill_dollars"] > 0
    give = base["facility.give_pct"]
    assert row["cushion_kept_2033"] == pytest.approx(row["value_2033"] * (1 - give))
    assert row["unpaid_pct_of_cushion"] == pytest.approx(row["unpaid_bill_dollars"] / row["cushion_kept_2033"])
    # Bills do not depend on stocks, so the P10 growth path has the same shortfall, bigger share.
    p10 = stress.loc["low_rates_2010s_p10"]
    assert p10["unpaid_bill_dollars"] == pytest.approx(row["unpaid_bill_dollars"])
    assert p10["unpaid_pct_of_cushion"] > row["unpaid_pct_of_cushion"]
    # Rate needed. Without the iBonds margin, assuming the true 0.5% reproduces perfect foresight,
    # so it pays and a bit more does not. With the official margin (iBonds pay their expected
    # amount on this path), the margin is extra cushion, so a higher assumed rate still pays.
    ladder = load_ladder(base)
    draws = analysis.stress_draws(base, ladder, {"stock_percentile": 50, "tbill_rate": 0.005})
    from mcsim.model import simulate
    no_margin = base.override({"waterfall.ibonds_margin_sd": 0.0})
    assert analysis.rule_rate_needed(no_margin, ladder, draws) == pytest.approx(0.005, abs=1e-6)
    ok = simulate(no_margin.override({"waterfall.rate_rule_rate": 0.005}), draws, ladder)
    short = simulate(no_margin.override({"waterfall.rate_rule_rate": 0.0055}), draws, ladder)
    assert ok.all_paid.all() and not short.all_paid.any()
    assert row["rule_rate_needed"] > 0.005
    assert simulate(base.override({"waterfall.rate_rule_rate": row["rule_rate_needed"]}), draws, ladder).all_paid.all()


def test_backstop_matches_hand_calculation(base):
    """Zero vol, T-bills 3%, no top-up (fixed rule of $0), iBonds rungs pay $40k. The reserve
    leaves bill 1 short by 10k - b2033 and bills 2-5 short by 10k each; the $10k backstop
    (grown at 3% from Jan 2033) pays them in order until it runs out."""
    a = base.override({**ZERO_VOL, "ladder.ibonds_error_mean": -0.20, "waterfall.topup_rule": "fixed_rule",
                       "waterfall.fixed_rule_amount": 0.0, "waterfall.backstop_amount": 10_000})
    res = run_monte_carlo(a, n=2)
    b2033 = res.buffer_start[0] * 1.03 ** 6
    unpaid = [10_000 - b2033] + [10_000] * 4 + [0] * 5
    backstop, draws = 10_000.0, []
    for k, u in enumerate(unpaid):
        if k:
            backstop *= 1.03
        d = min(u, backstop)
        draws.append(d)
        backstop -= d
    assert np.allclose(res.bill_amount - res.bill_paid, unpaid, atol=1e-6)
    assert np.allclose(res.backstop_draw, draws, atol=1e-6)
    assert np.allclose(res.backstop_left, backstop, atol=1e-6)
    assert np.allclose(res.unpaid_after_backstop, sum(unpaid) - sum(draws), atol=1e-6)
    assert not res.all_paid_with_backstop.any()
    # The backstop comes from the client's cushion, not the facility contribution.
    no_bs = run_monte_carlo(a.override({"waterfall.backstop_amount": 0.0}), n=2)
    assert np.allclose(res.facility, no_bs.facility)
    assert np.allclose(no_bs.backstop_draw, 0.0) and np.allclose(no_bs.unpaid_after_backstop, no_bs.unpaid)


def test_backstop_leftover_is_start_plus_interest_minus_used(base):
    """Required identity, on every simulated path and every stress scenario."""
    res = run_monte_carlo(base, n=20_000)
    assert np.allclose(res.backstop_left, res.backstop_start + res.backstop_interest - res.backstop_used)
    assert (res.backstop_interest >= 0).all()
    stress = analysis.run_stress_tests(base)
    assert np.allclose(stress["backstop_left_2042"],
                       stress["backstop_2033"] + stress["backstop_interest"] - stress["backstop_used"])


def test_combined_stress_backstop_interest_by_hand(base):
    """Combined stress: T-bills pay 0.5% a year. The $10,000 backstop earns interest from
    Jan 2033; the reserve leaves the 2041 and 2042 bills short."""
    stress = analysis.run_stress_tests(base).set_index("scenario")
    row = stress.loc["combined_low_rates"]
    ladder = load_ladder(base)
    sc = next(s for s in base["stress_tests.scenarios"] if s["name"] == "combined_low_rates")
    from mcsim.model import simulate
    r = simulate(base, analysis.stress_draws(base, ladder, sc), ladder)
    short = r.bill_amount - r.bill_paid[0]
    assert (short > 1e-6).any()                                         # some bills are short
    bal, interest, used = 10_000.0, 0.0, 0.0
    for k, year in enumerate(range(2033, 2043)):                        # backstop from Jan 2033
        if year > 2033:
            interest += bal * 0.005
            bal *= 1.005
        draw = min(short[k], bal)
        bal -= draw
        used += draw
    assert row["backstop_left_2042"] == pytest.approx(bal)
    assert row["backstop_interest"] == pytest.approx(interest)
    assert row["backstop_used"] == pytest.approx(used)


def test_combined_shortfall_depends_on_bond_cashflows_not_prices(base, tmp_path):
    """The stress tests read the current ladder.csv. YTMs and prices change what the ladder
    costs (and so the facility contribution) but not what the bonds pay, so the bill
    shortfall stays put; changing a bond quantity changes it."""
    from mcsim.model import simulate
    sc = next(s for s in base["stress_tests.scenarios"] if s["name"] == "combined_low_rates")
    sheet = pd.read_csv(base.path("ladder.csv_path"))

    def run(df):
        path = tmp_path / f"l{len(list(tmp_path.iterdir()))}.csv"
        df.to_csv(path, index=False)
        a = base.override({"ladder.csv_path": str(path)})
        lad = load_ladder(a)
        return simulate(a, analysis.stress_draws(a, lad, sc), lad)

    now = run(sheet)
    cheaper = run(sheet.assign(ytm=sheet["ytm"] + 0.01))
    assert cheaper.ladder_cost[0] < now.ladder_cost[0]
    assert cheaper.facility[0] > now.facility[0]
    assert cheaper.unpaid[0] == pytest.approx(now.unpaid[0])
    more_bonds = sheet.copy()
    more_bonds.loc[more_bonds["bill_number"] == 10, "quantity"] += 2
    assert run(more_bonds).unpaid[0] < now.unpaid[0]


def test_coverage_metrics_consistent(base):
    res = run_monte_carlo(base, n=20_000)
    total = res.bill_amount * len(res.timeline.bill_years)
    assert total == 500_000
    assert np.allclose(res.ladder_only_coverage, 1 - res.ladder_only_total_shortfall / total)
    assert ((res.ladder_only_coverage >= 1 - 1e-12) == res.ladder_only_all_paid).all()
    cs = analysis.coverage_stats(res)
    assert cs["coverage_worst"] <= cs["coverage_p10"] <= cs["coverage_median"] <= 1.0
    assert cs["p_short"] == pytest.approx(1 - res.ladder_only_all_paid.mean())
    short = res.ladder_only_total_shortfall[~res.ladder_only_all_paid]
    assert cs["shortfall_median"] == pytest.approx(np.median(short))
    assert cs["shortfall_max"] == pytest.approx(short.max())
    bm = analysis.bills_missed_table(res)
    assert bm["Paths"].sum() == res.n
    zero = bm.loc[bm["Bills short"] == 0, "Share of paths"]
    assert zero.iloc[0] == pytest.approx(res.ladder_only_all_paid.mean())
    rank = analysis.bill_failure_ranking(res)
    assert rank["Share of paths short"].is_monotonic_decreasing
    # Bill-by-bill short counts add up to the bills-missed distribution.
    assert (bm["Bills short"] * bm["Paths"]).sum() == round(rank["Share of paths short"].sum() * res.n)


def test_coverage_by_hand(base):
    """Zero vol, T-bills 3%, iBonds rungs pay $40k, no top-up: bills 1-5 are short
    (bill 1 by 10k - b2033), bills 6-10 are paid."""
    a = base.override({**ZERO_VOL, "ladder.ibonds_error_mean": -0.20})
    res = run_monte_carlo(a, n=2)
    b2033 = res.buffer_start[0] * 1.03 ** 6
    short = (10_000 - b2033) + 4 * 10_000
    assert (res.ladder_only_bills_short == 5).all()
    assert np.allclose(res.ladder_only_coverage, 1 - short / 500_000)
    rank = analysis.bill_failure_ranking(res)
    assert set(rank["Bill #"][:5]) == {1, 2, 3, 4, 5}


def test_backstop_capped_at_cushion(base):
    a = base.override({"waterfall.backstop_amount": 1e9})
    res = run_monte_carlo(a, n=1_000)
    assert np.allclose(res.backstop_start, res.cushion_kept)
    assert (res.all_paid_with_backstop >= res.all_paid).all()


def test_combined_stress_backstop(base):
    stress = analysis.run_stress_tests(base).set_index("scenario")
    comb, low = stress.loc["combined_low_rates"], stress.loc["combined_low_rates_p10"]
    assert comb["shortfall_from_2028"] > 0 and comb["buffer_jan_2027"] == 0.0     # yields -2 pts
    assert not comb["all_bills_paid"] and comb["unpaid_bill_dollars"] > 0         # 0.5% T-bills
    # The rule sees the smaller 2033 reserve, so the bill shortfall matches the low-rate-only path.
    assert comb["unpaid_bill_dollars"] == pytest.approx(stress.loc["low_rates_2010s", "unpaid_bill_dollars"])
    assert comb["backstop_2033"] == pytest.approx(base["waterfall.backstop_amount"])
    covers = comb["unpaid_bill_dollars"] <= comb["backstop_2033"] * 1.005 ** 9
    assert comb["backstop_covers"] == covers
    assert comb["backstop_used"] == pytest.approx(min(comb["unpaid_bill_dollars"], comb["backstop_used"]))
    assert comb["unpaid_after_backstop"] == pytest.approx(comb["unpaid_bill_dollars"] - comb["backstop_used"])
    assert low["facility_contribution"] < comb["facility_contribution"]
    assert low["unpaid_bill_dollars"] == pytest.approx(comb["unpaid_bill_dollars"])


def test_ladder_flags_estimate_rows(base):
    ladder = load_ladder(base)
    status = ladder.table["data_status"].fillna("")
    n_est = int(status.str.upper().str.contains("ESTIMATE").sum())
    assert len(ladder.unverified) == n_est
    if n_est:
        res = run_monte_carlo(base, n=1_000)
        from mcsim import analysis as an
        md = an.build_summary(base, res, an.run_stress_tests(base), an.run_sensitivity(base))
        assert "ladder.csv is not confirmed" in md
        assert all(u in md for u in ladder.unverified)


def test_cashflow_model_pays_coupons_plus_face_at_zero_rates(base):
    a = base.override({**ZERO_VOL, "tbills.mean": 0.0, "ladder.bond_payout_model": "cashflows"})
    res = run_monte_carlo(a, n=2)
    ladder = load_ladder(a)
    for k in np.flatnonzero(ladder.is_bond):
        flow = ladder.flows(pd.Timestamp("2027-01-01"), "cashflows")[k]
        face = ladder.quantity[k] * 1000
        assert flow.amounts.sum() == pytest.approx(face * (1 + ladder.coupon[k] / 2 * len(flow.dates)))
        assert np.allclose(res.rung_payout[:, k], flow.amounts.sum())


def test_simulated_returns_match_configured_moments(base):
    from mcsim.model import draw_random
    ladder = load_ladder(base)
    d = draw_random(base, ladder, 200_000, seed=1)
    assert d.us.mean() == pytest.approx(base["growth.us_mean"], abs=0.002)
    assert d.us.std() == pytest.approx(base["growth.us_vol"], abs=0.002)
    assert d.intl.mean() == pytest.approx(base["growth.intl_mean"], abs=0.002)
    assert d.intl.std() == pytest.approx(base["growth.intl_vol"], abs=0.002)
    rho = np.corrcoef(d.us[:, 0], d.intl[:, 0])[0, 1]
    assert rho == pytest.approx(base["growth.correlation"], abs=0.01)


# Task 6: headline.md must come from the same run as the other outputs -------------

def test_headline_matches_run_outputs(base):
    import json
    out = base.base_dir / "outputs"
    m = json.loads((out / "metrics.json").read_text())
    headline = (out / "headline.md").read_text()
    # Every number in headline.md is rendered from metrics.json; nothing is typed by hand.
    assert headline == analysis.render_headline(m)
    assert len([ln for ln in headline.splitlines() if ln[:2] in {"1.", "2.", "3.", "4.", "5."}]) == 5
    # metrics.json agrees with the stress table written in the same run.
    w = analysis.worst_stress(pd.read_csv(out / "stress_tests.csv"))
    assert m["worst_scenario"] == w["scenario"]
    for key, col in [("worst_unpaid", "unpaid_bill_dollars"), ("worst_backstop_left", "backstop_left_2042"),
                     ("worst_backstop_interest", "backstop_interest"), ("worst_facility", "facility_contribution")]:
        assert m[key] == pytest.approx(w[col]), key
    # ...and with summary.md from the same run.
    summary = (out / "summary.md").read_text()
    for text in [analysis.pct(m["all_paid_with_backstop"], 2), analysis.pct(m["all_paid_without_backstop"], 2),
                 analysis.money(m["facility_median"]), analysis.money(m["range_low"]),
                 analysis.money(m["range_high"]), analysis.money(m["topup_median"]),
                 analysis.pct(m["coverage_median"]), analysis.money(m["worst_unpaid"]),
                 f"{m['n_sims']:,} simulated paths"]:
        assert text in summary, text
    # Footnote: the same run with purchase-yield risk off, in both files, labelled as such.
    foot = analysis.oct2026_footnote({"median": m["facility_median"], "p10": m["facility_p10"]},
                                     {"median": m["oct2026_facility_median"], "p10": m["oct2026_facility_p10"]})
    assert "if bought at Oct 2026 WInS prices" in foot and foot in headline and foot in summary
    # The outputs were generated from the current config.yaml and ladder.csv.
    assert m["inputs_sha256"] == base.inputs_fingerprint(), "outputs/ is stale: rerun run_simulation.py"


# Task 8: run counts -------------------------------------------------------------

def test_run_count_settings(base):
    assert base["simulation.n_sims"] == 100_000              # official run
    assert base["simulation.dashboard_n_sims"] == 10_000     # dashboard
    assert base["simulation.report_n_sims"] == 500_000       # final report only


def test_official_outputs_use_official_run_count(base):
    import json
    m = json.loads((base.base_dir / "outputs" / "metrics.json").read_text())
    assert m["n_sims"] in (base["simulation.n_sims"], base["simulation.report_n_sims"])
    if base.placeholders():                                   # --final is not allowed yet
        assert m["n_sims"] == base["simulation.n_sims"]


def test_final_run_refused_while_placeholders_remain(base, tmp_path):
    import subprocess
    import sys
    if not base.placeholders():
        pytest.skip("no placeholders left; --final is allowed")
    out = tmp_path / "final"
    proc = subprocess.run([sys.executable, str(base.base_dir / "run_simulation.py"), "--final", "--out", str(out)],
                          capture_output=True, text=True, cwd=base.base_dir)
    assert proc.returncode != 0
    assert "placeholders" in proc.stderr
    assert not out.exists()


# Round 4: sourced assumptions ------------------------------------------------------

def test_tbill_mean_path_and_inflation_path(base):
    from mcsim.model import draw_random, inflation_deflator, make_timeline, tbill_mean_path
    ladder = load_ladder(base)
    tl = make_timeline(base, ladder)
    means = dict(zip(tl.tbill_years, tbill_mean_path(base, tl)))
    assert (means[2027], means[2028], means[2029], means[2030], means[2041]) == (0.040, 0.039, 0.036, 0.032, 0.032)
    # Without the 0% floor the simulated rates are centred on the mean path.
    d = draw_random(base.override({"tbills.floor": -1.0}), ladder, 200_000, seed=3)
    assert np.allclose(d.tbill.mean(axis=0), list(means.values()), atol=0.0005)
    assert inflation_deflator(base, 2033) == pytest.approx(1.024 * 1.023 ** 5)
    res = run_monte_carlo(base, n=1_000)
    assert np.allclose(res.facility_real, res.facility / (1.024 * 1.023 ** 5))


def test_ibonds_fee_and_error_scale_with_years_to_maturity(base):
    from mcsim.model import draw_random, ibond_error_sd, ibond_fee_factor, ibond_years_to_maturity
    ladder = load_ladder(base)
    years = ibond_years_to_maturity(base, ladder)
    sd, fee = ibond_error_sd(base, ladder), ibond_fee_factor(base, ladder)
    for k in range(ladder.n_rungs):
        if ladder.is_ibond[k]:
            assert sd[k] == pytest.approx(min(0.0015 * years[k], 0.015))
            assert fee[k] == pytest.approx((1 - 0.0007) ** years[k])
        else:
            assert sd[k] == 0.0 and fee[k] == 1.0
    res = run_monte_carlo(base, n=200_000, seed=5)
    for k in np.flatnonzero(ladder.is_ibond):           # payout = 50k x fee drag x (1 + error)
        assert res.rung_payout[:, k].mean() == pytest.approx(50_000 * fee[k], rel=0.0005)
        assert res.rung_payout[:, k].std() / (50_000 * fee[k]) == pytest.approx(sd[k], rel=0.02)


def test_geometric_to_arithmetic_matches_jpm(base):
    assert analysis.geo_to_arith(0.0670, 0.1647) == pytest.approx(0.0794, abs=0.0001)   # JPM US: 6.70% geo
    from mcsim.model import lognormal_params
    mu, _ = lognormal_params(base["growth.us_mean"], base["growth.us_vol"])
    assert np.expm1(mu) == pytest.approx(0.0670, abs=0.0002)                              # and back again
    v = analysis.vanguard_overrides(base)
    for key, geo, vol in [("growth.us_mean", 0.052, base["growth.us_vol"])]:
        assert np.expm1(lognormal_params(v[key], vol)[0]) == pytest.approx(geo, abs=1e-9)


def test_policy_status_counts_as_resolved(base):
    policy = [k for k, s in base.statuses.items() if s == "policy"]
    assert {"growth.rebalance_annually", "reporting.recommended_range", "ladder.yield_shift_mean"} <= set(policy)
    assert base["ladder.yield_shift_mean"] == 0.0
    assert base.sources["ladder.yield_shift_mean"] == \
        "Team policy: no directional view on rates between now and Jan 2027."
    assert base.unresolved() == []                       # nothing left blocks check_deploy or --final
    assert not set(policy) & set(base.unresolved())
    assert all(base.sources[k] != "TODO" for k in policy)


def test_sensitivity_includes_vanguard_pessimistic(base):
    sens = analysis.run_sensitivity(base.override({"simulation.n_sims": 5_000})).set_index("case")
    assert "Vanguard pessimistic" in sens.index
    assert sens.loc["Vanguard pessimistic", "facility_p50"] < sens.loc["base", "facility_p50"]


def test_sizing_gaps_report_placed_vs_rule(base):
    """ladder.csv holds the placed trades. For each Treasury rung the report gives the sizing rule's
    quantity (from the Jan 2027 purchase, at the bond's own YTM) and how many bonds short the order is."""
    from mcsim.model import size_bond_quantity, value_per_bond_at_bill
    ladder = load_ladder(base)
    gaps = analysis.sizing_gaps(base, ladder).set_index("Bill #")
    for k in np.flatnonzero(ladder.is_bond):
        rule = size_bond_quantity(base, ladder, k, ladder.yields[k])
        per_bond = value_per_bond_at_bill(base, ladder, k, ladder.yields[k])
        assert rule * per_bond >= ladder.bill_amount[k] > (rule - 1) * per_bond      # the rule is the minimum
        row = gaps.loc[k + 1]
        assert row["Rule"] == rule and row["Placed"] == ladder.quantity[k]
        assert row["Bonds short"] == max(rule - ladder.quantity[k], 0)
        assert row["Cost to close"] == pytest.approx(row["Bonds short"] * ladder.unit_cost[k])
    assert np.allclose(ladder.sheet_cost, ladder.quantity * ladder.unit_cost, atol=0.01)
    line = analysis.sizing_line(base, ladder)
    for b in gaps.index[gaps["Bonds short"] > 0]:
        assert str(b) in line


def test_worst_stress_breaks_ties_by_lowest_facility():
    stress = pd.DataFrame({
        "scenario": ["a", "b", "c"],
        "unpaid_bill_dollars": [7673.4738, 7673.4738 + 1e-9, 100.0],     # a and b tie to the cent
        "facility_contribution": [55_305.0, 94_791.0, 10_000.0],
    })
    assert analysis.worst_stress(stress)["scenario"] == "a"


def test_rate_rule_ibonds_margin_by_hand(base):
    """Zero volatility, T-bills 3%, rate rule at 3%, iBonds pay $40k (error -20%). With the
    safety margin the rule assumes each iBonds rung not yet matured in Jan 2033 (bills 2-5)
    pays 1 std dev of its payout error less, so it moves exactly the present value of those
    margins (at 3%) more than without the margin. The matured rung (bill 1) gets no margin."""
    from mcsim.model import draw_random, ibond_error_sd, simulate
    a0 = base.override({**ZERO_VOL, "ladder.ibonds_error_mean": -0.20})       # draws: no iBonds noise
    ladder = load_ladder(a0)
    draws = draw_random(a0, ladder, 2, seed=1)
    with_sd = a0.override({"ladder.ibonds_error_sd_per_year": 0.0015})
    no_margin = simulate(with_sd.override({"waterfall.ibonds_margin_sd": 0.0}), draws, ladder)
    margin = simulate(with_sd, draws, ladder)                                   # official 1 std dev
    sd = ibond_error_sd(with_sd, ladder)
    assert sd[0] > 0 and with_sd["waterfall.ibonds_margin_sd"] == 1.0
    extra = sum(50_000 * sd[k] / 1.03 ** k for k in range(1, 5))              # bills 2-5, Jan 2034-2037
    assert np.allclose(margin.topup_target - no_margin.topup_target, extra)
    # Nothing else moves: same payouts, same bills paid (the extra is released after the last bill).
    assert np.allclose(margin.rung_payout, no_margin.rung_payout)
    assert np.allclose(margin.excess_topup_final - no_margin.excess_topup_final, extra * 1.03 ** 9)


# Round 4b: AR(1) T-bills ---------------------------------------------------------------

def test_ar1_change_sd_matches_source_over_long_run(base):
    """Required: over a long simulated run, the std dev of year-to-year changes is 1.5 pp."""
    from mcsim.model import tbill_deviations, tbill_shock_sd
    phi = base["tbills.ar1_phi"]
    assert phi == 0.85 and base["tbills.sd"] == 0.015
    z = np.random.default_rng(11).standard_normal((1, 500_000))
    x = tbill_deviations(z, phi, tbill_shock_sd(base))
    assert np.diff(x[0]).std() == pytest.approx(0.015, rel=0.01)
    assert np.corrcoef(x[0, :-1], x[0, 1:])[0, 1] == pytest.approx(phi, abs=0.005)     # persistence
    assert x[0].std() == pytest.approx(tbill_shock_sd(base) / np.sqrt(1 - phi ** 2), rel=0.02)


def test_simulated_tbills_follow_ar1_recursion(base):
    """rate_t = mean_t + phi (rate_(t-1) - mean_(t-1)) + shock, starting on the mean path,
    floored at 0% (the floor applies to the rate, not the AR(1) deviation)."""
    from mcsim.model import draw_random, make_timeline, tbill_mean_path, tbill_shock_sd
    ladder = load_ladder(base)
    tl = make_timeline(base, ladder)
    raw = base.override({"tbills.floor": -1.0})
    d = draw_random(raw, ladder, 5_000, seed=4)
    x = d.tbill - tbill_mean_path(raw, tl)[None, :]
    phi = base["tbills.ar1_phi"]
    shocks = np.column_stack([x[:, 0], x[:, 1:] - phi * x[:, :-1]])
    rng = np.random.default_rng(4)
    rng.standard_normal(5_000)                                   # yield shift draws come first
    z = rng.standard_normal((5_000, len(tl.tbill_years)))
    assert np.allclose(shocks, tbill_shock_sd(base) * z)
    floored = draw_random(base, ladder, 5_000, seed=4).tbill
    assert np.allclose(floored, np.maximum(d.tbill, 0.0))



def test_official_rate_rule_is_team_policy_a2(base):
    assert base["waterfall.topup_rule"] == "rate_rule"
    assert base["waterfall.rate_rule_rate"] == 0.010
    assert base["waterfall.backstop_amount"] == 10_000
    assert base.statuses["waterfall.rate_rule_rate"] == "policy"
    note = base.notes["waterfall.rate_rule_rate"]
    assert note.startswith("Team policy: plan as if cash earns 1% after 2033, below all forecasts of 3.0-3.2%")
    assert "Locked Oct 16 2026 (round 8): A2 kept over A4" in note


# Range rounding: down at both ends, so we never overstate --------------------------------

@pytest.mark.parametrize("overrides,seed", [({}, None), ({}, 1), ({}, 2),
                                            ({"growth.us_vol": 0.30, "growth.intl_vol": 0.35}, 3),
                                            ({"facility.give_pct": 0.6}, 4)])
def test_cosponsor_range_never_overstates(base, overrides, seed):
    a = base.override(overrides)
    res = run_monte_carlo(a, n=20_000, seed=seed)
    rec = analysis.recommended_range(res, a)
    p10, med = np.percentile(res.facility, 10), np.median(res.facility)
    assert rec["Low"] <= p10 and rec["High"] <= med and rec["Low"] <= rec["High"]
    assert rec["Low"] > p10 - 1_000 and rec["High"] > med - 1_000       # within one rounding step below
    assert rec["Low"] % 1_000 == 0 and rec["High"] % 1_000 == 0
    assert rec["P(at or above low end)"] >= 0.90 - 1 / res.n             # "90% chance of at least the low end" holds
    for _, row in analysis.cosponsor_ranges(res, a).iterrows():        # every candidate range too
        lo_pct, hi_pct = (int(x) for x in row["Range"].strip("[]").replace("P", "").split(","))
        assert row["Low"] <= np.percentile(res.facility, lo_pct) and row["High"] <= np.percentile(res.facility, hi_pct)
        assert row["P(at or above low end)"] >= 1 - lo_pct / 100 - 1 / res.n


def test_range_rounding_when_band_is_narrower_than_a_step(base):
    res = run_monte_carlo(base.override({"growth.us_vol": 0.0, "growth.intl_vol": 0.0, "tbills.sd": 0.0,
                                         "ladder.yield_shift_sd": 0.0, "ladder.ibonds_error_sd_per_year": 0.0}),
                          n=100)
    row = analysis.range_row(res, 10, 50, 1_000)                       # all paths identical: P10 == median
    med = float(np.median(res.facility))
    assert row["Low"] == row["High"] == np.floor(med / 1_000) * 1_000 <= med   # both round down, never above


def test_oct2026_footnote_case_is_the_run_without_purchase_yield_risk(base):
    from mcsim.model import run_monte_carlo
    a = base.override(analysis.OCT2026_OVERRIDES)
    res = run_monte_carlo(a, n=5_000)
    assert np.allclose(res.ladder_cost, res.ladder_cost[0])               # one fixed price: no yield shift
    f = analysis.oct2026_facility(res)
    assert f["median"] == float(np.median(res.facility)) and f["p10"] == float(np.percentile(res.facility, 10))
