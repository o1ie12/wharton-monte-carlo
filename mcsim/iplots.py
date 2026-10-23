"""Interactive dashboard charts (Plotly): hover values, zoom, legend toggles.

The report PNGs in outputs/ still come from mcsim.plots (matplotlib); both read the same
simulation results. Colour roles match plots.THEMES. "clean" is the memo style of the Report
tab (white paper, near-black ink, one navy accent, red only for problems); "desk" is the dark
terminal style of the rest of the dashboard (graphite panels, cyan accent, teal/red for up/down).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from .model import Results
from . import plots

FONT = "Inter, -apple-system, 'Segoe UI', Helvetica, Arial, sans-serif"
SERIF = "'Source Serif 4', Georgia, 'Times New Roman', serif"
TV_FONT = "-apple-system, BlinkMacSystemFont, 'Trebuchet MS', Roboto, Ubuntu, sans-serif"   # TradingView charts
THEMES = {
    "clean": {"SURFACE": "#ffffff", "INK": "#16191f", "INK_2": "#5c6370", "TITLE": "#16191f", "GRID": "#e8e6e1",
              "BLUE_200": "#e3e9f1", "BLUE_300": "#b9c7da", "BLUE_450": "#1f3a5f", "BLUE_600": "#0f2440",
              "CRITICAL": "#b42318", "UP": "#1f3a5f", "TITLE_FONT": SERIF},
    "market": {**plots.THEMES["market"], "TITLE_FONT": FONT},
    # TradingView dark: chart #131722, grid #2a2e39 at 60%, text #d1d4dc / #787b86, blue #2962ff,
    # green #089981, red #f23645.
    "desk": {"SURFACE": "#131722", "INK": "#d1d4dc", "INK_2": "#787b86", "TITLE": "#ffffff",
             "GRID": "rgba(42,46,57,0.6)", "BLUE_200": "#1a2547", "BLUE_300": "#1f3474", "BLUE_450": "#2962ff",
             "BLUE_600": "#5b8cff", "CRITICAL": "#f23645", "UP": "#089981", "TITLE_FONT": TV_FONT,
             "TICK_FONT": TV_FONT, "MUTED": "#363a45"},
}
CONFIG = {"displaylogo": False, "displayModeBar": "hover",
          "modeBarButtonsToRemove": ["lasso2d", "select2d", "autoScale2d"],
          "toImageButtonOptions": {"format": "png", "scale": 2}}


def _rgba(hex_color: str, alpha: float) -> str:
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return f"rgba({r},{g},{b},{alpha})"


def _layout(fig: go.Figure, t: dict, title: str, subtitle: str = "", height: int = 380) -> go.Figure:
    fig.update_layout(
        paper_bgcolor=t["SURFACE"], plot_bgcolor=t["SURFACE"], height=height,
        font=dict(family=FONT, color=t["INK"], size=12),
        title=dict(text=title + (f"<br><span style='font-family:{FONT};font-size:12px;color:{t['INK_2']}'>"
                                 f"{subtitle}</span>" if subtitle else ""),
                   x=0.01, xanchor="left", y=0.97, yanchor="top",
                   font=dict(family=t["TITLE_FONT"], size=17, color=t["TITLE"])),
        margin=dict(l=10, r=14, t=78 if subtitle else 50, b=10),
        hoverlabel=dict(bgcolor=t["SURFACE"], bordercolor=t["GRID"], font=dict(family=FONT, color=t["INK"])),
        legend=dict(orientation="h", x=0, y=1.0, xanchor="left", yanchor="bottom", bgcolor="rgba(0,0,0,0)",
                    font=dict(size=11, color=t["INK_2"])),
        bargap=0.12,
        modebar=dict(bgcolor="rgba(0,0,0,0)", color=t["INK_2"], activecolor=t["INK"]),
    )
    axis = dict(gridcolor=t["GRID"], gridwidth=1, zeroline=False, automargin=True, ticks="",
                tickfont=dict(color=t["INK_2"], size=11, family=t.get("TICK_FONT", FONT)),
                title_font=dict(color=t["INK_2"], size=11))
    fig.update_xaxes(**axis, showgrid=False, showline=True, linecolor=t["GRID"] if "TICK_FONT" in t else t["INK_2"],
                     linewidth=1)
    fig.update_yaxes(**axis, showline=False)
    if "TICK_FONT" in t:                                  # terminal: crosshair and a mono hover box
        spike = dict(showspikes=True, spikemode="across", spikesnap="cursor", spikethickness=1, spikedash="dot",
                     spikecolor=t["INK_2"])
        fig.update_xaxes(**spike)
        fig.update_yaxes(**spike)
        fig.update_layout(hoverlabel=dict(bgcolor="#1e222d", bordercolor=t.get("MUTED", t["GRID"]),
                                          font=dict(family=TV_FONT, size=11, color=t["INK"])))
    return fig


def bare(fig: go.Figure) -> go.Figure:
    """Drop the chart's own title: the page shows it as an exhibit heading instead."""
    has_legend = any(tr.showlegend is not False for tr in fig.data) and fig.layout.showlegend is not False
    fig.update_layout(title=None, margin=dict(t=34 if has_legend else 12))
    return fig


