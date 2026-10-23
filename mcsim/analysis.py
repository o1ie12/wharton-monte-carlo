"""Summaries built on top of simulation results: percentiles, co-sponsor
ranges, stress tests, sensitivity and the summary.md report."""
from __future__ import annotations

import json
from datetime import date
from statistics import NormalDist

import numpy as np
import pandas as pd

from .config import Assumptions
from .model import (MONTHS, Draws, Ladder, Results, growth_mix, inflation_deflator, ladder_costs,
                    leveraged_monthly_returns, load_ladder, lognormal_params, make_timeline, run_monte_carlo,
                    simulate, stock_log_params, tbill_mean_path)


# ------------------------------------------------------------ formatting ----

def fmt_value(v) -> str:
    """Compact display of a config value."""
    if isinstance(v, list) and v and all(isinstance(x, dict) for x in v):
        return f"{len(v)} items (see config.yaml)"
    if isinstance(v, (list, dict)):
        return json.dumps(v)
    return str(v)


def assumptions_table(a: Assumptions) -> pd.DataFrame:
    """Every config assumption with its status and source; placeholders flagged."""
    return pd.DataFrame([{
        "Assumption": k,
        "Value": fmt_value(a[k]),
        "Status": "**PLACEHOLDER**" if a.statuses.get(k) == "placeholder" else "sourced",
        "Source": a.sources[k].replace("|", "/"),
        "Note": a.notes.get(k, "").replace("|", "/"),
    } for k in a.values])


def inflation_text(a: Assumptions) -> str:
    by_year = {int(y): float(r) for y, r in (a.values.get("inflation.rate_by_year") or {}).items()}
    if not by_year:
        return f"{pct(a['inflation.rate'])} inflation"
    parts = [f"{pct(r)} inflation in {y}" for y, r in sorted(by_year.items())]
    return ", ".join(parts) + f", {pct(a['inflation.rate'])} from {max(by_year) + 1}"


def money(x: float) -> str:
    return f"-${-x:,.0f}" if x < 0 else f"${x:,.0f}"


def pct(x: float, digits: int = 1) -> str:
    return f"{100 * x:.{digits}f}%"


def md_table(df: pd.DataFrame) -> str:
    cols = [str(c) for c in df.columns]
    lines = ["| " + " | ".join(cols) + " |", "|" + "|".join(["---"] * len(cols)) + "|"]
    for _, row in df.iterrows():
        lines.append("| " + " | ".join(str(v) for v in row.to_numpy()) + " |")
    return "\n".join(lines)


# ----------------------------------------------------------------- bills ----

TOPUP_PCTS = (50, 90, 99)
SHORTFALL_PCTS = (10, 25, 50, 75, 90, 99)


def sizing_gaps(a: Assumptions, ladder: Ladder) -> pd.DataFrame:
    """Placed bond quantities vs the sizing rule (smallest whole number of bonds whose cash after the
    Jan 2027 purchase, reinvested at the bond's own YTM, reaches the bill by its date)."""
    from .model import size_bond_quantity, value_per_bond_at_bill
    rows = []
    for k in np.flatnonzero(ladder.is_bond):
        rule = size_bond_quantity(a, ladder, k, ladder.yields[k])
        per_bond = value_per_bond_at_bill(a, ladder, k, ladder.yields[k])
        short = max(rule - int(ladder.quantity[k]), 0)
        rows.append({"Bill #": k + 1, "Security": ladder.table["security"][k], "Placed": int(ladder.quantity[k]),
                     "Rule": rule, "Placed delivers at YTM": ladder.quantity[k] * per_bond,
                     "Bonds short": short, "Cost to close": short * float(ladder.unit_cost[k])})
    return pd.DataFrame(rows)


def ladder_stats(res: Results) -> dict:
    over = res.shortfall > 0
    moved, needed = res.topup, res.topup_needed
    failed = res.failed
    return {
        # a) headline: whole portfolio under the no-foresight top-up rule, no further help
        "p_all_paid": float(res.all_paid.mean()),
        "n_failed": int(failed.sum()),
        "fail_unpaid_median": float(np.median(res.unpaid[failed])) if failed.any() else 0.0,
        "fail_unpaid_p90": float(np.percentile(res.unpaid[failed], 90)) if failed.any() else 0.0,
        "fail_unpaid_max": float(res.unpaid[failed].max()) if failed.any() else 0.0,
        # b) ladder + buffer alone, no top-up
        "p_ladder_only": float(res.ladder_only_all_paid.mean()),
        # c) top-up the rule moves (all paths)
        "topup_median": float(np.median(moved)),
        "topup_p90": float(np.percentile(moved, 90)),
        "topup_p99": float(np.percentile(moved, 99)),
        "topup_max": float(moved.max()),
        "n_rule_capped": int(res.rule_capped.sum()),
        # leftover released to the cushion after the last bill
        "cushion_mean": float(res.cushion_release.mean()),
        "excess_topup_mean": float(res.excess_topup_final.mean()),
        # backstop from the client's cushion
        "p_all_paid_with_backstop": float(res.all_paid_with_backstop.mean()),
        "p_backstop_used": float((res.backstop_used > 1e-6).mean()),
        "backstop_left_mean": float(res.backstop_left.mean()),
        "unpaid_after_backstop_max": float(res.unpaid_after_backstop.max()),
        # reference: perfect foresight
        "p_foresight": float(res.foresight_all_paid.mean()),
        "needed_median": float(np.median(needed)),
        "needed_p90": float(np.percentile(needed, 90)),
        "needed_p99": float(np.percentile(needed, 99)),
        "needed_max": float(needed.max()),
        "expected_unpaid": float(res.unpaid.mean()),
        # ladder purchase
        "p_shortfall": float(over.mean()),
        "median_shortfall_when_short": float(np.median(res.shortfall[over])) if over.any() else 0.0,
        "ladder_cost_median": float(np.median(res.ladder_cost)),
        "buffer_start_median": float(np.median(res.buffer_start)),
        # reserve after bills (whole portfolio, including the top-up)
        "min_buffer_p5": float(np.percentile(res.min_buffer, 5)),
        "min_buffer_median": float(np.median(res.min_buffer)),
        "min_buffer_worst": float(res.min_buffer.min()),
    }


def topup_table(res: Results) -> pd.DataFrame:
    vy = res.timeline.valuation_year

    def stats(x):
        return [np.median(x)] + [np.percentile(x, p) for p in TOPUP_PCTS[1:]] + [x.max()]
    return pd.DataFrame({
        "Statistic": ["Median"] + [f"P{p}" for p in TOPUP_PCTS[1:]] + ["Max"],
        f"Moved Jan {vy} ({rule_name(res.topup_rule)})": stats(res.topup),
        f"Needed with perfect foresight (reference)": stats(res.topup_needed),
    })


def failure_shortfall(res: Results) -> pd.DataFrame:
    """Total unpaid bill dollars (nominal) on paths where the rule's top-up was not enough."""
    x = res.unpaid[res.failed]
    rows = [("Paths that fail", f"{len(x):,} of {res.n:,} ({len(x) / res.n:.2%})")]
    if len(x):
        rows += [("Mean", x.mean()), ("Median", np.median(x)), ("P90", np.percentile(x, 90)), ("Max", x.max())]
    return pd.DataFrame(rows, columns=["Statistic", "Total unpaid"])


# ------------------------------------------------------------ top-up rules ----

RULES = ("rate_rule", "fixed_rule", "foresight")
COSPONSOR_NOTE = ("The actual range will be set in 2031 from Laura's real growth bucket value and the actual 2027 ladder cost, using the same percentile method.")


def rule_name(rule: str) -> str:
    return {"rate_rule": "rate rule", "fixed_rule": "fixed rule", "foresight": "perfect foresight"}[rule]


