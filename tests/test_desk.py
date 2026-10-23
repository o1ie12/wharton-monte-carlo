"""Desk tables: the ladder blotter and stress matrix match the simulation, and the HTML table
helper escapes text and applies its classes."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from mcsim import analysis, desk
from mcsim.config import load_config
from mcsim.model import load_ladder, run_monte_carlo


@pytest.fixture(scope="module")
def run():
    a = load_config()
    return a, load_ladder(a), run_monte_carlo(a, n=2000)


def test_blotter_one_row_per_bill_matching_the_ladder_and_results(run):
    a, ladder, res = run
    b = desk.blotter(ladder, res)
    assert list(b["Bill"]) == list(res.timeline.bill_years)
    np.testing.assert_allclose(b["Cost"], ladder.sheet_cost)
    np.testing.assert_allclose(b["Payout P50"], np.median(res.rung_payout, axis=0))
    np.testing.assert_allclose(b["Top-up %"], (res.ladder_only_shortfall > 1e-6).mean(axis=0))
    est = ladder.table["data_status"].astype(str).str.upper().str.contains("ESTIMATE")
    assert (b["Px"] == "EST").tolist() == est.tolist()
    assert b.loc[0, "Instrument"] == ladder.table["ticker_or_cusip"][0]          # ETF rung shows its ticker


def test_stress_matrix_results(run):
    a, ladder, res = run
    stress = analysis.run_stress_tests(a)
    sm = desk.stress_matrix(stress, 100_000.0)
    assert len(sm) == len(stress)
    assert sm["Scenario"].tolist() == [desk.stress_label(n) for n in stress["scenario"]]
    for (_, r), (_, s) in zip(sm.iterrows(), stress.iterrows()):
        want = "PAID" if s["all_bills_paid"] else "NET" if s["backstop_covers"] else "SHORT"
        assert r["Result"] == want
        assert r["vs P50"] == pytest.approx(s["facility_contribution"] / 100_000.0 - 1)


def test_table_html_escapes_and_classes():
    df = pd.DataFrame({"Name": ["<b>x</b>"], "Value": [1.5], "Note": ["long text"], "_title": ['say "hi"']})
    out = desk.table_html(df, fmt={"Value": lambda v: f"{v:.1f}"}, cls={"Value": lambda v: "up"},
                          left=("Name", "Note"), wrap=("Note",))
    assert "&lt;b&gt;x&lt;/b&gt;" in out and "<b>x</b>" not in out
    assert '<td class="up">1.5</td>' in out and '<td class="l w">long text</td>' in out
    assert 'title="say &quot;hi&quot;"' in out and "_title" not in out


def test_watchlist_covers_every_growth_scenario_against_g1(run):
    a, ladder, res = run
    wl = desk.watchlist(a, 2000)
    assert wl["Key"].tolist() == [s["key"] for s in a["growth_mix.scenarios"]]
    g1 = wl.set_index("Key").loc["G1"]
    assert g1["vs G1"] == 0 and g1["Gift P50"] == pytest.approx(float(np.median(res.facility)))   # G1 = official
    assert all(len(sp) == len(wl["Spread"][0]) for sp in wl["Spread"])     # one shared sparkline scale


def test_scenario_inputs_reproduce_the_growth_scenario(run):
    a, ladder, res = run
    from mcsim import growth
    for spec in a["growth_mix.scenarios"]:
        v = desk.scenario_inputs(a, spec)
        mine = run_monte_carlo(a.override(v), n=2000)
        theirs = run_monte_carlo(growth.scenario_assumptions(a, spec), n=2000)
        np.testing.assert_allclose(mine.facility, theirs.facility)      # same inputs -> same futures


def test_stress_path_matches_the_stress_test(run):
    a, ladder, res = run
    stress = analysis.run_stress_tests(a).set_index("scenario")
    for name in ("normal", "crash_2028", "bad"):
        path = desk.stress_growth_path(a, name)
        assert path[0] == pytest.approx(stress.loc[name, "growth_contribution"])
        assert path[-1] == pytest.approx(stress.loc[name, "value_2033_before_topup"])
    assert desk.stress_label("crash_2028") == "Stocks -40% in 2028"
    assert desk.stress_label("new_case") == "New case"                   # unknown names still read plainly