def _money_axis(fig: go.Figure, axis: str = "y") -> None:
    (fig.update_yaxes if axis == "y" else fig.update_xaxes)(tickprefix="$", tickformat="~s")


def _band(fig: go.Figure, x, lo, hi, color: str, name: str, show: bool = True) -> None:
    fig.add_trace(go.Scatter(x=x, y=lo, mode="lines", line=dict(width=0), hoverinfo="skip", showlegend=False))
    fig.add_trace(go.Scatter(x=x, y=hi, mode="lines", line=dict(width=0), fill="tonexty", fillcolor=color,
                             name=name, hoverinfo="skip", showlegend=show))


# ---------------------------------------------------------------- overview ----

def sample_paths_chart(m: dict, start_year: int, invested: float, n_total: int, theme: str = "clean") -> go.Figure:
    """Growth money month by month: sample futures (green ends above what was put in, red below),
    the typical path and the band 8 in 10 futures stay in."""
    t = THEMES[theme]
    months = m["sample"].shape[1]
    x = pd.date_range(f"{start_year}-01-01", periods=months, freq="MS")
    fig = go.Figure()
    _band(fig, x, m["p10"], m["p90"], _rgba(t["BLUE_450"], 0.08), "8 in 10 futures (P10–P90)", show=False)
    end = m["sample"][:, -1]
    for i, row in enumerate(m["sample"]):
        up = end[i] >= invested
        fig.add_trace(go.Scatter(
            x=x, y=row, mode="lines", line=dict(width=1, color=_rgba(t["UP"] if up else t["CRITICAL"], 0.30 if up else 0.5)),
            name=f"future {i + 1}", legendgroup="up" if up else "down", showlegend=False,
            hovertemplate=f"future {i + 1}<br>%{{x|%b %Y}}: $%{{y:,.0f}}<extra></extra>"))
    fig.add_trace(go.Scatter(x=x, y=m["median"], mode="lines", line=dict(width=2.6, color=t["TITLE"]),
                             name=f"typical (all {n_total:,})", showlegend=False,
                             hovertemplate="typical<br>%{x|%b %Y}: $%{y:,.0f}<extra></extra>"))
    fig.add_hline(y=invested, line=dict(color=t["INK_2"], width=1, dash="dot"),
                  annotation_text=f"${invested / 1e3:,.0f}k put in", annotation_position="bottom left",
                  annotation_font=dict(color=t["INK_2"], size=11))
    for y, label, strong in ((m["p90"][-1], "1 in 10 above", False), (m["median"][-1], "typical", True),
                             (m["p10"][-1], "1 in 10 below", False)):
        fig.add_annotation(x=x[-1], y=y, text=f"<b>${y / 1e3:,.0f}k</b> {label}" if strong else f"${y / 1e3:,.0f}k {label}",
                           showarrow=False, xanchor="left", xshift=8, align="left",
                           font=dict(color=t["INK"] if strong else t["INK_2"], size=11))
    share_up = float((end >= invested).mean())
    _layout(fig, t, "Growth money, month by month",
            f"{len(end)} of the {n_total:,} futures: {share_up:.0%} of these end above what was put in (blue), "
            f"{1 - share_up:.0%} below (red)", height=440)
    _money_axis(fig)
    fig.update_layout(hovermode="closest", margin=dict(r=120))
    return fig


