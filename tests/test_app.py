"""Dashboard smoke tests (Streamlit AppTest, no browser or server needed)."""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parent.parent
REPO_FILES = ["app.py", "config.yaml", "ladder.csv", "mcsim", "requirements.txt"]


def run_app(folder: Path) -> AppTest:
    return AppTest.from_file(str(folder / "app.py"), default_timeout=180).run()


def page_html(at: AppTest) -> str:
    return " ".join(m.value for m in at.markdown)


TOP_TABS = ["Desk", "Report", "Bills", "Facility", "Co-sponsor range", "Stress tests", "Assumptions"]


def top_tabs(at: AppTest) -> dict:
    """The dashboard's own tabs by label (at.tabs also lists the Desk's nested panel tabs)."""
    names, found, i = list(TOP_TABS), {}, 0
    for t in at.tabs:
        if i < len(names) and t.label == names[i] and (names[i] != "Stress tests" or "Report" in found):
            found[names[i]] = t
            i += 1
    return found


def test_dashboard_runs_and_shows_official_headline():
    at = run_app(ROOT)
    assert not at.exception, [e.value for e in at.exception]
    html = page_html(at)
    labels = ("Facility contribution 2033, median", "Example co-sponsor range (method)", "All bills paid",
              "Laura keeps in 2033, median", "Growth bucket 2033, before top-up and 75/25 split")
    for label in labels:
        assert label in html, label                                     # quote strip at the top
    strip = html.split('class="tk-row"')[1].split('class="sig"')[0]
    syms = [x.split("</div>")[0] for x in strip.split('<div class="sym">')[1:]]
    assert syms[:2] == list(labels[:2])                                 # facility median and range lead
    assert strip.count('class="tk lead"') == 2
    assert "Growth money" not in strip                                  # never read as the facility amount
    from mcsim.analysis import COSPONSOR_NOTE
    assert COSPONSOR_NOTE in html                                       # the 2031 note under the range
    bills = " ".join(m.value for m in top_tabs(at)["Bills"].markdown)
    assert "Bill-dollar coverage, median" in bills                       # detail tabs still there
    assert list(top_tabs(at)) == TOP_TABS


def test_overview_explains_the_plan_in_plain_words():
    at = run_app(ROOT)
    overview = top_tabs(at)["Report"]
    text = " ".join(m.value for m in overview.markdown)
    for phrase in ("The plan", "What protects the bills", "What can shrink the facility gift"):
        assert phrase in text
    captions = " ".join(c.value for c in overview.caption)
    assert captions.count("How to read:") == 5                           # five exhibits, each explained


def test_dashboard_reads_only_repo_files(tmp_path):
    """A clean copy with only the files the app needs (no outputs/, no venv) still runs."""
    for name in REPO_FILES:
        src = ROOT / name
        if src.is_dir():
            shutil.copytree(src, tmp_path / name, ignore=shutil.ignore_patterns("__pycache__"))
        else:
            shutil.copy(src, tmp_path / name)
    at = run_app(tmp_path)
    assert not at.exception, [e.value for e in at.exception]


def test_placeholder_banner_shown_while_placeholders_remain():
    from mcsim.config import load_config
    at = run_app(ROOT)
    banner = [w.value for w in at.warning if "placeholders" in w.value]
    assert bool(banner) == bool(load_config().placeholders())


def test_dashboard_runs_dashboard_run_count():
    from mcsim.config import load_config
    at = run_app(ROOT)
    n = load_config()["simulation.dashboard_n_sims"]
    assert any(f"{n:,} simulated paths" in c.value for c in at.caption)


def test_overview_reads_like_a_memo():
    at = run_app(ROOT)
    page = page_html(at)
    assert "Bottom line" in page and "Every bill is paid in all 10,000 simulated futures" in page
    assert page.count('<div class="fig">') + page.count('<div class="fig lead">') == 5   # key-figures strip
    html = " ".join(m.value for m in top_tabs(at)["Report"].markdown)
    for n in range(1, 6):
        assert f"Exhibit {n}</div>" in html                              # numbered exhibits
    assert html.count('class="ex-src">Source:') == 5                     # each exhibit has a source line
    assert html.count('class="bm-tile"') == 10 and "ev-table" in html     # bill map and schedule


