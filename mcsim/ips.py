"""Print-ready charts for the Investment Policy Statement: light style, large type, plain English
("typical", "bad case (1 in 10)"), no model jargon. Every number comes from outputs/metrics.json or
outputs/growth_scenarios.csv; nothing is typed by hand."""
from __future__ import annotations

import io
import textwrap

import matplotlib
import numpy as np
import pandas as pd
from matplotlib.figure import Figure
from matplotlib.ticker import FuncFormatter

from .analysis import money as _money, pct


def money(v: float) -> str:
    """$1,234 for chart text; the $ is escaped so matplotlib doesn't read $...$ as a formula."""
    return _money(v).replace("$", r"\$")

NAVY, MID, LIGHT, RED, INK, GREY, RULE = "#1f3a5f", "#6e8aaf", "#c9d6e7", "#b42318", "#16191f", "#5c6370", "#d9d6cf"
RC = {"font.family": "DejaVu Sans", "font.size": 15, "axes.edgecolor": RULE, "axes.labelcolor": GREY,
      "xtick.color": GREY, "ytick.color": INK, "axes.spines.top": False, "axes.spines.right": False}
SIZE = (13.0, 7.3)
DPI = 200
_k = FuncFormatter(lambda v, _: f"${v / 1e3:,.0f}k")


def _figure() -> tuple[Figure, object]:
    fig = Figure(figsize=SIZE, dpi=DPI, facecolor="white")
    ax = fig.add_subplot(111)
    ax.set_facecolor("white")
    return fig, ax


def _titles(fig: Figure, title: str, subtitle: str, source: str) -> None:
    fig.text(0.04, 0.95, title, fontsize=26, fontweight="bold", color=INK, va="top")
    fig.text(0.04, 0.875, subtitle, fontsize=16, color=GREY, va="top")
    fig.text(0.04, 0.025, "\n".join(textwrap.wrap(source, 150)), fontsize=11.5, color=GREY, va="bottom",
             linespacing=1.4)


def bills_chart(m: dict) -> Figure:
    """Who pays each bill: the bond/fund bought for it, the cash reserve, the safety net."""
    e = m["end_result"]
    src, b = e["bill_sources"], e["bills"]
    seeds = b["seeds"]
    years = [str(y) for y in src["years"]]
    own, reserve, net = (np.array(src[k]) for k in ("own", "reserve", "backstop"))
    with matplotlib.rc_context(RC):
        fig, ax = _figure()
        fig.subplots_adjust(left=0.08, right=0.97, top=0.75, bottom=0.2)
        x = np.arange(len(years))
        ax.bar(x, own, 0.68, color=NAVY, label="Bond or fund bought for that bill")
        ax.bar(x, reserve, 0.68, bottom=own, color=LIGHT,
               label=f"Cash reserve (incl. the {m['valuation_year']} top-up)")
        ax.bar(x, net, 0.68, bottom=own + reserve, color=RED,
               label=f"Safety net ({money(e['cushion']['backstop'])} from Laura's share)")
        for xi, o in zip(x, own):
            ax.text(xi, o / 2, f"{o / b['amount']:.0%}", ha="center", va="center", color="white", fontsize=14,
                    fontweight="bold")
        ax.axhline(b["amount"], color=INK, lw=1.2, ls=(0, (4, 3)))
        ax.text(-0.55, b["amount"] * 1.012, f"{money(b['amount'])} bill", va="bottom", fontsize=13.5, color=INK)
        ax.set_xticks(x, years)
        ax.set_ylim(0, b["amount"] * 1.08)
        ax.set_xlim(-0.6, len(x) - 0.1)
        ax.yaxis.set_major_formatter(_k)
        ax.grid(axis="y", color=RULE, lw=0.8)
        ax.set_axisbelow(True)
        ax.legend(loc="upper center", bbox_to_anchor=(0.46, -0.09), ncol=3, frameon=False, fontsize=13,
                  handlelength=1.2, columnspacing=1.6)
        all_paid = all(s["fails"] == 0 for s in seeds)
        title = (f"All {b['n']} bills are paid in every simulated future" if all_paid else
                 f"All {b['n']} bills are paid in {pct(min(s['p_paid'] for s in seeds), 2)} of simulated futures")
        _titles(fig, title,
                f"Where each {money(b['amount'])} bill comes from, on average. White % = share paid by the bond or "
                "fund bought for it.",
                f"{seeds[0]['n']:,} simulated futures, checked on {len(seeds)} separate runs. The safety net is used in "
                f"{pct(src['backstop_used_share'], 1)} of futures (typically {money(src['backstop_used_median'])}, "
                "for the last bills).")
    return fig


def _plain_mix(label: str) -> str:
    base = label.split(" (")[0]
    return base.replace(", Vanguard pessimistic returns", " with lower return forecasts")