def plan_timeline_chart(res: Results, ladder_budget: float, contribution: float, give_pct: float,
                        backstop: float, theme: str = "clean") -> go.Figure:
    tl = res.timeline
    t = THEMES[theme]
    first, last, vy = tl.purchase_year, tl.bill_years[-1], tl.valuation_year
    facility, cushion, topup = (float(np.median(v)) for v in (res.facility, res.cushion_kept, res.topup))
    events = [
        (first, 1, f"Jan {first}", f"${ladder_budget / 1e3:,.0f}k buys a<br>ladder of bonds"),
        (tl.contribution_year, -1, f"Jan {tl.contribution_year}", f"${contribution / 1e3:,.0f}k into<br>stocks"),
        (2031.5, 1, "2031–32", "half the stocks<br>move to cash"),
        (vy, -1, f"Jan {vy}", f"~${topup / 1e3:,.0f}k top-up to bills<br>~${facility / 1e3:,.0f}k to the facility "
                              f"({give_pct:.0%})<br>~${cushion / 1e3:,.0f}k kept by Laura"),
        ((tl.bill_years[0] + last) / 2, 1, f"{tl.bill_years[0]}–{last}",
         f"ten ${res.bill_amount / 1e3:,.0f}k bills<br>(+${backstop / 1e3:,.0f}k safety net)"),
    ]
    fig = go.Figure()
    fig.add_shape(type="rect", x0=tl.bill_years[0] - 0.15, x1=last + 0.15, y0=-0.08, y1=0.08,
                  fillcolor=t["BLUE_300"], line_width=0, layer="below")
    fig.add_shape(type="line", x0=first - 0.3, x1=last + 0.3, y0=0, y1=0, line=dict(color=t["INK_2"], width=1.2))
    for x, side, date, text in events:
        fig.add_annotation(x=x, y=0, ax=0, ay=-70 * side, text=f"<b>{date}</b><br>{text}", showarrow=True,
                           arrowhead=0, arrowcolor=t["GRID"], font=dict(size=11, color=t["INK"]), align="center")
    fig.add_trace(go.Scatter(
        x=[e[0] for e in events], y=[0] * len(events), mode="markers",
        marker=dict(size=12, color=t["BLUE_450"], line=dict(color=t["SURFACE"], width=2)),
        hovertext=[f"{e[2]}: {e[3].replace('<br>', ' ')}" for e in events], hoverinfo="text", showlegend=False))
    _layout(fig, t, "The plan at a glance", "Typical amounts from this run; the bar marks the ten bill years",
            height=340)
    fig.update_yaxes(visible=False, range=[-1.6, 1.6])
    fig.update_xaxes(range=[first - 1.3, last + 1.0], dtick=1, showgrid=False, tickfont=dict(size=10))
    return fig


def bill_sources_chart(res: Results, theme: str = "clean") -> go.Figure:
    t = THEMES[theme]
    years = [str(y) for y in res.timeline.bill_years]
    own = np.minimum(res.rung_payout, res.bill_paid).mean(axis=0)
    reserve = res.bill_paid.mean(axis=0) - own
    backstop = res.backstop_draw.mean(axis=0)
    fig = go.Figure()
    fig.add_bar(x=years, y=own, name="From the bond/ETF bought for that bill", marker_color=t["BLUE_450"],
                text=[f"{o / res.bill_amount:.0%}" for o in own], textposition="inside", insidetextanchor="middle",
                textfont=dict(color="#ffffff", size=11),
                hovertemplate="%{x}: own bond pays $%{y:,.0f} on average<extra></extra>")
    fig.add_bar(x=years, y=reserve, name="From the cash reserve (incl. 2033 top-up)", marker_color=t["BLUE_300"],
                hovertemplate="%{x}: cash reserve pays $%{y:,.0f} on average<extra></extra>")
    fig.add_bar(x=years, y=backstop, name="From the safety net", marker_color=t["CRITICAL"],
                hovertemplate="%{x}: safety net pays $%{y:,.2f} on average<extra></extra>")
    fig.add_hline(y=res.bill_amount, line=dict(color=t["INK"], width=1, dash="dot"),
                  annotation_text=f"bill ${res.bill_amount / 1e3:,.0f}k", annotation_position="top right",
                  annotation_font=dict(size=11, color=t["INK"]))
    _layout(fig, t, "Who pays each $50k bill", "Average over all simulated futures; % = share paid by the bond/ETF "
                                               "itself. Click a legend item to hide it.", height=400)
    fig.update_layout(barmode="stack", margin=dict(t=110), legend=dict(traceorder="normal"))
    fig.update_yaxes(range=[0, res.bill_amount * 1.12])
    _money_axis(fig)
    return fig


