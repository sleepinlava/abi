#!/usr/bin/env python3
"""Enforce risk-based line and branch coverage thresholds from coverage.py JSON."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


@dataclass(frozen=True)
class Threshold:
    line: float
    branch: float


THRESHOLDS: dict[str, Threshold] = {
    "src/abi/dag.py": Threshold(90, 85),
    "src/abi/dag_planner.py": Threshold(90, 85),
    "src/abi/executor.py": Threshold(80, 70),
    "src/abi/internal.py": Threshold(90, 85),
    "src/abi/resources.py": Threshold(80, 70),
    "src/abi/runtimes/hpc.py": Threshold(80, 70),
    "src/abi/runtimes/local.py": Threshold(80, 70),
    "src/abi/step_runner.py": Threshold(80, 70),
}


def _percentage(covered: int, total: int) -> float:
    return 100.0 if total == 0 else covered * 100.0 / total


def check_coverage(
    report: Mapping[str, Any], thresholds: Mapping[str, Threshold] = THRESHOLDS
) -> list[str]:
    files = report.get("files", {})
    errors: list[str] = []
    for module, threshold in thresholds.items():
        details = files.get(module)
        if not isinstance(details, Mapping):
            errors.append(f"{module}: missing from coverage report")
            continue
        summary = details.get("summary", {})
        line = _percentage(
            int(summary.get("covered_lines", 0)), int(summary.get("num_statements", 0))
        )
        branch = _percentage(
            int(summary.get("covered_branches", 0)), int(summary.get("num_branches", 0))
        )
        print(
            f"{module}: line={line:.2f}% (min {threshold.line:.0f}%), "
            f"branch={branch:.2f}% (min {threshold.branch:.0f}%)"
        )
        if line + 1e-9 < threshold.line:
            errors.append(f"{module}: line coverage {line:.2f}% < {threshold.line:.0f}%")
        if branch + 1e-9 < threshold.branch:
            errors.append(f"{module}: branch coverage {branch:.2f}% < {threshold.branch:.0f}%")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--coverage", type=Path, default=Path("coverage.json"))
    args = parser.parse_args()
    try:
        report = json.loads(args.coverage.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: cannot read coverage report {args.coverage}: {exc}", file=sys.stderr)
        return 2
    errors = check_coverage(report)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print("Risk-based module coverage gates passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
