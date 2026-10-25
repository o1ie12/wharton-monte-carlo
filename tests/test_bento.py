"""Overview bento cards: SVG gauge and tick bars, the hero ribbon chart, and the cards' numbers."""
from __future__ import annotations

import json
import re

import numpy as np
import pytest

from mcsim import bento, iplots


def test_gauge_lights_the_right_share_of_ticks():
    for frac, lit in [(1.0, 56), (0.0, 0), (0.5, 28), (0.926, round(0.926 * 56))]:
        svg = bento.gauge(frac)
        assert svg.count("<line") == 56 and f'data-lit="{lit}"' in svg
        assert svg.count(bento.OFF) == 56 - lit                       # unlit ticks are the dark grey
    assert 'data-lit="56"' in bento.gauge(7.0) and 'data-lit="0"' in bento.gauge(-1.0)   # clamped


def test_tickbar_lit_ticks_and_ruler_marks():
    svg = bento.tickbar(0.384, n=48)
    assert svg.count("<line") == 48 and f'data-lit="{round(0.384 * 48)}"' in svg
    tops = re.findall(r'y1="(\d+)"', svg)
    assert tops.count("1") == 8 and tops.count("5") == 40            # every 6th tick is taller


def test_pieces_use_only_grey_and_the_lavender_to_peach_blend():
    colours = set(re.findall(r"#[0-9a-f]{6}", bento.gauge(1.0) + bento.tickbar(1.0) + bento.gauge(0.3)))
    for c in colours - {bento.OFF}:
        rgb = [int(c[i:i + 2], 16) for i in (1, 3, 5)]
        t = (rgb[0] - bento.LAVENDER[0]) / (bento.PEACH[0] - bento.LAVENDER[0])      # position along the blend
        assert 0 <= t <= 1, c
        for ch in range(3):
            assert abs(rgb[ch] - (bento.LAVENDER[ch] + (bento.PEACH[ch] - bento.LAVENDER[ch]) * t)) <= 2, c


@pytest.fixture(scope="module")
def monthly_inputs():
    x = np.linspace(150e3, 200e3, 61)
    return {"sample": np.tile(x, (5, 1)) * np.linspace(0.8, 1.3, 5)[:, None], "median": x, "p10": x * 0.8, "p90": x * 1.3}


def test_hero_is_a_price_chart_with_a_range_switch(monthly_inputs):
    m = monthly_inputs
    fig = iplots.desk_paths_chart(m, 2028, 150_000.0, selector=False, height=300)
    assert fig.layout.paper_bgcolor == "rgba(0,0,0,0)" and fig.layout.yaxis.side == "right"   # price-chart axis
    assert not fig.layout.xaxis.rangeselector.buttons                                           # the card has its own switch
    p50 = next(t for t in fig.data if t.name == "P50")
    np.testing.assert_allclose(p50.y, m["median"])
    assert p50.line.color == "#ffffff" and p50.fill == "tozeroy"                                # white line, fading area
    tags = [a.text.replace("<b>", "").replace("</b>", "") for a in fig.layout.annotations if a.xref == "paper"]
    assert {"P50 200k", "P90 260k", "P10 160k"} <= set(tags)                                    # value tags on the right
    one_year = iplots.desk_paths_chart(m, 2028, 150_000.0, last_months=12, selector=False)
    p50y = next(t for t in one_year.data if t.name == "P50")
    assert len(p50y.x) == 12 and p50y.x[-1] == next(t for t in fig.data if t.name == "P50").x[-1]
    np.testing.assert_allclose(p50y.y, m["median"][-12:])
    assert len(iplots.desk_paths_chart(m, 2028, 150_000.0).layout.xaxis.rangeselector.buttons) == 3   # Desk keeps it
    json.loads(fig.to_json())


def test_bento_theme_charts_are_transparent_and_keep_numbers():
    from mcsim.config import load_config
    from mcsim.model import run_monte_carlo
    a = load_config()
    res = run_monte_carlo(a, n=2_000)
    fig = iplots.transparent(iplots.bill_sources_chart(res, "bento"), height=230)
    assert fig.layout.paper_bgcolor == "rgba(0,0,0,0)" and fig.layout.height == 230 and not fig.layout.showlegend
    own, reserve, net = (t.y for t in fig.data)
    np.testing.assert_allclose(np.asarray(own) + reserve, res.bill_paid.mean(0))