def rule_label(a: Assumptions, rule: str | None = None) -> str:
    rule = rule or a["waterfall.topup_rule"]
    if rule == "rate_rule":
        return f"Rate rule ({a['waterfall.rate_rule_rate']:.1%})"
    if rule == "fixed_rule":
        return f"Fixed rule ({money(a['waterfall.fixed_rule_amount'])})"
    return "Perfect foresight (reference)"


def rule_results(a: Assumptions) -> dict[str, Results]:
    """The same paths (same seed) run under each top-up rule."""
    return {r: run_monte_carlo(a.override({"waterfall.topup_rule": r})) for r in RULES}


def rule_comparison(a: Assumptions, results: dict[str, Results]) -> pd.DataFrame:
    """One column per rule: bill success, top-up, failures, leftover cushion, facility, range."""
    tl = next(iter(results.values())).timeline
    vy, last = tl.valuation_year, tl.bill_years[-1]
    defl_last = inflation_deflator(a, last)
    lo_pct, hi_pct = a["reporting.recommended_range"]
    cols = {}
    for rule, r in results.items():
        ls = ladder_stats(r)
        rec = recommended_range(r, a)
        label = rule_label(a, rule) + (" ★ official" if rule == a["waterfall.topup_rule"] else "")
        failed = r.failed.any()
        col = {
            "All bills paid, no further help": pct(ls["p_all_paid"], 2),
            f"All bills paid with {money(a['waterfall.backstop_amount'])} backstop": pct(ls["p_all_paid_with_backstop"], 2),
            "Paths that fail": f"{ls['n_failed']:,}",
            f"Top-up moved Jan {vy}: median / P90 / max":
                f"{money(ls['topup_median'])} / {money(ls['topup_p90'])} / {money(ls['topup_max'])}",
            "Shortfall when it fails: median / P90 / max":
                (f"{money(ls['fail_unpaid_median'])} / {money(ls['fail_unpaid_p90'])} / {money(ls['fail_unpaid_max'])}"
                 if failed else "no failures"),
            f"Released to cushion after Jan {last} bill (mean, nominal)": money(ls["cushion_mean"]),
            f"Released to cushion (mean, Jan {a['inflation.base_year']} dollars)": money(ls["cushion_mean"] / defl_last),
            "Unneeded top-up within the release (mean, nominal)": money(ls["excess_topup_mean"]),
        }
        for p_, v in zip(a["reporting.percentiles"], np.percentile(r.facility, a["reporting.percentiles"])):
            col[f"Facility P{p_}"] = money(v)
        col[f"Co-sponsor range [P{lo_pct}, P{hi_pct}]"] = f"{money(rec['Low'])} – {money(rec['High'])}"
        col["Range: P(at or above low end) / P(inside)"] = (f"{pct(rec['P(at or above low end)'], 0)} / "
                                                      f"{pct(rec['P(inside range)'], 0)}")
        cols[label] = col
    out = pd.DataFrame(cols)
    out.index.name = "Metric"
    return out.reset_index()


def coverage_stats(res: Results) -> dict:
    """Ladder + buffer by themselves: no top-up and no backstop."""
    cov = res.ladder_only_coverage
    short = ~res.ladder_only_all_paid
    total = res.ladder_only_total_shortfall[short]
    return {
        "bill_dollars": float(res.bill_amount * res.ladder_only_paid.shape[1]),
        "coverage_median": float(np.median(cov)),
        "coverage_p10": float(np.percentile(cov, 10)),
        "coverage_worst": float(cov.min()),
        "p_short": float(short.mean()),
        "n_short": int(short.sum()),
        "shortfall_median": float(np.median(total)) if short.any() else 0.0,
        "shortfall_p90": float(np.percentile(total, 90)) if short.any() else 0.0,
        "shortfall_max": float(total.max()) if short.any() else 0.0,
    }


def bills_missed_table(res: Results) -> pd.DataFrame:
    """How many of the bills ladder + buffer alone leave short, across paths."""
    counts = np.bincount(res.ladder_only_bills_short, minlength=res.ladder_only_paid.shape[1] + 1)
    df = pd.DataFrame({"Bills short": np.arange(len(counts)), "Paths": counts,
                       "Share of paths": counts / res.n})
    return df[df["Paths"] > 0].reset_index(drop=True)


def bill_failure_ranking(res: Results) -> pd.DataFrame:
    """Which bills ladder + buffer alone leave short most often."""
    short = res.ladder_only_shortfall > 1e-6
    df = pd.DataFrame({
        "Bill #": np.arange(1, short.shape[1] + 1),
        "Bill (Jan 1)": res.timeline.bill_years,
        "Share of paths short": short.mean(axis=0),
        "Median shortfall when short": [float(np.median(res.ladder_only_shortfall[short[:, k], k]))
                                        if short[:, k].any() else 0.0 for k in range(short.shape[1])],
    })
    return df.sort_values(["Share of paths short", "Bill #"], ascending=[False, True]).reset_index(drop=True)


def shortfall_distribution(res: Results) -> pd.DataFrame:
    """Total ladder-only shortfall (sum of unpaid bill dollars, nominal) on paths
    where ladder + buffer alone fall short."""
    x = res.ladder_only_total_shortfall[~res.ladder_only_all_paid]
    if len(x) == 0:
        return pd.DataFrame(columns=["Statistic", "Total shortfall"])
    rows = [("Paths short", f"{len(x):,} of {res.n:,} ({len(x) / res.n:.1%})"), ("Mean", x.mean())]
    rows += [(f"P{p}", np.percentile(x, p)) for p in SHORTFALL_PCTS] + [("Max", x.max())]
    return pd.DataFrame(rows, columns=["Statistic", "Total shortfall"])


def bill_table(res: Results) -> pd.DataFrame:
    sf = res.ladder_only_shortfall
    short = sf > 1e-6
    med = [float(np.median(sf[short[:, k], k])) if short[:, k].any() else 0.0 for k in range(sf.shape[1])]
    p90 = [float(np.percentile(sf[short[:, k], k], 90)) if short[:, k].any() else 0.0 for k in range(sf.shape[1])]
    return pd.DataFrame({
        "Bill (Jan 1)": res.timeline.bill_years,
        "Median rung payout": np.median(res.rung_payout, axis=0),
        "P5 rung payout": np.percentile(res.rung_payout, 5, axis=0),
        "Ladder-only: share of paths short": short.mean(axis=0),
        "Ladder-only: median shortfall when short": med,
        "Ladder-only: P90 shortfall when short": p90,
        "Whole portfolio: unpaid (mean)": np.maximum(res.bill_amount - res.bill_paid, 0).mean(axis=0),
    })


# -------------------------------------------------------------- facility ----

def percentile_table(res: Results, percentiles: list[int]) -> pd.DataFrame:
    vy = res.timeline.valuation_year
    cols = {
        f"Jan {vy} value before top-up": res.value_before_topup,
        f"Jan {vy} value after top-up (nominal)": res.value,
        f"Jan {vy} value after top-up (real)": res.value_real,
        "Facility contribution (nominal)": res.facility,
        "Facility contribution (real)": res.facility_real,
    }
    out = pd.DataFrame({k: np.percentile(v, percentiles) for k, v in cols.items()})
    out.insert(0, "Percentile", [f"P{p}" for p in percentiles])
    return out


