"""Charts as matplotlib Figures (no pyplot state, safe inside Streamlit)."""
from __future__ import annotations

import io
from contextlib import contextmanager

import matplotlib
import numpy as np
import pandas as pd
from matplotlib.figure import Figure
from matplotlib.ticker import FuncFormatter

from .model import Results

# Colour roles. "light" is the report style (outputs/ PNGs); "market" is the dashboard's dark
# trading-platform style (navy panels, blue series, green = up / paid, red = down / short).
# The BLUE_* names are roles (band light -> line dark), not literal hues.
THEMES = {
    "light": {"SURFACE": "#fcfcfb", "INK": "#0b0b0b", "INK_2": "#52514e", "TITLE": "#0b0b0b",
              "GRID": "#e4e3df", "BLUE_200": "#9ec5f4", "BLUE_300": "#6da7ec", "BLUE_450": "#2a78d6",
              "BLUE_600": "#184f95", "CRITICAL": "#d03b3b", "UP": "#0ca30c"},
    "clean": {"SURFACE": "#ffffff", "INK": "#111827", "INK_2": "#6b7280", "TITLE": "#111827",
              "GRID": "#eceef2", "BLUE_200": "#e3e7ed", "BLUE_300": "#c9d0da", "BLUE_450": "#475569",
              "BLUE_600": "#111827", "CRITICAL": "#dc2626", "UP": "#16a34a"},
    "market": {"SURFACE": "#131722", "INK": "#d1d4dc", "INK_2": "#787b86", "TITLE": "#eceff4",
               "GRID": "#222736", "BLUE_200": "#172a52", "BLUE_300": "#1f4196", "BLUE_450": "#2962ff",
               "BLUE_600": "#82b1ff", "CRITICAL": "#ef5350", "UP": "#26a69a"},
}
SURFACE, INK, INK_2, TITLE, GRID, BLUE_200, BLUE_300, BLUE_450, BLUE_600, CRITICAL, UP = THEMES["light"].values()


@contextmanager
def theme(name: str):
    """Draw charts in another colour theme for the duration of the block (e.g. the dashboard's
    "market" style); the report style is restored afterwards."""
    old = {k: globals()[k] for k in THEMES["light"]}
    globals().update(THEMES[name])
    rc = {"font.family": "sans-serif", "font.sans-serif": ["DejaVu Sans"]} if name in ("market", "clean") else {}
    if name == "clean":                                   # faint dashed grid, like a modern finance app
        rc.update({"grid.linestyle": (0, (4, 4))})
    try:
        with matplotlib.rc_context(rc):
            yield
    finally:
        globals().update(old)

_dollars_k = FuncFormatter(lambda v, _: f"-${-v / 1e3:,.0f}k" if v < 0 else f"${v / 1e3:,.0f}k")


def _figure(w: float = 8.0, h: float = 4.5) -> tuple[Figure, object]:
    fig = Figure(figsize=(w, h), dpi=150, facecolor=SURFACE)
    ax = fig.add_subplot(111)
    ax.set_facecolor(SURFACE)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    ax.tick_params(colors=INK_2, labelsize=9, length=0)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    return fig, ax


def _title(ax, title: str, subtitle: str | None = None) -> None:
    ax.set_title(title, loc="left", fontsize=12, color=TITLE, fontweight="bold", pad=22 if subtitle else 10)
    if subtitle:
        ax.text(0, 1.02, subtitle, transform=ax.transAxes, fontsize=9, color=INK_2, va="bottom")


