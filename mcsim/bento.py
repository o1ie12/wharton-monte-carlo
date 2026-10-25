"""Small SVG pieces for the Overview tab's bento cards: a radial tick gauge and tick progress bars.
Pure HTML/SVG strings, coloured with two hues only (lavender and a soft peach) plus greys."""
from __future__ import annotations

import math

LAVENDER = (154, 148, 255)
PEACH = (242, 166, 107)
OFF = "#363948"


def _mix(a: tuple, b: tuple, t: float) -> str:
    t = min(max(t, 0.0), 1.0)
    return "#{:02x}{:02x}{:02x}".format(*(round(x + (y - x) * t) for x, y in zip(a, b)))


def gauge(frac: float, n: int = 56, w: int = 320, h: int = 178) -> str:
    """Half-circle of ticks, filled left to right up to `frac` (0-1). Filled ticks fade from lavender
    to peach; the rest stay dark grey. The tick count that is lit is round(frac x n)."""
    frac = min(max(float(frac), 0.0), 1.0)
    lit = round(frac * n)
    cx, cy, r_out = w / 2, h - 8, w / 2 - 10
    body = ""
    for i in range(n):
        ang = math.pi * (1 - i / (n - 1))                       # left (pi) to right (0)
        length = 20 + 8 * math.sin(math.pi * i / (n - 1))       # a little longer in the middle of the arc
        x1, y1 = cx + (r_out - length) * math.cos(ang), cy - (r_out - length) * math.sin(ang)
        x2, y2 = cx + r_out * math.cos(ang), cy - r_out * math.sin(ang)
        on = i < lit
        color = _mix(LAVENDER, PEACH, (i / max(lit - 1, 1)) ** 2.2) if on else OFF
        body += (f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="{color}" '
                 f'stroke-width="3.2" stroke-linecap="round"/>')
    return (f'<svg class="bx-gauge" viewBox="0 0 {w} {h}" width="100%" xmlns="http://www.w3.org/2000/svg" '
            f'data-lit="{lit}" data-ticks="{n}">{body}</svg>')


def tickbar(frac: float, n: int = 48, w: int = 320, h: int = 22) -> str:
    """A row of vertical ticks, `round(frac x n)` of them lit (every 6th is taller, like a ruler)."""
    frac = min(max(float(frac), 0.0), 1.0)
    lit = round(frac * n)
    step = w / n
    body = ""
    for i in range(n):
        tall = i % 6 == 0
        top = 1 if tall else 5
        on = i < lit
        color = (_mix(LAVENDER, PEACH, i / max(n - 1, 1)) if on else OFF)
        x = i * step + step / 2
        body += (f'<line x1="{x:.1f}" y1="{top}" x2="{x:.1f}" y2="{h - 1}" stroke="{color}" stroke-width="2.4" '
                 f'stroke-linecap="round"/>')
    return (f'<svg class="bx-tickbar" viewBox="0 0 {w} {h}" width="100%" height="{h}" preserveAspectRatio="none" '
            f'xmlns="http://www.w3.org/2000/svg" data-lit="{lit}" data-ticks="{n}">{body}</svg>')