def range_row(res: Results, lo_pct: int, hi_pct: int, rounding: float) -> dict:
    """Co-sponsor range from two percentiles of the facility contribution, both ends rounded DOWN
    to `rounding`, so we never overstate: low end <= P_lo and top <= P_hi."""
    x = res.facility
    p_lo, p_hi = float(np.percentile(x, lo_pct)), float(np.percentile(x, hi_pct))
    lo = float(np.floor(p_lo / rounding) * rounding)
    hi = float(np.floor(p_hi / rounding) * rounding)
    return {
        "Range": f"[P{lo_pct}, P{hi_pct}]",
        "Low": lo,
        "High": hi,
        "Low (real)": lo / res.deflator,
        "High (real)": hi / res.deflator,
        "P(inside range)": float(((x >= lo) & (x <= hi)).mean()),
        "P(at or above low end)": float((x >= lo).mean()),
    }


def cosponsor_ranges(res: Results, a: Assumptions) -> pd.DataFrame:
    rounding = float(a["reporting.range_rounding"])
    return pd.DataFrame([range_row(res, lo, hi, rounding) for lo, hi in a["reporting.cosponsor_ranges"]])


def recommended_range(res: Results, a: Assumptions) -> dict:
    lo, hi = a["reporting.recommended_range"]
    return range_row(res, lo, hi, float(a["reporting.range_rounding"]))


# ---------------------------------------------------------- stress tests ----

def stress_draws(a: Assumptions, ladder: Ladder, scenario: dict) -> Draws:
    """A single fixed path. Inputs the scenario does not set use their means. Stock indexes
    (US, international and, for growth-mix scenarios, small cap) earn a steady return that puts
    each one's total at the scenario percentile; crash years override all of them. A 2x
    leveraged fund is built from the US path, with each year's US return spread evenly across
    its months."""
    tl = make_timeline(a, ladder)
    G, T = len(tl.growth_years), len(tl.tbill_years)
    mix = growth_mix(a)
    z = NormalDist().inv_cdf(scenario.get("stock_percentile", 50) / 100.0) / np.sqrt(G)

    def steady(mean_key: str, vol_key: str) -> np.ndarray:
        if "stock_fixed_return" in scenario:
            return np.full(G, float(scenario["stock_fixed_return"]))
        mu, s = lognormal_params(a[mean_key], a[vol_key])
        return np.full(G, np.expm1(mu + s * z))

    us = steady("growth.us_mean", "growth.us_vol")
    intl = steady("growth.intl_mean", "growth.intl_vol")
    extra = {"small_cap": steady("growth_mix.small_cap_mean", "growth_mix.small_cap_vol")} if "small_cap" in mix else {}
    for year, r in (scenario.get("stock_overrides") or {}).items():
        g = tl.growth_years.index(int(year))
        us[g] = intl[g] = float(r)
        if "small_cap" in extra:
            extra["small_cap"][g] = float(r)
    tbill = (np.full((1, T), float(scenario["tbill_rate"])) if "tbill_rate" in scenario
             else np.maximum(tbill_mean_path(a, tl), a["tbills.floor"])[None, :])
    if "us_2x" in mix:
        us_m = np.repeat(((1.0 + us) ** (1.0 / MONTHS) - 1.0)[None, :, None], MONTHS, axis=2)
        tcol = [tl.tbill_years.index(y) for y in tl.growth_years]
        lev = leveraged_monthly_returns(us_m, tbill[:, tcol], float(a["growth_mix.us_2x_multiple"]),
                                        float(a["growth_mix.us_2x_fee"]))
        extra["us_2x"] = (np.prod(1.0 + lev, axis=-1) - 1.0)[0]
    return Draws(
        yield_shift=np.array([float(scenario.get("yield_shift", a["ladder.yield_shift_mean"]))]),
        tbill=tbill,
        us=us[None, :],
        intl=intl[None, :],
        ibond_error=np.full((1, ladder.n_rungs), float(a["ladder.ibonds_error_mean"])),
        contribution=np.array([float(scenario.get("contribution", a["plan.growth_contribution"]))]),
        extra={k: v[None, :] for k, v in extra.items()},
    )


RATE_SEARCH = (-0.05, 0.20)


def rule_rate_needed(a: Assumptions, ladder: Ladder, draws: Draws, tol: float = 1e-7) -> float:
    """Highest reinvestment rate the rate rule can assume and still pay every bill on
    this fixed path. inf: every rate up to RATE_SEARCH[1] works (little or no top-up
    needed). nan: no rate works (the growth bucket cannot cover the top-up)."""
    b = a.override({"waterfall.topup_rule": "rate_rule"})

    def pays(rate: float) -> bool:
        return bool(simulate(b.override({"waterfall.rate_rule_rate": rate}), draws, ladder).all_paid[0])

    lo, hi = RATE_SEARCH
    if pays(hi):
        return float("inf")
    if not pays(lo):
        return float("nan")
    while hi - lo > tol:           # the rule's top-up falls as the assumed rate rises
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if pays(mid) else (lo, mid)
    return lo


def fmt_rate_needed(x: float) -> str:
    if np.isinf(x):
        return f"any rate up to {RATE_SEARCH[1]:.0%}"
    if np.isnan(x):
        return "none (growth bucket too small)"
    return f"{x:.2%}"


LOW_RATE_SCENARIOS = {"low_rates_2010s": "Median", "low_rates_2010s_p10": "P10"}
COMBINED_SCENARIOS = {"combined_low_rates": "Median", "combined_low_rates_p10": "P10"}


def scenario_report(stress: pd.DataFrame, scenarios: dict[str, str]) -> dict | None:
    """Headline facts for a pair of fixed paths that differ only in stock growth
    (median vs P10). Bills do not depend on stocks, so bill facts come from the first."""
    rows = stress.set_index("scenario")
    names = [n for n in scenarios if n in rows.index]
    if not names:
        return None
    first = rows.loc[names[0]]
    return {
        "all_paid": bool(first["all_bills_paid"]),
        "unpaid": float(first["unpaid_bill_dollars"]),
        "moved": float(first["topup_2033"]),
        "needed": float(first["topup_needed_foresight"]),
        "rate_needed": float(first["rule_rate_needed"]),
        "ladder_cost": float(first["ladder_cost"]),
        "shortfall_from_2028": float(first["shortfall_from_2028"]),
        "backstop": float(first["backstop_2033"]),
        "backstop_used": float(first["backstop_used"]),
        "backstop_interest": float(first["backstop_interest"]),
        "backstop_covers": bool(first["backstop_covers"]),
        "unpaid_after_backstop": float(first["unpaid_after_backstop"]),
        "backstop_left": float(first["backstop_left_2042"]),
        "by_growth": [{"growth": scenarios[n],
                       "cushion": float(rows.loc[n, "cushion_kept_2033"]),
                       "share": float(rows.loc[n, "unpaid_pct_of_cushion"]),
                       "facility": float(rows.loc[n, "facility_contribution"]),
                       "facility_real": float(rows.loc[n, "facility_contribution_real"]),
                       "backstop": float(rows.loc[n, "backstop_2033"]),
                       "backstop_covers": bool(rows.loc[n, "backstop_covers"])} for n in names],
    }


def low_rate_report(stress: pd.DataFrame) -> dict | None:
    return scenario_report(stress, LOW_RATE_SCENARIOS)


def combined_report(stress: pd.DataFrame) -> dict | None:
    return scenario_report(stress, COMBINED_SCENARIOS)


