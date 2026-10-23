"""Round 4c: options to harden scenario A against persistent low T-bill rates.

    python run_hardening.py [--n 500000]

Writes outputs/hardening_options.md and .csv, plus the --compare options on the official seed and
--seeds (outputs/hardening_seeds.csv). Does not change config.yaml or ladder.csv.
"""
from __future__ import annotations

import argparse
import time
from pathlib import Path

import pandas as pd

from mcsim import scenarios
from mcsim.config import load_config


def main() -> None:
    a = load_config()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--n", type=int, default=int(a["simulation.report_n_sims"]))
    ap.add_argument("--compare", nargs="*", default=["A2", "A4"], help="options to check on extra seeds")
    ap.add_argument("--seeds", type=int, nargs="*", default=[int(x) for x in a["simulation.robustness_seeds"]])
    args = ap.parse_args()
    started = time.perf_counter()
    rows = [scenarios.run_hardening_option(a, o, args.n) for o in scenarios.HARDENING_OPTIONS]
    out = Path(__file__).parent / "outputs"
    md = scenarios.hardening_markdown(rows)
    seed_rows = [{**r, "inputs_sha256": a.inputs_fingerprint()}   # summary.md only uses rows from these inputs
                 for r in scenarios.hardening_seed_check(a, args.compare, [int(a["simulation.seed"])] + args.seeds, args.n)]
    md += "\n" + scenarios.hardening_seed_markdown(seed_rows)
    (out / "hardening_options.md").write_text(md)
    pd.DataFrame(rows).to_csv(out / "hardening_options.csv", index=False)
    pd.DataFrame(seed_rows).to_csv(out / "hardening_seeds.csv", index=False)
    print(md)
    print(f"({time.perf_counter() - started:.0f}s)")


if __name__ == "__main__":
    main()