def outcomes_chart(res: Results, low: float, high: float, theme: str = "clean", plain: bool = True) -> go.Figure:
    """Spread of facility amounts; plain=True labels the lines in plain words (Overview)."""
    t = THEMES[theme]
    x = res.facility
    p10, med, p90 = np.percentile(x, [10, 50, 90])
    fig = go.Figure(go.Histogram(
        x=x, xbins=dict(start=float(x.min()), end=float(np.percentile(x, 99.5)),
                        size=float((np.percentile(x, 99.5) - x.min()) / 50)),
        marker=dict(color=t["BLUE_450"], line=dict(color=t["SURFACE"], width=0.6)),
        hovertemplate="$%{x}<br>%{y:,} futures<extra></extra>", showlegend=False))
    fig.add_vrect(x0=low, x1=high, fillcolor=t["BLUE_200"], opacity=0.7, line_width=0, layer="below")
    labels = ([("bad case", "1 in 10 below"), ("typical", "half above/below"), ("good case", "1 in 10 above")]
              if plain else [("P10", ""), ("Median", ""), ("P90", "")])
    for v, (name, words) in zip((p10, med, p90), labels):
        fig.add_vline(x=v, line=dict(color=t["INK"], width=1, dash="dot"))
        fig.add_annotation(x=v, y=1, yref="paper", yanchor="top", xanchor="left", showarrow=False,
                           text=f"<b>{name}</b> ${v / 1e3:,.0f}k" + (f"<br>{words}" if words else ""),
                           font=dict(size=11, color=t["INK"]), bgcolor=_rgba(t["SURFACE"], 0.85), align="left")
    title = (f"How much could the facility get in {res.timeline.valuation_year}?" if plain
             else f"Facility contribution at Jan {res.timeline.valuation_year} (nominal)")
    _layout(fig, t, title, f"Bars = how many of {res.n:,} simulated futures land at each amount. Shaded: co-sponsor "
                           f"range ${low / 1e3:,.0f}k–${high / 1e3:,.0f}k", height=400)
    _money_axis(fig, "x")
    fig.update_yaxes(title_text="futures", showticklabels=not plain)
    return fig


def whatif_chart(stress: pd.DataFrame, picks: list[tuple[str, str]], theme: str = "clean") -> go.Figure:
    t = THEMES[theme]
    rows = stress.set_index("scenario")
    picks = [(k, label) for k, label in picks if k in rows.index]
    vals, texts, colors, hovers = [], [], [], []
    for k, label in picks:
        r = rows.loc[k]
        v = float(r["facility_contribution"])
        if bool(r["all_bills_paid"]):
            status, c = "✓ all bills paid", t["UP"]
        elif bool(r["backstop_covers"]):
            status, c = "✓ all bills paid (safety net used)", t["UP"]
        else:
            status, c = "✗ bills short", t["CRITICAL"]
        vals.append(v)
        texts.append(f"${v / 1e3:,.0f}k · {status}")
        colors.append(c)
        hovers.append(f"<b>{label}</b><br>{r['description']}<br>facility ${v:,.0f} · top-up "
                      f"${float(r['topup_2033']):,.0f} · unpaid before safety net ${float(r['unpaid_bill_dollars']):,.0f}")
    labels = [label for _, label in picks]
    fig = go.Figure(go.Bar(x=vals, y=labels, orientation="h", marker_color=t["BLUE_450"], text=texts,
                           textposition="outside", textfont=dict(color=colors, size=11), cliponaxis=False,
                           hovertext=hovers, hoverinfo="text", showlegend=False))
    _layout(fig, t, "What if things go wrong?", "One fixed future per row; bars = money to the facility in 2033",
            height=60 * len(picks) + 120)
    fig.update_yaxes(autorange="reversed", showgrid=False, tickfont=dict(color=t["INK"], size=12))
    fig.update_xaxes(showgrid=True, showline=False)
    fig.update_xaxes(range=[0, max(vals) * 2.15])
    _money_axis(fig, "x")
    return fig


# ------------------------------------------------------------------ detail ----