def run_stress_tests(a: Assumptions) -> pd.DataFrame:
    ladder = load_ladder(a)
    give = float(a["facility.give_pct"])
    rows = []
    for sc in a["stress_tests.scenarios"]:
        draws = stress_draws(a, ladder, sc)
        r = simulate(a, draws, ladder)
        cushion = r.value[0] * (1.0 - give)
        rows.append({
            "scenario": sc["name"],
            "description": sc.get("description", ""),
            "ladder_cost": r.ladder_cost[0],
            "buffer_jan_2027": r.buffer_start[0],
            "shortfall_from_2028": r.shortfall[0],
            "growth_contribution": r.growth_contribution[0],
            "value_2033_before_topup": r.value_before_topup[0],
            "topup_2033": r.topup[0],
            "topup_needed_foresight": r.topup_needed[0],
            "cushion_release_2042": r.cushion_release[0],
            "value_2033": r.value[0],
            "value_2033_real": r.value_real[0],
            "facility_contribution": r.facility[0],
            "facility_contribution_real": r.facility_real[0],
            "all_bills_paid": bool(r.all_paid[0]),
            "ladder_only_all_paid": bool(r.ladder_only_all_paid[0]),
            "ladder_only_shortfall": float(r.ladder_only_total_shortfall[0]),
            "unpaid_bill_dollars": float(r.unpaid[0]),
            "backstop_2033": float(r.backstop_start[0]),
            "backstop_interest": float(r.backstop_interest[0]),
            "backstop_used": float(r.backstop_used[0]),
            "backstop_covers": bool(r.all_paid_with_backstop[0]),
            "unpaid_after_backstop": float(r.unpaid_after_backstop[0]),
            "backstop_left_2042": float(r.backstop_left[0]),
            "cushion_kept_2033": cushion,
            "unpaid_pct_of_cushion": float(r.unpaid[0]) / cushion if cushion > 0 else float("nan"),
            "rule_rate_needed": rule_rate_needed(a, ladder, draws),
            "min_buffer": r.min_buffer[0],
            "final_buffer": r.final_buffer[0],
        })
    return pd.DataFrame(rows)


# ----------------------------------------------------------- sensitivity ----

def geo_to_arith(geo: float, vol: float) -> float:
    """Arithmetic mean return of a lognormal asset with geometric return `geo` and volatility
    `vol` (sd of simple returns): with M = 1 + arith, (1 + geo)^2 = M^4 / (M^2 + vol^2)."""
    g2 = (1.0 + geo) ** 2
    return float(np.sqrt((g2 + np.sqrt(g2 ** 2 + 4.0 * g2 * vol ** 2)) / 2.0) - 1.0)


def vanguard_overrides(a: Assumptions) -> dict:
    """Vanguard pessimistic case as arithmetic means for the simulation (volatilities unchanged)."""
    v = a["sensitivity.vanguard_pessimistic"]
    intl = (v["developed_weight"] * geo_to_arith(v["intl_developed_geo"], v["developed_vol"])
            + v["em_weight"] * geo_to_arith(v["em_geo"], v["em_vol"]))
    return {"growth.us_mean": geo_to_arith(v["us_geo"], a["growth.us_vol"]), "growth.intl_mean": intl}


def run_sensitivity(a: Assumptions) -> pd.DataFrame:
    d = float(a["sensitivity.return_shift"])
    cases = [("base", {}),
             (f"-{d * 100:g} pt", {"growth.us_mean": a["growth.us_mean"] - d, "growth.intl_mean": a["growth.intl_mean"] - d}),
             (f"+{d * 100:g} pt", {"growth.us_mean": a["growth.us_mean"] + d, "growth.intl_mean": a["growth.intl_mean"] + d})]
    if "sensitivity.vanguard_pessimistic" in a.values:
        cases.append(("Vanguard pessimistic", vanguard_overrides(a)))
    rows, base_median = [], None
    for label, overrides in cases:
        case = a.override(overrides)
        r = run_monte_carlo(case)
        med = float(np.median(r.facility))
        base_median = med if base_median is None else base_median
        q = np.percentile(r.facility, [10, 25, 50, 75, 90])
        rows.append({
            "case": label,
            "us_mean": case["growth.us_mean"],
            "intl_mean": case["growth.intl_mean"],
            "p_all_bills_paid": float(r.all_paid.mean()),
            "p_ladder_only": float(r.ladder_only_all_paid.mean()),
            "topup_median": float(np.median(r.topup)),
            "facility_mean": float(r.facility.mean()),
            "facility_p10": q[0], "facility_p25": q[1], "facility_p50": q[2],
            "facility_p75": q[3], "facility_p90": q[4],
            "median_change_vs_base": med / base_median - 1.0,
        })
    return pd.DataFrame(rows)


# -------------------------------------------------------------- headline ----

def worst_stress(stress: pd.DataFrame) -> pd.Series:
    """Most unpaid bill dollars before the backstop; ties go to the lowest facility contribution.
    Shortfalls are compared to the nearest dollar so floating-point noise cannot break a tie."""
    ranked = stress.assign(_unpaid=stress["unpaid_bill_dollars"].round(0))
    return ranked.sort_values(["_unpaid", "facility_contribution"], ascending=[False, True]) \
        .iloc[0].drop("_unpaid")


# Footnote case: the ladder priced at the Oct 2026 WInS fill yields, with no purchase-yield risk.
# The official run keeps that risk on because Laura's money arrives in 2027.
OCT2026_OVERRIDES = {"ladder.yield_shift_mean": 0.0, "ladder.yield_shift_sd": 0.0}
OCT2026_LABEL = "if bought at Oct 2026 WInS prices"


def oct2026_facility(res: Results) -> dict:
    """Median and P10 facility contribution of a run made with OCT2026_OVERRIDES."""
    return {"median": float(np.median(res.facility)), "p10": float(np.percentile(res.facility, 10))}


def oct2026_footnote(official: dict, oct2026: dict) -> str:
    return (f"Footnote, {OCT2026_LABEL} (purchase-yield risk off): median facility contribution "
            f"{money(oct2026['median'])} and P10 {money(oct2026['p10'])}, vs {money(official['median'])} and "
            f"{money(official['p10'])} in the official run, which keeps purchase-yield risk on because Laura's "
            "money arrives in 2027.")


def headline_metrics(a: Assumptions, res: Results, stress: pd.DataFrame, oct2026: dict | None = None) -> dict:
    """Every number in headline.md, taken from one run (this res and this stress table), plus the
    footnote run's facility median and P10 when given (oct2026_facility)."""
    ls = ladder_stats(res)
    cs = coverage_stats(res)
    rec = recommended_range(res, a)
    w = worst_stress(stress)
    return {
        "generated": date.today().isoformat(),
        "n_sims": res.n,
        "seed": int(a["simulation.seed"]),
        "inputs_sha256": a.inputs_fingerprint(),
        "n_bills": len(res.timeline.bill_years),
        "rule_label": rule_label(a),
        "backstop_amount": float(a["waterfall.backstop_amount"]),
        "all_paid_with_backstop": ls["p_all_paid_with_backstop"],
        "all_paid_without_backstop": ls["p_all_paid"],
        "worst_scenario": str(w["scenario"]),
        "worst_description": str(w["description"]),
        "worst_unpaid": float(w["unpaid_bill_dollars"]),
        "worst_backstop_covers": bool(w["backstop_covers"]),
        "worst_backstop_interest": float(w["backstop_interest"]),
        "worst_backstop_left": float(w["backstop_left_2042"]),
        "worst_unpaid_after_backstop": float(w["unpaid_after_backstop"]),
        "worst_facility": float(w["facility_contribution"]),
        "bill_dollars": cs["bill_dollars"],
        "coverage_median": cs["coverage_median"],
        "valuation_year": res.timeline.valuation_year,
        "topup_median": ls["topup_median"],
        "facility_median": float(np.median(res.facility)),
        "range_label": rec["Range"],
        "range_low": rec["Low"],
        "range_high": rec["High"],
        "range_p_low": rec["P(at or above low end)"],
        "facility_p10": float(np.percentile(res.facility, 10)),
        **({"oct2026_facility_median": oct2026["median"], "oct2026_facility_p10": oct2026["p10"]} if oct2026 else {}),
    }


