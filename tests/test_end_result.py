"""outputs/end_result.md, the A2 decision line and the IPS charts: every number comes from
outputs/metrics.json (or the files it was built from); nothing is typed by hand."""
from __future__ import annotations

import json
import re

import numpy as np
import pandas as pd
import pytest

from mcsim import analysis, ips
from mcsim.config import load_config
from mcsim.model import run_monte_carlo


@pytest.fixture(scope="module")
def a():
    return load_config()


@pytest.fixture(scope="module")
def m(a):
    return json.loads((a.base_dir / "outputs" / "metrics.json").read_text())


def _numbers(node):
    if isinstance(node, dict):
        for v in node.values():
            yield from _numbers(v)
    elif isinstance(node, list):
        for v in node:
            yield from _numbers(v)
    elif isinstance(node, (int, float)) and not isinstance(node, bool):
        yield float(node)


def _allowed(m: dict) -> set[str]:
    """Every way a metrics.json number is formatted in the reports."""
    out = set()
    for v in _numbers(m):
        out |= {analysis.money(v), analysis.money(round(v, -2)), analysis.money(round(v, -3))}
        out |= {analysis.pct(v, d) for d in (0, 1, 2)}
    return out


def test_end_result_is_rendered_from_metrics(a, m):
    text = (a.base_dir / "outputs" / "end_result.md").read_text()
    assert text == analysis.render_end_result(m)
    assert m["inputs_sha256"] == a.inputs_fingerprint(), "outputs/ is stale: rerun run_simulation.py --final"


def test_every_number_in_end_result_is_a_metrics_value(a, m):
    pattern = r"\$\d{1,3}(?:,\d{3})*|\d+(?:\.\d+)?%"
    text = (a.base_dir / "outputs" / "end_result.md").read_text().split("<!--")[0]
    tokens = re.findall(pattern, text)
    allowed = _allowed(m) | set(re.findall(pattern, m["worst_description"]))   # scenario text from config.yaml
    assert tokens and all(t in allowed for t in tokens), [t for t in tokens if t not in allowed]
    e = m["end_result"]
    assert analysis.money(e["money_in"]["ladder"]) == "$300,000" and analysis.money(e["money_in"]["growth"]) == "$150,000"
    assert len(e["bills"]["seeds"]) == 1 + len(a["simulation.robustness_seeds"])          # official + 3 seeds


def test_end_result_metrics_add_up_path_by_path(a):
    res = run_monte_carlo(a, n=5_000)
    seeds = [{"seed": 1, "n": res.n, "p_paid": 1.0, "fails": 0}]
    e = analysis.end_result_metrics(a, res, seeds)
    paid = res.bill_paid.sum(axis=1) + res.backstop_draw.sum(axis=1)
    free = res.cushion_kept - res.backstop_start
    leftover = res.cushion_release + res.backstop_left
    assert e["leftover"]["median"] == pytest.approx(float(np.median(leftover)))
    assert e["total_value"]["median"] == pytest.approx(float(np.median(paid + res.facility + free + leftover)))
    assert e["bills"]["paid"]["p10"] <= e["bills"]["total"] + 1e-6
    if res.all_paid_with_backstop.all():
        assert e["bills"]["paid"]["median"] == pytest.approx(e["bills"]["total"])
    src = e["bill_sources"]
    assert np.allclose(np.array(src["own"]) + src["reserve"], res.bill_paid.mean(axis=0))
    # the backstop is counted once: what it paid is in bills paid, what is left in the leftover
    assert np.allclose(res.backstop_draw.sum(axis=1) + res.backstop_left,
                       res.backstop_start + res.backstop_interest)
    # no dollar counted twice: the total equals the money's sources, path by path (bills the portfolio paid,
    # reserve left after the last bill, growth bucket after the top-up, interest the backstop earned)
    assert (res.final_buffer >= -1e-9).all()
    total = paid + res.facility + free + leftover
    assert np.allclose(total, res.bill_paid.sum(axis=1) + res.final_buffer + res.value + res.backstop_interest)
    # adding the TOTAL cushion instead would count the backstop twice
    assert np.allclose(paid + res.facility + res.cushion_kept + leftover - total, res.backstop_start)


def test_a2_decision_line_matches_the_seed_check(a, m):
    d = m["option_decision"]
    seeds = pd.read_csv(a.base_dir / "outputs" / "hardening_seeds.csv")
    assert (seeds["inputs_sha256"] == a.inputs_fingerprint()).all()
    for key in ("A2", "A4"):
        rows = seeds[seeds["key"] == key]
        assert d[key]["spare"] == pytest.approx(rows["spare"].min())
        main = rows[rows["seed"] == int(a["simulation.seed"])].iloc[0]
        assert d[key]["facility_median"] == pytest.approx(main["facility_median"])
        assert d[key]["cushion_free_median"] == pytest.approx(main["cushion_free_median"])
    line = analysis.option_decision_line(d)
    assert line in (a.base_dir / "outputs" / "summary.md").read_text()
    assert "We chose the safer option for client money." in line
    assert a["waterfall.rate_rule_rate"] == 0.01 and a["waterfall.backstop_amount"] == 10_000        # A2 official


def test_ips_charts_use_metrics_and_plain_words(a, m):
    growth = pd.read_csv(a.base_dir / "outputs" / "growth_scenarios.csv")
    figs = [ips.bills_chart(m), ips.growth_mix_chart(growth, m["valuation_year"]), ips.facility_chart(m)]
    texts = []
    for fig in figs:
        t = [x.get_text() for x in fig.texts] + [x.get_text() for ax in fig.axes for x in ax.texts]
        t += [x.get_text() for ax in fig.axes for x in ax.get_yticklabels()]
        t += [x.get_text() for ax in fig.axes if ax.get_legend() for x in ax.get_legend().get_texts()]
        texts.append(" ".join(t))
    joined = " ".join(texts)
    for jargon in ("P10", "P50", "P90", "AR(1)", "percentile", "median"):
        assert jargon not in joined, jargon
    assert "bad case (1 in 10)" in joined.lower()
    assert analysis.money(m["end_result"]["facility"]["median"]) in texts[2]
    assert analysis.money(m["end_result"]["facility"]["p10"]) in texts[2]
    assert analysis.money(m["worst_facility"]) in texts[2]
    assert "Why 60/40, and why no leverage" in texts[1] and "(our plan)" in texts[1]
    for name in ("1_bills_paid.png", "2_growth_mix.png", "3_facility_range.png"):
        assert (a.base_dir / "outputs" / "ips" / name).exists(), name
