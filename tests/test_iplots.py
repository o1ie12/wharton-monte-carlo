"""Interactive dashboard charts: every builder returns a Plotly figure in both themes, with the
same numbers as the simulation results."""
from __future__ import annotations

import numpy as np
import plotly.graph_objects as go
import pytest

from mcsim import analysis, growth, iplots
from mcsim.config import load_config
from mcsim.model import draw_random, load_ladder, run_monte_carlo

N = 2000
PICKS = [("normal", "Markets as expected"), ("bad", "Weak markets"), ("not_a_scenario", "ignored")]


@pytest.fixture(scope="module")
def run():
    a = load_config("config.yaml")
    res = run_monte_carlo(a, n=N)
    seed = int(a["simulation.seed"])
    v = growth.monthly_bucket_values(a, draw_random(a, load_ladder(a), N, seed), seed, res.growth_contribution)
    m = {"sample": v[:40], "median": np.median(v, 0), "p10": np.percentile(v, 10, 0), "p90": np.percentile(v, 90, 0)}
    return a, res, analysis.run_stress_tests(a), analysis.recommended_range(res, a), m


def builders(a, res, stress, rec, m, theme):
    return {
        "paths": iplots.sample_paths_chart(m, res.timeline.contribution_year, float(a["plan.growth_contribution"]),
                                           res.n, theme),
        "timeline": iplots.plan_timeline_chart(res, 300000, 150000, 0.75, 10000, theme),
        "sources": iplots.bill_sources_chart(res, theme),
        "outcomes": iplots.outcomes_chart(res, rec["Low"], rec["High"], theme),
        "histogram": iplots.outcomes_chart(res, rec["Low"], rec["High"], theme, plain=False),
        "whatif": iplots.whatif_chart(stress, PICKS, theme),
        "bills": iplots.bills_chart(res, theme),
        "buffer": iplots.buffer_chart(res, theme),
        "shortfall": iplots.shortfall_chart(res, theme),
        "fan": iplots.fan_chart(res, theme),
        "stress": iplots.stress_chart(stress, float(np.median(res.facility)), theme),
        "desk_paths": iplots.desk_paths_chart(m, res.timeline.contribution_year,
                                              float(a["plan.growth_contribution"]), theme),
        "desk_facility": iplots.desk_facility_chart(res, rec["Low"], rec["High"], theme),
    }


@pytest.mark.parametrize("theme", ["clean", "market", "desk"])
def test_every_chart_builds_with_theme_colours(run, theme):
    figs = builders(*run, theme)
    for name, fig in figs.items():
        assert isinstance(fig, go.Figure), name
        assert fig.layout.paper_bgcolor == iplots.THEMES[theme]["SURFACE"], name
        assert fig.layout.title.text or name.startswith("desk_"), name   # desk panels carry their own header
        fig.to_json()                                                    # serialisable for the browser


def test_charts_show_the_simulation_numbers(run):
    a, res, stress, rec, m = run
    figs = builders(*run, "clean")
    paths = figs["paths"]
    assert sum(bool(t.name and t.name.startswith("future")) for t in paths.data) == 40     # one line per sample future
    typical = next(t for t in paths.data if t.name and t.name.startswith("typical"))
    np.testing.assert_allclose(typical.y, m["median"])
    np.testing.assert_allclose(figs["outcomes"].data[0].x, res.facility)          # histogram of every path
    own, reserve, backstop = (t.y for t in figs["sources"].data)
    np.testing.assert_allclose(np.asarray(own) + reserve + backstop,
                               res.bill_paid.mean(0) + res.backstop_draw.mean(0))
    np.testing.assert_allclose(figs["bills"].data[0].y, np.median(res.rung_payout, axis=0))
    whatif = figs["whatif"].data[0]
    assert list(whatif.y) == ["Markets as expected", "Weak markets"]              # unknown scenario dropped
    want = stress.set_index("scenario").loc[["normal", "bad"], "facility_contribution"]
    np.testing.assert_allclose(whatif.x, want)
    assert len(figs["stress"].data[0].y) == len(stress)


def test_bare_drops_the_title_for_exhibit_headings(run):
    fig = iplots.bare(builders(*run, "clean")["outcomes"])
    assert not fig.layout.title.text


def test_desk_charts_show_the_simulation_numbers(run):
    a, res, stress, rec, m = run
    figs = builders(*run, "desk")
    p50 = next(t for t in figs["desk_paths"].data if t.name == "P50")
    np.testing.assert_allclose(p50.y, m["median"])
    assert figs["desk_paths"].layout.yaxis.side == "right"               # price-chart axis
    bars = figs["desk_facility"].data[0]
    assert abs(sum(bars.y) - (res.facility <= np.percentile(res.facility, 99.5)).mean()) < 1e-9
    accent = iplots.THEMES["desk"]["BLUE_450"]
    inside = [c == accent for c in bars.marker.color]
    assert all(rec["Low"] <= x <= rec["High"] for x, i in zip(bars.x, inside) if i)   # range bars highlighted


def test_desk_paths_ghost_and_overlay(run):
    a, res, stress, rec, m = run
    from mcsim import desk
    path = desk.stress_growth_path(a, "crash_2028")
    fig = iplots.desk_paths_chart(m, res.timeline.contribution_year, 150000.0, ghost=m["median"] * 1.1,
                                  overlay=("Stocks -40% in 2028", path))
    by_name = {t.name: t for t in fig.data}
    np.testing.assert_allclose(by_name["Official P50"].y, m["median"] * 1.1)
    np.testing.assert_allclose(by_name["Stocks -40% in 2028"].y, path)
    tags = sorted(an.y for an in fig.layout.annotations if an.xref == "paper")
    assert all(b - a_ > 0 for a_, b in zip(tags, tags[1:]))               # value tags never stack on each other
    fac = iplots.desk_facility_chart(res, rec["Low"], rec["High"], ghost=res.facility)
    assert [t.name for t in fac.data] == ["This run", "Official"]
    bill = iplots.desk_bill_chart(res, 9)
    reds = sum(y for x, y, c in zip(bill.data[0].x, bill.data[0].y, bill.data[0].marker.color)
               if c == iplots.THEMES["desk"]["CRITICAL"])
    assert all(x < res.bill_amount for x, c in zip(bill.data[0].x, bill.data[0].marker.color)
               if c == iplots.THEMES["desk"]["CRITICAL"]) and 0 < reds < 1
