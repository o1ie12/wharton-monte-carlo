"""Reinvestment-risk sizing scenarios for the Treasury rungs (bills 6-10).

Nothing here changes the official ladder.csv: each scenario is a set of config
overrides (and, for STRIPS, a separate scenario sheet) run through the same model.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .analysis import (coverage_stats, ladder_stats, md_table, money, pct, recommended_range, run_stress_tests,
                       vanguard_overrides, worst_stress)
from .config import Assumptions
from .model import draw_random, load_ladder, run_monte_carlo, value_per_bond_at_bill


# ------------------------------------------------------------- diagnosis ----

def diagnose(a: Assumptions) -> dict:
    """Task 1: why bills 6-10 fall short when ladder + buffer pay alone."""
    ladder = load_ladder(a)
    res = run_monte_carlo(a)
    tl = res.timeline
    draws = draw_random(a, ladder, res.n, int(a["simulation.seed"]))
    tcol = {y: i for i, y in enumerate(tl.tbill_years)}
    settle = pd.Timestamp(a["plan.ladder_purchase_date"])
    flows = ladder.flows(settle, "cashflows")
    rows = []
    for k in np.flatnonzero(ladder.is_bond):
        face = ladder.quantity[k] * 1000
        coupons = float(flows[k].amounts.sum() - face)
        yrs = [tcol[y] for y in range(tl.purchase_year, tl.bill_years[k])]
        life_rate = np.prod(1 + draws.tbill[:, yrs], axis=1) ** (1 / len(yrs)) - 1
        sf = res.ladder_only_shortfall[:, k]
        rows.append({
            "Bill": k + 1,
            "Bond": ladder.table["security"][k].replace("US Treasury ", ""),
            "Bonds held": int(ladder.quantity[k]),
            "Face at maturity": face,
            "Coupons from Jan 2027": coupons,
            "Reinvestment interest needed for $50k": ladder.bill_amount[k] - face - coupons,
            "YTM": ladder.yields[k],
            "Payout if reinvested at YTM": ladder.quantity[k] * value_per_bond_at_bill(a, ladder, k, ladder.yields[k]),
            "Median simulated T-bill rate over life": float(np.median(life_rate)),
            "Rung payout, median": float(np.median(res.rung_payout[:, k])),
            "Rung payout, P10": float(np.percentile(res.rung_payout[:, k], 10)),
            "Share of paths short (ladder alone)": float((sf > 1e-6).mean()),
            "Shortfall, median (ladder alone)": float(np.median(sf)),
            "Shortfall, P10 outcome (ladder alone)": float(np.percentile(sf, 90)),
        })
    cases = {}
    for name, o in {"official": {},
                    "bonds pay exactly $50k": {"ladder.bond_payout_model": "face"},
                    "T-bills earn ~bond YTM (5.35%)": {"tbills.mean": 0.0535, "tbills.mean_by_year": {}}}.items():
        r = res if not o else run_monte_carlo(a.override(o))
        short = r.ladder_only_shortfall > 1e-6
        cases[name] = {"ladder_alone": float(r.ladder_only_all_paid.mean()),
                       "short_6_10": short[:, 5:].mean(axis=0).tolist(),
                       "any_1_5_short": float(short[:, :5].any(axis=1).mean())}
    return {"n": res.n, "rows": pd.DataFrame(rows), "cases": cases}


def diagnosis_markdown(d: dict) -> str:
    t = d["rows"].copy()
    money_cols = ["Face at maturity", "Coupons from Jan 2027", "Reinvestment interest needed for $50k",
                  "Payout if reinvested at YTM", "Rung payout, median", "Rung payout, P10",
                  "Shortfall, median (ladder alone)", "Shortfall, P10 outcome (ladder alone)"]
    for c in money_cols:
        t[c] = t[c].map(money)
    for c in ["YTM", "Median simulated T-bill rate over life", "Share of paths short (ladder alone)"]:
        t[c] = t[c].map(lambda v: pct(v, 2))
    c = d["cases"]
    lines = [
        "# Reinvestment diagnosis: Treasury rungs (bills 6-10)",
        "",
        f"{d['n']:,} paths, official settings. Ladder alone = ladder + buffer with no top-up and no backstop. "
        "\"P10 outcome\" = the 90th-percentile shortfall (bad tail).",
        "",
        md_table(t),
        "",
        "| Case | Ladder alone pays all bills | Bills 6-10 short (% of paths) | Any of bills 1-5 short |",
        "|---|---|---|---|",
    ]
    for name, v in c.items():
        lines.append(f"| {name} | {pct(v['ladder_alone'])} | " + " / ".join(pct(x) for x in v["short_6_10"])
                     + f" | {pct(v['any_1_5_short'])} |")
    lines += [
        "",
        "Reinvestment drives the bill 6-10 failures: when the bonds pay exactly $50k they are never short, "
        "and when T-bills earn about the bonds' YTM the failure rates collapse. The small remainder (bills 8 "
        "and 10 fall short even at their YTM) is sizing timing: ladder.csv sized them from the quote date, "
        "counting the Nov 2026 coupon, but the ladder is bought Jan 1 2027.",
        "",
        "Resizing bills 6-10 cannot lift \"ladder alone pays all bills\" above about "
        f"{pct(1 - c['official']['any_1_5_short'], 0)}: an iBonds bill (1-5) is already short on "
        f"{pct(c['official']['any_1_5_short'])} of paths (placeholder iBonds payout error plus a thin buffer).",
        "",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------- sizing runs ----

def scenario_specs(a: Assumptions, strips_sheet: str | None = None) -> list[dict]:
    """A = official ladder.csv as is; B-E = Treasury rungs resized at each sizing rate;
    F (optional) = rungs 6-10 swapped for STRIPS via a separate scenario sheet."""
    specs = [{"key": "A", "label": "A (official): each bond's own YTM, sized from Jan 2027", "overrides": {}}]
    for key, rate in a["scenarios.sizing_rates"].items():
        specs.append({"key": key, "label": f"{key}: sized at {rate:.1%}",
                      "overrides": {"ladder.sizing_reinvest_rate": float(rate)}})
    if strips_sheet:
        specs.append({"key": "F", "label": "F: STRIPS for rungs 6-10",
                      "overrides": {"ladder.csv_path": str(strips_sheet)}, "estimate": True})
    active = a.values.get("scenarios.active")
    return [s for s in specs if active is None or s["key"] in active]


def budget_check(a: Assumptions, ladder_cost: float) -> dict:
    """SGOV buffer left after buying the ladder at current prices, keeping the cash reserve
    and paying fees. A negative buffer means the scenario does not fit the budget."""
    sgov = float(a["scenarios.budget"]) - ladder_cost - float(a["scenarios.cash_reserve"]) - float(a["scenarios.fees"])
    return {"sgov_buffer": sgov, "fits_budget": sgov >= 0, "over_budget_by": max(-sgov, 0.0)}


def run_sizing_scenario(a: Assumptions, spec: dict, base_cost: float) -> dict:
    s = a.override(spec["overrides"])
    ladder = load_ladder(s)
    cost = float(ladder.sheet_cost.sum())
    budget = budget_check(a, cost)
    res = run_monte_carlo(s)
    ls, cs = ladder_stats(res), coverage_stats(res)
    rec = recommended_range(res, s)
    w = worst_stress(run_stress_tests(s))
    return {
        "key": spec["key"], "label": spec["label"], "estimate": bool(spec.get("estimate")),
        "n_sims": res.n,
        "quantities_6_10": [int(q) for q in ladder.quantity[5:]],
        "extra_cost": cost - base_cost,
        "ladder_cost": cost,
        **budget,
        "ladder_alone": ls["p_ladder_only"],
        "coverage_median": cs["coverage_median"], "coverage_p10": cs["coverage_p10"],
        "coverage_worst": cs["coverage_worst"],
        "topup_median": ls["topup_median"], "topup_p90": ls["topup_p90"],
        "all_paid_with_backstop": ls["p_all_paid_with_backstop"],
        "all_paid_without_backstop": ls["p_all_paid"],
        "facility_median": float(np.median(res.facility)),
        "range_low": rec["Low"], "range_high": rec["High"],
        "worst_stress": str(w["scenario"]),
        "worst_stress_shortfall": float(w["unpaid_bill_dollars"]),
        "worst_stress_backstop_left": float(w["backstop_left_2042"]),
        **vanguard_metrics(s),
    }


def vanguard_metrics(s: Assumptions) -> dict:
    """The same scenario under the Vanguard pessimistic stock returns."""
    v = s.override(vanguard_overrides(s))
    res = run_monte_carlo(v)
    ls = ladder_stats(res)
    rec = recommended_range(res, v)
    return {"vg_all_paid_with_backstop": ls["p_all_paid_with_backstop"],
            "vg_all_paid_without_backstop": ls["p_all_paid"],
            "vg_facility_median": float(np.median(res.facility)),
            "vg_facility_p10": float(np.percentile(res.facility, 10)),
            "vg_range_low": rec["Low"], "vg_range_high": rec["High"]}


def run_sizing_scenarios(a: Assumptions, strips_sheet: str | None = None) -> list[dict]:
    base_cost = float(load_ladder(a).sheet_cost.sum())
    return [run_sizing_scenario(a, spec, base_cost) for spec in scenario_specs(a, strips_sheet)]


# ---------------------------------------------------------------- STRIPS ----

STRIPS_NOTE = "ESTIMATE, STRIPS availability in WInS unconfirmed."
PAR_TENORS = {"6 Mo": 0.5, "1 Yr": 1, "2 Yr": 2, "3 Yr": 3, "5 Yr": 5, "7 Yr": 7, "10 Yr": 10,
              "20 Yr": 20, "30 Yr": 30}


def load_par_curve(path) -> tuple[pd.Timestamp, dict[float, float]]:
    """Treasury daily par yield curve (home.treasury.gov CSV row): {tenor years: yield}."""
    row = pd.read_csv(path).iloc[0]
    return pd.Timestamp(row["Date"]), {t: float(row[c]) / 100 for c, t in PAR_TENORS.items()}


def bootstrap_spot_rates(par: dict[float, float], max_years: float = 30.0) -> tuple[np.ndarray, np.ndarray]:
    """Semiannual zero-coupon (spot) rates from a par curve.

    Par yields are interpolated linearly at every half-year; a par bond prices at 100, so
    100 = sum_{i<n} (c/2) DF_i + (100 + c/2) DF_n gives each discount factor DF_n in turn,
    and the spot rate is s_n = 2 (DF_n^(-1/n) - 1), semiannual bond-equivalent.
    """
    tenors = np.array(sorted(par))
    yields = np.array([par[t] for t in tenors])
    t = np.arange(1, int(max_years * 2) + 1) / 2.0
    c = np.interp(t, tenors, yields)
    df = np.empty_like(t)
    for n in range(len(t)):
        df[n] = (1 - c[n] / 2 * df[:n].sum()) / (1 + c[n] / 2)
    spot = 2 * (df ** (-1 / (2 * t)) - 1)
    return t, spot


def strips_quote(curve_date: pd.Timestamp, par: dict[float, float], maturity: pd.Timestamp,
                 basis: float = 365.25) -> tuple[float, float]:
    """(price per 100, spot yield) for a STRIPS maturing on `maturity`, priced on curve_date:
    spot rate interpolated linearly in time, price = 100 / (1 + s/2)^(2t)."""
    t_nodes, spot = bootstrap_spot_rates(par)
    years = (maturity - curve_date).days / basis
    s = float(np.interp(years, t_nodes, spot))
    return 100.0 / (1 + s / 2) ** (2 * years), s


def build_strips_sheet(a: Assumptions, curve_csv, out_path, face_per_rung: float = 50_000) -> pd.DataFrame:
    """Scenario F: the official sheet with each Treasury coupon-bond rung replaced by a STRIPS
    maturing Nov 15 of the year before its bill, sized to $50,000 face."""
    curve_date, par = load_par_curve(curve_csv)
    sheet = pd.read_csv(a.path("ladder.csv_path"), dtype={"price_date": str})
    qty = int(round(face_per_rung / 1000))
    for i, r in sheet.iterrows():
        if str(r["type"]).strip().lower() != "bond":
            continue
        mat = pd.Timestamp(year=int(str(r["bill_date"])[:4]) - 1, month=11, day=15)
        price, spot = strips_quote(curve_date, par, mat, float(a["ladder.day_count_basis"]))
        sheet.loc[i, ["security", "ticker_or_cusip", "type", "maturity_date", "price_date"]] = [
            f"Treasury STRIPS (principal) Nov 15 {mat.year}", "TBD", "STRIPS", mat.date().isoformat(),
            curve_date.date().isoformat()]
        sheet.loc[i, ["price", "accrued_per_100", "ytm", "quantity"]] = [round(price, 4), 0.0, round(spot, 6), qty]
        sheet.loc[i, "rung_cost"] = round(qty * round(price, 4) * 10, 2)
        sheet.loc[i, "data_status"] = (f"{STRIPS_NOTE} Priced from the Treasury par yield curve of "
                                       f"{curve_date.date().isoformat()} (bootstrapped zero rate).")
    sheet.to_csv(out_path, index=False)
    return sheet


# ---------------------------------------------------------------- report ----

def sizing_markdown(a: Assumptions, rows: list[dict], any_1_5_short: float, curve_date: str | None) -> str:
    """outputs/sizing_scenarios.md: one table (A-F) and at most three sentences, every number
    taken from `rows`."""
    mark = lambda r, text: f"{text} †" if r["estimate"] else text        # noqa: E731
    header = ["Scenario", "Bonds, rungs 6-10", "Extra cost vs A", "Ladder cost", "SGOV buffer", "Fits $300k?",
              "Ladder alone pays all", "Coverage median / P10 / worst", "Top-up median / P90",
              "All paid with / without backstop", "Median facility", "Co-sponsor range",
              "Worst stress shortfall / backstop left", "Vanguard pessimistic: median / P10 facility",
              "Vanguard pessimistic: co-sponsor range", "Vanguard pessimistic: all paid with / without backstop"]
    lines = [
        "# Treasury rung sizing scenarios (reinvestment risk)",
        "",
        f"{rows[0]['n_sims']:,} paths per scenario, same seed. Scenarios never modify ladder.csv: A is the official "
        "sheet, B-E are config overrides, F is a separate scenario sheet. Costs use current clean price + accrued; "
        f"SGOV buffer = {money(a['scenarios.budget'])} budget - ladder cost - {money(a['scenarios.cash_reserve'])} "
        f"cash - {money(a['scenarios.fees'])} fees. Ladder alone = no top-up, no backstop.",
        "",
        "| " + " | ".join(header) + " |",
        "|" + "|".join(["---"] * len(header)) + "|",
    ]
    for r in rows:
        cells = [
            r["label"] + (" (" + STRIPS_NOTE + ")" if r["estimate"] else ""),
            mark(r, "STRIPS 50k face each" if r["estimate"] else "/".join(str(q) for q in r["quantities_6_10"])),
            mark(r, money(r["extra_cost"]) if r["key"] != "A" else "-"),
            mark(r, money(r["ladder_cost"])),
            mark(r, money(r["sgov_buffer"])),
            mark(r, "yes" if r["fits_budget"] else f"**NO** (over by {money(r['over_budget_by'])})"),
            mark(r, pct(r["ladder_alone"])),
            mark(r, f"{pct(r['coverage_median'], 2)} / {pct(r['coverage_p10'], 2)} / {pct(r['coverage_worst'], 2)}"),
            mark(r, f"{money(r['topup_median'])} / {money(r['topup_p90'])}"),
            mark(r, f"{pct(r['all_paid_with_backstop'], 2)} / {pct(r['all_paid_without_backstop'], 2)}"),
            mark(r, money(r["facility_median"])),
            mark(r, f"{money(r['range_low'])} - {money(r['range_high'])}"),
            mark(r, f"{money(r['worst_stress_shortfall'])} / {money(r['worst_stress_backstop_left'])}"),
            mark(r, f"{money(r['vg_facility_median'])} / {money(r['vg_facility_p10'])}"),
            mark(r, f"{money(r['vg_range_low'])} - {money(r['vg_range_high'])}"),
            mark(r, f"{pct(r['vg_all_paid_with_backstop'], 2)} / {pct(r['vg_all_paid_without_backstop'], 2)}"),
        ]
        lines.append("| " + " | ".join(cells) + " |")
    if any(r["estimate"] for r in rows):
        lines += ["", f"† {STRIPS_NOTE} STRIPS priced from the Treasury par yield curve of {curve_date} "
                      "(bootstrapped zero rates); rungs 6-10 swapped for STRIPS maturing Nov 15 of the year before "
                      "each bill, $50,000 face each."]
    lines += ["", " ".join(recommendation_sentences(rows, any_1_5_short)), ""]
    return "\n".join(lines)


def recommendation_sentences(rows: list[dict], any_1_5_short: float) -> list[str]:
    """Three sentences, all numbers from `rows`. Lays out the options; does not choose."""
    by = {r["key"]: r for r in rows}
    a = by["A"]
    name = lambda r: r["key"] + (" (STRIPS, estimate)" if r["estimate"] else "")       # noqa: E731
    ok = sorted((r for r in rows if r["ladder_alone"] >= 0.90), key=lambda r: r["ladder_cost"])
    if ok:
        pick = ok[0]
        s1 = f"The cheapest scenario where the ladder alone pays all bills on at least 90% of paths is {name(pick)}."
    else:
        best = max(rows, key=lambda r: r["ladder_alone"])
        fitting = [r for r in rows if r["fits_budget"]]
        pick = max(fitting, key=lambda r: r["ladder_alone"]) if fitting else best
        s1 = (f"No scenario reaches 90% for \"ladder alone pays all bills\" (best: {name(best)} at "
              f"{pct(best['ladder_alone'])}), because an iBonds bill (1-5) is already short on "
              f"{pct(any_1_5_short)} of paths, which no change to rungs 6-10 can fix.")
    def effect(r):
        cost = (f"costs {money(r['extra_cost'])} more than A" if r["extra_cost"] >= 0
                else f"costs {money(-r['extra_cost'])} less than A")
        fac = r["facility_median"] - a["facility_median"]
        return (f"{cost}, takes the SGOV buffer from {money(a['sgov_buffer'])} to {money(r['sgov_buffer'])}, "
                f"moves ladder-alone success from {pct(a['ladder_alone'])} to {pct(r['ladder_alone'])}, and "
                f"{'raises' if fac >= 0 else 'lowers'} the median facility contribution by {money(abs(fac))}")
    bonds = [r for r in rows if r["fits_budget"] and not r["estimate"] and r["key"] != "A"]
    best_bond = max(bonds, key=lambda r: r["ladder_alone"]) if bonds else None
    lead = ("It" if ok else f"The best option within budget, {name(pick)}," if pick["fits_budget"]
            else f"No scenario fits the budget; the best, {name(pick)},")
    s2 = (f"{lead} {effect(pick)}"
          + (f"; the best confirmed-price option, {name(best_bond)}, {effect(best_bond)}"
             if best_bond is not None and best_bond is not pick else "") + ".")
    weak = [r for r in rows if not r["fits_budget"]
            and any(o["ladder_cost"] < r["ladder_cost"] and o["ladder_alone"] >= r["ladder_alone"] for o in rows)]
    if weak:
        worst = max(weak, key=lambda r: r["extra_cost"])
        s3 = (f"{', '.join(name(r) for r in weak)} {'is' if len(weak) == 1 else 'are'} over budget and "
              f"{'does' if len(weak) == 1 else 'do'} no better on ladder-alone than a cheaper option: the extra bonds "
              f"use up the 2027 buffer, and without the backstop all bills are paid on only "
              f"{pct(worst['all_paid_without_backstop'])} of paths in {name(worst)}, because the rate rule then "
              f"moves nothing and small iBonds misses go unpaid.")
    else:
        s3 = "No scenario is both over budget and dominated by a cheaper one."
    return [s1, s2, s3]


# ------------------------------------------------------- hardening of A ----

# Round 4c: ways to make scenario A robust to persistent low T-bill rates, each spelled out
# in full so the comparison does not depend on the official config. A2 (1.0% rule, $10k
# backstop) became official on Oct 13 2026.
HARDENING_OPTIONS = [
    {"key": "A0", "label": "2% rule, $10k backstop (official until Oct 13)",
     "overrides": {"waterfall.rate_rule_rate": 0.02, "waterfall.backstop_amount": 10_000}},
    {"key": "A1", "label": "rule assumes 1.5%",
     "overrides": {"waterfall.rate_rule_rate": 0.015, "waterfall.backstop_amount": 10_000}},
    {"key": "A2", "label": "rule assumes 1.0% (official)",
     "overrides": {"waterfall.rate_rule_rate": 0.010, "waterfall.backstop_amount": 10_000}},
    {"key": "A3", "label": "backstop $12,500 (2% rule)",
     "overrides": {"waterfall.rate_rule_rate": 0.02, "waterfall.backstop_amount": 12_500}},
    {"key": "A4", "label": "rule assumes 1.5% + backstop $12,500",
     "overrides": {"waterfall.rate_rule_rate": 0.015, "waterfall.backstop_amount": 12_500}},
]


def option_assumptions(a: Assumptions, option: dict, n: int | None = None) -> Assumptions:
    s = a.override(option["overrides"])
    return s.override({"simulation.n_sims": int(n)}) if n is not None else s


def run_hardening_option(a: Assumptions, option: dict, n: int) -> dict:
    s = option_assumptions(a, option, n)
    res = run_monte_carlo(s)
    ls = ladder_stats(res)
    rec = recommended_range(res, s)
    w = worst_stress(run_stress_tests(s))
    cushion = res.cushion_kept
    return {
        "key": option["key"], "label": option["label"], "n_sims": res.n,
        "rate_rule_rate": float(s["waterfall.rate_rule_rate"]),
        "backstop_amount": float(s["waterfall.backstop_amount"]),
        "all_paid_with_backstop": ls["p_all_paid_with_backstop"],
        "all_paid_without_backstop": ls["p_all_paid"],
        "fail_with_backstop": int((~res.all_paid_with_backstop).sum()),
        "max_shortfall_with_backstop": float(res.unpaid_after_backstop.max()),
        "max_shortfall_without_backstop": float(res.unpaid.max()),
        "topup_median": ls["topup_median"], "topup_p90": ls["topup_p90"],
        "facility_median": float(np.median(res.facility)),
        "range_low": rec["Low"], "range_high": rec["High"],
        "cushion_median": float(np.median(cushion)),
        "cushion_free_median": float(np.median(cushion - res.backstop_start)),
        "worst_stress": str(w["scenario"]),
        "worst_stress_shortfall": float(w["unpaid_bill_dollars"]),
        "worst_stress_backstop_left": float(w["backstop_left_2042"]),
        "worst_stress_unpaid_after_backstop": float(w["unpaid_after_backstop"]),
    }


def hardening_markdown(rows: list[dict]) -> str:
    base = rows[0]
    header = ["Option", "Rule rate / backstop", "All paid with / without backstop", "Paths failing with backstop",
              "Max shortfall with / without backstop", "Top-up median / P90", "Median facility (vs A0)",
              "Co-sponsor range", "Laura's median cushion (free after backstop)", "Worst stress shortfall / backstop left"]
    lines = ["# Hardening scenario A against persistent low T-bill rates", "",
             f"{base['n_sims']:,} paths per option, same seed, official settings otherwise (AR(1) T-bills, iBonds "
             "margin). Laura's cushion = growth bucket after the top-up x (1 - give_pct); the backstop is set aside "
             "from it and returned after the last bill. Official config.yaml is unchanged.", "",
             "| " + " | ".join(header) + " |", "|" + "|".join(["---"] * len(header)) + "|"]
    for r in rows:
        dfac = r["facility_median"] - base["facility_median"]
        lines.append("| " + " | ".join([
            f"{r['key']}: {r['label']}", f"{pct(r['rate_rule_rate'])} / {money(r['backstop_amount'])}",
            f"{pct(r['all_paid_with_backstop'], 2)} / {pct(r['all_paid_without_backstop'], 2)}",
            f"{r['fail_with_backstop']:,}",
            f"{money(r['max_shortfall_with_backstop'])} / {money(r['max_shortfall_without_backstop'])}",
            f"{money(r['topup_median'])} / {money(r['topup_p90'])}",
            f"{money(r['facility_median'])} ({'+' if dfac >= 0 else '-'}{money(abs(dfac))})",
            f"{money(r['range_low'])} - {money(r['range_high'])}",
            f"{money(r['cushion_median'])} ({money(r['cushion_free_median'])})",
            f"{money(r['worst_stress_shortfall'])} / {money(r['worst_stress_backstop_left'])}",
        ]) + " |")
    lines += ["", " ".join(hardening_sentences(rows)), ""]
    return "\n".join(lines)


def hardening_sentences(rows: list[dict]) -> list[str]:
    """Facts only, numbers from `rows`; no option is recommended. 'Pays every bill' means no path
    fails with the backstop."""
    n = rows[0]["n_sims"]
    ok = [r for r in rows if r["fail_with_backstop"] == 0]
    short = [r for r in rows if r["fail_with_backstop"] > 0]
    if not ok:
        return [f"No option pays every bill on all {n:,} paths with the backstop; paths failing: "
                + ", ".join(f"{r['key']} {r['fail_with_backstop']:,}" for r in rows) + "."]
    s1 = (f"With the backstop, {len(ok)} of {len(rows)} options pay every bill on all {n:,} paths: "
          + ", ".join(f"{r['key']} ({r['label']})" for r in ok) + ".")
    s2 = ("Among them, median facility contribution and Laura's median free cushion after the backstop: "
          + "; ".join(f"{r['key']} {money(r['facility_median'])} and {money(r['cushion_free_median'])}" for r in ok) + ".")
    s3 = ("Paths failing with the backstop for the others: "
          + ", ".join(f"{r['key']} {r['fail_with_backstop']:,}" for r in short) + ".") if short else ""
    return [x for x in (s1, s2, s3) if x]


def hardening_seed_check(a: Assumptions, keys: list[str], seeds: list[int], n: int) -> list[dict]:
    """Each option in `keys` on each seed: largest backstop draw, spare backstop room ($ and share of
    the backstop), median facility contribution and Laura's median free cushion after the backstop."""
    rows = []
    for option in [o for o in HARDENING_OPTIONS if o["key"] in keys]:
        s = option_assumptions(a, option, n)
        backstop = float(s["waterfall.backstop_amount"])
        for seed in seeds:
            res = run_monte_carlo(s, seed=seed)
            draw = float(res.backstop_used.max())
            rows.append({"key": option["key"], "label": option["label"], "seed": seed, "n_sims": res.n,
                         "backstop_amount": backstop, "fail_with_backstop": int((~res.all_paid_with_backstop).sum()),
                         "max_backstop_draw": draw, "spare": backstop - draw, "spare_share": (backstop - draw) / backstop,
                         "facility_median": float(np.median(res.facility)),
                         "cushion_free_median": float(np.median(res.cushion_kept - res.backstop_start))})
    return rows


