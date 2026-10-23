"""Seed robustness and before/after check: the official run's headline numbers on the official
seed and on extra seeds, for the current ladder.csv or another ladder file.

    python run_seeds.py                                    # current ladder, official seed + 1, 2, 3
    python run_seeds.py --ladder data/ladder_round6_estimates.csv --label "Round 6"

Runs simulation.report_n_sims paths per seed (500,000) and writes outputs/seed_check.md.
"""
from __future__ import annotations

import argparse
import time
from pathlib import Path

import numpy as np
import pandas as pd

from mcsim import analysis
from mcsim.config import load_config
from mcsim.model import ladder_costs, load_ladder, run_monte_carlo


def key_metrics(a, n: int, seed: int) -> dict:
    """Headline numbers for one run (the rows of the Round 6 before/after table)."""
    res = run_monte_carlo(a, n=n, seed=seed)
    ladder = load_ladder(a)
    short = (res.bill_paid < res.bill_amount - 1e-6)                  # bill short before the backstop
    by_bill = short.sum(axis=0)
    order = np.argsort(-by_bill)
    rec = analysis.recommended_range(res, a)
    return {
        "seed": seed, "n": res.n,
        "fail_with_backstop": int((~res.all_paid_with_backstop).sum()),
        "p_with_backstop": float(res.all_paid_with_backstop.mean()),
        "p_without_backstop": float(res.all_paid.mean()),
        "max_unpaid_pre_backstop": float(res.unpaid.max()),
        "max_backstop_draw": float(res.backstop_used.max()),
        "bills_short": [(int(k) + 1, int(by_bill[k])) for k in order if by_bill[k] > 0][:3],
        "sheet_cost": float(ladder.sheet_cost.sum()),
        "jan_cost": float(ladder_costs(ladder, [0.0], a).sum()),
        "buffer_median": float(np.median(res.buffer_start)),
        "topup_median": float(np.median(res.topup)),
        "facility_median": float(np.median(res.facility)),
        "facility_p10": float(np.percentile(res.facility, 10)),
        "range": (float(rec["Low"]), float(rec["High"])),
    }


def run(ladder_path: str | None, seeds: list[int], n: int | None = None) -> list[dict]:
    a = load_config()
    if ladder_path:
        a = a.override({"ladder.csv_path": str(Path(ladder_path).resolve())})
    n = int(n or a["simulation.report_n_sims"])
    return [key_metrics(a, n, s) for s in [int(a["simulation.seed"])] + seeds]


def table(runs: list[dict]) -> pd.DataFrame:
    money = analysis.money
    return pd.DataFrame([{
        "Seed": r["seed"], "Paths": f"{r['n']:,}",
        "All paid with backstop": f"{r['p_with_backstop']:.2%} ({r['fail_with_backstop']} fail)",
        "Without backstop": f"{r['p_without_backstop']:.2%}",
        "Max shortfall pre-backstop": money(r["max_unpaid_pre_backstop"]),
        "Largest backstop draw": money(r["max_backstop_draw"]),
        "Facility median": money(r["facility_median"]),
    } for r in runs])


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ladder", help="ladder file to use instead of config.yaml's ladder.csv")
    ap.add_argument("--label", default="Current ladder")
    ap.add_argument("--seeds", type=int, nargs="*", default=[1, 2, 3])
    ap.add_argument("--n", type=int)
    ap.add_argument("--out", default=None, help="markdown file to write (default outputs/seed_check.md for the current ladder)")
    args = ap.parse_args()
    t0 = time.perf_counter()
    runs = run(args.ladder, args.seeds, args.n)
    md = (f"# Seed check: {args.label}\n\n" + analysis.md_table(table(runs)) + "\n\n"
          f"Largest backstop draw on any seed: {analysis.money(max(r['max_backstop_draw'] for r in runs))} "
          f"of the backstop.\n")
    out = args.out or (None if args.ladder else str(Path(__file__).parent / "outputs" / "seed_check.md"))
    if out:
        Path(out).write_text(md)
    print(md)
    import json
    print(json.dumps(runs, default=str))
    print(f"[{time.perf_counter() - t0:.0f}s]")