def growth_mix_chart(growth: pd.DataFrame, year: int,
                     keys: tuple[str, ...] = ("G1", "G2", "G3", "G4", "G5", "G6", "G7", "G8"),
                     plan: str = "G1", leveraged: str = "G6") -> Figure:
    """Typical vs bad-case facility contribution for each stock mix (from growth_scenarios.csv)."""
    g = growth.set_index("key").loc[[k for k in keys if k in set(growth["key"])]]
    with matplotlib.rc_context(RC):
        fig, ax = _figure()
        fig.subplots_adjust(left=0.40, right=0.96, top=0.74, bottom=0.17)
        y = np.arange(len(g))[::-1]
        for yi, (key, r) in zip(y, g.iterrows()):
            c = NAVY if key == plan else RED if key == leveraged else MID
            ax.plot([r["facility_p10"], r["facility_median"]], [yi, yi], color=c, lw=3, alpha=0.55, zorder=1)
            ax.scatter([r["facility_p10"]], [yi], s=130, color="white", edgecolor=c, linewidth=2.5, zorder=2)
            ax.scatter([r["facility_median"]], [yi], s=150, color=c, zorder=3)
        labels = [_plain_mix(r["label"]) + (" (our plan)" if k == plan else "") for k, r in g.iterrows()]
        ax.set_yticks(y, labels, fontsize=13.5)
        for t, k in zip(ax.get_yticklabels(), g.index):
            if k == plan:
                t.set_fontweight("bold"); t.set_color(NAVY)
            elif k == leveraged:
                t.set_color(RED)
        ax.xaxis.set_major_formatter(_k)
        ax.grid(axis="x", color=RULE, lw=0.8)
        ax.set_axisbelow(True)
        lo = float(g[["facility_p10", "facility_median"]].min().min())
        hi = float(g[["facility_p10", "facility_median"]].max().max())
        ax.set_xlim(lo - (hi - lo) * 0.08, hi + (hi - lo) * 0.08)
        ax.scatter([], [], s=130, color="white", edgecolor=GREY, linewidth=2.5, label="Bad case (1 in 10)")
        ax.scatter([], [], s=150, color=GREY, label="Typical future")
        ax.legend(loc="lower right", bbox_to_anchor=(1.0, 1.0), ncol=2, frameon=False, fontsize=13)
        p, lev = g.loc[plan], g.loc[leveraged]
        lev_note = (f"2x leverage: typical {money(abs(lev['facility_median'] - p['facility_median']))} "
                    f"{'lower' if lev['facility_median'] < p['facility_median'] else 'higher'}, bad case "
                    f"{money(p['facility_p10'] - lev['facility_p10'])} lower")
        if int(lev["n_fail_with_backstop"]) > 0:
            lev_note += (f", and bills go unpaid in {int(lev['n_fail_with_backstop']):,} of "
                         f"{int(lev['n_sims']):,} futures even with the safety net")
        _titles(fig, "Why 60/40, and why no leverage",
                f"Facility contribution in {year} for each stock mix: typical future vs bad case (1 in 10).",
                lev_note + f". {int(p['n_sims']):,} simulated futures per mix.")
    return fig


def facility_chart(m: dict) -> Figure:
    """Typical vs bad case vs worst tested facility contribution, with the example co-sponsor range."""
    e = m["end_result"]
    rows = [("Typical future", e["facility"]["median"], NAVY),
            ("Bad case (1 in 10)", e["facility"]["p10"], MID),
            ("Worst case we tested:\nlow rates + weak markets", m["worst_facility"], RED)]
    with matplotlib.rc_context(RC):
        fig, ax = _figure()
        fig.subplots_adjust(left=0.27, right=0.93, top=0.76, bottom=0.18)
        y = np.arange(len(rows))[::-1]
        ax.axvspan(m["range_low"], m["range_high"], color=LIGHT, alpha=0.6, lw=0, zorder=0)
        ax.text((m["range_low"] + m["range_high"]) / 2, y[0] + 0.62, "Example co-sponsor range", ha="center",
                va="bottom", fontsize=13, color=NAVY)
        for yi, (label, v, c) in zip(y, rows):
            ax.barh(yi, v, 0.5, color=c, zorder=2)
            ax.text(v + m["range_high"] * 0.015, yi, money(v), va="center", fontsize=17, fontweight="bold", color=INK)
        ax.set_yticks(y, [r[0] for r in rows], fontsize=15)
        ax.set_ylim(-0.6, len(rows) - 0.2)
        ax.set_xlim(0, max(r[1] for r in rows) * 1.18)
        ax.xaxis.set_major_formatter(_k)
        ax.grid(axis="x", color=RULE, lw=0.8)
        ax.set_axisbelow(True)
        _titles(fig, f"What the facility can expect in {m['valuation_year']}",
                f"Example co-sponsor range {money(m['range_low'])} to {money(m['range_high'])}: "
                f"{pct(m['range_p_low'], 0)} of futures give at least the low end.",
                ("Bills are paid in full in all three cases. " if all(s["fails"] == 0 for s in e["bills"]["seeds"])
                 and (m["worst_backstop_covers"] or m["worst_unpaid"] <= 0) else "")
                + "The actual range will be set in 2031 from the real growth money and ladder cost, using the same "
                  "method.")
    return fig


def to_png(fig: Figure) -> bytes:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=DPI, facecolor="white")
    return buf.getvalue()
