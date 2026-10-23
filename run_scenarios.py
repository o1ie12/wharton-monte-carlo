"""Treasury rung sizing scenarios (reinvestment risk). Never touches ladder.csv.

    python run_scenarios.py

Writes outputs/reinvestment_diagnosis.md, outputs/scenarios/ladder_F_strips.csv,
outputs/sizing_scenarios.md and outputs/sizing_scenarios.csv.
"""
from __future__ import annotations

import time
from pathlib import Path

import pandas as pd

from mcsim import scenarios
from mcsim.config import load_config

ROOT = Path(__file__).parent
PAR_CURVE = ROOT / "data" / "treasury_par_curve_2026-10-09.csv"


def main() -> None:
    started = time.perf_counter()
    a = load_config()
    out = ROOT / "outputs"
    (out / "scenarios").mkdir(parents=True, exist_ok=True)

    diag = scenarios.diagnose(a)
    (out / "reinvestment_diagnosis.md").write_text(scenarios.diagnosis_markdown(diag))

    strips = out / "scenarios" / "ladder_F_strips.csv"
    scenarios.build_strips_sheet(a, PAR_CURVE, strips)
    rows = scenarios.run_sizing_scenarios(a, strips_sheet=str(strips))
    curve_date, _ = scenarios.load_par_curve(PAR_CURVE)
    md = scenarios.sizing_markdown(a, rows, diag["cases"]["official"]["any_1_5_short"],
                                   curve_date.date().isoformat())
    (out / "sizing_scenarios.md").write_text(md)
    pd.DataFrame(rows).assign(estimate_note=[scenarios.STRIPS_NOTE if r["estimate"] else "" for r in rows]) \
        .to_csv(out / "sizing_scenarios.csv", index=False)
    print(md)
    print(f"({time.perf_counter() - started:.0f}s)")


if __name__ == "__main__":
    main()