def _fan(ax, years, paths, inner=(25, 75), outer=(10, 90), label_fmt=None) -> None:
    q = np.percentile(paths, [outer[0], inner[0], 50, inner[1], outer[1]], axis=0)
    ax.fill_between(years, q[0], q[4], color=BLUE_200, linewidth=0, label=f"P{outer[0]}–P{outer[1]}")
    ax.fill_between(years, q[1], q[3], color=BLUE_300, linewidth=0, label=f"P{inner[0]}–P{inner[1]}")
    ax.plot(years, q[2], color=BLUE_600, linewidth=2, label="Median")
    if label_fmt:
        names = [f"P{outer[0]}", f"P{inner[0]}", "P50", f"P{inner[1]}", f"P{outer[1]}"]
        ends = q[:, -1]
        # Nudge end labels apart so they never overlap (bands can collapse to the same value).
        gap = 0.07 * (q.max() - q.min() or 1.0)
        ys = list(ends)
        for i in range(1, len(ys)):
            ys[i] = max(ys[i], ys[i - 1] + gap)
        for name, v, y in zip(names, ends, ys):
            ax.annotate(f"{name} {label_fmt(v)}", (years[-1], y), xytext=(6, 0),
                        textcoords="offset points", va="center", fontsize=8,
                        color=INK if name == "P50" else INK_2)
    ax.legend(loc="upper left", frameon=False, fontsize=8, labelcolor=INK_2)


def fan_chart(res: Results) -> Figure:
    tl = res.timeline
    years = list(range(tl.contribution_year, tl.valuation_year + 1))
    fig, ax = _figure()
    _fan(ax, years, res.growth_path_after_topup, label_fmt=lambda v: f"${v / 1e3:,.0f}k")
    ax.set_xticks(years)
    ax.set_xlim(years[0], years[-1] + 1.1)
    ax.yaxis.set_major_formatter(_dollars_k)
    _title(ax, f"Growth bucket value, Jan {years[0]}–Jan {years[-1]} (nominal)",
           f"{res.n:,} paths. Bands: P10–P90, P25–P75. Jan {years[-1]} is after the bill top-up.")
    fig.tight_layout()
    return fig


def histogram(res: Results, low: float | None = None, high: float | None = None) -> Figure:
    fig, ax = _figure()
    x = res.facility
    # Cut the long right tail so the bulk of the distribution stays readable.
    ax.hist(x, bins=60, range=(x.min(), np.percentile(x, 99.5)), color=BLUE_450, edgecolor=SURFACE, linewidth=0.6)
    ax.xaxis.set_major_formatter(_dollars_k)
    ax.set_ylabel("Paths", color=INK_2, fontsize=9)
    marks = {"P10": np.percentile(x, 10), "Median": np.median(x), "P90": np.percentile(x, 90)}
    ymax = ax.get_ylim()[1]
    for name, v in marks.items():
        ax.axvline(v, color=INK_2, linewidth=1, linestyle=(0, (3, 3)))
        ax.text(v, ymax * 0.97, f" {name} ${v / 1e3:,.0f}k", fontsize=8, color=INK, va="top")
    if low is not None and high is not None:
        ax.axvspan(low, high, color=BLUE_200, alpha=0.35, linewidth=0, zorder=0,
                   label=rf"Example co-sponsor range (method) \${low / 1e3:,.0f}k–\${high / 1e3:,.0f}k")
        ax.legend(loc="center right", frameon=False, fontsize=8, labelcolor=INK_2)
    _title(ax, f"Facility contribution at Jan {res.timeline.valuation_year} (nominal)",
           f"{100 * res.give_pct:.0f}% of growth bucket after bill top-up, {res.n:,} paths; axis cut at P99.5")
    fig.tight_layout()
    return fig


