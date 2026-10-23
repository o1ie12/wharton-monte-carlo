"""Growth-bucket mix scenarios (round 5): what each stock mix does to the facility money
and to the bills. Scenarios are config overrides; the official config is unchanged.

The model steps one year at a time. For drawdowns (and the 2x leveraged fund) the growth
bucket is also walked month by month: each asset's annual log return is split into 12
monthly log returns by a Brownian bridge, so the months compound back to exactly the annual
return the main model uses. Monthly shocks are correlated across assets like the annual ones.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from matplotlib.figure import Figure

from . import plots
from .analysis import ladder_stats, money, pct, recommended_range, vanguard_overrides
from .config import Assumptions, parse_fraction
from .model import (MONTHS, Draws, draw_random, extra_normals, growth_log_corr, growth_mix,
                    leveraged_monthly_returns, load_ladder, make_timeline, monthly_log_returns, simulate,
                    stock_log_params)


def scenario_assumptions(a: Assumptions, spec: dict, n: int | None = None) -> Assumptions:
    s = a.override({"growth_mix.mix": dict(spec["mix"])})
    if spec.get("returns") == "vanguard":
        s = s.override(vanguard_overrides(s))
    return s.override({"simulation.n_sims": int(n)}) if n is not None else s


def monthly_bucket_values(a: Assumptions, draws: Draws, seed: int, contribution: np.ndarray) -> np.ndarray:
    """Growth-bucket value at each month end from the contribution date to the valuation date
    (before the 2033 top-up). Shape (n, 12 * G + 1). `contribution` is the amount that actually
    goes in (Results.growth_contribution: the 2028 contribution less any ladder overrun). Same
    January rebalancing and glide-path moves as the annual model."""
    ladder = load_ladder(a)
    tl = make_timeline(a, ladder)
    n, G = draws.us.shape
    _, bridge = extra_normals(seed, n, G)
    shocks = bridge @ np.linalg.cholesky(growth_log_corr(a)).T          # correlated monthly shocks
    p = stock_log_params(a)
    tcol = [tl.tbill_years.index(y) for y in tl.growth_years]
    tbill = draws.tbill[:, tcol]                                          # (n, G)

    mix = growth_mix(a)
    monthly = {}                                                          # asset -> (n, G, 12) growth factors
    if "us" in mix or "us_2x" in mix:
        us_m = np.expm1(monthly_log_returns(np.log1p(draws.us), p["s_us"], shocks[..., 0]))
        monthly["us"] = 1.0 + us_m
        if "us_2x" in mix:
            monthly["us_2x"] = 1.0 + leveraged_monthly_returns(
                us_m, tbill, float(a["growth_mix.us_2x_multiple"]), float(a["growth_mix.us_2x_fee"]))
    if "intl" in mix:
        monthly["intl"] = np.exp(monthly_log_returns(np.log1p(draws.intl), p["s_intl"], shocks[..., 1]))
    if "small_cap" in mix:
        from .model import lognormal_params
        _, s_sc = lognormal_params(a["growth_mix.small_cap_mean"], a["growth_mix.small_cap_vol"])
        monthly["small_cap"] = np.exp(monthly_log_returns(np.log1p(draws.extra["small_cap"]), s_sc, shocks[..., 2]))
    tbill_m = (1.0 + tbill) ** (1.0 / MONTHS)                            # (n, G)

    glide = {}
    if a["glide_path.enabled"]:
        glide = {int(s["year"]): parse_fraction(s["fraction_of_stocks"]) for s in a["glide_path.steps"]}
    stock_w = {k: w for k, w in mix.items() if k != "tbills" and w > 0}
    total_w = sum(stock_w.values())
    hold = {k: w * contribution for k, w in stock_w.items()}
    tbills = mix.get("tbills", 0.0) * contribution
    values = [np.asarray(contribution, float).copy()]
    for g, year in enumerate(tl.growth_years):
        stocks = sum(hold.values())
        if a["growth.rebalance_annually"] and total_w > 0:
            hold = {k: (w / total_w) * stocks for k, w in stock_w.items()}
        f = glide.get(year, 0.0)
        if f:
            hold = {k: v * (1 - f) for k, v in hold.items()}
            tbills = tbills + f * stocks
        for m in range(MONTHS):
            hold = {k: v * monthly[k][:, g, m] for k, v in hold.items()}
            tbills = tbills * tbill_m[:, g]
            values.append(sum(hold.values()) + tbills)
    return np.column_stack(values)


def max_drawdown(values: np.ndarray) -> np.ndarray:
    """Largest peak-to-trough fall along each path (0.25 = fell 25% from its high)."""
    peak = np.maximum.accumulate(values, axis=1)
    return (1.0 - values / peak).max(axis=1)


def run_growth_scenario(a: Assumptions, spec: dict, n: int, with_drawdown: bool = True) -> dict:
    s = scenario_assumptions(a, spec, n)
    ladder = load_ladder(s)
    seed = int(s["simulation.seed"])
    draws = draw_random(s, ladder, n, seed)
    res = simulate(s, draws, ladder)
    ls = ladder_stats(res)
    rec = recommended_range(res, s)
    fac = res.facility
    row = {
        "key": spec["key"], "label": spec["label"], "n_sims": res.n, "mix": dict(spec["mix"]),
        "returns": spec.get("returns", "official"),
        "facility_median": float(np.median(fac)), "facility_p10": float(np.percentile(fac, 10)),
        "facility_p5": float(np.percentile(fac, 5)), "facility_worst": float(fac.min()),
        "p_bucket_below_150k": float((res.value_before_topup < float(s["plan.growth_contribution"])).mean()),
        "p_topup_not_fully_funded": float(res.rule_capped.mean()),
        "n_topup_not_fully_funded": int(res.rule_capped.sum()),
        "n_fail_with_backstop": int((~res.all_paid_with_backstop).sum()),
        "n_facility_zero": int((fac <= 0.5).sum()),
        "all_paid_with_backstop": ls["p_all_paid_with_backstop"],
        "all_paid_without_backstop": ls["p_all_paid"],
        "cushion_median": float(np.median(res.cushion_kept)),
        "cushion_p10": float(np.percentile(res.cushion_kept, 10)),
        "range_low": rec["Low"], "range_high": rec["High"],
    }
    if with_drawdown:
        dd = max_drawdown(monthly_bucket_values(s, draws, seed, res.growth_contribution))
        row["drawdown_median"] = float(np.median(dd))
        row["drawdown_p10_outcome"] = float(np.percentile(dd, 90))
    return row


def growth_scenarios(a: Assumptions) -> list[dict]:
    return list(a["growth_mix.scenarios"])


def run_growth_scenarios(a: Assumptions, n: int | None = None) -> list[dict]:
    n = int(n or a["simulation.n_sims"])
    return [run_growth_scenario(a, spec, n) for spec in growth_scenarios(a)]


# ---------------------------------------------------------------- report ----

def growth_markdown(rows: list[dict]) -> str:
    header = ["Scenario", "Facility median / P10 / P5 / worst", "Bucket < $150k in Jan 2033",
              "Max drawdown 2028-33: median / P10 outcome", "2033 top-up not fully funded",
              "All bills paid with / without backstop", "Laura's cushion median / P10", "Co-sponsor range"]
    lines = ["# Growth-bucket mix scenarios", "",
             f"{rows[0]['n_sims']:,} paths per scenario, official seed and the same random draws in every scenario. "
             "Everything else is official: ladder, AR(1) T-bills, 1.0% top-up rule with iBonds margin, $10k "
             "backstop, glide path (1/3 to T-bills in 2031, half the rest in 2032), 75/25 facility/cushion split. "
             "Drawdowns use month-end values of the growth bucket (annual returns split into months by a "
             "Brownian bridge); \"P10 outcome\" = the 90th-percentile drawdown. VTI = J.P. Morgan U.S. Large Cap, "
             "VXUS = 75/25 EAFE/EM blend.", "",
             "| " + " | ".join(header) + " |", "|" + "|".join(["---"] * len(header)) + "|"]
    for r in rows:
        lines.append("| " + " | ".join([
            f"{r['key']}: {r['label']}",
            f"{money(r['facility_median'])} / {money(r['facility_p10'])} / {money(r['facility_p5'])} / "
            f"{money(r['facility_worst'])}",
            pct(r["p_bucket_below_150k"]),
            f"{pct(r['drawdown_median'])} / {pct(r['drawdown_p10_outcome'])}",
            f"{pct(r['p_topup_not_fully_funded'], 2)} ({r['n_topup_not_fully_funded']:,} paths)",
            f"{pct(r['all_paid_with_backstop'], 2)} ({r['n_fail_with_backstop']:,} paths fail) / "
            f"{pct(r['all_paid_without_backstop'], 2)}",
            f"{money(r['cushion_median'])} / {money(r['cushion_p10'])}",
            f"{money(r['range_low'])} - {money(r['range_high'])}",
        ]) + " |")
    lines += ["", "![Median vs P10 facility contribution](growth_scenarios.png)", "",
              " ".join(growth_sentences(rows)), ""]
    return "\n".join(lines)


def growth_sentences(rows: list[dict]) -> list[str]:
    """Four plain-fact sentences, all numbers from `rows`; no recommendation."""
    by = {r["key"]: r for r in rows}
    g1 = by["G1"]
    best = max(rows, key=lambda r: r["facility_p10"])
    s1 = (f"{best['key']} has the best P10 facility contribution, {money(best['facility_p10'])} "
          f"(G1: {money(g1['facility_p10'])}).")

    def delta(k):
        r = by[k]
        d = lambda key: r[key] - g1[key]                                   # noqa: E731
        sign = lambda v: ("+" if v >= 0 else "-") + money(abs(v))           # noqa: E731
        return f"{k} {sign(d('facility_median'))} at the median, {sign(d('facility_p10'))} at P10, {sign(d('facility_p5'))} at P5"
    s2 = f"Against G1, {delta('G5')}; {delta('G6')}." if {"G5", "G6"} <= set(by) else ""

    wo = sorted({round(r["all_paid_without_backstop"], 6) for r in rows})
    without = (f"all bills are paid on {pct(wo[0], 2)} of paths in every scenario without the backstop, because "
               "bills are funded first and the mix only matters if the growth bucket cannot cover the 2033 top-up"
               if len(wo) == 1 else
               f"without the backstop all bills are paid on {pct(wo[0], 2)} to {pct(wo[-1], 2)} of paths "
               f"(G1: {pct(g1['all_paid_without_backstop'], 2)})")
    fails = [r for r in rows if r["n_fail_with_backstop"] > 0]
    capped = [r for r in rows if r["n_topup_not_fully_funded"] > 0]
    s3 = (without[0].upper() + without[1:] + "; "
          + ("with the backstop every scenario pays every bill on every path" if not fails else
             "with the backstop, bills go unpaid on " + ", ".join(
                 f"{r['n_fail_with_backstop']:,} of {r['n_sims']:,} {r['key']} paths" for r in fails))
          + ("" if not capped else "; the growth bucket cannot fully fund the 2033 top-up on " + ", ".join(
                 f"{r['n_topup_not_fully_funded']:,} {r['key']} paths" for r in capped)) + ".")

    def beats(k):
        r = by[k]
        both = r["facility_median"] > g1["facility_median"] and r["facility_p10"] > g1["facility_p10"]
        return (f"{k} {'beats' if both else 'does not beat'} G1 on both median and P10 "
                f"({money(r['facility_median'])} / {money(r['facility_p10'])} vs "
                f"{money(g1['facility_median'])} / {money(g1['facility_p10'])})")
    s4 = "; ".join(beats(k) for k in ("G2", "G4") if k in by)
    if "G8" in by and {"G2-V", "G3-V"} & set(by):                          # same question under Vanguard returns
        g8 = by["G8"]
        def beats_v(k):
            r = by[k]
            both = r["facility_median"] > g8["facility_median"] and r["facility_p10"] > g8["facility_p10"]
            return (f"{k} {'beats' if both else 'does not beat'} G8 ({money(r['facility_median'])} / "
                    f"{money(r['facility_p10'])} vs {money(g8['facility_median'])} / {money(g8['facility_p10'])})")
        s4 += "; under Vanguard returns, " + "; ".join(beats_v(k) for k in ("G2-V", "G3-V") if k in by)
    s4 += "."
    return [s for s in (s1, s2, s3, s4) if s]


def _seg_dist(p: np.ndarray, a: np.ndarray, b: np.ndarray) -> float:
    """Distance from point p to the segment a-b (display pixels)."""
    ab = b - a
    t = np.clip(np.dot(p - a, ab) / max(np.dot(ab, ab), 1e-9), 0.0, 1.0)
    return float(np.hypot(*(p - (a + t * ab))))


def growth_chart(rows: list[dict]) -> Figure:
    fig, ax = plots._figure(8.0, 5.0)
    ax.grid(axis="x", color=plots.GRID, linewidth=0.8)
    for r in rows:
        official = r["key"] == "G1"
        ax.scatter(r["facility_p10"], r["facility_median"], s=70 if official else 45,
                   color=plots.BLUE_600 if official else plots.BLUE_450, edgecolor=plots.SURFACE, linewidth=1.5,
                   zorder=3)
    xs = [r["facility_p10"] for r in rows]
    ys = [r["facility_median"] for r in rows]
    ax.set_xlim(min(xs) - 0.08 * (max(xs) - min(xs)), max(xs) + 0.15 * (max(xs) - min(xs)))
    ax.set_ylim(min(ys) - 0.15 * (max(ys) - min(ys)), max(ys) + 0.15 * (max(ys) - min(ys)))
    # Labels: try a few offsets per dot and keep the first that overlaps no label already placed.
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.text import Text
    renderer = FigureCanvasAgg(fig).get_renderer()
    placed: list = []
    dots = [ax.transData.transform((x, y)) for x, y in zip(xs, ys)]     # dot centres (display coords)
    placed += dots
    area = ax.get_window_extent(renderer)
    directions = [(1, 1), (-1, 1), (1, -1), (-1, -1), (0, 1.3), (0, -1.3), (1.4, 0), (-1.4, 0)]
    # Dots closer than ~10 px share one label ("G8, G2-V, G3-V"); the line points at their middle.
    groups: list[list[dict]] = []
    for r in sorted(rows, key=lambda r: r["key"] != "G1"):                 # official label first
        here = ax.transData.transform((r["facility_p10"], r["facility_median"]))
        for grp in groups:
            if any(np.hypot(*(here - ax.transData.transform((o["facility_p10"], o["facility_median"])))) < 10
                   for o in grp):
                grp.append(r)
                break
        else:
            groups.append([r])
    for grp in groups:
        r = {"key": ", ".join(o["key"] for o in grp),
             "facility_p10": float(np.mean([o["facility_p10"] for o in grp])),
             "facility_median": float(np.mean([o["facility_median"] for o in grp]))}
        xy = (r["facility_p10"], r["facility_median"])
        for radius in (16, 28, 40, 52):
            done = False
            for dx, dy in directions:
                ha = "left" if dx > 0 else "right" if dx < 0 else "center"
                va = "bottom" if dy > 0 else "top" if dy < 0 else "center"
                t = ax.annotate(r["key"], xy, xytext=(dx * radius, dy * radius), textcoords="offset points",
                                ha=ha, va=va, fontsize=9, color=plots.INK,
                                fontweight="bold" if r["key"] == "G1" else "normal",
                                arrowprops=dict(arrowstyle="-", color=plots.INK_2, linewidth=0.6, shrinkA=1,
                                                shrinkB=4))
                t.update_positions(renderer)                       # place the text before measuring it
                box = Text.get_window_extent(t, renderer).expanded(1.15, 1.3)   # text only, not the leader line
                inside = (box.x0 >= area.x0 and box.x1 <= area.x1 and box.y0 >= area.y0 and box.y1 <= area.y1)
                here = ax.transData.transform(xy)
                tip = here + np.array([dx, dy]) * radius * fig.dpi / 72.0            # leader line end
                crosses = any(_seg_dist(np.asarray(pt), here, tip) < 7 for pt in dots
                              if np.hypot(*(np.asarray(pt) - here)) > 12)
                clash = not inside or crosses or any(box.overlaps(b) for b in placed if hasattr(b, "overlaps")) or \
                    any(box.contains(*pt) for pt in placed if not hasattr(pt, "overlaps"))
                if not clash:
                    placed.append(box)
                    done = True
                    break
                if radius == 52 and (dx, dy) == directions[-1]:
                    placed.append(box)                     # nowhere clear: keep the last try
                    done = True
                    break
                t.remove()
            if done:
                break
    ax.xaxis.set_major_formatter(plots._dollars_k)
    ax.yaxis.set_major_formatter(plots._dollars_k)
    ax.set_xlabel("P10 facility contribution (bad case) →", color=plots.INK_2, fontsize=9)
    ax.set_ylabel("Median facility contribution →", color=plots.INK_2, fontsize=9)
    plots._title(ax, "Growth-bucket mixes: median vs. bad-case facility contribution",
                 f"{rows[0]['n_sims']:,} paths each, same draws. Up and to the right is better. G1 = official.")
    fig.tight_layout()
    return fig


def rows_frame(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame([{**{k: v for k, v in r.items() if k != "mix"},
                          "mix": ", ".join(f"{k} {w:.0%}" for k, w in r["mix"].items())} for r in rows])
