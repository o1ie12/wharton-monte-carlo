"""Dense terminal tables for the dashboard's Desk screen: the ladder blotter (one row per bill,
like a positions blotter) and the stress matrix. Plain HTML, styled by the page's .tt classes."""
from __future__ import annotations

import html
from typing import Callable

import numpy as np
import pandas as pd

from . import analysis, growth
from .config import Assumptions
from .model import Ladder, Results, load_ladder, run_monte_carlo, simulate

# Plain names for the stress scenarios in config.yaml (the descriptions there have the detail).
STRESS_LABELS = {
    "good": "Good markets (P90 stocks)", "normal": "Markets as expected", "bad": "Weak markets (P10 stocks)",
    "zero_growth": "Stocks flat, 0% a year", "crash_2028": "Stocks -40% in 2028", "crash_2032": "Stocks -40% in 2032",
    "yields_down_1pt": "Yields 1 pt lower at purchase", "yields_down_2pt": "Yields 2 pts lower at purchase",
    "contribution_100k": "Only $100k invested in 2028", "low_rates_2010s": "Cash earns 0.5% (2010s)",
    "low_rates_2010s_p10": "Cash 0.5% + weak markets", "combined_low_rates": "Low yields + cash 0.5%",
    "combined_low_rates_p10": "Low yields + cash 0.5% + weak mkts",
}


def stress_label(name: str) -> str:
    return STRESS_LABELS.get(name, name.replace("_", " ").capitalize())


def instrument_label(ladder: Ladder, k: int) -> str:
    """IBTM for an ETF rung, "T 4.75% Feb '37" for a Treasury."""
    if not ladder.is_treasury[k]:
        return str(ladder.table["ticker_or_cusip"][k])
    m = ladder.maturity[k]
    return f"T {ladder.coupon[k] * 100:g}% {m:%b} '{m:%y}"


def blotter(ladder: Ladder, res: Results) -> pd.DataFrame:
    """One row per bill: what was bought, what it cost, what it pays across the simulated futures
    and how often it needs the 2033 top-up."""
    p5, p50, p95 = np.percentile(res.rung_payout, [5, 50, 95], axis=0)
    needs = (res.ladder_only_shortfall > 1e-6).mean(axis=0)
    status = ladder.table["data_status"].astype(str).str.upper().str.contains("ESTIMATE")
    return pd.DataFrame({
        "Bill": list(res.timeline.bill_years),
        "Instrument": [instrument_label(ladder, k) for k in range(ladder.n_rungs)],
        "Type": ladder.table["type"].astype(str).str.upper().tolist(),
        "Qty": ladder.quantity.astype(int),
        "Price": ladder.table["price"].astype(float).to_numpy(),
        "Cost": ladder.sheet_cost,
        "Payout P5": p5, "Payout P50": p50, "Payout P95": p95,
        "Top-up %": needs,
        "Px": np.where(status, "EST", "QUOTE"),
    })


def stress_matrix(stress: pd.DataFrame, mc_median: float) -> pd.DataFrame:
    """Every stress scenario in one grid: facility gift, its gap to the Monte Carlo median, the
    top-up, unpaid bill dollars before the safety net, and the result."""
    result = np.where(stress["all_bills_paid"], "PAID", np.where(stress["backstop_covers"], "NET", "SHORT"))
    return pd.DataFrame({
        "Scenario": [stress_label(n) for n in stress["scenario"]],
        "Facility": stress["facility_contribution"],
        "vs P50": stress["facility_contribution"] / mc_median - 1,
        "Top-up": stress["topup_2033"],
        "Unpaid pre-net": stress["unpaid_bill_dollars"],
        "Result": result,
        "_title": stress["description"],
    })


def table_html(df: pd.DataFrame, fmt: dict[str, Callable] | None = None,
               cls: dict[str, Callable] | None = None, left: tuple[str, ...] = (), wrap: tuple[str, ...] = ()) -> str:
    """HTML table: fmt maps column -> value formatter, cls maps column -> value -> CSS class.
    Columns in `left` are left-aligned (text), columns in `wrap` may wrap onto several lines;
    a "_title" column becomes each row's tooltip and a "_class" column its CSS class."""
    fmt, cls = fmt or {}, cls or {}
    cols = [c for c in df.columns if not c.startswith("_")]
    head = "".join(f'<th class="{"l" if c in left else ""}">{html.escape(c)}</th>' for c in cols)
    rows = []
    for _, r in df.iterrows():
        cells = []
        for c in cols:
            v = r[c]
            text = fmt[c](v) if c in fmt else html.escape(str(v))
            classes = " ".join(x for x in ("l" if c in left else "", "w" if c in wrap else "",
                                           cls[c](v) if c in cls else "") if x)
            cells.append(f'<td class="{classes}">{text}</td>')
        title = f' title="{html.escape(str(r["_title"]))}"' if "_title" in df.columns else ""
        row_cls = f' class="{r["_class"]}"' if "_class" in df.columns and r["_class"] else ""
        rows.append(f"<tr{title}{row_cls}>{''.join(cells)}</tr>")
    return f'<table class="tt"><thead><tr>{head}</tr></thead><tbody>{"".join(rows)}</tbody></table>'


# ------------------------------------------------------------- watchlist ----

def short_label(spec: dict) -> str:
    """'60% VTI / 40% VXUS · Vanguard' from the config label (caveats in brackets dropped)."""
    return spec["label"].split(" (")[0].replace(", Vanguard pessimistic returns", " · Vanguard")


def scenario_inputs(a: Assumptions, spec: dict) -> dict:
    """The dashboard inputs that reproduce a growth scenario: its mix and the two return means
    (official, or Vanguard pessimistic for the -V rows and G8)."""
    s = growth.scenario_assumptions(a, spec)
    return {"growth_mix.mix": dict(spec["mix"]), "growth.us_mean": float(s["growth.us_mean"]),
            "growth.intl_mean": float(s["growth.intl_mean"])}


def watchlist(a: Assumptions, n: int, bins: int = 24) -> pd.DataFrame:
    """Every growth scenario in config.yaml run on the official assumptions (same seed, n paths):
    facility gift median and P10, its gap to G1, bills paid, and a coarse histogram for a sparkline."""
    rows = []
    for spec in a["growth_mix.scenarios"]:
        r = run_monte_carlo(growth.scenario_assumptions(a, spec, n))
        rows.append({"Key": spec["key"], "Mix": short_label(spec), "Gift P50": float(np.median(r.facility)),
                     "Gift P10": float(np.percentile(r.facility, 10)), "Bills paid": float(r.all_paid_with_backstop.mean()),
                     "_facility": r.facility})
    df = pd.DataFrame(rows)
    base = float(df.loc[df["Key"] == "G1", "Gift P50"].iloc[0]) if (df["Key"] == "G1").any() else float(df["Gift P50"].iloc[0])
    df["vs G1"] = df["Gift P50"] / base - 1
    hi = float(np.percentile(np.concatenate(df["_facility"].to_list()), 99))       # one shared scale for every row
    df["Spread"] = [np.histogram(np.clip(f, 0, hi), bins=bins, range=(0, hi))[0].tolist() for f in df["_facility"]]
    return df.drop(columns="_facility")


def stress_growth_path(a: Assumptions, name: str) -> np.ndarray:
    """Growth bucket value each Jan 1 (contribution year to valuation year, before the top-up)
    on one stress scenario's fixed path."""
    ladder = load_ladder(a)
    sc = next(s for s in a["stress_tests.scenarios"] if s["name"] == name)
    return simulate(a, analysis.stress_draws(a, ladder, sc), ladder).growth_path[0]