def test_desk_screen_has_command_bar_panels_and_status_bar():
    from mcsim.analysis import run_stress_tests
    from mcsim.config import load_config
    at = run_app(ROOT)
    for key in ("us_mean", "give_pct", "rate_rule_rate", "backstop_amount"):
        assert at.number_input(key=key) is not None                    # command bar inputs, always in view
    desk = top_tabs(at)["Desk"]
    html = " ".join(m.value for m in desk.markdown)
    for title in ("Growth bucket, monthly", "Facility gift,", "Bill map", "Watchlist"):
        assert f'<span class="pn-title">{title}' in html                  # panels, each with an ⓘ note
    assert html.count('class="tip"') >= 5
    blotter = html.split('class="tt"')[1].split("</table>")[0]
    assert blotter.count("<tr") == 1 + 10 and blotter.count('class="focus"') == 1   # one row per bill, one focused
    assert [t.label for t in desk.tabs if t.label != "Desk"] == ["Positions", "Stress tests", "Calendar"]  # bottom panel
    assert len(desk.dataframe) == 2                                       # stress table + watchlist (selectable)
    assert len(desk.dataframe[0].value) == len(run_stress_tests(load_config()))
    assert len(desk.dataframe[1].value) == len(load_config()["growth_mix.scenarios"])
    assert "● G1" in desk.dataframe[1].value["Key"].tolist()             # official mix marked as loaded
    page = page_html(at)
    assert 'class="sbar"' in page and "Official inputs" in page and "Deploy" in page
    assert '<span class="tag">Official inputs</span>' in page


def test_bill_tile_focuses_that_bill():
    at = run_app(ROOT)
    at.button(key="tile_2").click().run()
    assert not at.exception, [e.value for e in at.exception]
    html = " ".join(m.value for m in top_tabs(at)["Desk"].markdown)
    rows = html.split('class="tt"')[1].split("</table>")[0].split("<tr")
    focused = [r for r in rows if 'class="focus"' in r]
    assert len(focused) == 1 and ">2035<" in focused[0]                  # third bill (Jan 2035) highlighted
    assert "Bill 2035" in html                                            # and summarised above its payout chart


def test_loading_vanguard_returns_marks_g8_in_the_watchlist_and_ghosts_official():
    import json
    from mcsim import desk
    from mcsim.config import load_config
    a = load_config()
    g8 = next(s for s in a["growth_mix.scenarios"] if s["key"] == "G8")
    v = desk.scenario_inputs(a, g8)
    at = run_app(ROOT)
    at.number_input(key="us_mean").set_value(round(v["growth.us_mean"] * 100, 6))
    at.slider(key="intl_mean").set_value(round(v["growth.intl_mean"] * 100, 6)).run()
    assert not at.exception, [e.value for e in at.exception]
    dk = top_tabs(at)["Desk"]
    assert "● G8" in dk.dataframe[1].value["Key"].tolist()
    names = {tr.get("name") for c in dk.get("plotly_chart") for tr in json.loads(c.proto.spec)["data"]}
    assert {"Official P50", "Official"} <= names                          # official run drawn as a ghost


def test_changing_an_input_marks_the_run_modified_and_shows_moves():
    at = run_app(ROOT)
    at.number_input(key="us_mean").set_value(5.0).run()
    assert not at.exception, [e.value for e in at.exception]
    page = page_html(at)
    assert '<span class="tag mod">Modified inputs</span>' in page
    assert "vs official" in page and "▼" in page                         # lower returns: facility moves down


def test_charts_are_interactive_terminal_on_desk_light_in_report():
    import json
    at = run_app(ROOT)
    tabs = top_tabs(at)
    bg = lambda tab: {json.loads(c.proto.spec)["layout"]["paper_bgcolor"] for c in tab.get("plotly_chart")}
    assert len(tabs["Desk"].get("plotly_chart")) == 3                   # Desk: paths, facility, focused bill
    assert len(tabs["Report"].get("plotly_chart")) == 4                 # Report: four exhibits (+ the bill map)
    assert len(at.get("plotly_chart")) == 13 and len(at.get("imgs")) == 0   # every chart interactive, no PNGs
    assert bg(tabs["Desk"]) == bg(tabs["Bills"]) == {"#131722"}         # TradingView dark
    assert bg(tabs["Report"]) == {"#ffffff"}                            # the memo stays on white paper


def test_detail_tabs_use_quote_strips_and_panels():
    at = run_app(ROOT)
    tabs = top_tabs(at)
    for name in ("Bills", "Facility", "Co-sponsor range", "Stress tests", "Assumptions"):
        html = " ".join(m.value for m in tabs[name].markdown)
        assert 'class="tk-row q"' in html, name                            # headline figures as a quote strip
        assert html.count('class="pn-title"') >= 1, name                   # content in titled panels
    assert len(at.metric) == 0                                            # no leftover boxed metrics
    from mcsim.analysis import COSPONSOR_NOTE
    assert COSPONSOR_NOTE in " ".join(m.value for m in tabs["Co-sponsor range"].markdown)