def hardening_seed_markdown(rows: list[dict]) -> str:
    """Table of hardening_seed_check rows, plus each option's worst seed (facts only)."""
    header = ["Option", "Seed", "Paths failing with backstop", "Largest backstop draw", "Spare backstop room",
              "Median facility", "Laura's median free cushion"]
    lines = [f"## {' vs '.join(dict.fromkeys(r['key'] for r in rows))} on {len({r['seed'] for r in rows})} seeds",
             "", f"{rows[0]['n_sims']:,} paths per seed. Spare room = backstop minus the largest draw on any path. "
             "Free cushion = Laura's cushion minus the backstop held until the last bill.", "",
             "| " + " | ".join(header) + " |", "|" + "|".join(["---"] * len(header)) + "|"]
    for r in rows:
        lines.append("| " + " | ".join([
            f"{r['key']}: {money(r['backstop_amount'])} backstop", str(r["seed"]), f"{r['fail_with_backstop']:,}",
            money(r["max_backstop_draw"]), f"{money(r['spare'])} ({pct(r['spare_share'], 1)})",
            money(r["facility_median"]), money(r["cushion_free_median"])]) + " |")
    lines.append("")
    for key in dict.fromkeys(r["key"] for r in rows):
        mine = [r for r in rows if r["key"] == key]
        worst = max(mine, key=lambda r: r["max_backstop_draw"])
        lines.append(f"- {key}: largest draw on any seed {money(worst['max_backstop_draw'])} (seed {worst['seed']}), "
                     f"leaving {money(worst['spare'])} ({pct(worst['spare_share'], 1)}) of the "
                     f"{money(worst['backstop_amount'])} backstop; paths failing with the backstop on all seeds: "
                     f"{sum(r['fail_with_backstop'] for r in mine):,}.")
    return "\n".join(lines) + "\n"