def render_headline(m: dict) -> str:
    """headline.md: five plain-language lines, every number formatted from `m`."""
    backstop = money(m["backstop_amount"])
    cover = (f"the {backstop} backstop covers it, with {money(m['worst_backstop_left'])} left over "
             f"(including {money(m['worst_backstop_interest'])} of T-bill interest)"
             if m["worst_backstop_covers"] else
             f"the {backstop} backstop does not cover it ({money(m['worst_unpaid_after_backstop'])} still unpaid)")
    lines = [
        "# Headline numbers",
        "",
        f"1. All {m['n_bills']} bills are paid in {pct(m['all_paid_with_backstop'], 2)} of {m['n_sims']:,} "
        f"simulated paths with the official settings ({m['rule_label']} + {backstop} backstop); "
        f"{pct(m['all_paid_without_backstop'], 2)} without the backstop.",
        f"2. Worst stress case ({m['worst_description'].rstrip('.')}): {money(m['worst_unpaid'])} of bills go "
        f"unpaid before the backstop; {cover}, and the facility receives {money(m['worst_facility'])}.",
        f"3. On its own, with no top-up and no backstop, the ladder plus its cash buffer pays a median "
        f"{pct(m['coverage_median'])} of the {money(m['bill_dollars'])} in bills.",
        f"4. The median Jan {m['valuation_year']} top-up from the growth bucket to the bill reserve is "
        f"{money(m['topup_median'])}.",
        f"5. The median facility contribution is {money(m['facility_median'])}; example co-sponsor range (method) "
        f"{m['range_label']} is {money(m['range_low'])} to {money(m['range_high'])}, with a "
        f"{pct(m['range_p_low'], 0)} chance of reaching at least the low end.",
        "",
    ]
    if "oct2026_facility_median" in m:
        lines += [oct2026_footnote({"median": m["facility_median"], "p10": m["facility_p10"]},
                                   {"median": m["oct2026_facility_median"], "p10": m["oct2026_facility_p10"]}), ""]
    lines += [
        f"<!-- Generated {m['generated']} by run_simulation.py from one run: {m['n_sims']:,} paths, seed "
        f"{m['seed']}, inputs sha256 {m['inputs_sha256'][:16]}. Numbers come from outputs/metrics.json. -->",
        "",
    ]
    return "\n".join(lines)


# --------------------------------------------------------------- summary ----

