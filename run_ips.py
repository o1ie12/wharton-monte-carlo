"""Print-ready charts for the Investment Policy Statement, written to outputs/ips/.

    python run_ips.py

Reads outputs/metrics.json (run_simulation.py --final) and outputs/growth_scenarios.csv
(run_growth.py); refuses if metrics.json was made from different inputs than the current ones.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

from mcsim import ips
from mcsim.config import load_config

CHARTS = ("1_bills_paid.png", "2_growth_mix.png", "3_facility_range.png")


def build(out: Path) -> dict:
    a = load_config()
    m = json.loads((out / "metrics.json").read_text())
    if m["inputs_sha256"] != a.inputs_fingerprint() or "end_result" not in m:
        sys.exit("outputs/metrics.json is stale or old: run run_simulation.py --final first.")
    growth = pd.read_csv(out / "growth_scenarios.csv")
    return {CHARTS[0]: ips.bills_chart(m), CHARTS[1]: ips.growth_mix_chart(growth, int(m["valuation_year"])),
            CHARTS[2]: ips.facility_chart(m)}


if __name__ == "__main__":
    out = Path(__file__).parent / "outputs"
    (out / "ips").mkdir(exist_ok=True)
    for name, fig in build(out).items():
        (out / "ips" / name).write_bytes(ips.to_png(fig))
        print("wrote", out / "ips" / name)
