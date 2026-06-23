from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "check_module_coverage.py"
SPEC = importlib.util.spec_from_file_location("check_module_coverage", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
coverage_gate = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = coverage_gate
SPEC.loader.exec_module(coverage_gate)


def _report(*, lines: tuple[int, int], branches: tuple[int, int]):
    return {
        "files": {
            "module.py": {
                "summary": {
                    "covered_lines": lines[0],
                    "num_statements": lines[1],
                    "covered_branches": branches[0],
                    "num_branches": branches[1],
                }
            }
        }
    }


def test_module_coverage_gate_accepts_exact_threshold() -> None:
    threshold = {"module.py": coverage_gate.Threshold(80, 70)}
    assert coverage_gate.check_coverage(_report(lines=(8, 10), branches=(7, 10)), threshold) == []


def test_module_coverage_gate_reports_line_branch_and_missing_module() -> None:
    thresholds = {
        "module.py": coverage_gate.Threshold(90, 85),
        "missing.py": coverage_gate.Threshold(80, 70),
    }
    errors = coverage_gate.check_coverage(_report(lines=(8, 10), branches=(3, 4)), thresholds)
    assert any("line coverage" in error for error in errors)
    assert any("branch coverage" in error for error in errors)
    assert any("missing from coverage report" in error for error in errors)


def test_module_coverage_gate_treats_branchless_module_as_fully_covered() -> None:
    threshold = {"module.py": coverage_gate.Threshold(100, 100)}
    assert coverage_gate.check_coverage(_report(lines=(1, 1), branches=(0, 0)), threshold) == []