def _fan(fig: go.Figure, t: dict, x, paths: np.ndarray, inner=(25, 75), outer=(10, 90), money_fmt=",.0f") -> None:
    q = np.percentile(paths, [outer[0], inner[0], 50, inner[1], outer[1]], axis=0)
    _band(fig, x, q[0], q[4], t["BLUE_200"], f"P{outer[0]}–P{outer[1]}")
    _band(fig, x, q[1], q[3], t["BLUE_300"], f"P{inner[0]}–P{inner[1]}")
    fig.add_trace(go.Scatter(x=x, y=q[2], mode="lines+markers", line=dict(width=2.4, color=t["BLUE_600"]),
                             marker=dict(size=5), name="median",
                             customdata=np.column_stack([q[0], q[1], q[3], q[4]]),
                             hovertemplate=(f"%{{x}}<br>median $%{{y:{money_fmt}}}<br>"
                                            f"P{inner[0]}–P{inner[1]}: $%{{customdata[1]:{money_fmt}}}–$%{{customdata[2]:{money_fmt}}}<br>"
                                            f"P{outer[0]}–P{outer[1]}: $%{{customdata[0]:{money_fmt}}}–$%{{customdata[3]:{money_fmt}}}"
                                            "<extra></extra>")))


def fan_chart(res: Results, theme: str = "clean") -> go.Figure:
    t = THEMES[theme]
    tl = res.timeline
    years = list(range(tl.contribution_year, tl.valuation_year + 1))
    fig = go.Figure()
    _fan(fig, t, years, res.growth_path_after_topup)
    _layout(fig, t, f"Growth bucket value, Jan {years[0]}–Jan {years[-1]} (nominal)",
            f"{res.n:,} paths. Jan {years[-1]} is after the bill top-up. Hover for the bands.")
    fig.update_xaxes(dtick=1)
    _money_axis(fig)
    fig.update_layout(hovermode="x")
    return fig


def buffer_chart(res: Results, theme: str = "clean") -> go.Figure:
    t = THEMES[theme]
    years = list(res.timeline.buffer_years)
    fig = go.Figure()
    _fan(fig, t, years, res.buffer_path, inner=(25, 75), outer=(5, 95))
    fig.add_hline(y=0, line=dict(color=t["INK_2"], width=1))
    _layout(fig, t, "T-bill reserve each Jan 1 (after that day's bill)",
            f"Includes the Jan {res.timeline.valuation_year} top-up from the growth bucket")
    fig.update_xaxes(dtick=2)
    _money_axis(fig)
    fig.update_layout(hovermode="x")
    return fig


def bills_chart(res: Results, theme: str = "clean") -> go.Figure:
    t = THEMES[theme]
    years = [str(y) for y in res.timeline.bill_years]
    p5, p50, p95 = np.percentile(res.rung_payout, [5, 50, 95], axis=0)
    sf = res.ladder_only_shortfall
    short = (sf > 1e-6).mean(axis=0)
    med_short = [float(np.median(sf[sf[:, k] > 1e-6, k])) if short[k] > 0 else 0.0 for k in range(len(years))]
    fig = go.Figure(go.Scatter(
        x=years, y=p50, mode="markers", marker=dict(size=10, color=t["BLUE_600"], line=dict(color=t["SURFACE"], width=2)),
        error_y=dict(type="data", symmetric=False, array=p95 - p50, arrayminus=p50 - p5, color=t["BLUE_300"],
                     thickness=5, width=0),
        customdata=np.column_stack([p5, p95, short, med_short]), name="rung payout (median, P5–P95)",
        hovertemplate=("%{x}<br>median payout $%{y:,.0f}<br>P5–P95 $%{customdata[0]:,.0f}–$%{customdata[1]:,.0f}"
                       "<br>ladder alone short in %{customdata[2]:.0%} of futures"
                       "<br>median shortfall then $%{customdata[3]:,.0f}<extra></extra>")))
    fig.add_hline(y=res.bill_amount, line=dict(color=t["INK"], width=1.2, dash="dot"),
                  annotation_text=f"bill ${res.bill_amount / 1e3:,.0f}k", annotation_position="top right")
    _layout(fig, t, "Ladder payout vs. bill, by bill date",
            "Dot = median payout, bar = P5–P95. Hover for how often each bill falls short on the ladder alone.")
    fig.update_yaxes(tickprefix="$", tickformat=",.0f")
    return fig


