"""Load config.yaml into flat {dotted.key: value} and {dotted.key: source} maps."""
from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = PROJECT_ROOT / "config.yaml"
REQUIRED_FIELDS = ("value", "source", "status")
STATUSES = ("sourced", "policy", "placeholder")   # sourced and policy count as resolved


def _is_leaf(node: Any) -> bool:
    return isinstance(node, dict) and "value" in node


def _flatten(node: dict, prefix: str, values: dict, sources: dict, statuses: dict, notes: dict) -> None:
    for key, child in node.items():
        dotted = f"{prefix}{key}"
        if _is_leaf(child):
            missing = [f for f in REQUIRED_FIELDS if f not in child]
            if missing:
                raise ValueError(f"config entry '{dotted}' is missing {missing}")
            if child["status"] not in STATUSES:
                raise ValueError(f"config entry '{dotted}' status must be one of {STATUSES}")
            if not str(child["source"]).strip():
                raise ValueError(f"config entry '{dotted}' has an empty source")
            values[dotted] = child["value"]
            sources[dotted] = str(child["source"])
            statuses[dotted] = child["status"]
            notes[dotted] = str(child.get("note", ""))
        elif isinstance(child, dict):
            _flatten(child, f"{dotted}.", values, sources, statuses, notes)
        else:
            raise ValueError(
                f"config entry '{dotted}' must be {{value, source, status}} or a group of them"
            )


def parse_fraction(x: Any) -> float:
    """Accept 0.5, "0.5" or "1/3"."""
    return float(Fraction(str(x)))


@dataclass(frozen=True)
class Assumptions:
    values: dict[str, Any]
    sources: dict[str, str]
    base_dir: Path = field(default=PROJECT_ROOT)
    statuses: dict[str, str] = field(default_factory=dict)
    notes: dict[str, str] = field(default_factory=dict)
    config_path: Path = field(default=DEFAULT_CONFIG)

    def __getitem__(self, key: str) -> Any:
        return self.values[key]

    def with_overrides(self, **overrides: Any) -> "Assumptions":
        """Return a copy with some values replaced. Keys use '__' for '.'."""
        values = copy.deepcopy(self.values)
        for key, val in overrides.items():
            dotted = key.replace("__", ".")
            if dotted not in values:
                raise KeyError(f"unknown assumption '{dotted}'")
            values[dotted] = val
        return Assumptions(values, self.sources, self.base_dir, self.statuses, self.notes, self.config_path)

    def override(self, mapping: dict[str, Any]) -> "Assumptions":
        """Same as with_overrides but takes dotted keys directly."""
        return self.with_overrides(**{k.replace(".", "__"): v for k, v in mapping.items()})

    def cache_key(self) -> str:
        return json.dumps(self.values, sort_keys=True, default=str)

    def unresolved(self) -> list[str]:
        """Assumptions still marked status: placeholder (sourced and policy are resolved)."""
        return [k for k, s in self.statuses.items() if s == "placeholder"]

    def placeholders(self) -> list[str]:
        return self.unresolved()

    def inputs_fingerprint(self) -> str:
        """SHA-256 of config.yaml and the ladder sheet: identifies the inputs behind a run."""
        h = hashlib.sha256(Path(self.config_path).read_bytes())
        h.update(self.path("ladder.csv_path").read_bytes())
        return h.hexdigest()

    def path(self, key: str) -> Path:
        p = Path(self.values[key])
        return p if p.is_absolute() else self.base_dir / p


def load_config(path: str | Path = DEFAULT_CONFIG) -> Assumptions:
    path = Path(path)
    with open(path) as f:
        raw = yaml.safe_load(f)
    values: dict[str, Any] = {}
    sources: dict[str, str] = {}
    statuses: dict[str, str] = {}
    notes: dict[str, str] = {}
    _flatten(raw, "", values, sources, statuses, notes)
    return Assumptions(values, sources, path.resolve().parent, statuses, notes, path.resolve())
