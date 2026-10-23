"""Pre-deploy gate. Exits non-zero until the project is ready for Streamlit Community Cloud.

    python check_deploy.py

Blocks deployment while any assumption is unresolved (status: placeholder; sourced and
policy count as resolved), any ladder.csv row is an estimate, or outputs/ was generated
from different inputs than the current ones.
"""
from __future__ import annotations

import json
import sys

from mcsim.config import load_config
from mcsim.model import load_ladder


def problems() -> list[str]:
    a = load_config()
    found = [f"unresolved assumption (status: placeholder, source: TODO): {k}" for k in a.unresolved()]
    found += [f"ladder.csv estimate row: {u}" for u in load_ladder(a).unverified]
    metrics = a.base_dir / "outputs" / "metrics.json"
    if not metrics.exists():
        found.append("outputs/metrics.json missing: run run_simulation.py")
    elif json.loads(metrics.read_text())["inputs_sha256"] != a.inputs_fingerprint():
        found.append("outputs/ is stale: rerun run_simulation.py")
    return found


if __name__ == "__main__":
    issues = problems()
    for issue in issues:
        print("NOT READY:", issue)
    print("Ready to deploy." if not issues else f"{len(issues)} issue(s); do not deploy.")
    sys.exit(1 if issues else 0)
