"""Streamlit dashboard for the client plan Monte Carlo.

    streamlit run app.py

All simulation logic lives in the mcsim package; this file only collects
inputs, calls it, and lays out the results.
"""
from __future__ import annotations

import html
import json
import re
import time
from datetime import datetime
from dataclasses import dataclass

import numpy as np
import pandas as pd
import streamlit as st

from mcsim import analysis, desk, growth, iplots, sparks
from mcsim.config import Assumptions, load_config
from mcsim.model import draw_random, ladder_costs, load_ladder, run_monte_carlo

st.set_page_config(page_title="Laura's plan review", layout="wide", initial_sidebar_state="collapsed")

SAMPLE_PATHS = 40                                     # sample futures drawn in the stock-style chart
OVERVIEW_STRESS = [("normal", "Markets as expected"), ("bad", "Weak markets (1-in-10 bad)"),
                   ("crash_2028", "Stocks drop 40% in 2028"), ("low_rates_2010s", "Cash earns 0.5% for 15 years"),
                   ("combined_low_rates_p10", "Worst tested: low rates + weak markets")]

REPORT = ".st-key-report"                                     # the Report tab: memo on a white sheet
DESK_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Source+Serif+4:opsz,wght@8..60,400;8..60,600;8..60,700&display=swap');
/* TradingView's dark palette and its charting library's font stack; Finviz's heatmap scale. */
:root { --bg:#131722; --bar:#1e222d; --line:#2a2e39; --line-2:#222632; --ink:#d1d4dc; --ink-2:#787b86;
        --ink-3:#5d606b; --white:#ffffff; --acc:#2962ff; --up:#089981; --down:#f23645; --amber:#ff9800;
        --sans: -apple-system, BlinkMacSystemFont, 'Trebuchet MS', Roboto, Ubuntu, sans-serif;
        --serif:'Source Serif 4', Georgia, 'Times New Roman', serif; }
html, body, .stApp, .stMarkdown, p, li, label, input, textarea, select, button, [data-testid="stCaptionContainer"] {
  font-family: var(--sans) !important; }
.stApp { background: var(--bg); }
[data-testid="stAppDeployButton"], [data-testid="stMainMenu"], #MainMenu, footer { display:none !important; }
header[data-testid="stHeader"] { background: transparent; height: 2.2rem; }
.block-container { max-width: none !important; padding: .6rem 1rem 3rem !important; }
.st-key-cmdbar { padding-left: 44px !important; }          /* room for the sidebar opener in the corner */
h1, h2, h3, h4 { color: var(--white) !important; font-family: var(--sans) !important; font-weight:600 !important;
                 font-size: .95rem !important; letter-spacing: 0; }
.stMarkdown p, .stMarkdown li { font-size: .84rem; line-height: 1.55; color: var(--ink); }
.stMarkdown strong { color: var(--white); font-weight: 600; }
[data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] p { color: var(--ink-2) !important;
  font-size: .76rem !important; line-height: 1.5 !important; }
section[data-testid="stSidebar"] { background: var(--bar); border-right: 1px solid var(--line); }
[data-testid="stMetric"] { background: transparent !important; border: 1px solid var(--line) !important;
                           border-radius: 4px !important; padding: 8px 12px !important; box-shadow: none !important; }
[data-testid="stMetricLabel"] p { color: var(--ink-2) !important; font-size: .76rem !important; }
[data-testid="stMetricValue"] { color: var(--white) !important; font-weight: 600; font-variant-numeric: tabular-nums;
                                font-size: clamp(1rem, 1.4vw, 1.35rem) !important; }
[data-testid="stMetricValue"] *, [data-testid="stMetricLabel"] * { white-space: normal !important;
  overflow: visible !important; text-overflow: clip !important; }
[data-testid="stVerticalBlockBorderWrapper"], [data-testid="stExpander"] details, [data-testid="stAlert"],
[data-testid="stDataFrame"] { border-radius: 4px !important; }
[data-testid="stDataFrame"] { border: 1px solid var(--line); }
/* tabs: plain text, white when selected with a thin blue rule, as on TradingView and Yahoo */
[role="tablist"] { gap: 22px !important; border-bottom: 1px solid var(--line); }
[data-testid="stTab"] { background: transparent !important; border: none !important; border-radius: 0 !important;
                        padding: 8px 0 !important; border-bottom: 2px solid transparent !important; }
[data-testid="stTab"] p { color: var(--ink-2) !important; font-weight: 500; font-size: .86rem !important; }
[data-testid="stTab"]:hover p { color: var(--white) !important; }
[data-testid="stTab"][aria-selected="true"] { border-bottom: 2px solid var(--acc) !important; }
[data-testid="stTab"][aria-selected="true"] p { color: var(--white) !important; }
.stButton button, .stDownloadButton button { border-radius: 4px !important; background: var(--bar) !important;
  color: var(--ink) !important; border: 1px solid var(--line) !important; font-size: .8rem !important; font-weight: 500; }
.stButton button:hover, .stDownloadButton button:hover { background: #2a2e39 !important; color: var(--white) !important; }
/* top toolbar: symbol header on the left, inputs, reset */
.st-key-cmdbar { background: var(--bar); border: 1px solid var(--line); border-radius: 4px 4px 0 0; padding: 6px 12px 8px; gap: 0 !important; }
.st-key-cmdbar label p { font-size: .72rem !important; color: var(--ink-2) !important; }
.st-key-cmdbar [data-baseweb="input"], .st-key-cmdbar [data-baseweb="select"] > div { border-radius: 4px !important;
  background: var(--bg) !important; border-color: var(--line) !important; font-size: .84rem !important; min-height: 32px; }
.st-key-cmdbar input { font-size: .84rem !important; font-variant-numeric: tabular-nums; }
.st-key-cmdbar .stButton button { margin-top: 21px; height: 34px; width: 100%; }
.st-key-cmdbar [data-testid="stNumberInputStepUp"], .st-key-cmdbar [data-testid="stNumberInputStepDown"] { display:none; }
.sym-head { padding-top: 3px; line-height: 1.3; }
.sym-head .name { color: var(--white); font-weight: 600; font-size: 1.02rem; }
.sym-head .meta { color: var(--ink-2); font-size: .74rem; margin-top: 2px; }
.sym-head .badge { display:inline-block; font-size:.68rem; color: var(--ink); border:1px solid var(--line);
                   border-radius:3px; padding:0 5px; margin-left:6px; vertical-align: 2px; font-weight: 500; }
/* quote strip (Yahoo/Google Finance market summary) */
.tk-row { display:grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); background: var(--bg);
          border:1px solid var(--line); border-top:none; }
