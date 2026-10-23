"""Tiny inline SVG charts (sparklines) for the dashboard's KPI cards and the bill map colours.

Shapes only: colours come from CSS classes (sp-line, sp-band, sp-bar, sp-hi, sp-ok, sp-warn,
sp-bad, sp-mark) so the page's stylesheet decides how they look.
"""
from __future__ import annotations

import numpy as np

W, H = 180, 40


def _svg(body: str, w: int = W, h: int = H) -> str:
    return (f'<svg class="spark" viewBox="0 0 {w} {h}" width="100%" height="{h}" preserveAspectRatio="none" '
            f'xmlns="http://www.w3.org/2000/svg">{body}</svg>')


def _scale(v: np.ndarray, lo: float, hi: float, h: int = H, pad: float = 3.0) -> np.ndarray:
    span = (hi - lo) or 1.0
    return h - pad - (np.asarray(v, float) - lo) / span * (h - 2 * pad)


def line(series, band_lo=None, band_hi=None, baseline: float | None = None, w: int = W, h: int = H) -> str:
    """A line (e.g. the typical path) with an optional shaded band and dashed baseline."""
    y = np.asarray(series, float)
    vals = [y] + [np.asarray(b, float) for b in (band_lo, band_hi) if b is not None]
    lo = min(v.min() for v in vals + ([np.array([baseline])] if baseline is not None else []))
    hi = max(v.max() for v in vals + ([np.array([baseline])] if baseline is not None else []))
    x = np.linspace(0, w, len(y))
    body = ""
    if band_lo is not None and band_hi is not None:
        top = _scale(band_hi, lo, hi, h)
        bot = _scale(band_lo, lo, hi, h)
        pts = " ".join(f"{a:.1f},{b:.1f}" for a, b in zip(x, top)) + " " + \
              " ".join(f"{a:.1f},{b:.1f}" for a, b in zip(x[::-1], bot[::-1]))
        body += f'<polygon class="sp-band" points="{pts}"/>'
    if baseline is not None:
        yb = float(_scale([baseline], lo, hi, h)[0])
        body += f'<line class="sp-base" x1="0" x2="{w}" y1="{yb:.1f}" y2="{yb:.1f}"/>'
    pts = " ".join(f"{a:.1f},{b:.1f}" for a, b in zip(x, _scale(y, lo, hi, h)))
    body += f'<polyline class="sp-line" fill="none" points="{pts}"/>'
    return _svg(body, w, h)


def hist(x, bins: int = 32, highlight: tuple[float, float] | None = None, mark: float | None = None,
         clip_pct: float = 99.0, w: int = W, h: int = H) -> str:
    """A small histogram; bars inside `highlight` get the sp-hi class, `mark` draws a thin line."""
    x = np.asarray(x, float)
    lo, hi = float(x.min()), float(np.percentile(x, clip_pct))
    counts, edges = np.histogram(np.clip(x, lo, hi), bins=bins, range=(lo, hi))
    bw = w / bins
    peak = counts.max() or 1
    body = ""
    for i, c in enumerate(counts):
        bh = (h - 2) * c / peak
        mid = (edges[i] + edges[i + 1]) / 2
        cls = "sp-hi" if highlight and highlight[0] <= mid <= highlight[1] else "sp-bar"
        body += f'<rect class="{cls}" x="{i * bw + 0.6:.1f}" y="{h - bh:.1f}" width="{bw - 1.2:.1f}" height="{bh:.1f}"/>'
    if mark is not None:
        xm = (mark - lo) / ((hi - lo) or 1.0) * w
        body += f'<line class="sp-mark" x1="{xm:.1f}" x2="{xm:.1f}" y1="0" y2="{h}"/>'
    return _svg(body, w, h)


def bars(values, classes, top: float | None = None, w: int = W, h: int = H) -> str:
    """One bar per value (e.g. one per bill), each with its own CSS class."""
    v = np.asarray(values, float)
    top = top or (v.max() or 1.0)
    n = len(v)
    bw = w / n
    body = ""
    for i, (val, cls) in enumerate(zip(v, classes)):
        bh = max((h - 2) * min(val / top, 1.0), 1.5)
        body += f'<rect class="{cls}" x="{i * bw + 1.5:.1f}" y="{h - bh:.1f}" width="{bw - 3:.1f}" height="{bh:.1f}" rx="1.5"/>'
    return _svg(body, w, h)


def split(parts: list[tuple[float, str]], w: int = W, h: int = 14) -> str:
    """A horizontal bar split into shares, e.g. [(0.75, "sp-bar"), (0.25, "sp-hi")]."""
    total = sum(p for p, _ in parts) or 1.0
    x, body = 0.0, ""
    for p, cls in parts:
        pw = w * p / total
        body += f'<rect class="{cls}" x="{x:.1f}" y="2" width="{max(pw - 2, 0):.1f}" height="{h - 4}" rx="3"/>'
        x += pw
    return _svg(body, w, h)


# Bill-map colours: green (never needs help) -> amber -> red (often needs help), like a market heatmap.
HEAT_STOPS = [(0.00, (21, 128, 61)), (0.05, (52, 152, 92)), (0.20, (120, 150, 100)), (0.35, (202, 138, 4)),
              (0.50, (234, 88, 12)), (0.65, (185, 28, 28))]


def heat_color(share: float) -> str:
    """Hex colour for a share of paths needing help (0 = green, >= 65% = deep red)."""
    s = float(np.clip(share, 0.0, HEAT_STOPS[-1][0]))
    for (a, ca), (b, cb) in zip(HEAT_STOPS, HEAT_STOPS[1:]):
        if s <= b:
            t = (s - a) / (b - a)
            rgb = [round(x + (y - x) * t) for x, y in zip(ca, cb)]
            return "#{:02x}{:02x}{:02x}".format(*rgb)
    return "#{:02x}{:02x}{:02x}".format(*HEAT_STOPS[-1][1])


# Memo-style bill map: one navy scale, light (never needs help) -> deep navy (often needs help).
NAVY_STOPS = [(0.00, (238, 242, 247)), (0.10, (201, 214, 231)), (0.30, (110, 138, 175)), (0.60, (31, 58, 95))]


def navy_color(share: float) -> tuple[str, str]:
    """(background, text) hex colours for a share of paths needing help."""
    s = float(np.clip(share, 0.0, NAVY_STOPS[-1][0]))
    rgb = NAVY_STOPS[-1][1]
    for (a, ca), (b, cb) in zip(NAVY_STOPS, NAVY_STOPS[1:]):
        if s <= b:
            t = (s - a) / (b - a)
            rgb = tuple(round(x + (y - x) * t) for x, y in zip(ca, cb))
            break
    text = "#ffffff" if s >= 0.2 else "#16191f"
    return "#{:02x}{:02x}{:02x}".format(*rgb), text


# Finviz heatmap scale (green = good, grey = flat, red = bad), in its seven fixed steps.
FINVIZ = ["#30cc5a", "#2f9e4f", "#35764e", "#414554", "#8b444e", "#bf4045", "#f63538"]
FINVIZ_STEPS = [0.05, 0.15, 0.25, 0.35, 0.45, 0.55]          # upper edges of each step (share needing help)


def finviz_color(share: float) -> str:
    """Tile colour for a share of paths where the bill needs the top-up: 0% bright green ... 55%+ red."""
    for edge, color in zip(FINVIZ_STEPS, FINVIZ):
        if share < edge:
            return color
    return FINVIZ[-1]