def bills_chart(res: Results) -> Figure:
    years = np.array(res.timeline.bill_years)
    fig, ax = _figure()
    payout = res.rung_payout
    p5, p50, p95 = np.percentile(payout, [5, 50, 95], axis=0)
    ax.vlines(years, p5, p95, color=BLUE_300, linewidth=3, label="Rung payout P5–P95")
    ax.scatter(years, p50, s=40, color=BLUE_600, zorder=3, edgecolor=SURFACE, linewidth=1.5,
               label="Median rung payout")
    ax.hlines(res.bill_amount, years[0] - 0.4, years[-1] + 0.4, color=INK, linewidth=1.2,
              linestyle=(0, (4, 3)))
    ax.text(years[-1] + 0.5, res.bill_amount, f"Bill ${res.bill_amount / 1e3:,.0f}k", va="center",
            fontsize=8, color=INK)
    sf = res.ladder_only_shortfall
    lo = min(p5.min(), res.bill_amount) - 0.006 * res.bill_amount
    for k, y in enumerate(years):
        short = sf[:, k] > 1e-6
        txt = f"{short.mean():.0%} short\nmed ${np.median(sf[short, k]) / 1e3:,.1f}k" if short.any() else "never\nshort"
        ax.text(y, lo, txt, ha="center", va="top", fontsize=7, color=INK_2, linespacing=1.3)
    ax.set_xticks(years)
    ax.set_xlim(years[0] - 0.6, years[-1] + 1.4)
    ax.set_ylim(lo - 0.018 * res.bill_amount, max(p95.max(), res.bill_amount) + 0.01 * res.bill_amount)
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"${v:,.0f}"))
    ax.legend(loc="upper left", frameon=False, fontsize=8, labelcolor=INK_2)
    _title(ax, "Ladder payout vs. bill, by bill date",
           "Under each bill: share of paths where ladder + buffer alone fall short, and median shortfall then")
    fig.tight_layout()
    return fig


def buffer_chart(res: Results) -> Figure:
    years = list(res.timeline.buffer_years)
    fig, ax = _figure()
    _fan(ax, years, res.buffer_path, inner=(25, 75), outer=(5, 95),
         label_fmt=lambda v: f"${v / 1e3:,.1f}k")
    ax.axhline(0, color=INK_2, linewidth=0.8)
    ax.set_xticks(years[::2])
    ax.set_xlim(years[0], years[-1] + 2.2)
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"${v / 1e3:,.1f}k"))
    _title(ax, "T-bill reserve each Jan 1 (after that day's bill)",
           f"Includes the Jan {res.timeline.valuation_year} top-up from the growth bucket. Bands: P5–P95, P25–P75")
    fig.tight_layout()
    return fig


def stress_chart(stress: pd.DataFrame, mc_median: float | None = None) -> Figure:
    df = stress.iloc[::-1]
    fig, ax = _figure(8.0, 0.42 * len(df) + 1.4)
    ax.grid(axis="y", visible=False)
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    ax.spines["bottom"].set_visible(False)
    y = np.arange(len(df))
    ax.barh(y, df["facility_contribution"], height=0.6, color=BLUE_450)
    xmax = df["facility_contribution"].max()
    for yi, (_, row) in zip(y, df.iterrows()):
        txt = rf"\${row['facility_contribution'] / 1e3:,.0f}k"
        if row["topup_2033"] > 0.5:
            txt += rf"  (after \${row['topup_2033'] / 1e3:,.1f}k bill top-up)"
        if not row["all_bills_paid"]:
            txt += "   bills short"
        ax.text(row["facility_contribution"] + xmax * 0.01, yi, txt, va="center", fontsize=8,
                color=CRITICAL if not row["all_bills_paid"] else INK)
    if mc_median is not None:
        ax.axvline(mc_median, color=INK, linewidth=1, linestyle=(0, (3, 3)))
        ax.text(mc_median, -0.65, f"Monte Carlo median ${mc_median / 1e3:,.0f}k", fontsize=8,
                color=INK, ha="center", va="top")
        ax.set_ylim(-1.1, len(df) - 0.4)
    ax.set_yticks(y)
    ax.set_yticklabels(df["scenario"], fontsize=9, color=INK)
    ax.set_xlim(0, xmax * 1.45)
    ax.xaxis.set_major_formatter(_dollars_k)
    _title(ax, "Facility contribution by stress scenario (nominal, after bill top-up)")
    fig.tight_layout()
    return fig