def shortfall_chart(res: Results, theme: str = "clean") -> go.Figure:
    t = THEMES[theme]
    x = res.ladder_only_total_shortfall[~res.ladder_only_all_paid]
    fig = go.Figure()
    if len(x):
        fig.add_trace(go.Histogram(x=x, nbinsx=50, marker=dict(color=t["BLUE_450"], line=dict(color=t["SURFACE"], width=0.6)),
                                   hovertemplate="$%{x}<br>%{y:,} futures<extra></extra>", showlegend=False))
        for name, v in (("median", np.median(x)), ("P90", np.percentile(x, 90))):
            fig.add_vline(x=v, line=dict(color=t["INK_2"], width=1, dash="dot"),
                          annotation_text=f"{name} ${v / 1e3:,.1f}k", annotation_position="top right",
                          annotation_font=dict(size=11, color=t["INK"]))
    _layout(fig, t, "Ladder-only shortfall: total unpaid bill dollars",
            f"{len(x):,} of {res.n:,} paths ({len(x) / res.n:.0%}) where ladder + buffer alone fall short; "
            "the growth bucket covers these")
    _money_axis(fig, "x")
    fig.update_yaxes(title_text="futures")
    return fig


def stress_chart(stress: pd.DataFrame, mc_median: float, theme: str = "clean") -> go.Figure:
    t = THEMES[theme]
    df = stress.copy()
    texts, colors = [], []
    for _, r in df.iterrows():
        txt = f"${r['facility_contribution'] / 1e3:,.0f}k"
        if r["topup_2033"] > 0.5:
            txt += f"  (after ${r['topup_2033'] / 1e3:,.1f}k top-up)"
        if not r["all_bills_paid"]:
            txt += "  bills short" + (" · safety net covers" if r["backstop_covers"] else "")
        texts.append(txt)
        colors.append(t["CRITICAL"] if not r["all_bills_paid"] else t["INK"])
    fig = go.Figure(go.Bar(
        x=df["facility_contribution"], y=df["scenario"], orientation="h", marker_color=t["BLUE_450"],
        text=texts, textposition="outside", textfont=dict(color=colors, size=11), cliponaxis=False,
        hovertext=[f"<b>{r['scenario']}</b><br>{r['description']}" for _, r in df.iterrows()], hoverinfo="text",
        showlegend=False))
    fig.add_vline(x=mc_median, line=dict(color=t["INK"], width=1, dash="dot"),
                  annotation_text=f"Monte Carlo median ${mc_median / 1e3:,.0f}k", annotation_position="bottom")
    _layout(fig, t, "Facility contribution by stress scenario (nominal, after bill top-up)",
            height=34 * len(df) + 150)
    fig.update_yaxes(autorange="reversed", showgrid=False, tickfont=dict(color=t["INK"]))
    fig.update_xaxes(showgrid=True, showline=False)
    fig.update_xaxes(range=[0, float(df["facility_contribution"].max()) * 1.6])
    _money_axis(fig, "x")
    return fig


# -------------------------------------------------------------------- desk ----
# Main-screen charts in the terminal style: price-chart look (right axis, value tags, crosshair).

def _tag(fig: go.Figure, y: float, text: str, bg: str, fg: str = "#ffffff") -> None:
    """A value tag on the right edge, like the last-price tag on a trading chart."""
    fig.add_annotation(x=1, xref="paper", y=y, text=f"<b>{text}</b>", showarrow=False, xanchor="left", xshift=2,
                       font=dict(family=TV_FONT, size=11, color=fg), bgcolor=bg, borderpad=3)


def _spread_tags(tags: list[tuple[float, str, str, str]], gap: float) -> list[tuple[float, str, str, str]]:
    """Nudge value tags apart (lowest first, then upward) so none overlap; gap is in data units."""
    tags = sorted(tags, key=lambda t_: t_[0])
    out, last = [], -np.inf
    for y, text, bg, fg in tags:
        y = max(y, last + gap)
        out.append((y, text, bg, fg))
        last = y
    return out