.tk { padding: 9px 14px 10px; border-left: 1px solid var(--line); min-width:0; }
.tk:first-child { border-left:none; }
.tk.lead { background: rgba(41,98,255,.07); box-shadow: inset 0 2px 0 #2962ff; }
.tk.lead .sym { color: var(--ink); font-weight: 600; }
.tk .sym { font-size:.74rem; color: var(--ink-2); line-height: 1.25; min-height: 2.5em; }   /* labels wrap, never cut */
.tk .px { font-size: clamp(1.05rem, 1.4vw, 1.4rem); font-weight:600; color: var(--white); margin-top:2px; white-space: nowrap;
          font-variant-numeric: tabular-nums; }
.tk .chg { font-size:.76rem; color: var(--ink-2); margin-top:1px; white-space: nowrap; overflow:hidden;
           text-overflow: ellipsis; font-variant-numeric: tabular-nums; }
.up { color: var(--up) !important; } .down { color: var(--down) !important; } .warn { color: var(--amber) !important; }
.acc { color: #5b8cff !important; } .muted { color: var(--ink-3) !important; }
.sig { font-size:.8rem; color: var(--ink); background: var(--bg); border:1px solid var(--line); border-top:none;
       border-radius: 0 0 4px 4px; padding: 7px 14px; margin-bottom: 10px; white-space: nowrap; overflow:hidden;
       text-overflow: ellipsis; }
.sig .tag { color: var(--up); font-weight:600; margin-right:10px; }
.sig .tag::before { content:""; display:inline-block; width:7px; height:7px; border-radius:50%; background: currentColor;
                    margin-right:6px; vertical-align: 1px; }
.sig .tag.mod { color: var(--amber); }
/* panels: TradingView widgets */
[class*="st-key-pn_"] { background: var(--bg); border: 1px solid var(--line) !important; border-radius: 4px !important;
                        padding: 0 0 4px !important; gap: 0 !important; }
[class*="st-key-pn_"] [data-testid="stMarkdown"], [class*="st-key-pn_"] .stMarkdown { margin-bottom: 0 !important; }
[class*="st-key-pn_"] [data-testid="stMarkdownContainer"] { margin-bottom: 0 !important; }
.pn-head { display:flex; justify-content:space-between; align-items:baseline; gap:12px; padding:9px 12px 4px; }
.pn-title { color: var(--white); font-weight:600; font-size:.92rem; white-space:nowrap; }
.pn-stats { color: var(--ink-2); font-size:.78rem; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;
            font-variant-numeric: tabular-nums; }
.pn-stats span { margin-left: 14px; } .pn-stats b { color: var(--ink); font-weight:500; }
.pn-sig { font-size:.76rem; color: var(--ink-2); padding: 0 12px 4px; }
.pn-sig b { color: var(--ink); font-weight:500; }
.pn-body { padding: 4px 12px 6px; }
/* tables: TradingView screener */
.tt { width:100%; border-collapse:collapse !important; font-size:.8rem; border:none !important; font-variant-numeric: tabular-nums; }
.tt th { text-align:right; color: var(--ink-2); font-weight:400; font-size:.74rem; padding:6px 8px !important; border:none !important;
         border-bottom:1px solid var(--line) !important; white-space:nowrap; background: transparent !important; }
.tt td { text-align:right; padding:6px 8px !important; border:none !important; border-bottom:1px solid var(--line-2) !important;
         color: var(--ink); white-space:nowrap; }
.tt tr { border:none !important; background: transparent !important; }
.tt .l { text-align:left; } .tt .w { white-space: normal; min-width: 160px; }
.tt tbody tr:hover td { background: #1e222d; }
.tt .chip { display:inline-block; padding:1px 7px; border-radius:3px; font-size:.72rem; font-weight:500; }
.tt .chip.up { background: rgba(8,153,129,.18); } .tt .chip.down { background: rgba(242,54,69,.18); }
.tt .chip.warn { background: rgba(255,152,0,.16); }
/* bill heatmap: Finviz map tiles */
.hm { display:grid; grid-template-columns: repeat(5, 1fr); gap:1px; background: var(--bg); }
.hm-t { padding:8px 9px; min-height:76px; color:#fff; text-align:center; display:flex; flex-direction:column; justify-content:center; }
.hm-y { font-weight:700; font-size:.98rem; } .hm-i { font-size:.7rem; opacity:.85; }
.hm-v { font-size:.92rem; font-weight:600; margin-top:3px; font-variant-numeric: tabular-nums; }
.hm-n { font-size:.66rem; opacity:.85; }
.hm-legend { display:flex; gap:1px; margin-top:8px; font-size:.68rem; color:#fff; }
.hm-legend span { flex:1; text-align:center; padding:2px 0; }
/* ⓘ hover notes (instead of explanation lines under every title) */
.tip { position: relative; display:inline-block; margin-left:7px; color: var(--ink-3); font-size:.8rem; cursor: help;
       font-weight: 400; }
.tip:hover { color: var(--ink); }
.tip:hover::after { content: attr(data-tip); position:absolute; left:-8px; top: 130%; z-index: 1000; width: 300px;
                    white-space: normal; background: #1e222d; color: var(--ink); border:1px solid var(--line);
                    border-radius:4px; padding: 8px 10px; font-size:.76rem; line-height:1.45; font-weight:400;
                    box-shadow: 0 6px 18px rgba(0,0,0,.45); }
.pn-sum { color: var(--ink-2); font-size:.76rem; padding: 6px 12px 2px; font-variant-numeric: tabular-nums; }
.pn-sum b { color: var(--ink); font-weight: 500; }
.pn-scroll { max-height: 232px; overflow:auto; padding: 0 12px 4px; }
.pn-scroll .tt th { position: sticky; top: 0; background: var(--bg) !important; z-index: 1; }
.tt tr.focus td { background: rgba(41,98,255,.16) !important; }
.tt tr.focus td:first-child { box-shadow: inset 2px 0 0 #2962ff; }
/* tabbed bottom panel (TradingView's bottom panel) */
.st-key-pn_book { background: var(--bg); border: 1px solid var(--line) !important; border-radius: 4px !important;
                  padding: 0 0 4px !important; }
.st-key-pn_book [role="tablist"] { padding: 0 12px; gap: 18px !important; }
.st-key-pn_book [data-testid="stTab"] p { font-size: .84rem !important; font-weight: 600; }
.st-key-pn_book [data-testid="stDataFrame"] { margin: 0 12px; border: none; }
/* bill map tiles: buttons coloured per tile */
[class*="st-key-tile_"] button { border: none !important; border-radius: 0 !important; min-height: 66px; padding: 4px 2px !important;
                                 color: #ffffff !important; }
[class*="st-key-tile_"] button:hover { filter: brightness(1.15); color:#fff !important; }
[class*="st-key-tile_"] button p { font-size: .68rem !important; line-height: 1.3 !important; color:#fff !important;
                                   white-space: nowrap; }
[class*="st-key-tile_"] button, [class*="st-key-tile_"] button * { overflow: visible !important; text-overflow: clip !important;
                                                               max-width: none !important; }
[class*="st-key-tile_"] button p strong { font-size: .9rem; }
.st-key-pn_heat [data-testid="stHorizontalBlock"] { gap: 1px !important; padding: 0 12px; margin-bottom: 1px;
                                                    flex-wrap: nowrap !important; }
.st-key-pn_heat [data-testid="stColumn"] { min-width: 0 !important; flex: 1 1 0 !important; width: auto !important; }
.st-key-pn_heat .hm-legend { margin-top: 18px; }
.wl-legend { font-size: .7rem; color: var(--ink-2); line-height: 1.5; columns: 1; }
.wl-legend b { color: var(--ink); font-weight: 600; display:inline-block; min-width: 34px; }
.st-key-pn_watch [data-testid="stDataFrame"] { margin: 4px 8px 0; border: none; }
.tk-row.q { border-top: 1px solid var(--line); border-radius: 4px; margin-bottom: 8px; }
.note-warn { border-left: 3px solid var(--amber); background: rgba(255,152,0,.08); color: var(--ink); padding: 7px 12px;
             font-size: .8rem; margin-bottom: 8px; border-radius: 0 4px 4px 0; }
.note-warn b { color: var(--amber); }
[class*="st-key-pn_"] [data-testid="stDataFrame"] { margin: 4px 12px 8px; border: none; }
[class*="st-key-pn_"] .stDownloadButton, [class*="st-key-pn_"] [data-testid="stExpander"] { margin: 0 12px 8px; }
[class*="st-key-pn_"] [role="tablist"] { padding: 0 12px; }
.pn-text { padding: 4px 12px 8px; font-size: .82rem; color: var(--ink); line-height: 1.55; }
.pn-text b { color: var(--white); font-weight: 600; }
/* status bar */
.sbar { position: fixed; left:0; right:0; bottom:0; height:26px; z-index: 999990; background: var(--bar);
        border-top:1px solid var(--line); display:flex; align-items:center; gap:20px; padding: 0 14px;
        font-size:.74rem; color: var(--ink-2); }
.sbar b { font-weight:500; color: var(--ink); } .sbar .r { margin-left:auto; }
.sbar .dot { display:inline-block; width:7px; height:7px; border-radius:50%; margin-right:6px; vertical-align: 0; }

/* ---- Report tab: the memo, on a white sheet ---- */
""" + f"""
{REPORT} {{ background:#ffffff; max-width:1280px; margin: 14px auto 0; padding: 2.4rem 3rem 2.6rem !important;
           --page:#f3f1ec; --paper:#ffffff; --rule:#d9d6cf; --hair:#ebe8e2; --ink:#16191f; --ink-2:#5c6370; --ink-3:#8b919c;
           --navy:#1f3a5f; --navy-soft:#e3e9f1; --red:#b42318; --red-soft:#fbeae8; }}
{REPORT} .stMarkdown p, {REPORT} .stMarkdown li {{ color:#2a2f38; font-size:.92rem; line-height:1.65; }}
{REPORT} .stMarkdown strong {{ color:#16191f; }}
{REPORT} h3 {{ color:#16191f !important; font-family: var(--serif) !important; font-size:1.3rem !important;
              text-transform:none; letter-spacing:-.005em; }}
{REPORT} [data-testid="stCaptionContainer"] p {{ color:#5c6370 !important; font-size:.78rem !important; }}
{REPORT} [data-testid="stExpander"] details {{ background:#ffffff; border-color:#d9d6cf !important; }}
{REPORT} [data-testid="stExpander"] summary p, {REPORT} [data-testid="stExpander"] summary span {{ color:#16191f !important; }}
{REPORT} .stDownloadButton button {{ background:#ffffff !important; color:#16191f !important; border-color:#d9d6cf !important; }}
""" + """
.mast { border-bottom: 3px double var(--ink); padding-bottom: 14px; margin-bottom: 26px; }
.mast-top { display:flex; justify-content:space-between; color: var(--ink-2); font-size:.7rem; font-weight:600;
            text-transform:uppercase; letter-spacing:.12em; border-bottom: 1px solid var(--rule); padding-bottom: 8px; }
.mast-title { font-family: var(--serif); font-size: clamp(1.7rem, 3vw, 2.4rem); font-weight: 600; color: var(--ink);
              letter-spacing: -.015em; line-height: 1.15; margin-top: 16px; }
.mast-meta { color: var(--ink-2); font-size: .8rem; margin-top: 6px; }
.mast-meta .mod { color: var(--red); font-weight: 600; }
.kicker { color: var(--navy); font-size:.7rem; font-weight:700; text-transform:uppercase; letter-spacing:.12em; margin-bottom:6px; }
.lead { max-width: 900px; margin-bottom: 24px; }
.lead-text { font-family: var(--serif); font-size: clamp(1.25rem, 2.1vw, 1.65rem); line-height: 1.35; color: var(--ink); }
.lead-sub { color: var(--ink-2); font-size: .92rem; line-height: 1.6; margin-top: 10px; }
.figs { display:grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); border-top: 2px solid var(--ink);
        border-bottom: 1px solid var(--rule); margin-bottom: 22px; }
.fig { padding: 12px 18px 14px; border-left: 1px solid var(--hair); }
.fig:first-child { border-left: none; padding-left: 0; }
.fig.lead .val { color: var(--navy); }
.fig .lbl { color: var(--ink-2); font-size:.68rem; font-weight:600; text-transform:uppercase; letter-spacing:.07em; }
.fig .val { color: var(--ink); font-size: clamp(1.25rem, 1.9vw, 1.75rem); font-weight:600; letter-spacing:-.015em;
            margin: 6px 0 4px; font-variant-numeric: tabular-nums; }
.fig .sub { color: var(--ink-2); font-size:.76rem; line-height:1.45; }
.fig .note { color: var(--ink-3); font-size:.7rem; line-height:1.4; margin-top:6px; }
.neg { color: var(--red) !important; font-weight:600; }
.ex-head { border-top: 1px solid var(--ink); padding-top: 10px; margin: 18px 0 2px; }
.ex-num { color: var(--navy); font-size:.68rem; font-weight:700; text-transform:uppercase; letter-spacing:.12em; }
.ex-title { font-family: var(--serif); font-size: 1.22rem; font-weight: 600; color: var(--ink); line-height: 1.3; margin-top: 3px; }
.ex-sub { color: var(--ink-2); font-size: .8rem; margin-top: 3px; }
.ex-src { color: var(--ink-3); font-size: .7rem; border-top: 1px solid var(--hair); padding-top: 5px; margin-top: 2px; }
.bm-grid { display:grid; grid-template-columns: repeat(5, 1fr); gap:3px; margin-top: 12px; }
.bm-tile { padding:10px 10px; min-height:92px; }
.bm-year { font-weight:700; font-size:1.05rem; font-variant-numeric: tabular-nums; }
.bm-sec { font-size:.7rem; opacity:.85; margin-bottom:6px; }
.bm-stat { font-size:.68rem; line-height:1.4; font-variant-numeric: tabular-nums; }
.bm-net { color: var(--red); font-weight:600; background: #fff; padding: 0 3px; display:inline-block; margin-top:2px; }
.bm-legend { display:flex; align-items:center; gap:8px; margin-top:10px; color: var(--ink-2); font-size:.7rem; }
.bm-scale { flex:1; height:5px; background: linear-gradient(90deg, #eef2f7, #c9d6e7 17%, #6e8aaf 50%, #1f3a5f); }
.ev-table { width:100%; border-collapse:collapse; font-size:.82rem; border-top: 2px solid var(--ink); }
.ev-table, .ev-table tr { border-left:none !important; border-right:none !important; }
.ev-table td { padding:7px 6px; border:none !important; border-bottom:1px solid var(--hair) !important;
               vertical-align:top; color:#2a2f38; }
.ev-date { color: var(--ink-2); white-space:nowrap; font-variant-numeric: tabular-nums; }
.ev-kind { color: var(--navy); font-size:.64rem; font-weight:700; letter-spacing:.08em; white-space:nowrap; padding-top:9px !important; }
.ev-amt { text-align:right; font-weight:600; white-space:nowrap; font-variant-numeric: tabular-nums; }
.cl-notice { border-left: 3px solid var(--red); background: var(--red-soft); color: #7a1a12; padding: 8px 14px;
             font-size:.8rem; margin: -8px 0 18px; }
</style>
"""
st.markdown(DESK_CSS, unsafe_allow_html=True)


# ------------------------------------------------------------- controls ----

@dataclass(frozen=True)
class Control:
    key: str        # session-state key
    config: str     # dotted config key
    label: str
    kind: str       # slider | toggle | runs | choice
    scale: float = 1.0
    lo: float = 0.0
    hi: float = 1.0
    step: float = 0.1
    fmt: str = "%.1f"
    help: str = ""
    unit: str = "%"
    options: tuple = ()


RUN_OPTIONS = [1_000, 2_000, 5_000, 10_000, 20_000, 50_000]
CONTROLS = [
    Control("us_mean", "growth.us_mean", "US stocks: expected return (%)", "slider", 100, 0.0, 15.0, 0.25, "%.2f"),
    Control("us_vol", "growth.us_vol", "US stocks: volatility (%)", "slider", 100, 0.0, 35.0, 0.5, "%.1f"),
    Control("intl_mean", "growth.intl_mean", "Intl stocks: expected return (%)", "slider", 100, 0.0, 15.0, 0.25, "%.2f"),
    Control("intl_vol", "growth.intl_vol", "Intl stocks: volatility (%)", "slider", 100, 0.0, 35.0, 0.5, "%.1f"),
    Control("give_pct", "facility.give_pct", "Give % of Jan 2033 value", "slider", 100, 50.0, 100.0, 1.0, "%.0f"),
    Control("glide", "glide_path.enabled", "Glide path (2031 and 2032 moves to T-bills)", "toggle"),
    Control("yield_shift", "ladder.yield_shift_mean", "Jan 2027 yield shift (pts)", "slider", 100, -2.0, 2.0, 0.05,
            "%+.2f", "Mean parallel shift vs. ladder.csv yields at purchase. Random shocks are added on top."),
    Control("growth_mix", "growth_mix.mix", "Growth mix (2028 growth bucket)", "mix",
            help="G1 is official. G2-G7 are the growth-bucket scenarios from outputs/growth_scenarios.md "
                 "(G8 is G1 with Vanguard returns: use the return sliders)."),
    Control("bond_model", "ladder.bond_payout_model", "Treasury rung payout model", "choice",
            help="face: each rung pays exactly $50k (plan spec). cashflows: actual coupons + principal "
                 "from ladder.csv quantities, reinvested at simulated T-bill rates.",
            options=("cashflows", "face")),
    Control("topup_rule", "waterfall.topup_rule", "Jan 2033 top-up rule", "choice",
            help="rate_rule: move the shortfall assuming reinvestment earns the conservative rate below. "
                 "fixed_rule: always move the fixed amount below.",
            options=("rate_rule", "fixed_rule")),
    Control("rate_rule_rate", "waterfall.rate_rule_rate", "Rate rule: conservative rate (%)", "slider",
            100, 0.0, 5.0, 0.25, "%.2f"),
    Control("fixed_rule_amount", "waterfall.fixed_rule_amount", "Fixed rule: amount moved ($)", "slider",
            1, 0.0, 30_000.0, 200.0, "%d", unit="$"),
    Control("backstop_amount", "waterfall.backstop_amount", "Backstop from Laura's cushion ($)", "slider",
            1, 0.0, 30_000.0, 500.0, "%d", unit="$",
            help="Set aside from Laura's cushion in Jan 2033, held in T-bills, used only for unpaid bills. "
                 "Does not change the facility contribution."),
    Control("n_sims", "simulation.dashboard_n_sims", "Number of runs", "runs"),
]
# Shown in the command bar across the top (short label); the rest stay in the sidebar.
BAR = {"growth_mix": "Scenario · growth mix", "us_mean": "US ret %", "give_pct": "Give %",
       "rate_rule_rate": "Cash rule %", "backstop_amount": "Backstop $", "n_sims": "Paths"}


def inputs_fingerprint() -> str:
    """Hash of config.yaml and the ladder sheet it points to. Part of every cache key,
    so editing either file while the app runs never shows stale results."""
    return load_config().inputs_fingerprint()


@st.cache_resource(max_entries=4)
def _official(fingerprint: str) -> Assumptions:
    return load_config()


def official() -> Assumptions:
    return _official(FINGERPRINT)


def mix_choices() -> dict[str, dict]:
    """Growth-mix scenarios offered in the sidebar: those that only change the mix (not returns)."""
    return {s["key"]: s for s in official()["growth_mix.scenarios"] if s.get("returns", "official") == "official"}


def to_ui(c: Control, value):
    if c.kind == "slider":
        return float(round(value * c.scale, 6))
    if c.kind == "mix":                                   # config value (None = official) -> scenario key
        if value is None:
            return "G1"
        return next((k for k, s in mix_choices().items() if dict(s["mix"]) == dict(value)), "G1")
    return value


def from_ui(c: Control, value):
    if c.kind == "slider":
        return value / c.scale
    if c.kind == "mix":                                   # scenario key -> config value (G1 = official None)
        return None if value == "G1" else dict(mix_choices()[value]["mix"])
    return value


def reset_to_official() -> None:
    a = official()
    for c in CONTROLS:
        st.session_state[c.key] = to_ui(c, a[c.config])


def differs(c: Control, ui_value, official_value) -> bool:
    if c.kind == "slider":
        return abs(ui_value - to_ui(c, official_value)) > 1e-9
    if c.kind == "mix":
        return ui_value != to_ui(c, official_value)
    return ui_value != official_value


def fmt_value(c: Control, ui_value) -> str:
    if c.kind == "slider":
        if c.unit == "$":
            return f"${ui_value:,.0f}"
        return (c.fmt % ui_value) + (" pts" if c.key == "yield_shift" else "%")
    if c.kind == "toggle":
        return "on" if ui_value else "off"
    if c.kind == "runs":
        return f"{ui_value:,}"
    if c.kind == "mix":
        return f"{ui_value} ({mix_choices()[ui_value]['label']})"
    return str(ui_value)


# --------------------------------------------------------- cached runs ----

def assumptions_for(overrides_json: str, fingerprint: str) -> Assumptions:
    """Official assumptions plus the sidebar changes. The dashboard runs
    simulation.dashboard_n_sims paths, not the official run's simulation.n_sims."""
    a = _official(fingerprint).override(json.loads(overrides_json))
    return a.override({"simulation.n_sims": a["simulation.dashboard_n_sims"]})


@st.cache_data(show_spinner="Running simulation…", max_entries=64)
def compute(overrides_json: str, note: str | None, fingerprint: str) -> dict:
    t0 = time.perf_counter()
    a = assumptions_for(overrides_json, fingerprint)
    res = run_monte_carlo(a)
    stress = analysis.run_stress_tests(a)
    sens = analysis.run_sensitivity(a)
    ladder = load_ladder(a)
    return {
        "res": res,
        "stats": analysis.ladder_stats(res),
        "bills": analysis.bill_table(res),
        "topup": analysis.topup_table(res),
        "fail_shortfall": analysis.failure_shortfall(res),
        "coverage": analysis.coverage_stats(res),
        "bills_missed": analysis.bills_missed_table(res),
        "bill_rank": analysis.bill_failure_ranking(res),
        "rules": analysis.rule_comparison(a, analysis.rule_results(a)),
        "rule_label": analysis.rule_label(a),
        "shortfall": analysis.shortfall_distribution(res),
        "percentiles": analysis.percentile_table(res, a["reporting.percentiles"]),
        "ranges": analysis.cosponsor_ranges(res, a),
        "rec": analysis.recommended_range(res, a),
        "stress": stress,
        "sens": sens,
        "summary": analysis.build_summary(a, res, stress, sens, note=note),
        "jan_cost": float(ladder_costs(ladder, [0.0], a).sum()),
        "sheet_cost": float(ladder.sheet_cost.sum()),
        "price_dates": ladder.price_date_label(),
        "unverified": ladder.unverified,
        "blotter": desk.blotter(ladder, res),
        "runtime": time.perf_counter() - t0,
    }


@st.cache_data(show_spinner="Tracing monthly paths…", max_entries=16)
def monthly(overrides_json: str, note: str | None, fingerprint: str) -> dict:
    """Growth money month by month on the run's own draws (same seed, same n): a few sample
    paths plus the typical path and its P10-P90 band."""
    out = compute(overrides_json, note, fingerprint)
    res = out["res"]
    a = assumptions_for(overrides_json, fingerprint)
    seed = int(a["simulation.seed"])
    values = growth.monthly_bucket_values(a, draw_random(a, load_ladder(a), res.n, seed), seed,
                                          res.growth_contribution)
    return {"sample": values[:SAMPLE_PATHS], "median": np.median(values, axis=0),
            "p10": np.percentile(values, 10, axis=0), "p90": np.percentile(values, 90, axis=0)}


@st.cache_data(show_spinner="Drawing charts…", max_entries=64)
def charts(overrides_json: str, note: str | None, fingerprint: str) -> dict:
    """Interactive Plotly figures: terminal style for the Desk and detail tabs, the light memo
    style for the Report tab."""
    out = compute(overrides_json, note, fingerprint)
    res, rec = out["res"], out["rec"]
    a = assumptions_for(overrides_json, fingerprint)
    m = monthly(overrides_json, note, fingerprint)
    detail = "desk"
    bare = iplots.bare                      # Report titles are exhibit headings on the page
    return {
        "overview_paths": bare(iplots.sample_paths_chart(m, res.timeline.contribution_year,
                                                         float(a["plan.growth_contribution"]), res.n)),
        "overview_bills": bare(iplots.bill_sources_chart(res)),
        "overview_outcomes": bare(iplots.outcomes_chart(res, rec["Low"], rec["High"])),
        "overview_whatif": bare(iplots.whatif_chart(out["stress"], OVERVIEW_STRESS)),
        # Detail tabs: titles live in the panel headers, so the charts drop their own.
        "bills": bare(iplots.bills_chart(res, detail)),
        "buffer": bare(iplots.buffer_chart(res, detail)),
        "shortfall": bare(iplots.shortfall_chart(res, detail)),
        "fan_chart": bare(iplots.fan_chart(res, detail)),
        "histogram": bare(iplots.outcomes_chart(res, rec["Low"], rec["High"], detail, plain=False)),
        "stress_tests": bare(iplots.stress_chart(
            out["stress"].assign(scenario=[desk.stress_label(n) for n in out["stress"]["scenario"]]),
            float(np.median(res.facility)), detail)),
    }


# --------------------------------------------------------------- layout ----

def money(x: float) -> str:
    """Dollar string for Streamlit markdown, where a bare $ starts LaTeX."""
    return analysis.money(x).replace("$", r"\$")


def chart(name: str, fig=None) -> None:
    """An interactive chart: hover for values, drag to zoom, double-click to reset; the camera
    icon in its toolbar saves a PNG. Cached figures by name, or pass one built for this rerun."""
    st.plotly_chart(fig if fig is not None else figs[name], width="stretch", theme=None, key=f"chart_{name}",
                    config={**iplots.CONFIG, "toImageButtonOptions": {**iplots.CONFIG["toImageButtonOptions"],
                                                                      "filename": name}})


# Coloured cells, terminal colours: teal = good / paid, red = bad / short.
GOOD_CELL = "color:#089981; font-weight:600"
BAD_CELL = "color:#f23645; font-weight:600"
WARN_CELL = "color:#ff9800"
MUTED_CELL = "color:#5d606b"


def show_table(df: pd.DataFrame, fmt: dict | None = None, bad_if_positive: tuple = (), signed: tuple = (),
               yes_no: tuple = (), height: int | None = None, cell_styles: dict | None = None) -> None:
    """Render an interactive table (st.dataframe, dark from the theme) with coloured numbers."""
    fmt = dict(fmt or {})
    for c in yes_no:                         # one .format() call: a second call would reset the others
        if c in df:
            fmt[c] = lambda v: "✓ yes" if bool(v) else "✗ no"
    styler = df.style.format({c: f for c, f in fmt.items() if c in df}, na_rep="")
    for c in bad_if_positive:
        if c in df:
            styler = styler.map(lambda v: BAD_CELL if isinstance(v, (int, float)) and v > 1e-9 else MUTED_CELL,
                                subset=[c])
    for c in signed:
        if c in df:
            styler = styler.map(lambda v: GOOD_CELL if v > 1e-9 else BAD_CELL if v < -1e-9 else MUTED_CELL,
                                subset=[c])
    for c in yes_no:
        if c in df:
            styler = styler.map(lambda v: GOOD_CELL if bool(v) else BAD_CELL, subset=[c])
    for c, fn in (cell_styles or {}).items():
        if c in df:
            styler = styler.map(fn, subset=[c])
    st.dataframe(styler, hide_index=True, width="stretch", **({"height": height} if height else {}))


def money_table(df: pd.DataFrame, money_cols: list[str], pct_cols: tuple[str, ...] = (), **colour) -> None:
    fmt = {c: "${:,.0f}" for c in money_cols}
    fmt.update({c: "{:.1%}" for c in pct_cols})
    show_table(df, fmt, **colour)


FINGERPRINT = inputs_fingerprint()
a0 = official()
if "initialized" not in st.session_state:
    reset_to_official()
    st.session_state["initialized"] = True

# Sidebar
with st.sidebar:
    st.header("More inputs")
    st.caption("The main inputs are in the command bar at the top. Change any of these to see what happens; "
               "everything updates. The official numbers come back with the button below.")
    st.button("Official assumptions", on_click=reset_to_official, type="primary", width="stretch",
              help="Reset every control to config.yaml")
    for c in CONTROLS:
        if c.key in BAR:
            continue
        if c.kind == "slider":
            st.slider(c.label, c.lo, c.hi, step=c.step, format=c.fmt, key=c.key, help=c.help or None)
        elif c.kind == "toggle":
            st.toggle(c.label, key=c.key)
        elif c.kind == "runs":
            options = sorted(set(RUN_OPTIONS) | {int(a0[c.config])})
            st.select_slider(c.label, options=options, key=c.key, format_func=lambda v: f"{v:,}")
        elif c.kind == "choice":
            st.radio(c.label, list(c.options), key=c.key, horizontal=True, help=c.help)
        elif c.kind == "mix":
            st.selectbox(c.label, list(mix_choices()), key=c.key, help=c.help,
                         format_func=lambda k: f"{k}: {mix_choices()[k]['label']}")

CTRL = {c.key: c for c in CONTROLS}


def bar_widget(c: Control) -> None:
    """A command-bar input: compact number fields instead of sliders."""
    label = BAR[c.key]
    if c.kind == "slider":
        st.number_input(label, min_value=c.lo, max_value=c.hi, step=c.step,
                        format="%.0f" if c.unit == "$" else c.fmt, key=c.key)
    elif c.kind == "runs":
        st.selectbox(label, sorted(set(RUN_OPTIONS) | {int(a0[c.config])}), key=c.key,
                     format_func=lambda v: f"{v:,}")
    elif c.kind == "mix":
        st.selectbox(label, list(mix_choices()), key=c.key,
                     format_func=lambda k: f"{k} · {mix_choices()[k]['label']}"[:44])


# Command bar: the inputs people change most, always in view (like a symbol box and order ticket).
with st.container(key="cmdbar"):
    cols = st.columns([1.35, 2.6, 0.85, 0.85, 0.85, 0.95, 0.85, 0.85], gap="small")
    with cols[0]:
        st.markdown(f'<div class="sym-head"><div class="name">Laura\'s plan<span class="badge">Monte Carlo</span></div>'
                    f'<div class="meta">Ten bills · facility gift {a0["plan.valuation_year"]}</div></div>',
                    unsafe_allow_html=True)
    for col, key in zip(cols[1:7], BAR):
        with col:
            bar_widget(CTRL[key])
    with cols[7]:
        st.button("Official", key="bar_reset", on_click=reset_to_official, help="Reset every input to config.yaml")

ui = {c.key: st.session_state[c.key] for c in CONTROLS}
changed = [c for c in CONTROLS if differs(c, ui[c.key], a0[c.config])]
overrides = {c.config: from_ui(c, ui[c.key]) for c in changed}
overrides_json = json.dumps(overrides, sort_keys=True)
note = None
if changed:
    note = "Exploratory run, not the official assumptions: " + "; ".join(
        f"{c.label} {fmt_value(c, ui[c.key])} (official {fmt_value(c, to_ui(c, a0[c.config]))})" for c in changed)

out = compute(overrides_json, note, FINGERPRINT)
figs = charts(overrides_json, note, FINGERPRINT)
mo = monthly(overrides_json, note, FINGERPRINT)
res, stats, rec = out["res"], out["stats"], out["rec"]
a = assumptions_for(overrides_json, FINGERPRINT)

# Header: command bar and a plain-language ticker of the headline numbers.
def html_money(x: float) -> str:
    return analysis.money(x).replace("$", "&#36;")          # keep $ out of Streamlit's LaTeX


def k(x: float) -> str:
    """$140k-style short money for headline cards (escaped for Streamlit markdown)."""
    return f"\\${x / 1e3:,.0f}k"


paid = stats["p_all_paid_with_backstop"]
facility_med = float(np.median(res.facility))
cushion_med = float(np.median(res.cushion_kept))
growth_med = float(np.median(res.value_before_topup))
growth_chg = growth_med / float(a["plan.growth_contribution"]) - 1


tl = res.timeline
vy, last_bill = tl.valuation_year, tl.bill_years[-1]
p10, p90 = (float(np.percentile(res.facility, q)) for q in (10, 90))
needs_help = (res.ladder_only_shortfall > 1e-6).mean(axis=0)            # per bill: ladder alone falls short
backstop = float(a["waterfall.backstop_amount"])
n_bills = len(tl.bill_years)
n_paid = int(res.all_paid_with_backstop.sum())
stress_rows = out["stress"].set_index("scenario")
worst_key, worst_label = OVERVIEW_STRESS[-1]
if paid >= 0.9995 and n_paid == res.n:
    lead = (f"Every bill is paid in all {res.n:,} simulated futures, and the facility receives about "
            f"{html_money(round(facility_med, -3))} in {vy}.")
else:
    lead = (f"All {n_bills} bills are paid in {paid:.1%} of {res.n:,} simulated futures; the facility receives about "
            f"{html_money(round(facility_med, -3))} in {vy}.")
lead_sub = (f"Without the {html_money(backstop)} safety net, {stats['p_all_paid']:.1%} of futures pay every bill on "
            f"their own. 8 in 10 futures give the facility between {html_money(round(p10, -3))} and "
            f"{html_money(round(p90, -3))}.")
if worst_key in stress_rows.index:
    w = stress_rows.loc[worst_key]
    covered = bool(w["all_bills_paid"]) or bool(w["backstop_covers"])
    lead_sub += (f" In the hardest case we tested (low rates and weak markets) the bills are "
                 f"{'still paid' if covered else '<span class=neg>not fully paid</span>'} and the gift falls to "
                 f"{html_money(round(float(w['facility_contribution']), -3))}.")
# Headline labels. The facility contribution and the co-sponsor range lead; the growth bucket is
# labelled so it can't be read as the facility amount.
give = float(a["facility.give_pct"])
FACILITY_LABEL = f"Facility contribution {vy}, median"
RANGE_LABEL = "Example co-sponsor range (method)"
GROWTH_LABEL = f"Growth bucket {vy}, before top-up and {give * 100:.0f}/{(1 - give) * 100:.0f} split"
LAURA_LABEL = f"Laura keeps in {vy}, median"
figures = [
    (FACILITY_LABEL, html_money(facility_med),
     f"1 in 10 below {html_money(p10)} · 1 in 10 above {html_money(p90)}", ""),
    (RANGE_LABEL, f"{html_money(rec['Low'])}–{html_money(rec['High'])}",
     f"{rec['P(at or above low end)']:.0%} of futures give at least {html_money(rec['Low'])}", analysis.COSPONSOR_NOTE),
    ("All bills paid", f"{paid:.2%}",
     f"with the {html_money(backstop)} safety net · {stats['p_all_paid']:.1%} without it", ""),
    (LAURA_LABEL, html_money(cushion_med),
     f"her {1 - give:.0%} share; {html_money(backstop)} of it held as the bills' safety net until {last_bill}", ""),
    (GROWTH_LABEL, html_money(growth_med),
     (f"{growth_chg:+.1%}" if growth_chg >= 0 else f'<span class="neg">{growth_chg:+.1%}</span>')
     + f" on {html_money(a['plan.growth_contribution'])} invested; not the facility amount", ""),
]
# Ticker strip: the headline numbers as quotes; with modified inputs each shows its move vs official.
off = compute("{}", None, FINGERPRINT) if changed else out
off_res, off_stats = off["res"], off["stats"]


def kk(x: float) -> str:
    return f"&#36;{x / 1e3:,.0f}k"


def move(new: float, old: float, points: bool = False) -> str:
    """Quote-style change against the official run: '▲ +5,512 (+4.10%)' green, '▼' red."""
    if points:
        d = (new - old) * 100
        if abs(d) < 0.005:
            return '<span class="muted">unch vs official</span>'
        return f'<span class="{"up" if d > 0 else "down"}">{"▲" if d > 0 else "▼"} {d:+.2f} pts</span> vs official'
    d = new - old
    if abs(d) < 0.5:
        return '<span class="muted">unch vs official</span>'
    pct = d / old * 100 if old else 0.0
    return (f'<span class="{"up" if d > 0 else "down"}">{"▲" if d > 0 else "▼"} {d:+,.0f} ({pct:+.2f}%)</span>'
            " vs official")


topup_med = float(stats["topup_median"])
worst = stress_rows.loc[worst_key] if worst_key in stress_rows.index else None
tiles = [
    (FACILITY_LABEL, html_money(facility_med),
     move(facility_med, float(np.median(off_res.facility))) if changed else f"P10 {kk(p10)} · P90 {kk(p90)}", ""),
    (RANGE_LABEL, f"{html_money(rec['Low'])}–{rec['High']:,.0f}",
     f"{rec['P(at or above low end)']:.0%} of futures ≥ low end", analysis.COSPONSOR_NOTE),
    ("All bills paid", f"{paid:.2%}",
     move(paid, off_stats["p_all_paid_with_backstop"], True) if changed
     else f'<span class="up">all {res.n:,}</span> · {stats["p_all_paid"]:.1%} w/o net' if n_paid == res.n
     else f'<span class="down">{n_paid:,} of {res.n:,}</span> · {stats["p_all_paid"]:.1%} w/o net', ""),
    (LAURA_LABEL, html_money(cushion_med),
     move(cushion_med, float(np.median(off_res.cushion_kept))) if changed else
     f"incl. {kk(backstop)} net to {last_bill}", ""),
    (f"Top-up {vy}, median", html_money(topup_med),
     move(topup_med, float(off_stats["topup_median"])) if changed else
     f"cash rule {a['waterfall.rate_rule_rate']:.1%}", ""),
    (GROWTH_LABEL, html_money(growth_med),
     move(growth_med, float(np.median(off_res.value_before_topup))) if changed else
     f'<span class="{"up" if growth_chg >= 0 else "down"}">'
     f"{growth_med - float(a['plan.growth_contribution']):+,.0f} ({growth_chg:+.2%})</span> on "
     f"{kk(a['plan.growth_contribution'])}", ""),
]
if worst is not None:
    w_ok = bool(worst["all_bills_paid"]) or bool(worst["backstop_covers"])
    tiles.append(("Worst stress: facility gift", html_money(float(worst["facility_contribution"])),
                  f'<span class="{"up" if w_ok else "down"}">{"bills paid" if w_ok else "bills short"}</span>'
                  f" · {worst_label.split(': ')[-1]}", ""))
LEAD = (FACILITY_LABEL, RANGE_LABEL)                       # highlighted: what the facility can count on
tile_html = "".join(
    f'<div class="tk{" lead" if sym in LEAD else ""}" title="{html.escape(sym + (". " + note if note else ""))}">'
    f'<div class="sym">{sym}</div><div class="px">{px}</div><div class="chg">{chg}</div></div>'
    for sym, px, chg, note in tiles)
if changed:
    sig = ('<span class="tag mod">Modified inputs</span>' + " · ".join(
        f"{BAR.get(c.key, c.label)} {fmt_value(c, ui[c.key])} <span class='muted'>(off "
        f"{fmt_value(c, to_ui(c, a0[c.config]))})</span>" for c in changed))
else:
    sig = f'<span class="tag">Official inputs</span>{lead}'
st.markdown(f'<div class="tk-row">{tile_html}</div><div class="sig">{sig}</div>', unsafe_allow_html=True)

if a0.placeholders():
    st.warning(f"**{len(a0.placeholders())} of {len(a0.values)} assumptions are placeholders (source: TODO).** "
               "Results are not ready for client use until Kyan and Nathan supply the sources. See the "
               "Assumptions tab.", icon="⚠️")

# Status bar along the bottom: what run this is and whether the project is ready to deploy.
metrics_file = a0.base_dir / "outputs" / "metrics.json"
if not metrics_file.exists():
    outputs_state = ("warn", "Outputs missing")
elif json.loads(metrics_file.read_text()).get("inputs_sha256") != FINGERPRINT:
    outputs_state = ("down", "Outputs stale")
else:
    outputs_state = ("up", "Outputs fresh")
n_est, n_ph = len(out["unverified"]), len(a0.placeholders())
ready = n_est == 0 and n_ph == 0 and outputs_state[0] == "up"
items = [
    ("warn" if changed else "up", "Modified inputs" if changed else "Official inputs"),
    ("", f"Run {res.n:,} paths · seed {a['simulation.seed']} · calc {out['runtime']:.1f}s"),
    ("", f"Inputs {FINGERPRINT[:8]}"),
    ("warn" if n_est else "up", f"Ladder: {n_est} estimated price" + ("s" if n_est != 1 else "") if n_est else "Ladder: all quoted"),
    ("down" if n_ph else "up", f"Assumptions: {n_ph} placeholder" + ("s" if n_ph != 1 else "")),
    outputs_state,
    ("up" if ready else "down", "Deploy ready" if ready else "Deploy blocked"),
]
colour = {"up": "var(--up)", "down": "var(--down)", "warn": "var(--amber)", "": "var(--ink-3)"}
st.markdown('<div class="sbar">' + "".join(
    f'<span><span class="dot" style="background:{colour[c]}"></span><b>{txt}</b></span>'
    for c, txt in items) + f'<span class="r">{datetime.now():%d %b %Y %H:%M}</span></div>', unsafe_allow_html=True)

t_desk, t_report, t_bills, t_fac, t_range, t_stress, t_assump = st.tabs(
    ["Desk", "Report", "Bills", "Facility", "Co-sponsor range", "Stress tests", "Assumptions"])

# --------------------------------------------------------------- report ----
# The memo: plain words and five exhibits on a white sheet, for people who don't know the details.
with t_report, st.container(key="report"):
    status = ('<span class="mod">Modified inputs (not official)</span>' if changed else "Official inputs")
    st.markdown(
        '<div class="mast"><div class="mast-top"><span>Monte Carlo plan review</span>'
        f'<span>{datetime.now():%-d %B %Y}</span></div>'
        f'<div class="mast-title">Laura\'s bills and facility gift, {tl.purchase_year}–{last_bill}</div>'
        f'<div class="mast-meta">{status} · {res.n:,} simulated futures · seed {a["simulation.seed"]}</div></div>'
        f'<div class="lead"><div class="kicker">Bottom line</div><div class="lead-text">{lead}</div>'
        f'<div class="lead-sub">{lead_sub}</div></div>'
        '<div class="figs">' + "".join(
            f'<div class="fig{" lead" if lbl in (FACILITY_LABEL, RANGE_LABEL) else ""}"><div class="lbl">{lbl}</div><div class="val">{val}</div><div class="sub">{sub}</div>'
            + (f'<div class="note">{note}</div>' if note else "") + "</div>"
            for lbl, val, sub, note in figures) + "</div>",
        unsafe_allow_html=True)
    if out["unverified"]:
        est_bills = ", ".join(u.split(" (")[0].replace("Bill ", "") for u in out["unverified"])
        st.markdown(f'<div class="cl-notice"><b>Note.</b> {len(out["unverified"])} ladder prices are estimates (bills {est_bills}): '
                    "replace them with the WInS fill prices. Details in the Bills tab.</div>", unsafe_allow_html=True)

    tl = res.timeline
    vy, first_bill, last_bill = tl.valuation_year, tl.bill_years[0], tl.bill_years[-1]
    invested = float(a["plan.growth_contribution"])
    source = (f"Source: team Monte Carlo simulation, {res.n:,} futures, seed {a['simulation.seed']}. "
              "Assumptions and their sources are listed in the Assumptions tab.")

    def exhibit_head(n: int, title: str, sub: str) -> None:
        st.markdown(f'<div class="ex-head"><div class="ex-num">Exhibit {n}</div><div class="ex-title">{title}</div>'
                    f'<div class="ex-sub">{sub}</div></div>', unsafe_allow_html=True)

    def exhibit_foot(how_to_read: str) -> None:
        st.caption("How to read: " + how_to_read)
        st.markdown(f'<div class="ex-src">{source}</div>', unsafe_allow_html=True)

    def exhibit(n: int, name: str, title: str, sub: str, how_to_read: str) -> None:
        exhibit_head(n, title, sub)
        chart(name)
        exhibit_foot(how_to_read)

    ladder = load_ladder(a)
    own_share = np.minimum(res.rung_payout, res.bill_paid).mean(axis=0) / res.bill_amount
    net_used = (res.backstop_draw > 1e-6).mean(axis=0)

    def rung_label(k: int) -> str:
        if not ladder.is_treasury[k]:
            return str(ladder.table["ticker_or_cusip"][k])
        m = ladder.maturity[k]
        return f"T {ladder.coupon[k] * 100:g}% {m:%b} '{m:%y}"

    glide = {int(g["year"]): g["fraction_of_stocks"] for g in a["glide_path.steps"]} if a["glide_path.enabled"] else {}
    events = [
        (f"Jan {tl.purchase_year}", "BUY", "Buy the bond ladder: 5 iBonds funds and 5 Treasury bonds",
         html_money(out["sheet_cost"])),
        (f"Jan {tl.purchase_year}", "CASH", "Leftover cash held in T-bills (SGOV) as a buffer",
         "~" + html_money(stats["buffer_start_median"])),
        (f"Jan {tl.contribution_year}", "INVEST",
         f"Growth money into stocks ({a['growth.us_weight']:.0%} US, {a['growth.intl_weight']:.0%} international)",
         html_money(invested)),
    ] + [(f"Jan {y}", "DE-RISK", f"Move {f} of the {'remaining ' if i else ''}stocks to cash", "")
         for i, (y, f) in enumerate(glide.items())] + [
        (f"Jan {vy}", "TOP-UP", f"Move money to the bill reserve, planning for {a['waterfall.rate_rule_rate']:.0%} "
                                "cash returns", "~" + html_money(stats["topup_median"])),
        (f"Jan {vy}", "GIVE", f"Gift to the facility ({a['facility.give_pct']:.0%} of what is left)",
         "~" + html_money(facility_med)),
        (f"Jan {vy}", "KEEP", f"Laura keeps her share; {html_money(backstop)} of it held as the safety net",
         "~" + html_money(cushion_med)),
        (f"{first_bill}–{last_bill}", "PAY", "Ten bills, every January", html_money(res.bill_amount) + " each"),
        (f"After {last_bill}", "RETURN", "Unused safety net back to Laura",
         "~" + html_money(float(np.median(res.backstop_left)))),
    ]
    rows_html = "".join(f'<tr><td class="ev-date">{d}</td><td class="ev-kind">{kind}</td><td>{what}</td>'
                        f'<td class="ev-amt">{amt}</td></tr>' for d, kind, what, amt in events)

    s1, s2 = st.columns([1, 1.15], gap="large")
    with s1:
        st.markdown(
            f"### The plan\n"
            f"Laura needs **{n_bills} payments of {money(res.bill_amount)}**, one every January from {first_bill} to "
            f"{last_bill}, and wants to give the rest to the **facility**.\n\n"
            f"In {tl.purchase_year} she puts **{money(a['plan.ladder_budget'])}** into a ladder of bonds that mature "
            f"one by one to pay those bills. In {tl.contribution_year} she puts **{money(invested)}** into stocks to "
            f"grow. In {vy} the growth money is split: first a top-up for the bills if needed, then "
            f"**{a['facility.give_pct']:.0%} to the facility**, and the rest stays with Laura.\n\n"
            f"We simulated **{res.n:,} possible futures** for markets and interest rates to see how the plan can "
            "turn out.")
    with s2:
        st.markdown('<div class="ex-head" style="border-top:none;margin-top:0;padding-top:0">'
                    '<div class="ex-num">Schedule</div><div class="ex-title">What happens when</div>'
                    '<div class="ex-sub">Typical amounts from this run</div></div>'
                    f'<table class="ev-table" style="margin-top:10px">{rows_html}</table>', unsafe_allow_html=True)

    share_up = float((res.value_before_topup >= invested).mean())
    exhibit(1, "overview_paths",
            f"The growth money ends above the {html_money(invested)} invested in {share_up:.0%} of futures",
            f"Growth bucket value month by month, {tl.contribution_year}–{vy}: {SAMPLE_PATHS} sample futures, the "
            "typical path, and the band 8 in 10 futures stay inside",
            f"each thin line is one possible future, like a stock chart; blue lines finish above the "
            f"{money(invested)} put in, red ones below. The dark line is the typical path; it flattens near the end "
            "because half the stocks move to cash in 2031–32.")

    heavy = [y for y, s_ in zip(tl.bill_years, needs_help) if s_ >= 0.25]
    if heavy:
        years_txt = ", ".join(str(y) for y in heavy[:-1]) + (" and " if len(heavy) > 1 else "") + str(heavy[-1])
        map_title = f"The {years_txt} bill{'s lean' if len(heavy) > 1 else ' leans'} most on the {vy} top-up"
    else:
        map_title = "Each bill is covered mainly by the bond bought for it"
    tiles = ""
    for k_, y in enumerate(tl.bill_years):
        bg, fg = sparks.navy_color(needs_help[k_])
        tiles += (f'<div class="bm-tile" style="background:{bg};color:{fg}">'
                  f'<div class="bm-year">{y}</div><div class="bm-sec">{rung_label(k_)}</div>'
                  f'<div class="bm-stat">top-up needed {needs_help[k_]:.0%}</div>'
                  f'<div class="bm-stat">own bond pays {own_share[k_]:.0%}</div>'
                  + (f'<div class="bm-stat bm-net">safety net {net_used[k_]:.1%}</div>' if net_used[k_] > 0 else "")
                  + "</div>")
    c1, c2 = st.columns(2, gap="large")
    with c1:
        exhibit_head(2, map_title, "One tile per bill. Darker = the bond bought for it falls short on its own more "
                                   "often and needs the top-up")
        st.markdown(f'<div class="bm-grid">{tiles}</div><div class="bm-legend"><span>never</span>'
                    '<div class="bm-scale"></div><span>often</span></div>', unsafe_allow_html=True)
        exhibit_foot("read each tile as one January bill. \"Top-up needed\" is how often its own bond or fund pays "
                     "less than the bill; \"own bond pays\" is the share it covers on average. A red line means "
                     "the safety net was used for that bill in some futures.")
    with c2:
        exhibit(3, "overview_bills",
                f"The ladder itself pays {own_share.mean():.0%} of all bill dollars",
                "Average source of each $50k bill across all futures",
                "each bar is one bill. The dark part is paid by the bond or fund bought for that year; the light "
                f"top is paid from the cash reserve, mostly the top-up moved over from the growth money in {vy}.")

    c3, c4 = st.columns(2, gap="large")
    with c3:
        exhibit(4, "overview_outcomes",
                f"8 in 10 futures give the facility between {html_money(round(p10, -3))} and "
                f"{html_money(round(p90, -3))}",
                f"Facility gift in {vy} across {res.n:,} futures; shaded: example co-sponsor range "
                f"{html_money(rec['Low'])}–{html_money(rec['High'])}",
                "taller bars are more likely amounts. The dotted lines mark the bad, typical and good cases; the "
                "shaded block is the example co-sponsor range.")
    with c4:
        picked = [k_ for k_, _ in OVERVIEW_STRESS if k_ in stress_rows.index]
        all_ok = all(bool(stress_rows.loc[k_, "all_bills_paid"]) or bool(stress_rows.loc[k_, "backstop_covers"])
                     for k_ in picked)
        exhibit(5, "overview_whatif",
                "In every tough case we tested, the bills are paid and the gift absorbs the damage" if all_ok
                else "Some tough cases leave bills short",
                f"Five fixed futures; bars = money to the facility in {vy}",
                "each row is one tough future we forced on purpose. The bar is what the facility still gets; the "
                "text says whether every bill was still paid.")

    st.markdown('<div class="ex-head"></div>', unsafe_allow_html=True)
    lc, rc = st.columns(2, gap="large")
    with lc:
        st.markdown(
            "### What protects the bills\n"
            f"1. **The bond ladder.** Each bill has a bond or bond fund bought for it in {tl.purchase_year}; on its "
            f"own the ladder covers about {out['coverage']['coverage_median']:.1%} of all bill dollars.\n"
            f"2. **A cash top-up in {vy}.** Before anything goes to the facility, money is moved to a cash reserve, "
            f"planning as if cash earns only {a['waterfall.rate_rule_rate']:.1%} after {vy} (well below forecasts), "
            f"so a rough guess is enough. Typical top-up: {money(stats['topup_median'])}.\n"
            f"3. **A {money(a['waterfall.backstop_amount'])} safety net** from Laura's share, used only if a bill "
            "would otherwise come up short, and returned to her if it isn't needed.")
    with rc:
        sens = out["sens"].set_index("case")
        forecast = ""
        if "Vanguard pessimistic" in sens.index:
            forecast = ("\n- **The forecast itself:** with more pessimistic return forecasts (Vanguard) the typical "
                        f"gift is about {money(float(sens.loc['Vanguard pessimistic', 'facility_p50']))} instead of "
                        f"{money(facility_med)}.")
        st.markdown(
            "### What can shrink the facility gift\n"
            "- **Weak stock markets** between 2028 and 2033: the biggest swing factor (Exhibits 1 and 5).\n"
            "- **Low interest rates** when the bonds are bought or while cash waits for the bills: more money "
            "goes to the bills first." + forecast)

    with st.expander("Glossary: words used in this review"):
        st.markdown(
            "- **Bill:** one of the ten fixed payments Laura has to make, every January.\n"
            "- **Bond ladder:** bonds and bond funds that each mature just before one bill, so each bill has money "
            "waiting for it.\n"
            "- **T-bills / cash reserve:** very safe short-term government savings that hold spare cash.\n"
            f"- **Growth money:** the {money(invested)} put into stocks in {tl.contribution_year}; it can go up or "
            "down.\n"
            f"- **Top-up:** money moved from the growth money to the cash reserve in {vy} so the later bills are "
            "covered.\n"
            "- **Safety net (backstop):** cash set aside from Laura's share only to cover a bill that would "
            "otherwise be short.\n"
            "- **Facility gift:** the share of the growth money given to the facility in " + str(vy) + ".\n"
            "- **Simulated futures:** thousands of possible paths for markets and interest rates, drawn at random "
            "from expert forecasts, to see the range of outcomes.\n"
            "- **Typical / bad case / good case:** the middle outcome, and the outcomes that only 1 in 10 futures "
            "fall below or rise above.")
    st.caption(f"{res.n:,} simulated paths · seed {a['simulation.seed']} · "
               f"real dollars are Jan {a['inflation.base_year']} dollars ({analysis.inflation_text(a)}). "
               "The other tabs have the full detail.")
    st.download_button("Download the full summary (summary.md)", out["summary"], file_name="summary.md",
                       mime="text/markdown")

# ----------------------------------------------------------------- desk ----
# The main screen: every headline view on one screen, numbers first, like a trading terminal.
# Panels are linked: a bill tile focuses that bill, a stress-test row draws its future on the
# growth chart, a watchlist row loads that growth scenario into every input.
def panel(key: str, title: str, stats: list[tuple[str, str]], tip: str = ""):
    """A bordered widget panel with a one-line header: title, an ⓘ hover note, key stats."""
    box = st.container(border=True, key=f"pn_{key}")
    stat_html = "".join(f"<span>{k_} <b>{v_}</b></span>" for k_, v_ in stats)
    tip_html = f'<span class="tip" data-tip="{html.escape(tip)}">ⓘ</span>' if tip else ""
    box.markdown(f'<div class="pn-head"><span class="pn-title">{title}{tip_html}</span>'
                 f'<span class="pn-stats">{stat_html}</span></div>', unsafe_allow_html=True)
    return box


def quote_strip(items: list[tuple[str, str, str]]) -> None:
    """A row of quotes (label, value, line under it), like the strip at the top of the Desk. The
    line under each value is also its hover text, since narrow tiles cut it short."""
    st.markdown('<div class="tk-row q">' + "".join(
        f'<div class="tk" title="{html.escape(re.sub("<[^>]+>", "", sub))}"><div class="sym">{lbl}</div>'
        f'<div class="px">{val}</div><div class="chg">{sub}</div></div>' for lbl, val, sub in items) + "</div>",
        unsafe_allow_html=True)


def selected_row(key: str) -> int | None:
    """Row picked in a selectable st.dataframe (None when nothing is selected)."""
    try:
        rows = st.session_state[key]["selection"]["rows"]
    except (KeyError, TypeError):
        return None
    return rows[0] if rows else None


@st.cache_data(show_spinner="Running the watchlist…", max_entries=4)
def watch_data(fingerprint: str) -> pd.DataFrame:
    a_ = _official(fingerprint)
    return desk.watchlist(a_, int(a_["simulation.dashboard_n_sims"]))


@st.cache_data(max_entries=64)
def stress_path(overrides_json: str, fingerprint: str, name: str) -> np.ndarray:
    return desk.stress_growth_path(assumptions_for(overrides_json, fingerprint), name)


def load_scenario() -> None:
    """Watchlist click: set the inputs that reproduce that growth scenario."""
    row = selected_row("watch")
    if row is None:
        return
    spec = official()["growth_mix.scenarios"][row]
    vals = desk.scenario_inputs(official(), spec)
    st.session_state["growth_mix"] = to_ui(CTRL["growth_mix"], vals["growth_mix.mix"])
    st.session_state["us_mean"] = to_ui(CTRL["us_mean"], vals["growth.us_mean"])
    st.session_state["intl_mean"] = to_ui(CTRL["intl_mean"], vals["growth.intl_mean"])


def tile_label(k: int) -> str:
    """Short rung name for a bill-map tile: the ETF ticker, or "4.75% '37" (coupon, maturity
    year) for a Treasury. The full name is in Positions and under the map."""
    if not ladder.is_treasury[k]:
        return str(ladder.table["ticker_or_cusip"][k])
    return f"{ladder.coupon[k] * 100:g}% '{ladder.maturity[k]:%y}"


def focus(k: int) -> None:
    st.session_state["focus_bill"] = k


with t_desk:
    end_p10, end_p50, end_p90 = (float(mo[q][-1]) for q in ("p10", "median", "p90"))
    sm = desk.stress_matrix(out["stress"], facility_med)
    pick = selected_row("stress_table")
    overlay = None
    if pick is not None and pick < len(sm):
        name = out["stress"]["scenario"].iloc[pick]
        overlay = (desk.stress_label(name), stress_path(overrides_json, FINGERPRINT, name))
    ghost_m = monthly("{}", None, FINGERPRINT)["median"] if changed else None
    ghost_f = off_res.facility if changed else None
    if "focus_bill" not in st.session_state:
        st.session_state["focus_bill"] = int(np.argmax(needs_help))
    fk = min(int(st.session_state["focus_bill"]), n_bills - 1)

    main, side = st.columns([2.85, 1.15], gap="small")
    with main:
        r1a, r1b = st.columns([1.9, 1], gap="small")
        with r1a:
            stats_ = [("P10", kk(end_p10)), ("P50", kk(end_p50)), ("P90", kk(end_p90))]
            if overlay:
                stats_.append((overlay[0], kk(overlay[1][-1])))
            with panel("paths", f"Growth bucket, monthly {tl.contribution_year}–{vy}", stats_,
                       f"{share_up:.0%} of {res.n:,} futures end above the {analysis.money(invested)} invested. "
                       f"Thin lines: {SAMPLE_PATHS} sample futures (green above, red below). Blue: the median. "
                       "Dotted: P10 and P90. Dashed white: the official run, when inputs are changed. "
                       "Orange: the stress test picked in the Stress tests tab below."):
                chart("desk_paths", iplots.desk_paths_chart(mo, tl.contribution_year, invested, ghost=ghost_m,
                                                            overlay=overlay, height=255))
        with r1b:
            with panel("facility", f"Facility gift, {vy}", [("Median", kk(facility_med))],
                       f"Blue bars: the example co-sponsor range, {analysis.money(rec['Low'])}–{analysis.money(rec['High'])}; "
                       f"{rec['P(at or above low end)']:.0%} of futures reach its low end. Dashed white outline: the "
                       "official run, when inputs are changed."):
                chart("desk_facility", iplots.desk_facility_chart(res, rec["Low"], rec["High"], ghost=ghost_f,
                                                                  height=255))

        r2a, r2b = st.columns([1.9, 1], gap="small")
        with r2a:
            with st.container(border=True, key="pn_book"):
                tab_pos, tab_stress, tab_cal = st.tabs(["Positions", "Stress tests", "Calendar"])
            with tab_pos:
                bl = out["blotter"].assign(_class=["focus" if k_ == fk else "" for k_ in range(n_bills)])
                money0 = lambda v: f"{v:,.0f}"
                blot_html = desk.table_html(
                    bl, left=("Instrument", "Type"),
                    fmt={"Qty": lambda v: f"{v:,}", "Price": lambda v: f"{v:,.2f}", "Cost": money0,
                         "Payout P5": money0, "Payout P50": money0, "Payout P95": money0,
                         "Top-up %": lambda v: f"{v:.1%}",
                         "Px": lambda v: f'<span class="chip {"warn" if v == "EST" else "up"}">{v.title()}</span>'},
                    cls={"Payout P5": lambda v: "down" if v < 0.95 * res.bill_amount else "",
                         "Top-up %": lambda v: "down" if v >= 0.5 else "warn" if v >= 0.25 else "up"})
                st.markdown(
                    f'<div class="pn-sum">Cost <b>{html_money(out["sheet_cost"])}</b> · Jan 2027 reprice '
                    f'<b>{html_money(out["jan_cost"])}</b> · cash buffer <b>{html_money(stats["buffer_start_median"])}</b>'
                    f'<span class="tip" data-tip="Payout: what each rung pays at its Jan 1 bill across {res.n:,} '
                    f'futures. Top-up %: how often it falls short of the bill on its own. Est: estimated price, '
                    f'replace with the WInS fill. The highlighted row is the bill picked on the bill map.">ⓘ</span>'
                    f'</div><div class="pn-scroll">{blot_html}</div>', unsafe_allow_html=True)
            with tab_stress:
                counts = sm["Result"].value_counts()
                shown = sm.drop(columns="_title").assign(Result=sm["Result"].map(
                    {"PAID": "Paid", "NET": "With net", "SHORT": "Short"}))
                res_style = {"Paid": GOOD_CELL, "With net": WARN_CELL, "Short": BAD_CELL}
                styler = (shown.style.format({"Facility": "${:,.0f}", "vs P50": "{:+.1%}", "Top-up": "${:,.0f}",
                                              "Unpaid pre-net": "${:,.0f}"})
                          .map(lambda v: GOOD_CELL if v > 0.005 else BAD_CELL if v < -0.005 else MUTED_CELL,
                               subset=["vs P50"])
                          .map(lambda v: WARN_CELL if v > 0.5 else MUTED_CELL, subset=["Unpaid pre-net"])
                          .map(lambda v: res_style.get(v, ""), subset=["Result"]))
                st.markdown(f'<div class="pn-sum">Paid <b>{counts.get("PAID", 0)}</b> · with net '
                            f'<b>{counts.get("NET", 0)}</b> · short <b>{counts.get("SHORT", 0)}</b> · '
                            '<span class="acc">click a row to draw that future on the growth chart</span></div>',
                            unsafe_allow_html=True)
                st.dataframe(styler, key="stress_table", on_select="rerun", selection_mode="single-row",
                             hide_index=True, width="stretch", height=232)
            with tab_cal:
                cal = pd.DataFrame(events, columns=["Date", "Event", "What", "Amount"])
                cal_html = desk.table_html(cal, left=("Date", "Event", "What"), wrap=("What",),
                                           fmt={"Amount": lambda v: v or "—", "What": lambda v: v,
                                                "Event": lambda v: v.capitalize()},
                                           cls={"Event": lambda v: "acc", "Date": lambda v: "muted"})
                st.markdown(f'<div class="pn-sum">Typical amounts from this run</div>'
                            f'<div class="pn-scroll">{cal_html}</div>', unsafe_allow_html=True)
        with r2b:
            with panel("heat", "Bill map", [("All paid", f"{paid:.2%}"), ("Without net", f"{stats['p_all_paid']:.1%}")],
                       "One tile per Jan 1 bill. The % is how often its own bond or fund falls short and the 2033 "
                       "top-up pays the gap. Colours follow the Finviz heatmap scale. Click a tile to see that "
                       "bill's payouts below and highlight it in Positions."):
                tile_css = "".join(
                    f'.st-key-tile_{k_} button {{ background:{sparks.finviz_color(needs_help[k_])} !important; }}'
                    for k_ in range(n_bills))
                tile_css += f'.st-key-tile_{fk} button {{ box-shadow: inset 0 0 0 2px #ffffff; }}'
                st.markdown(f"<style>{tile_css}</style>", unsafe_allow_html=True)
                for row_ in (range(0, 5), range(5, n_bills)):
                    cols_ = st.columns(5, gap=None)
                    for col_, k_ in zip(cols_, row_):
                        with col_:
                            st.button(f"**{tl.bill_years[k_]}**  \n{tile_label(k_)}  \n{needs_help[k_]:.0%}",
                                      key=f"tile_{k_}", on_click=focus, args=(k_,), width="stretch")
                edges = [0] + [round(e * 100) for e in sparks.FINVIZ_STEPS]
                legend = "".join(f'<span style="background:{c}">{lo}%{"+" if i == len(sparks.FINVIZ) - 1 else ""}</span>'
                                 for i, (c, lo) in enumerate(zip(sparks.FINVIZ, edges)))
                bp = res.rung_payout[:, fk]
                st.markdown(
                    f'<div class="pn-body"><div class="hm-legend">{legend}</div>'
                    f'<div class="pn-sum" style="padding:8px 0 0">Bill {tl.bill_years[fk]} · {rung_label(fk)} · '
                    f'median payout <b>{html_money(float(np.median(bp)))}</b> · needs top-up <b>{needs_help[fk]:.0%}</b> · '
                    f'own bond pays <b>{own_share[fk]:.0%}</b>'
                    + (f' · net used <b class="down">{net_used[fk]:.2%}</b>' if net_used[fk] > 0 else "")
                    + "</div></div>", unsafe_allow_html=True)
                chart("desk_bill", iplots.desk_bill_chart(res, fk, height=118))

    with side:
        wl = watch_data(FINGERPRINT)
        specs = a0["growth_mix.scenarios"]

        def is_active(spec: dict) -> bool:
            v = desk.scenario_inputs(a0, spec)
            return (to_ui(CTRL["growth_mix"], v["growth_mix.mix"]) == ui["growth_mix"]
                    and abs(to_ui(CTRL["us_mean"], v["growth.us_mean"]) - ui["us_mean"]) < 1e-6
                    and abs(to_ui(CTRL["intl_mean"], v["growth.intl_mean"]) - ui["intl_mean"]) < 1e-6)

        unpaid = wl["Bills paid"] < 1.0
        shown = wl.assign(Key=[("● " if is_active(sp) else "") + k_ + (" ⚠" if u else "")
                               for sp, k_, u in zip(specs, wl["Key"], unpaid)])
        shown = shown[["Key", "Gift P50", "vs G1", "Gift P10", "Spread"]]
        styler = (shown.style.format({"Gift P50": "${:,.0f}", "vs G1": "{:+.1%}", "Gift P10": "${:,.0f}"})
                  .map(lambda v: GOOD_CELL if v > 0.0005 else BAD_CELL if v < -0.0005 else MUTED_CELL, subset=["vs G1"])
                  .map(lambda v: BAD_CELL if "⚠" in v else "", subset=["Key"]))
        with panel("watch", "Watchlist", [("Growth mixes", str(len(wl)))],
                   f"Every growth-mix scenario in config.yaml, run on the official assumptions ({int(a0['simulation.dashboard_n_sims']):,} "
                   "paths, same seed). Click a row to load it into the inputs above; ● marks the one loaded. "
                   "Spread: the facility gift distribution on one shared scale. -V rows and G8 use Vanguard's "
                   "pessimistic returns."):
            st.dataframe(styler, key="watch", on_select=load_scenario, selection_mode="single-row", hide_index=True,
                         width="stretch", height=390,
                         column_config={"Key": st.column_config.TextColumn("Mix", width="small"),
                                        "Spread": st.column_config.AreaChartColumn("Spread", y_min=0, width="small")})
            warn = "".join(f'<div class="down">⚠ {k_}: bills unpaid in {1 - p_:.2%} of futures even with the '
                           f'safety net</div>' for k_, p_ in zip(wl["Key"], wl["Bills paid"]) if p_ < 1.0)
            st.markdown('<div class="pn-body wl-legend">' + "".join(
                f'<div><b>{k_}</b> {html.escape(m_)}</div>' for k_, m_ in zip(wl["Key"], wl["Mix"])) + warn + "</div>",
                unsafe_allow_html=True)

# --------------------------------------------------------- detail tabs ----
# Same panels as the Desk: quote strips for the headline figures, titled chart panels, and
# tables grouped in tabbed panels. Explanations sit in the ⓘ notes.
with t_bills:
    vy = res.timeline.valuation_year
    last = res.timeline.bill_years[-1]
    if out["unverified"]:
        est = ", ".join(u.split(" (")[0].replace("Bill ", "") for u in out["unverified"])
        detail = " | ".join(out["unverified"]).replace('"', "'")
        st.markdown(f'<div class="note-warn"><b>{len(out["unverified"])} ladder prices are estimates</b> (bills {est}): '
                    'replace them with the WInS fill prices in ladder.csv'
                    f'<span class="tip" data-tip="{html.escape(detail)}">ⓘ</span></div>', unsafe_allow_html=True)
    cs = out["coverage"]
    top = out["bill_rank"].iloc[0]
    quote_strip([
        ("(a) All bills paid, whole portfolio", f"{stats['p_all_paid']:.2%}",
         f"{stats['n_failed']:,} paths fail · with {html_money(a['waterfall.backstop_amount'])} net "
         f"{stats['p_all_paid_with_backstop']:.2%} · foresight {stats['p_foresight']:.2%}"),
        ("(b) Paid by ladder + buffer alone", f"{stats['p_ladder_only']:.1%}", "no top-up from the growth bucket"),
        (f"(c) Top-up moved in {vy}, median", html_money(stats["topup_median"]),
         f"P90 {html_money(stats['topup_p90'])} · P99 {html_money(stats['topup_p99'])} · max "
         f"{html_money(stats['topup_max'])} · mean released after {last} {html_money(stats['cushion_mean'])}"),
        ("Bill-dollar coverage, median", f"{cs['coverage_median']:.1%}",
         f"ladder + buffer ÷ {html_money(cs['bill_dollars'])} · P10 {cs['coverage_p10']:.1%} · worst "
         f"{cs['coverage_worst']:.1%}"),
        ("Shortfall when short, median", html_money(cs["shortfall_median"]),
         f"P90 {html_money(cs['shortfall_p90'])} · max {html_money(cs['shortfall_max'])} · {cs['n_short']:,} paths"),
        ("Bill short most often", f"#{int(top['Bill #'])} · Jan {int(top['Bill (Jan 1)'])}",
         f"short on {top['Share of paths short']:.1%} of paths"),
    ])
    c1, c2 = st.columns(2, gap="small")
    with c1:
        with panel("d_bills", "Ladder payout vs. bill", [("Bills", str(n_bills))],
                   f"Bills are paid in order: ladder payouts, then the T-bill buffer, then the growth bucket. On Jan 1 "
                   f"{vy}, before the facility gift, money moves from the growth bucket to the T-bill reserve using "
                   f"{out['rule_label']}, which needs no knowledge of future rates; what isn't needed is released to "
                   f"Laura after the Jan {last} bill. Dot: median payout of each bill's own rung; bar: P5–P95. "
                   "Hover a bill for how often the ladder alone falls short."):
            chart("bills")
    with c2:
        with panel("d_short", "Ladder-only shortfall", [("Paths short", f"{cs['n_short']:,}"),
                                                        ("Share", f"{cs['p_short']:.1%}")],
                   "Total unpaid bill dollars on the paths where the ladder and buffer alone fall short. The growth "
                   "bucket top-up covers these."):
            chart("shortfall")
    c1, c2 = st.columns(2, gap="small")
    with c1:
        with panel("d_buffer", "T-bill reserve, each Jan 1", [("Model", a["ladder.bond_payout_model"])],
                   f"After that day's bill; includes the Jan {vy} top-up from the growth bucket. "
                   "Bands: P5–P95 and P25–P75."):
            chart("buffer")
    with c2:
        with panel("d_tables", "Shortfalls", [("Rule", out["rule_label"])]):
            t1, t2, t3, t4, t5 = st.tabs(["Missed per path", "Short most often", "Shortfall sizes", "Rule fails",
                                          f"Top-up {vy}"])
            with t1:
                show_table(out["bills_missed"], {"Share of paths": "{:.2%}", "Paths": "{:,}"}, height=300,
                           cell_styles={"Bills short": lambda v: GOOD_CELL if v == 0 else BAD_CELL})
            with t2:
                show_table(out["bill_rank"], {"Share of paths short": "{:.1%}", "Median shortfall when short": "${:,.0f}"},
                           bad_if_positive=("Share of paths short", "Median shortfall when short"), height=300)
            with t3:
                sd = out["shortfall"].copy()
                if len(sd):
                    sd["Total shortfall"] = sd["Total shortfall"].map(
                        lambda v: v if isinstance(v, str) else analysis.money(v))
                    show_table(sd)
                else:
                    st.markdown('<div class="pn-text">Ladder + buffer alone pay every bill on every path.</div>',
                                unsafe_allow_html=True)
            with t4:
                fs = out["fail_shortfall"].copy()
                fs["Total unpaid"] = fs["Total unpaid"].map(lambda v: v if isinstance(v, str) else analysis.money(v))
                show_table(fs)
            with t5:
                tt = out["topup"]
                money_table(tt, list(tt.columns[1:]))
    with panel("d_rules", "Top-up rules compared", [("Paths", f"{res.n:,}")],
               "Every rule on the same simulated paths. Perfect foresight is a reference line only: it knows the "
               "future rates, which no real rule can."):
        show_table(out["rules"], height=35 * (len(out["rules"]) + 1) + 3)
    with panel("d_bybill", "By bill", [("Ladder cost", html_money(out["sheet_cost"])),
                                       (f"Jan 1 {res.timeline.purchase_year} reprice", html_money(out["jan_cost"])),
                                       ("Budget", html_money(a["plan.ladder_budget"]))],
               f"Treasury rung payout model: {a['ladder.bond_payout_model']}. Ladder cost from ladder.csv (priced "
               f"{out['price_dates']}), and repriced at unchanged yields on Jan 1 {res.timeline.purchase_year}. "
               f"Chance the ladder costs more than the budget: {stats['p_shortfall']:.1%} (median overrun "
               f"{analysis.money(stats['median_shortfall_when_short'])}, taken from the 2028 contribution)."):
        bt = out["bills"]
        money_table(bt, [c for c in bt.columns if c != "Bill (Jan 1)" and "share" not in c],
                    ("Ladder-only: share of paths short",),
                    bad_if_positive=("Ladder-only: share of paths short", "Ladder-only: median shortfall when short",
                                     "Ladder-only: P90 shortfall when short", "Whole portfolio: unpaid (mean)"))

with t_fac:
    pt = out["percentiles"]
    quote_strip([(f"Facility gift {vy}, median", html_money(facility_med), f"{a['facility.give_pct']:.0%} of the bucket after the top-up"),
                 ("P10", html_money(p10), "1 in 10 futures below"), ("P90", html_money(p90), "1 in 10 futures above"),
                 (f"Growth bucket {vy}, median", html_money(growth_med), f"before the top-up, on {kk(a['plan.growth_contribution'])}")])
    c1, c2 = st.columns(2, gap="small")
    with c1:
        with panel("d_fan", f"Growth bucket, each Jan 1 {tl.contribution_year}–{vy}", [("Paths", f"{res.n:,}")],
                   f"Nominal dollars. Jan {vy} is after the bill top-up. Bands: P10–P90 and P25–P75; hover a year for "
                   "its values."):
            chart("fan_chart")
    with c2:
        with panel("d_hist", f"Facility contribution, Jan {vy}", [("Median", kk(facility_med))],
                   f"{a['facility.give_pct']:.0%} of the growth bucket after the bill top-up; nominal. Shaded: the "
                   f"example co-sponsor range {analysis.money(rec['Low'])}–{analysis.money(rec['High'])}. Axis cut at P99.5."):
            chart("histogram")
    with panel("d_pct", "Percentiles", [("Nominal and real", f"Jan {a['inflation.base_year']} dollars")],
               f"Real dollars are Jan {a['inflation.base_year']} dollars ({analysis.inflation_text(a)})."):
        money_table(pt, list(pt.columns[1:]))

with t_range:
    quote_strip([("Example co-sponsor range (method)", f"{html_money(rec['Low'])}–{rec['High']:,.0f}",
                  f"{rec['P(at or above low end)']:.0%} of futures give at least the low end"),
                 ("Method", "P10 to median", f"both ends rounded down to {html_money(a['reporting.range_rounding'])}"),
                 ("Set for real", "2031", "from the actual bucket and ladder cost")])
    with panel("d_ranges", "Candidate ranges", [("Rule", out["rule_label"])],
               f"Each range is taken from the simulated facility contribution after the Jan {vy} top-up and rounded "
               f"down at both ends to the nearest {analysis.money(a['reporting.range_rounding'])}, so we never overstate. "
               f"P(inside range): chance the Jan {vy} contribution lands between the endpoints. P(at or above low "
               "end): chance the co-sponsor can count on at least the low end. The Bills tab compares the rules."):
        rt = out["ranges"].copy()
        rt.insert(0, "Example co-sponsor range (method)", rt["Range"].eq(rec["Range"]).map({True: "★", False: ""}))
        money_table(rt, ["Low", "High", "Low (real)", "High (real)"], ("P(inside range)", "P(at or above low end)"))
        st.markdown(f'<div class="pn-text">★ Example co-sponsor range (method). {analysis.COSPONSOR_NOTE}</div>',
                    unsafe_allow_html=True)

with t_stress:
    stx = out["stress"]
    vy, last = res.timeline.valuation_year, res.timeline.bill_years[-1]

    def growth_label(g: str) -> str:
        return g.lower() if g == "Median" else g

    lr = analysis.low_rate_report(stx)
    cb = analysis.combined_report(stx)
    c1, c2 = st.columns(2, gap="small")
    if lr:
        with c1:
            with panel("d_low", "Low rates: T-bills at 0.5% every year, 2027–2042",
                       [("Rate the rule needs", analysis.fmt_rate_needed(lr["rate_needed"]))],
                       f"Fixed path, {out['rule_label']}, no further help. Only T-bill rates are stressed; the ladder "
                       f"is still bought at the sheet's yields. The rule uses {a['waterfall.rate_rule_rate']:.2%}; it "
                       f"pays every bill only if it assumes no more than T-bills actually earn after {vy}."):
                quote_strip([("All bills paid", "Yes" if lr["all_paid"] else "No",
                              f"rule moves {html_money(lr['moved'])} in Jan {vy}; {html_money(lr['needed'])} needed"),
                             ("Total shortfall", html_money(lr["unpaid"]),
                              f"{html_money(a['waterfall.backstop_amount'])} net "
                              f"{'covers it' if lr['backstop_covers'] else 'does not cover it'}")]
                            + [(f"Share of cushion ({growth_label(g['growth'])})", f"{g['share']:.1%}",
                                f"of {html_money(g['cushion'])} kept") for g in lr["by_growth"]])
    if cb:
        with c2:
            with panel("d_comb", "Combined: yields 2 pts lower AND T-bills at 0.5%",
                       [("Ladder cost", html_money(cb["ladder_cost"]))],
                       f"Fixed path, {out['rule_label']}. {analysis.money(cb['shortfall_from_2028'])} of the ladder cost "
                       f"comes out of the 2028 contribution. The rule moves {analysis.money(cb['moved'])} in Jan {vy}; "
                       f"{analysis.money(cb['needed'])} was needed. The bill shortfall matches the low-rate case: the rule "
                       f"sees the smaller reserve and moves more, so its only error is the "
                       f"{a['waterfall.rate_rule_rate']:.1%} reinvestment assumption. The costlier ladder shows up as a "
                       "smaller facility gift."):
                quote_strip([("Pre-net shortfall", html_money(cb["unpaid"]), "unpaid bill dollars"),
                             ("Net covers it?", "Yes" if cb["backstop_covers"] else "No",
                              f"used {html_money(cb['backstop_used'])} of {html_money(cb['backstop'])}"),
                             (f"Net left after {last}", html_money(cb["backstop_left"]),
                              f"incl. {html_money(cb['backstop_interest'])} interest · back to Laura")]
                            + [(f"Facility ({growth_label(g['growth'])})", html_money(g["facility"]),
                                f"{html_money(g['facility_real'])} real") for g in cb["by_growth"]])
    c1, c2 = st.columns([1, 1.25], gap="small")
    with c1:
        with panel("d_stress_chart", "Facility by stress scenario", [("MC median", kk(facility_med))],
                   f"One fixed future per row, after the bill top-up, nominal. {out['rule_label']}."):
            chart("stress_tests")
    with c2:
        with panel("d_stress_tbl", "All scenarios", [("Scenarios", str(len(stx)))],
                   "rule_rate_needed: highest reinvestment rate the rate rule can assume and still pay every bill "
                   "on that path."):
            fmt_cols = ("scenario", "description", "all_bills_paid", "ladder_only_all_paid", "backstop_covers",
                        "unpaid_pct_of_cushion", "rule_rate_needed")
            shown = stx.drop(columns=["description"]).copy()
            shown["scenario"] = [desk.stress_label(n) for n in shown["scenario"]]
            shown["rule_rate_needed"] = shown["rule_rate_needed"].map(analysis.fmt_rate_needed)
            show_table(shown, {**{c: "${:,.0f}" for c in stx.columns if c not in fmt_cols},
                               "unpaid_pct_of_cushion": "{:.1%}"},
                       yes_no=("all_bills_paid", "ladder_only_all_paid", "backstop_covers"),
                       bad_if_positive=("unpaid_bill_dollars", "unpaid_after_backstop", "shortfall_from_2028",
                                        "ladder_only_shortfall", "unpaid_pct_of_cushion"), height=360)
            with st.expander("Scenario definitions"):
                show_table(stx.assign(label=[desk.stress_label(n) for n in stx["scenario"]])[
                    ["label", "scenario", "description"]])
            st.download_button("Download stress_tests.csv", stx.to_csv(index=False), file_name="stress_tests.csv",
                               mime="text/csv")
    with panel("d_sens", "Sensitivity: expected stock return ± 1 point", [("Cases", str(len(out["sens"])))],
               "The same paths with both stock means shifted by the amount in config.yaml, plus Vanguard's "
               "pessimistic forecast."):
        sv = out["sens"]
        show_table(sv, {"us_mean": "{:.2%}", "intl_mean": "{:.2%}", "p_ladder_only": "{:.1%}",
                        "topup_median": "${:,.0f}", "p_all_bills_paid": "{:.2%}", "median_change_vs_base": "{:+.1%}",
                        **{c: "${:,.0f}" for c in sv.columns if c.startswith("facility_")}},
                   signed=("median_change_vs_base",))

with t_assump:
    rows = []
    for k, v in a0.values.items():
        cur = a[k]
        rows.append({
            "Assumption": k,
            "Official value": json.dumps(v) if isinstance(v, (list, dict)) else str(v),
            "Current value": json.dumps(cur) if isinstance(cur, (list, dict)) else str(cur),
            "Changed": "yes" if k in overrides else "",
            "Status": a0.statuses.get(k, ""),
            "Source": a0.sources[k],
            "Note": a0.notes.get(k, ""),
        })
    status_counts = pd.Series([r["Status"] for r in rows]).value_counts()
    quote_strip([("Assumptions", f"{len(rows)}", "every input in config.yaml"),
                 ("Sourced", str(status_counts.get("sourced", 0)), "with a cited source"),
                 ("Policy", str(status_counts.get("policy", 0)), "team decisions"),
                 ("Placeholders", str(status_counts.get("placeholder", 0)), "no confirmed source yet"),
                 ("Changed now", str(len(overrides)), "by the inputs above")])
    with panel("d_config", "config.yaml", [("Inputs", html.escape(FINGERPRINT[:8]))],
               "Every input with its status and source. Placeholders (source: TODO) have no confirmed source yet. "
               "Changed: differs from config.yaml because of the inputs above."):
        show_table(pd.DataFrame(rows), height=520,
                   cell_styles={"Status": lambda v: GOOD_CELL if v in ("sourced", "policy") else BAD_CELL,
                                "Changed": lambda v: WARN_CELL if v else ""})
    with panel("d_ladder", "ladder.csv", [("Rows", str(n_bills)), ("Estimates", str(len(out["unverified"])))]):
        show_table(load_ladder(a).table,
                   cell_styles={"data_status": lambda v: WARN_CELL if "estimate" in str(v).lower() else ""})