def shortfall_chart(res: Results) -> Figure:
    """Distribution of total ladder-only shortfall on the paths that fall short."""
    fig, ax = _figure()
    x = res.ladder_only_total_shortfall[~res.ladder_only_all_paid]
    if len(x) == 0:
        ax.text(0.5, 0.5, "Ladder + buffer alone pay every bill on every path", ha="center",
                transform=ax.transAxes, color=INK_2)
        ax.set_yticks([])
    else:
        ax.hist(x, bins=50, color=BLUE_450, edgecolor=SURFACE, linewidth=0.6)
        ymax = ax.get_ylim()[1]
        for name, v in {"Median": np.median(x), "P90": np.percentile(x, 90)}.items():
            ax.axvline(v, color=INK_2, linewidth=1, linestyle=(0, (3, 3)))
            ax.text(v, ymax * 0.97, f" {name} ${v / 1e3:,.1f}k", fontsize=8, color=INK, va="top")
        ax.set_ylabel("Paths", color=INK_2, fontsize=9)
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"${v / 1e3:,.0f}k"))
    _title(ax, "Ladder-only shortfall: total unpaid bill dollars",
           f"{len(x):,} of {res.n:,} paths ({len(x) / res.n:.0%}) where ladder + buffer alone fall short; "
           "the growth bucket covers these")
    fig.tight_layout()
    return fig


def to_png(fig: Figure) -> bytes:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", facecolor=fig.get_facecolor(), bbox_inches="tight")
    return buf.getvalue()


# ----------------------------------------------------------- overview charts ----
# Plain-language charts for the dashboard's Overview tab (readers who don't know the details).

def plan_timeline_chart(res: Results, ladder_budget: float, contribution: float, give_pct: float,
                        backstop: float) -> Figure:
    """The plan on one line: what happens when, with the typical amounts from this run."""
    tl = res.timeline
    fig, ax = _figure(8.0, 3.4)
    ax.grid(False)
    for side in ("bottom",):
        ax.spines[side].set_visible(False)
    ax.set_yticks([])
    ax.set_xticks([])
    first, last = tl.purchase_year, tl.bill_years[-1]
    ax.set_xlim(first - 0.6, last + 0.8)
    ax.set_ylim(-1.25, 1.35)
    ax.hlines(0, first - 0.3, last + 0.3, color=INK_2, linewidth=1.2)
    ax.axvspan(tl.bill_years[0] - 0.15, last + 0.15, ymin=0.42, ymax=0.50, color=BLUE_300, linewidth=0)
    vy = tl.valuation_year
    facility = float(np.median(res.facility))
    cushion = float(np.median(res.cushion_kept))
    topup = float(np.median(res.topup))
    events = [
        (first, 0.75, f"Jan {first}\n${ladder_budget / 1e3:,.0f}k buys a\nladder of bonds", BLUE_450),
        (tl.contribution_year, -0.75, f"Jan {tl.contribution_year}\n${contribution / 1e3:,.0f}k goes into\nstocks (growth)", BLUE_450),
        (2031.5, 0.75, "2031-32\nhalf the stocks\nmoved to cash", INK_2),
        (vy, -0.80, f"Jan {vy}: growth money split\n~${topup / 1e3:,.0f}k tops up bill cash\n"
                    f"~${facility / 1e3:,.0f}k to the facility ({give_pct:.0%})\n~${cushion / 1e3:,.0f}k kept by Laura", BLUE_600),
        ((tl.bill_years[0] + last) / 2, 0.80, f"{tl.bill_years[0]}-{last}: ten ${res.bill_amount / 1e3:,.0f}k bills\n"
                                             f"paid from the ladder\n(+${backstop / 1e3:,.0f}k safety net)", BLUE_450),
    ]
    for x, y, text, color in events:
        ax.plot([x], [0], "o", color=color, markersize=8, markeredgecolor=SURFACE, markeredgewidth=1.5, zorder=3)
        ax.vlines(x, 0, y * 0.55, color=GRID, linewidth=0.8)
        ax.text(x, y, text, ha="center", va="bottom" if y > 0 else "top", fontsize=8, color=INK, linespacing=1.35)
    event_x = [e[0] for e in events]
    for year in range(first, last + 1):
        if all(abs(year - x) > 0.6 for x in event_x) and (year - first) % 2 == 1:
            ax.text(year, -0.10, str(year), ha="center", va="top", fontsize=7, color=INK_2)
    _title(ax, "The plan at a glance", "Typical amounts from this run; the bar marks the ten bill years")
    fig.tight_layout()
    return fig