def desk_paths_chart(m: dict, start_year: int, invested: float, theme: str = "desk",
                     ghost: np.ndarray | None = None, overlay: tuple[str, np.ndarray] | None = None,
                     height: int = 300) -> go.Figure:
    """Growth bucket month by month like a price chart: the typical path as the 'price' with a
    fading area under it, the P10-P90 band, faint sample futures, and value tags on the right.
    ghost: the official run's monthly median, drawn dashed when the inputs are modified (like a
    'compare symbol' line). overlay: (label, value each Jan 1) for one stress scenario's path."""
    t = THEMES[theme]
    muted = t.get("MUTED", t["GRID"])
    months = m["sample"].shape[1]
    x = pd.date_range(f"{start_year}-01-01", periods=months, freq="MS")
    fig = go.Figure()
    end = m["sample"][:, -1]
    fade = 0.16 if overlay is not None else 0.38
    for i, row in enumerate(m["sample"]):
        up = end[i] >= invested
        fig.add_trace(go.Scatter(x=x, y=row, mode="lines", hoverinfo="skip", showlegend=False,
                                 line=dict(width=0.9, color=_rgba(t["UP"] if up else t["CRITICAL"], fade))))
    for q, name in ((m["p90"], "P90"), (m["p10"], "P10")):
        fig.add_trace(go.Scatter(x=x, y=q, mode="lines", name=name, showlegend=False,
                                 line=dict(width=1, color=t["INK_2"], dash="dot"),
                                 hovertemplate=f"{name} $%{{y:,.0f}}<extra></extra>"))
    fig.add_trace(go.Scatter(
        x=x, y=m["median"], mode="lines", name="P50", showlegend=False, line=dict(width=2, color=t["BLUE_450"]),
        fill="tozeroy", fillgradient=dict(type="vertical", colorscale=[[0, _rgba(t["BLUE_450"], 0.0)],
                                                                         [1, _rgba(t["BLUE_450"], 0.28)]]),
        hovertemplate="P50 $%{y:,.0f}<extra></extra>"))
    ys = [m["p10"].min(), invested]
    tags = [(m["p90"][-1], f"P90 {m['p90'][-1] / 1e3:,.0f}k", muted, t["INK"]),
            (m["median"][-1], f"P50 {m['median'][-1] / 1e3:,.0f}k", t["BLUE_450"], "#ffffff"),
            (m["p10"][-1], f"P10 {m['p10'][-1] / 1e3:,.0f}k", muted, t["INK"]),
            (invested, f"Invested {invested / 1e3:,.0f}k", t["INK_2"], "#ffffff")]
    if ghost is not None:
        fig.add_trace(go.Scatter(x=x, y=ghost, mode="lines", name="Official P50", showlegend=False,
                                 line=dict(width=1.6, color="#ffffff", dash="dash"), opacity=0.55,
                                 hovertemplate="Official P50 $%{y:,.0f}<extra></extra>"))
        tags.append((ghost[-1], f"Official {ghost[-1] / 1e3:,.0f}k", "#5d606b", "#ffffff"))
    if overlay is not None:
        label, path = overlay
        xs = pd.date_range(f"{start_year}-01-01", periods=len(path), freq="YS")
        fig.add_trace(go.Scatter(x=xs, y=path, mode="lines+markers", name=label, showlegend=False,
                                 line=dict(width=2.2, color="#ff9800"), marker=dict(size=6),
                                 hovertemplate=f"{label} $%{{y:,.0f}}<extra></extra>"))
        tags.append((path[-1], f"{label[:22]} {path[-1] / 1e3:,.0f}k", "#ff9800", "#131722"))
        ys.append(float(np.min(path)))
    fig.add_hline(y=invested, line=dict(color=t["INK_2"], width=1, dash="dash"))
    lo, hi = float(min(min(ys), m["sample"].min())) * 0.94, float(m["p90"].max()) * 1.3   # extreme paths run off the top
    for y, text, bg, fg in _spread_tags(tags, gap=(hi - lo) * 0.08):
        _tag(fig, y, text, bg, fg)
    _layout(fig, t, "", height=height)
    fig.update_layout(title=None, hovermode="x unified", margin=dict(l=8, r=96, t=30, b=6),
                      hoverlabel=dict(bgcolor="#1e222d", bordercolor=muted,
                                      font=dict(family=TV_FONT, size=11, color=t["INK"])))
    fig.update_yaxes(side="right", range=[lo, hi])
    _money_axis(fig)
    fig.update_xaxes(rangeselector=dict(
        buttons=[dict(count=1, label="1Y", step="year", stepmode="backward"),
                 dict(count=3, label="3Y", step="year", stepmode="backward"), dict(step="all", label="All")],
        x=0, y=1.02, xanchor="left", yanchor="bottom", bgcolor=t["SURFACE"], activecolor=muted,
        bordercolor=t["GRID"], borderwidth=1, font=dict(family=TV_FONT, size=11, color=t["INK"])))
    return fig