def _fmt_money_cols(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    out = df.copy()
    for c in cols:
        out[c] = out[c].map(money)
    return out


def sizing_line(a: Assumptions, ladder: Ladder) -> str:
    gaps = sizing_gaps(a, ladder)
    short = gaps[gaps["Bonds short"] > 0]
    if short.empty:
        return "- Sizing check: every Treasury rung holds at least the sizing rule's quantity."
    bills = ", ".join(str(b) for b in short["Bill #"])
    return (f"- Sizing check: bills {bills} hold fewer bonds than the sizing rule "
            f"({int(short['Bonds short'].sum())} bonds short in total); buying them would cost about "
            f"{money(float(short['Cost to close'].sum()))} at current prices.")


def build_summary(a: Assumptions, res: Results, stress: pd.DataFrame, sens: pd.DataFrame,
                  note: str | None = None, oct2026: dict | None = None, decision: dict | None = None) -> str:
    tl = res.timeline
    ls = ladder_stats(res)
    ladder = load_ladder(a)
    by = a["inflation.base_year"]
    n_bills = len(tl.bill_years)
    rec = recommended_range(res, a)
    lines = [
        "# Client plan Monte Carlo summary",
        "",
        f"{res.n:,} simulated paths, seed {a['simulation.seed']}, generated {date.today().isoformat()}. "
        f"Real figures are in Jan {by} dollars ({inflation_text(a)}).",
    ]
    lines += [
        "",
        f"**Headline (official): all {n_bills} bills paid on {pct(ls['p_all_paid_with_backstop'], 2)} of paths** "
        f"with the {rule_label(a)} and the {money(a['waterfall.backstop_amount'])} backstop; "
        f"{pct(ls['p_all_paid'], 2)} without the backstop. Median facility contribution "
        f"{money(float(np.median(res.facility)))}; example co-sponsor range (method) {money(rec['Low'])} to "
        f"{money(rec['High'])} ({pct(rec['P(at or above low end)'], 0)} confidence of reaching the low end).",
        "",
        f"{COSPONSOR_NOTE}",
    ]
    if decision:
        lines += ["", option_decision_line(decision)]
    if oct2026:
        lines += ["", "<sup>" + oct2026_footnote(oct2026_facility(res), oct2026) + "</sup>"]
    if note:
        lines += ["", f"> **{note}**"]
    ph = a.placeholders()
    if ph:
        lines += ["", f"> **{len(ph)} assumptions are placeholders and need a confirmed source:** "
                      + ", ".join(f"`{k}`" for k in ph)]

    # Data status of the ladder sheet: estimates stay flagged until replaced.
    if ladder.unverified:
        lines += ["", f"> **ladder.csv is not confirmed: {len(ladder.unverified)} rows are estimates "
                      "(data_status contains \"ESTIMATE\") and must be replaced with market data.**"]
        lines += [f"> - {u}" for u in ladder.unverified]

    # Bills
    vy = tl.valuation_year
    lines += [
        "",
        "## Bills: ladder, buffer, then growth bucket",
        "",
        f"Bills are funded in order: ladder payouts, then the T-bill buffer, then the growth bucket. "
        f"On Jan 1 {vy}, before the facility contribution, the growth bucket tops up the T-bill reserve "
        f"using a rule that needs no knowledge of future rates ({rule_label(a)}). Money moved but not "
        f"needed stays in T-bills and is released to the client's cushion after the Jan {tl.bill_years[-1]} bill.",
        "",
        f"- **(a) Official: probability all {n_bills} bills are paid, {rule_label(a)} + "
        f"{money(a['waterfall.backstop_amount'])} backstop: {pct(ls['p_all_paid_with_backstop'], 2)}** "
        f"({res.n - int(res.all_paid_with_backstop.sum()):,} of {res.n:,} paths fail). The backstop is used on "
        f"{pct(ls['p_backstop_used'], 2)} of paths; mean returned to the client after Jan {tl.bill_years[-1]}: "
        f"{money(ls['backstop_left_mean'])}.",
        f"- Without the backstop (whole portfolio, {rule_label(a)}): {pct(ls['p_all_paid'], 2)} "
        f"({ls['n_failed']:,} paths fail; when they do, total unpaid median {money(ls['fail_unpaid_median'])}, "
        f"max {money(ls['fail_unpaid_max'])}).",
        f"- **(b) Probability ladder + buffer alone pay all bills, no top-up: {pct(ls['p_ladder_only'])}**",
        f"- **(c) Top-up moved in Jan {vy}:** median {money(ls['topup_median'])}, P90 {money(ls['topup_p90'])}, "
        f"P99 {money(ls['topup_p99'])}, max {money(ls['topup_max'])}. Mean released to the cushion after the "
        f"Jan {tl.bill_years[-1]} bill: {money(ls['cushion_mean'])} (of which unneeded top-up "
        f"{money(ls['excess_topup_mean'])}).",
        f"- Reference only, perfect foresight (exact top-up, needs future T-bill rates): all bills paid "
        f"{pct(ls['p_foresight'], 2)}; top-up median {money(ls['needed_median'])}, P90 {money(ls['needed_p90'])}, "
        f"P99 {money(ls['needed_p99'])}, max {money(ls['needed_max'])}.",
    ]
    model = a["ladder.bond_payout_model"]
    other = "cashflows" if model == "face" else "face"
    alt = ladder_stats(run_monte_carlo(a.override({"ladder.bond_payout_model": other})))
    desc = {"face": "each Treasury rung pays exactly the bill amount",
            "cashflows": "Treasury rungs pay their actual coupons and principal, reinvested at simulated T-bill rates"}
    lines += [
        f"- Bond payout model: **{model}** ({desc[model]}). Under **{other}** ({desc[other]}): "
        f"(a) {pct(alt['p_all_paid'], 2)}, (b) {pct(alt['p_ladder_only'])}.",
        f"- Ladder cost in ladder.csv (priced {ladder.price_date_label()}): {money(ladder.sheet_cost.sum())}. "
        f"Repriced on Jan 1 {tl.purchase_year} at unchanged yields: "
        f"{money(ladder_costs(ladder, [0.0], a).sum())} against a {money(a['plan.ladder_budget'])} budget; "
        f"median simulated cost {money(ls['ladder_cost_median'])}.",
        sizing_line(a, ladder),
        f"- Probability the ladder costs more than the budget: {pct(ls['p_shortfall'])} "
        f"(median shortfall when it does: {money(ls['median_shortfall_when_short'])}, taken from the "
        f"{tl.contribution_year} contribution). Median buffer at Jan {tl.purchase_year}: "
        f"{money(ls['buffer_start_median'])}.",
        f"- Minimum reserve left after any bill (whole portfolio): median {money(ls['min_buffer_median'])}, "
        f"P5 {money(ls['min_buffer_p5'])}, worst path {money(ls['min_buffer_worst'])}.",
        "",
    ]
    cs = coverage_stats(res)
    bm = bills_missed_table(res)
    bm_fmt = bm.assign(**{"Share of paths": bm["Share of paths"].map(lambda v: pct(v, 2))})
    rank = bill_failure_ranking(res)
    rank_fmt = rank.assign(**{"Share of paths short": rank["Share of paths short"].map(pct),
                              "Median shortfall when short": rank["Median shortfall when short"].map(money)})
    lines += [
        "### Ladder + buffer by themselves (no top-up, no backstop)",
        "",
        f"The ladder is not self-sufficient: by itself it leaves at least one bill short on "
        f"{pct(cs['p_short'])} of paths, but those gaps are small relative to the {money(cs['bill_dollars'])} "
        "of bills.",
        "",
        f"- **Bill-dollar coverage** (bill dollars ladder + buffer pay by themselves / "
        f"{money(cs['bill_dollars'])}): median **{pct(cs['coverage_median'])}**, P10 {pct(cs['coverage_p10'])}, "
        f"worst path {pct(cs['coverage_worst'])}.",
        f"- **Shortfall size** on the {cs['n_short']:,} paths that fall short: median "
        f"**{money(cs['shortfall_median'])}**, P90 {money(cs['shortfall_p90'])}, max {money(cs['shortfall_max'])}.",
        "- **Bills missed** (how many of the 10 bills are short):",
        "",
        md_table(bm_fmt),
        "",
        "Bills short most often:",
        "",
        md_table(rank_fmt),
        "",
        "Full distribution of total ladder-only shortfall (nominal, summed over the 10 bills), "
        "on the paths where ladder + buffer fall short:",
        "",
    ]
    sd = shortfall_distribution(res)
    if len(sd):
        sd["Total shortfall"] = sd["Total shortfall"].map(lambda v: v if isinstance(v, str) else money(v))
        lines.append(md_table(sd))
    else:
        lines.append("Ladder + buffer alone pay every bill on every path.")
    bt = bill_table(res)
    bt["Ladder-only: share of paths short"] = bt["Ladder-only: share of paths short"].map(pct)
    lines += ["", "### By bill", "",
              md_table(_fmt_money_cols(bt, [c for c in bt.columns if c != "Bill (Jan 1)" and "share" not in c]))]

    # Rule comparison
    results = rule_results(a)
    lines += [
        "",
        f"## Jan {vy} top-up rules compared",
        "",
        f"Same {res.n:,} paths under each rule. **Rate rule:** move the shortfall assuming all reinvestment "
        f"from Jan {vy} earns {a['waterfall.rate_rule_rate']:.1%} and unmatured ETF rungs pay their expected "
        f"amount. **Fixed rule:** always move {money(a['waterfall.fixed_rule_amount'])}. Perfect foresight "
        "is shown for reference only; it is not a rule anyone can follow.",
        "",
        md_table(rule_comparison(a, results)),
    ]
    for rule in ("rate_rule", "fixed_rule"):
        cr = cosponsor_ranges(results[rule], a)
        crf = _fmt_money_cols(cr, ["Low", "High", "Low (real)", "High (real)"])
        for c in ["P(inside range)", "P(at or above low end)"]:
            crf[c] = cr[c].map(pct)
        lines += ["", f"Co-sponsor ranges under the {rule_label(a, rule)}:", "", md_table(crf)]

    # Growth / facility
    pt = percentile_table(res, a["reporting.percentiles"])
    lines += [
        "",
        f"## Growth bucket and facility contribution (Jan {tl.valuation_year}, {rule_label(a)})",
        "",
        f"Facility contribution = {pct(res.give_pct, 0)} of the Jan {tl.valuation_year} growth-bucket value "
        "after the bill top-up. "
        f"Glide path {'on' if a['glide_path.enabled'] else 'off'}.",
        "",
        md_table(_fmt_money_cols(pt, list(pt.columns[1:]))),
    ]

    # Ranges
    cr = cosponsor_ranges(res, a)
    crf = _fmt_money_cols(cr, ["Low", "High", "Low (real)", "High (real)"])
    for c in ["P(inside range)", "P(at or above low end)"]:
        crf[c] = cr[c].map(pct)
    lines += [
        "",
        f"## Candidate co-sponsor ranges (facility contribution, nominal, {rule_label(a)})",
        "",
        md_table(crf),
        "",
        f"Example co-sponsor range (method): **{rec['Range']} = {money(rec['Low'])} to {money(rec['High'])}**, "
        f"{pct(rec['P(at or above low end)'], 0)} confidence the contribution reaches the low end. "
        f"Both endpoints are rounded down to the nearest {money(a['reporting.range_rounding'])} so we never overstate: the "
        "low end is at or below the percentile it comes from and the top is at or below the median, so the chance of "
        "reaching the low end is at least the percentile's.",
        "",
        COSPONSOR_NOTE,
    ]

    # Stress tests
    st = stress[["scenario", "ladder_cost", "shortfall_from_2028", "topup_2033", "value_2033",
                 "facility_contribution", "all_bills_paid", "unpaid_bill_dollars", "unpaid_pct_of_cushion",
                 "unpaid_after_backstop", "backstop_left_2042", "rule_rate_needed"]].copy()
    st["all_bills_paid"] = st["all_bills_paid"].map({True: "yes", False: "NO"})
    st["unpaid_pct_of_cushion"] = st["unpaid_pct_of_cushion"].map(pct)
    st["rule_rate_needed"] = st["rule_rate_needed"].map(fmt_rate_needed)
    lines += [
        "",
        "## Stress tests (fixed paths)",
        "",
        md_table(_fmt_money_cols(st, ["ladder_cost", "shortfall_from_2028", "topup_2033", "value_2033",
                                      "facility_contribution", "unpaid_bill_dollars", "unpaid_after_backstop",
                                      "backstop_left_2042"])),
        "",
        f"value_2033 and facility contribution are after the Jan {tl.valuation_year} top-up ({rule_label(a)}). "
        "all_bills_paid: whole portfolio, no further help. unpaid_pct_of_cushion: unpaid bills as a share of "
        f"the cushion kept, growth bucket x (1 - give_pct). rule_rate_needed: highest reinvestment rate the "
        "rate rule can assume and still pay every bill on that path. unpaid_after_backstop / backstop_left_2042: "
        f"after the {money(a['waterfall.backstop_amount'])} backstop held from the client's cushion.",
    ]

    lr = low_rate_report(stress)
    if lr:
        lines += [
            "",
            f"### Low-rate stress: T-bills at 0.5% every year (2010s-style), {rule_label(a)}",
            "",
            f"- **All bills paid with no further help: {'yes' if lr['all_paid'] else 'NO'}.** "
            f"The rule moves {money(lr['moved'])} in Jan {vy}; {money(lr['needed'])} was needed.",
            f"- **Total shortfall: {money(lr['unpaid'])}** of unpaid bills (nominal, at the bill dates).",
        ]
        lines += [f"- {g['growth']} growth outcome: shortfall = **{pct(g['share'])}** of the {money(g['cushion'])} "
                  f"cushion kept (growth bucket x {pct(1 - a['facility.give_pct'], 0)})." for g in lr["by_growth"]]
        lines += [
            f"- **Reinvestment rate the rule would need: {fmt_rate_needed(lr['rate_needed'])}.** The rule pays "
            "every bill only if it assumes a rate no higher than what T-bills actually earn from "
            f"{vy}; at the {a['waterfall.rate_rule_rate']:.1%} default it under-funds the reserve.",
            "- Only T-bill rates are stressed here; the ladder is still bought at the sheet's yields.",
            f"- With the {money(a['waterfall.backstop_amount'])} backstop: "
            f"{'covered' if lr['backstop_covers'] else 'NOT covered'}. {money(lr['backstop'])} start + "
            f"{money(lr['backstop_interest'])} T-bill interest (0.5% a year from Jan {vy}) - "
            f"{money(lr['backstop_used'])} used = {money(lr['backstop_left'])} left after the Jan "
            f"{tl.bill_years[-1]} bill.",
        ]
    cb = combined_report(stress)
    if cb:
        lines += [
            "",
            f"### Combined stress: yields 2 pts lower at purchase AND T-bills at 0.5% every year, {rule_label(a)}",
            "",
            f"- Ladder costs {money(cb['ladder_cost'])}; {money(cb['shortfall_from_2028'])} comes out of the "
            f"{tl.contribution_year} contribution and there is no 2027 buffer. The rule moves {money(cb['moved'])} "
            f"in Jan {vy}; {money(cb['needed'])} was needed.",
            f"- **Shortfall before the backstop: {money(cb['unpaid'])}** of unpaid bills (nominal).",
            f"- **Backstop ({money(cb['backstop'])} from the cushion, in T-bills from Jan {vy}): "
            f"{'covers it' if cb['backstop_covers'] else 'does NOT cover it'}.** Used {money(cb['backstop_used'])}"
            + (f"; {money(cb['unpaid_after_backstop'])} still unpaid" if not cb['backstop_covers'] else "")
            + f". **Left over after the Jan {tl.bill_years[-1]} bill: {money(cb['backstop_left'])}**, returned to the client.",
            f"- Backstop arithmetic: {money(cb['backstop'])} start + {money(cb['backstop_interest'])} T-bill interest "
            f"(0.5% a year in this scenario, earned from Jan {vy}) - {money(cb['backstop_used'])} used = "
            f"{money(cb['backstop_left'])} left.",
        ]
        lines += [f"- **Facility contribution, {g['growth'].lower() if g['growth'] == 'Median' else g['growth']} "
                  f"growth: {money(g['facility'])}** ({money(g['facility_real'])} in Jan {a['inflation.base_year']} "
                  f"dollars); cushion kept {money(g['cushion'])}." for g in cb["by_growth"]]
        lines += [
            "- The bill shortfall equals the low-rate-only scenario: the rule sees the smaller reserve in "
            f"{vy} and moves more, so its only error is assuming {a['waterfall.rate_rule_rate']:.1%} reinvestment "
            "after that. The costlier ladder shows up as a smaller facility contribution instead.",
        ]

    # Sensitivity
    sv = sens[["case", "us_mean", "intl_mean", "p_all_bills_paid", "p_ladder_only", "topup_median",
               "facility_p10", "facility_p50", "facility_p90", "median_change_vs_base"]].copy()
    for c in ["us_mean", "intl_mean", "p_all_bills_paid", "p_ladder_only"]:
        sv[c] = sv[c].map(pct)
    sv["median_change_vs_base"] = sens["median_change_vs_base"].map(lambda v: f"{100 * v:+.1f}%")
    lines += [
        "",
        "## Sensitivity: expected stock return +/- 1 point, and Vanguard pessimistic",
        "",
        "Vanguard pessimistic (VCMM 6/30/2026): US 5.2%, intl developed 5.5%, EM 3.0% geometric, converted to "
        "arithmetic with the base-case volatilities and blended 75/25 for international.",
        "",
        md_table(_fmt_money_cols(sv, ["topup_median", "facility_p10", "facility_p50", "facility_p90"])),
        "",
        "## Assumptions",
        "",
        (f"**{len(ph)} of {len(a.values)} assumptions are placeholders (source: TODO) and must be sourced "
         "before these results are used with the client.**" if ph else
         f"All {len(a.values)} assumptions are sourced."),
        "",
        md_table(assumptions_table(a)),
        "",
        "## Method notes",
        "",
        "- All cash flows occur Jan 1. Each year's T-bill rate and stock return apply Jan 1 to Jan 1.",
        f"- Ladder cost = present value on Jan 1 {tl.purchase_year} of each rung's cash flows at (sheet YTM + one "
        f"parallel shift), {a['ladder.compounding_per_year']}x/year compounding, actual/{a['ladder.day_count_basis']} years. "
        "Repricing on the purchase date (not the sheet date) adds about 3 months of accretion at unchanged yields.",
        "- ETF rungs (and bond rungs in the face model) pay on the bill date; interest between maturity and the bill is ignored (conservative). "
        "In the cashflows model, bond coupons and principal earn the path's T-bill rate until the bill date.",
        "- A bill counts as paid only if it is paid in full. The top-up rule uses only information available "
        "on the valuation date; the perfect-foresight top-up (exact amount, using the path's future T-bill "
        "rates) is reported for reference only.",
        "- Stock returns are correlated lognormal with the configured arithmetic mean and volatility; "
        + ("stocks are rebalanced to target weights each January." if a["growth.rebalance_annually"]
           else "stocks are not rebalanced."),
        "- Stress tests use one fixed path; inputs a scenario does not set use their mean values.",
        "- Sensitivity runs reuse the same random shocks (common random numbers).",
        "",
    ]
    return "\n".join(lines)


# ----------------------------------------------------- option decision ----

def option_decision(a: Assumptions, out_dir) -> dict | None:
    """A2 vs A4 numbers for the 'why A2' line, from outputs/hardening_seeds.csv (run_hardening.py).
    None when that file is missing or was made from different inputs."""
    from pathlib import Path
    f = Path(out_dir) / "hardening_seeds.csv"
    if not f.exists():
        return None
    df = pd.read_csv(f)
    if "inputs_sha256" not in df or (df["inputs_sha256"] != a.inputs_fingerprint()).any() \
            or not {"A2", "A4"} <= set(df["key"]):
        return None
    seed = int(a["simulation.seed"])

    def on(key: str) -> dict:
        rows = df[df["key"] == key]
        main = rows[rows["seed"] == seed].iloc[0]
        worst = rows.loc[rows["spare"].idxmin()]
        return {"facility_median": float(main["facility_median"]), "cushion_free_median": float(main["cushion_free_median"]),
                "worst_seed": int(worst["seed"]), "spare": float(worst["spare"]), "spare_share": float(worst["spare_share"]),
                "fails": int(rows["fail_with_backstop"].sum()), "seeds": int(rows["seed"].nunique())}
    return {"A2": on("A2"), "A4": on("A4")}


def option_decision_line(d: dict) -> str:
    a2, a4 = d["A2"], d["A4"]
    extra = a4["facility_median"] - a2["facility_median"]
    return (f"Why A2 (1.0% rule, $10,000 backstop) stays official: A4 adds about {money(round(extra, -2))} to the median "
            f"facility but leaves less spare backstop room ({money(a4['spare'])} / {pct(a4['spare_share'], 1)} vs "
            f"{money(a2['spare'])} / {pct(a2['spare_share'], 1)} on the worst seed) and less free cushion for Laura "
            f"({money(a4['cushion_free_median'])} vs {money(a2['cushion_free_median'])}). We chose the safer option for "
            "client money.")


# ------------------------------------------------------------ end result ----

def _q(x: np.ndarray) -> dict:
    return {"median": float(np.median(x)), "p10": float(np.percentile(x, 10))}


def end_result_metrics(a: Assumptions, res: Results, seed_runs: list[dict]) -> dict:
    """Money in and money out for outputs/end_result.md, per path, so medians and bad cases of the
    totals are real paths, not sums of medians. All nominal dollars, not discounted.
    seed_runs: [{"seed", "n", "p_paid", "fails"}] for the official seed and the robustness seeds."""
    paid = res.bill_paid.sum(axis=1) + res.backstop_draw.sum(axis=1)            # portfolio + backstop
    free = res.cushion_kept - res.backstop_start
    leftover = res.cushion_release + res.backstop_left                          # unused reserve + unused backstop
    own = np.minimum(res.rung_payout, res.bill_paid).mean(axis=0)
    tl = res.timeline
    return {
        "money_in": {"ladder": float(a["plan.ladder_budget"]), "ladder_year": tl.purchase_year,
                     "growth": float(a["plan.growth_contribution"]), "growth_year": tl.contribution_year,
                     "total": float(a["plan.ladder_budget"]) + float(a["plan.growth_contribution"])},
        "bills": {"n": len(tl.bill_years), "amount": float(res.bill_amount), "first": tl.bill_years[0],
                  "last": tl.bill_years[-1], "total": float(res.bill_amount * len(tl.bill_years)),
                  "paid": _q(paid), "seeds": seed_runs},
        "facility": _q(res.facility),
        "cushion": {"total": _q(res.cushion_kept), "free": _q(free), "backstop": float(a["waterfall.backstop_amount"])},
        "leftover": {**_q(leftover), "reserve": _q(res.cushion_release), "backstop": _q(res.backstop_left)},
        "total_value": _q(paid + res.facility + free + leftover),
        "bill_sources": {"years": list(tl.bill_years), "own": own.tolist(),
                         "reserve": (res.bill_paid.mean(axis=0) - own).tolist(),
                         "backstop": res.backstop_draw.mean(axis=0).tolist(),
                         "backstop_used_share": float((res.backstop_used > 1e-6).mean()),
                         "backstop_used_median": float(np.median(res.backstop_used[res.backstop_used > 1e-6]))
                         if (res.backstop_used > 1e-6).any() else 0.0},
    }


def plain_words(text: str) -> str:
    """Scenario descriptions for non-specialist readers: percentiles in words."""
    return (text.replace("P10 stock returns", "bad-case (1 in 10) stock returns")
            .replace("P90 stock returns", "good-case (1 in 10) stock returns")
            .replace("median stock returns", "typical stock returns"))


def render_end_result(m: dict) -> str:
    """outputs/end_result.md, every number formatted from metrics.json (m)."""
    e = m["end_result"]
    b, mi = e["bills"], e["money_in"]
    seeds = b["seeds"]
    all_paid = all(s["fails"] == 0 for s in seeds)
    n = seeds[0]["n"]
    worst_paid = m["worst_backstop_covers"] or m["worst_unpaid"] <= 0
    lead = (f"Laura's {money(mi['total'])} pays all {b['n']} of her {money(b['amount'])} bills in every one "
            f"of {n:,} simulated futures (checked on {len(seeds)} separate runs) and gives the facility about "
            f"{money(round(e['facility']['median'], -3))} in {m['valuation_year']}; even in the worst case we tested, the "
            f"bills are {'still paid' if worst_paid else 'not all paid'} and the facility gets {money(m['worst_facility'])}."
            if all_paid else
            f"Laura's {money(mi['total'])} pays all {b['n']} bills in "
            f"{pct(min(s['p_paid'] for s in seeds), 2)} or more of {n:,} simulated futures and gives the facility about "
            f"{money(round(e['facility']['median'], -3))} in {m['valuation_year']}.")

    def row(label: str, q: dict, note: str = "") -> str:
        return f"| {label} | {money(q['median'])} | {money(q['p10'])} | {note} |"
    seed_txt = "; ".join(f"seed {s['seed']}: {pct(s['p_paid'], 2)} ({s['fails']:,} fail)" for s in seeds)
    lines = [
        "# End result", "",
        f"**{lead}**", "",
        "## Money in", "",
        f"- {money(mi['ladder'])} in {mi['ladder_year']} (bond ladder and cash buffer)",
        f"- {money(mi['growth'])} in {mi['growth_year']} (growth bucket)",
        f"- Total {money(mi['total'])}", "",
        "## Money out", "",
        f"Typical = median future; bad case = 1 in 10 futures does worse. {n:,} futures, nominal dollars "
        "(not adjusted for inflation or discounted).", "",
        "| | Typical | Bad case (1 in 10) | |",
        "|---|---|---|---|",
        row(f"Bills paid, {b['first']}–{b['last']} (of {money(b['total'])})", b["paid"],
            f"all bills paid on every seed: {seed_txt}"),
        row(f"Facility contribution, Jan {m['valuation_year']}", e["facility"],
            f"example co-sponsor range {money(m['range_low'])} to {money(m['range_high'])}"),
        row(f"Laura's cushion, Jan {m['valuation_year']} (not added to the total)", e["cushion"]["total"],
            f"includes the {money(e['cushion']['backstop'])} backstop, which is counted once below: what it pays is in "
            "bills paid, what is left is in the amount returned after the last bill"),
        row(f"Laura's free cushion after the {money(e['cushion']['backstop'])} backstop", e["cushion"]["free"], ""),
        row(f"Returned to Laura after {b['last']}", e["leftover"],
            f"unused reserve (typical {money(e['leftover']['reserve']['median'])}) + unused backstop with its T-bill "
            f"interest since {m['valuation_year']} (typical {money(e['leftover']['backstop']['median'])})"),
        row("**Total value delivered**", e["total_value"], "see the formula below"), "",
        "**Total value delivered = bills paid + facility contribution + Laura's free cushion + returned to Laura "
        "after the last bill**, added up future by future (so the typical total is a real future's total, not a sum "
        "of typical rows). Each dollar is counted once: the backstop is left out of the free cushion, and its "
        "unused part, with interest, is in the amount returned.", "",
        "## Worst stress case tested", "",
        f"{plain_words(m['worst_description']).rstrip('.')}: bills "
        + (f"paid in full (the backstop covers {money(m['worst_unpaid'])}, with {money(m['worst_backstop_left'])} left)"
           if worst_paid else f"short by {money(m['worst_unpaid_after_backstop'])} after the backstop")
        + f"; the facility receives {money(m['worst_facility'])}.", "",
        f"<!-- Generated {m['generated']} by run_simulation.py from outputs/metrics.json: seed {m['seed']}, "
        f"inputs sha256 {m['inputs_sha256'][:16]}. -->", "",
    ]
    return "\n".join(lines)