def bill_sources_chart(res: Results) -> Figure:
    """For each bill: how much comes from the bond/ETF bought for it, from the cash reserve
    (leftover cash, coupons and the 2033 top-up) and from the backstop; averages over all paths."""
    years = np.array(res.timeline.bill_years)
    own = np.minimum(res.rung_payout, res.bill_paid).mean(axis=0)
    reserve = res.bill_paid.mean(axis=0) - own
    backstop = res.backstop_draw.mean(axis=0)
    fig, ax = _figure()
    ax.bar(years, own, width=0.62, color=BLUE_450, label="From the bond/ETF bought for that bill")
    ax.bar(years, reserve, width=0.62, bottom=own, color=BLUE_200, label="From the cash reserve (incl. 2033 top-up)")
    ax.bar(years, backstop, width=0.62, bottom=own + reserve, color=CRITICAL, label="From the safety net (backstop)")
    ax.hlines(res.bill_amount, years[0] - 0.4, years[-1] + 0.4, color=INK, linewidth=1, linestyle=(0, (3, 3)))
    ax.text(years[-1] + 0.5, res.bill_amount, f"bill ${res.bill_amount / 1e3:,.0f}k", va="center",
            fontsize=8, color=INK)
    for x, o in zip(years, own):
        ax.text(x, o / 2, f"{o / res.bill_amount:.0%}", ha="center", va="center", fontsize=7.5,
                color=SURFACE if SURFACE != "#fcfcfb" else "#ffffff")
    ax.set_xticks(years)
    ax.set_xlim(years[0] - 0.6, years[-1] + 1.4)
    ax.set_ylim(0, res.bill_amount * 1.28)
    ax.yaxis.set_major_formatter(_dollars_k)
    ax.legend(loc="upper left", frameon=False, fontsize=8, labelcolor=INK_2, ncol=1)
    _title(ax, "Who pays each $50k bill", "Average over all simulated futures; % = share paid by the bond/ETF itself")
    fig.tight_layout()
    return fig


def outcomes_chart(res: Results, low: float, high: float) -> Figure:
    """Spread of possible facility amounts, labelled in plain words."""
    x = res.facility
    p10, med, p90 = np.percentile(x, [10, 50, 90])
    fig, ax = _figure()
    ax.hist(x, bins=50, range=(x.min(), np.percentile(x, 99.5)), color=BLUE_450, edgecolor=SURFACE, linewidth=0.5)
    ax.axvspan(low, high, color=BLUE_200, alpha=0.45, linewidth=0, zorder=0)
    ymax = ax.get_ylim()[1]
    for v, text in [(p10, f"bad case\n1 in 10 below\n${p10 / 1e3:,.0f}k"), (med, f"typical\nhalf above/below\n${med / 1e3:,.0f}k"),
                    (p90, f"good case\n1 in 10 above\n${p90 / 1e3:,.0f}k")]:
        ax.axvline(v, color=INK, linewidth=1, linestyle=(0, (3, 3)))
        ax.text(v, ymax * 0.98, text, fontsize=8, color=INK, va="top", ha="left", linespacing=1.3,
                bbox=dict(boxstyle="square,pad=0.3", facecolor=SURFACE, edgecolor="none", alpha=0.85))
    ax.set_yticks([])
    ax.spines["left"].set_visible(False)
    ax.xaxis.set_major_formatter(_dollars_k)
    _title(ax, f"How much could the facility get in {res.timeline.valuation_year}?",
           f"Each bar = how many of {res.n:,} simulated futures land there. "
           rf"Shaded: co-sponsor range \${low / 1e3:,.0f}k-\${high / 1e3:,.0f}k")
    fig.tight_layout()
    return fig