def desk_facility_chart(res: Results, low: float, high: float, theme: str = "desk",
                        ghost: np.ndarray | None = None, height: int = 300) -> go.Figure:
    """Facility gift distribution: bars inside the co-sponsor range in the accent colour, P10 /
    P50 / P90 marked along the top. ghost: the official run's facility amounts, drawn as an
    outline on the same bins when the inputs are modified."""
    t = THEMES[theme]
    x = res.facility
    both = x if ghost is None else np.concatenate([x, ghost])
    edges = np.histogram_bin_edges(both, bins=42, range=(float(both.min()), float(np.percentile(both, 99.5))))
    counts = np.histogram(x, bins=edges)[0]
    mids = (edges[:-1] + edges[1:]) / 2
    inside = (mids >= low) & (mids <= high)
    fig = go.Figure(go.Bar(
        x=mids, y=counts / len(x), width=(edges[1] - edges[0]) * 0.86, showlegend=False, name="This run",
        marker=dict(color=[t["BLUE_450"] if i else t.get("MUTED", t["GRID"]) for i in inside], line_width=0),
        customdata=np.column_stack([edges[:-1], edges[1:], counts]),
        hovertemplate="$%{customdata[0]:,.0f}–$%{customdata[1]:,.0f}<br>%{customdata[2]:,} futures "
                      "(%{y:.1%})<extra></extra>"))
    if ghost is not None:
        g = np.histogram(ghost, bins=edges)[0] / len(ghost)
        fig.add_trace(go.Scatter(x=edges, y=np.append(g, g[-1]), mode="lines", line=dict(shape="hv", width=1.4,
                                 color="#ffffff", dash="dash"), opacity=0.6, name="Official", showlegend=False,
                                 hovertemplate="Official %{y:.1%}<extra></extra>"))
    for q, name in zip(np.percentile(x, [10, 50, 90]), ("P10", "P50", "P90")):
        fig.add_vline(x=q, line=dict(color=t["INK"] if name == "P50" else t["INK_2"], width=1, dash="dot"))
        fig.add_annotation(x=q, y=1, yref="paper", yanchor="bottom", showarrow=False,
                           text=f"{name} {q / 1e3:,.0f}k", font=dict(family=TV_FONT, size=11, color=t["INK"]))
    _layout(fig, t, "", height=height)
    fig.update_layout(title=None, bargap=0, margin=dict(l=8, r=8, t=30, b=6))
    fig.update_yaxes(tickformat=".0%", side="right")
    _money_axis(fig, "x")
    return fig


def desk_bill_chart(res: Results, k: int, theme: str = "desk", height: int = 150) -> go.Figure:
    """One bill's own rung payout across the futures: red where the rung pays less than the bill
    (the cash reserve, then the 2033 top-up, covers the gap), green at or above it."""
    t = THEMES[theme]
    x = res.rung_payout[:, k]
    bill = res.bill_amount
    counts, edges = np.histogram(x, bins=36)
    mids = (edges[:-1] + edges[1:]) / 2
    fig = go.Figure(go.Bar(
        x=mids, y=counts / len(x), width=(edges[1] - edges[0]) * 0.86, showlegend=False,
        marker=dict(color=[t["CRITICAL"] if v < bill else t["UP"] for v in mids], line_width=0),
        customdata=np.column_stack([edges[:-1], edges[1:]]),
        hovertemplate="Rung pays $%{customdata[0]:,.0f}–$%{customdata[1]:,.0f}: %{y:.1%} of futures<extra></extra>"))
    fig.add_vline(x=bill, line=dict(color="#ffffff", width=1, dash="dash"))
    fig.add_annotation(x=bill, y=1, yref="paper", yanchor="bottom", showarrow=False, text=f"Bill {bill / 1e3:,.0f}k",
                       font=dict(family=TV_FONT, size=11, color=t["INK"]))
    _layout(fig, t, "", height=height)
    fig.update_layout(title=None, bargap=0, margin=dict(l=8, r=8, t=22, b=4))
    fig.update_yaxes(tickformat=".0%", side="right", nticks=3)
    _money_axis(fig, "x")
    return fig
