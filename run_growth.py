"""Round 5: growth-bucket mix scenarios G1-G8.

    python run_growth.py [--n 100000]

Writes outputs/growth_scenarios.md, .csv and .png. Does not change config.yaml or ladder.csv.
"""
from __future__ import annotations

import argparse
import time
from pathlib import Path

from mcsim import growth, plots
from mcsim.config import load_config


def main() -> None:
    a = load_config()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--n", type=int, default=int(a["simulation.n_sims"]))
    args = ap.parse_args()
    started = time.perf_counter()
    rows = growth.run_growth_scenarios(a, args.n)
    out = Path(__file__).parent / "outputs"
    (out / "growth_scenarios.png").write_bytes(plots.to_png(growth.growth_chart(rows)))
    growth.rows_frame(rows).to_csv(out / "growth_scenarios.csv", index=False)
    md = growth.growth_markdown(rows)
    (out / "growth_scenarios.md").write_text(md)
    print(md)
    print(f"({time.perf_counter() - started:.0f}s)")


if __name__ == "__main__":
    main()