def whatif_chart(stress: pd.DataFrame, picks: list[tuple[str, str]]) -> Figure:
    """A few plain-language stress cases: facility amount and whether every bill still gets paid."""
    rows = stress.set_index("scenario")
    picks = [(k, label) for k, label in picks if k in rows.index]
    fig, ax = _figure(8.0, 0.55 * len(picks) + 1.5)
    ax.grid(axis="y", visible=False)
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    ax.spines["bottom"].set_visible(False)
    y = np.arange(len(picks))[::-1]
    vals = [float(rows.loc[k, "facility_contribution"]) for k, _ in picks]
    ax.barh(y, vals, height=0.58, color=BLUE_450)
    xmax = max(vals)
    for yi, (k, _), v in zip(y, picks, vals):
        r = rows.loc[k]
        if bool(r["all_bills_paid"]):
            status, color = "✓ all bills paid", UP
        elif bool(r["backstop_covers"]):
            status, color = "✓ all bills paid (safety net used)", UP
        else:
            status, color = "✗ BILLS SHORT", CRITICAL
        ax.text(v + xmax * 0.015, yi, f"${v / 1e3:,.0f}k to facility  ·  {status}", va="center", fontsize=8,
                color=color)
    ax.set_yticks(y)
    ax.set_yticklabels([label for _, label in picks], fontsize=8.5, color=INK)
    ax.set_xlim(0, xmax * 1.75)
    ax.xaxis.set_major_formatter(_dollars_k)
    _title(ax, "What if things go wrong?", "One fixed future per row; bars = money to the facility in 2033")
    fig.tight_layout()
    return fig


def price_tag(ax, y: float, text: str, color: str) -> None:
    """A trading-chart style value tag on the right edge of the plot."""
    ax.annotate(text, xy=(1.0, y), xycoords=("axes fraction", "data"), xytext=(4, 0), textcoords="offset points",
                va="center", ha="left", fontsize=8, color="#ffffff", fontweight="bold",
                bbox=dict(boxstyle="square,pad=0.3", facecolor=color, edgecolor="none"))


def sample_paths_chart(values: np.ndarray, typical: np.ndarray, start_year: int, invested: float,
                       n_total: int, width: float = 8.0) -> Figure:
    """Growth money month by month for a handful of the simulated futures, drawn like stock prices:
    green if a future ends above what was put in, red if below. `typical` (white) is the month-by-
    month median over all n_total futures."""
    months = values.shape[1]
    t = start_year + np.arange(months) / 12.0
    fig, ax = _figure(width, 4.6)
    ax.yaxis.tick_right()
    end = values[:, -1]
    for row, e in zip(values, end):
        ax.plot(t, row, color=UP if e >= invested else CRITICAL, linewidth=0.9, alpha=0.55)
    ax.plot(t, typical, color=TITLE, linewidth=2.0)
    ax.axhline(invested, color=INK_2, linewidth=1, linestyle=(0, (4, 3)))
    ax.text(t[-1], invested, f"${invested / 1e3:,.0f}k put in ", va="top", ha="right", fontsize=8, color=INK_2,
            bbox=dict(boxstyle="square,pad=0.2", facecolor=SURFACE, edgecolor="none", alpha=0.85))
    up = float((end >= invested).mean())
    price_tag(ax, typical[-1], f"typical ${typical[-1] / 1e3:,.0f}k", BLUE_450)
    ax.set_xlim(t[0], t[-1])
    ax.set_xticks(range(start_year, int(t[-1]) + 1))
    ax.yaxis.set_major_formatter(_dollars_k)
    ax.spines["right"].set_visible(False)
    _title(ax, "Growth money, month by month",
           f"{len(values)} of the {n_total:,} futures: {up:.0%} of these end above what was put in (green), "
           f"{1 - up:.0%} below (red). Thick line = typical of all {n_total:,}")
    fig.tight_layout()
    return fig
