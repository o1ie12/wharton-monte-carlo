"""Run the Monte Carlo with config.yaml and write every report to outputs/.

    python run_simulation.py [--config config.yaml] [--out outputs] [--final]

Default: the official run, simulation.n_sims paths. --final: the final-report run,
simulation.report_n_sims paths; refused while any assumption is still a placeholder.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

from mcsim import analysis, plots
from mcsim.config import load_config
from mcsim.model import run_monte_carlo


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default=Path(__file__).parent / "config.yaml")
    ap.add_argument("--out", default=Path(__file__).parent / "outputs")
    ap.add_argument("--final", action="store_true",
                    help="final-report run with simulation.report_n_sims paths (needs zero placeholders)")
    args = ap.parse_args()
    out = Path(args.out)

    a = load_config(args.config)
    if args.final:
        if a.placeholders():
            sys.exit(f"--final refused: {len(a.placeholders())} assumptions are still placeholders "
                     "(source: TODO). Source them first; see config.yaml.")
        a = a.override({"simulation.n_sims": a["simulation.report_n_sims"]})
    out.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    res = run_monte_carlo(a)
    stress = analysis.run_stress_tests(a)
    sens = analysis.run_sensitivity(a)
    rec = analysis.recommended_range(res, a)
    oct2026 = analysis.oct2026_facility(run_monte_carlo(a.override(analysis.OCT2026_OVERRIDES)))   # footnote
    seed_runs = [{"seed": int(a["simulation.seed"]), "n": res.n, "p_paid": float(res.all_paid_with_backstop.mean()),
                  "fails": int((~res.all_paid_with_backstop).sum())}]
    for seed in a["simulation.robustness_seeds"]:                  # same run on the robustness seeds
        r = run_monte_carlo(a, seed=int(seed))
        seed_runs.append({"seed": int(seed), "n": r.n, "p_paid": float(r.all_paid_with_backstop.mean()),
                          "fails": int((~r.all_paid_with_backstop).sum())})
        del r
    decision = analysis.option_decision(a, out)                    # needs run_hardening.py on these inputs

    (out / "summary.md").write_text(analysis.build_summary(a, res, stress, sens, oct2026=oct2026, decision=decision))
    stress.to_csv(out / "stress_tests.csv", index=False)
    metrics = analysis.headline_metrics(a, res, stress, oct2026)
    metrics["end_result"] = analysis.end_result_metrics(a, res, seed_runs)
    if decision:
        metrics["option_decision"] = decision
    (out / "metrics.json").write_text(json.dumps(metrics, indent=1) + "\n")
    (out / "headline.md").write_text(analysis.render_headline(metrics))
    (out / "end_result.md").write_text(analysis.render_end_result(metrics))
    if not decision:
        print("NOTE: outputs/hardening_seeds.csv is missing or stale; run run_hardening.py, then this again, "
              "to add the A2 vs A4 line to summary.md.")
    sens.to_csv(out / "sensitivity.csv", index=False)
    figures = {
        "fan_chart.png": plots.fan_chart(res),
        "histogram.png": plots.histogram(res, rec["Low"], rec["High"]),
        "bills.png": plots.bills_chart(res),
        "buffer.png": plots.buffer_chart(res),
        "shortfall.png": plots.shortfall_chart(res),
        "stress_tests.png": plots.stress_chart(stress, float(np.median(res.facility))),
    }
    for name, fig in figures.items():
        (out / name).write_bytes(plots.to_png(fig))

    ls = analysis.ladder_stats(res)
    print(f"(a) P(all bills paid) official, {analysis.rule_label(a)} + ${a['waterfall.backstop_amount']:,.0f} "
          f"backstop = {ls['p_all_paid_with_backstop']:.2%}; without backstop {ls['p_all_paid']:.2%} "
          f"[perfect-foresight reference {ls['p_foresight']:.2%}]")
    print(f"(b) P(ladder + buffer alone pay all bills) = {ls['p_ladder_only']:.1%}")
    print(f"(c) Jan {res.timeline.valuation_year} top-up moved: median ${ls['topup_median']:,.0f}, "
          f"P90 ${ls['topup_p90']:,.0f}, P99 ${ls['topup_p99']:,.0f}, max ${ls['topup_max']:,.0f}")
    print(f"Median facility contribution = ${np.median(res.facility):,.0f}")
    print(f"Example co-sponsor range (method) {rec['Range']}: ${rec['Low']:,.0f}-${rec['High']:,.0f} "
          f"({rec['P(at or above low end)']:.0%} at or above low end)")
    print(f"Wrote {len(figures) + 6} files to {out.resolve()} "
          f"({res.n:,} paths, {time.perf_counter() - started:.1f}s)")


if __name__ == "__main__":
    main()
