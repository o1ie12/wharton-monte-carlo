"""Sparklines and bill-map colours for the dashboard."""
import numpy as np

from mcsim import sparks


def test_bars_one_rect_per_value_with_its_class():
    svg = sparks.bars([0.0, 0.1, 0.5], ["sp-ok", "sp-warn", "sp-bad"])
    assert svg.startswith("<svg") and svg.endswith("</svg>")
    assert svg.count("<rect") == 3
    assert svg.index("sp-ok") < svg.index("sp-warn") < svg.index("sp-bad")


def test_hist_highlights_only_bars_inside_the_range():
    x = np.random.default_rng(0).normal(100, 10, 10_000)
    svg = sparks.hist(x, bins=20, highlight=(95, 105), mark=100)
    assert svg.count("<rect") == 20
    assert 0 < svg.count('class="sp-hi"') < 20
    assert 'class="sp-mark"' in svg


def test_line_with_band_and_baseline():
    t = np.linspace(0, 1, 61)
    svg = sparks.line(150 + 50 * t, 140 + 20 * t, 160 + 90 * t, baseline=150)
    assert "<polyline" in svg and "<polygon" in svg and 'class="sp-base"' in svg


def test_split_bar_shares():
    svg = sparks.split([(75, "sp-bar"), (25, "sp-hi")])
    assert svg.count("<rect") == 2


def test_heat_colour_runs_green_to_red():
    import colorsys
    assert sparks.heat_color(0.0) == "#15803d"
    assert sparks.heat_color(0.9) == "#b91c1c"                 # clipped at the top stop

    def hue(share):
        h = sparks.heat_color(share)
        r, g, b = (int(h[i:i + 2], 16) / 255 for i in (1, 3, 5))
        return colorsys.rgb_to_hsv(r, g, b)[0] * 360
    hues = [hue(s) for s in (0.0, 0.1, 0.2, 0.35, 0.5, 0.65)]
    assert hues == sorted(hues, reverse=True)                  # green (~140 deg) down to red (~0 deg)
    assert hues[0] > 120 and hues[-1] < 10


def test_navy_colour_darkens_with_share_and_flips_text():
    light_bg, light_text = sparks.navy_color(0.0)
    dark_bg, dark_text = sparks.navy_color(0.9)
    assert light_bg == "#eef2f7" and light_text == "#16191f"
    assert dark_bg == "#1f3a5f" and dark_text == "#ffffff"
    lum = lambda h: sum(int(h[i:i + 2], 16) for i in (1, 3, 5))
    assert lum(sparks.navy_color(0.1)[0]) > lum(sparks.navy_color(0.3)[0]) > lum(sparks.navy_color(0.5)[0])


def test_finviz_scale_steps_green_to_red():
    assert sparks.finviz_color(0.0) == "#30cc5a" and sparks.finviz_color(0.9) == "#f63538"
    shares = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6]
    assert [sparks.finviz_color(x) for x in shares] == sparks.FINVIZ          # one step per band
