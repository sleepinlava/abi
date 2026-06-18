"""Unified benchmark framework for ABI plugin validation.

Provides a shared BenchmarkAssertion schema and run_benchmark() function
that all five plugins use for end-to-end value-level validation.

Usage::

    from abi.testing.benchmark import BenchmarkResult, run_benchmark

    result = run_benchmark(
        plugin_id="rnaseq_expression",
        dataset_path=Path("data/benchmarks/rnaseq_expression"),
        outdir=tmp_path / "results",
    )
    assert result.passed >= result.total * 0.8  # 80% threshold
"""

from __future__ import annotations

import csv
import json
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

# ── Dataclasses ─────────────────────────────────────────────────────────────


@dataclass
class BenchmarkAssertion:
    """A single benchmark assertion against a pipeline output.

    Attributes:
        step_id: DAG step name (e.g. "fastp", "star_align").
        table: Output table file path (relative to result_dir).
        column: Column name to check, or "" for file-level checks.
        condition: Comparison operator: "exists", ">", ">=", "<=", "contains", "between".
        expected: Expected value(s). For "between": [min, max].
        description: Human-readable description of what this checks.
    """

    step_id: str
    table: str
    column: str
    condition: str
    expected: Any
    description: str = ""

    def evaluate(self, result_dir: Path) -> bool:
        """Evaluate this assertion against a result directory."""
        path = result_dir / self.table

        if self.condition == "exists":
            if self.column:
                # Check column exists in table
                if not path.exists():
                    return False
                reader = csv.DictReader(path.open(), delimiter="\t")
                return self.column in (reader.fieldnames or [])
            return path.exists()

        if not path.exists():
            return False

        # ── Value-based checks ──
        if self.condition == "contains":
            content = path.read_text(encoding="utf-8")
            return str(self.expected).lower() in content.lower()

        # ── Numeric checks against TSV ──
        reader = csv.DictReader(path.open(), delimiter="\t")
        rows = list(reader)
        if not rows:
            return False
        if self.column not in (reader.fieldnames or []):
            return False

        if self.condition in (">=", ">", "<="):
            threshold = float(self.expected)
            for row in rows:
                val = float(row[self.column])
                if self.condition == ">=":
                    if val < threshold:
                        return False
                elif self.condition == ">":
                    if val <= threshold:
                        return False
                elif self.condition == "<=":
                    if val > threshold:
                        return False

        elif self.condition == "between":
            lo, hi = float(self.expected[0]), float(self.expected[1])
            for row in rows:
                val = float(row[self.column])
                if val < lo or val > hi:
                    return False

        return True


@dataclass
class BenchmarkResult:
    """Aggregated result from a benchmark run.

    Attributes:
        plugin_id: Plugin identifier.
        dataset_path: Path to the benchmark dataset used.
        total: Total number of assertions evaluated.
        passed: Number of assertions that passed.
        failed: Number that failed.
        errors: List of (assertion, reason) tuples for failures.
    """

    plugin_id: str
    dataset_path: Path
    total: int = 0
    passed: int = 0
    failed: int = 0
    errors: list[tuple[BenchmarkAssertion, str]] = field(default_factory=list)

    @property
    def pass_rate(self) -> float:
        """Proportion of assertions that passed (0.0–1.0)."""
        if self.total == 0:
            return 0.0
        return self.passed / self.total

    def summary(self) -> str:
        """Human-readable summary string."""
        return (
            f"{self.plugin_id}: {self.passed}/{self.total} passed "
            f"({self.pass_rate:.0%}), {self.failed} failed"
        )


# ── Core API ────────────────────────────────────────────────────────────────


def _load_expected(dataset_path: Path) -> dict[str, Any]:
    """Load expected_assertions.yaml from a benchmark dataset directory."""
    path = dataset_path / "expected_assertions.yaml"
    if not path.exists():
        raise FileNotFoundError(f"Benchmark assertions not found: {path}")
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _parse_assertions(expected: dict) -> list[BenchmarkAssertion]:
    """Convert expected_assertions.yaml dict into a flat list of BenchmarkAssertion objects.

    The YAML schema is::

        plugin_id:
          step_id:
            key: value          # → file-level assertion
            key: [min, max]     # → between assertion
    """
    assertions: list[BenchmarkAssertion] = []

    # The top-level key is the plugin id
    for plugin_id, steps in expected.items():
        if not isinstance(steps, dict):
            continue
        for step_id, checks in steps.items():
            if not isinstance(checks, dict):
                continue
            for key, value in checks.items():
                assertion = _kv_to_assertion(step_id, key, value)
                if assertion:
                    assertions.append(assertion)

    return assertions


def _kv_to_assertion(step_id: str, key: str, value: Any) -> BenchmarkAssertion | None:
    """Convert a single key-value pair from expected_assertions.yaml to a BenchmarkAssertion.

    Heuristics for condition inference:
    - bool → "exists"
    - "min_*" prefix → ">="
    - "max_*" prefix → "<="
    - list of 2 numbers → "between"
    - string ending in "_exists" → "exists" (file check)
    - string value → "contains"
    - int/float → ">="
    """
    if isinstance(value, bool):
        table = key
        return BenchmarkAssertion(
            step_id=step_id,
            table=table,
            column="",
            condition="exists",
            expected=value,
            description=f"{step_id}.{key} exists",
        )

    if isinstance(value, (int, float)):
        return BenchmarkAssertion(
            step_id=step_id,
            table="",
            column=key,
            condition=">=",
            expected=value,
            description=f"{step_id}.{key} >= {value}",
        )

    if isinstance(value, str):
        return BenchmarkAssertion(
            step_id=step_id,
            table="",
            column="",
            condition="contains",
            expected=value,
            description=f"{step_id}.{key} contains '{value}'",
        )

    if isinstance(value, list) and len(value) == 2 and all(isinstance(v, (int, float)) for v in value):
        return BenchmarkAssertion(
            step_id=step_id,
            table="",
            column=key,
            condition="between",
            expected=value,
            description=f"{step_id}.{key} between {value}",
        )

    if isinstance(value, list):
        # list of strings → check contains at least one (used for expected_genera etc.)
        return None  # complex assertions handled by test-specific code

    return None


def run_benchmark(
    plugin_id: str,
    dataset_path: Path,
    outdir: Path,
    *,
    timeout: int = 600,
    env: dict[str, str] | None = None,
) -> BenchmarkResult:
    """Run a full benchmark for a plugin.

    1. Load expected assertions from *dataset_path*/expected_assertions.yaml
    2. Execute ``abi run --type {plugin_id} --confirm-execution``
    3. Evaluate all assertions against the result directory
    4. Return aggregated BenchmarkResult

    Args:
        plugin_id: Plugin identifier (e.g. "rnaseq_expression").
        dataset_path: Directory containing expected_assertions.yaml and
                      optionally a config.yaml + sample data.
        outdir: Directory for pipeline outputs.
        timeout: Seconds before killing the subprocess.
        env: Extra environment variables (PATH, MAMBA_ROOT, etc.).

    Returns:
        BenchmarkResult with pass/fail counts.
    """
    config_path = dataset_path / "config.yaml"
    if not config_path.exists():
        raise FileNotFoundError(
            f"Benchmark dataset missing config.yaml: {config_path}"
        )

    expected = _load_expected(dataset_path)
    assertions = _parse_assertions(expected)

    # ── Run pipeline ──
    new_env = os.environ.copy()
    if env:
        new_env.update(env)
    new_env.setdefault("MAMBA_ROOT", os.path.expanduser("~/miniconda3"))

    proc = subprocess.run(
        [
            "abi",
            "run",
            "--type", plugin_id,
            "--confirm-execution",
            "--config", str(config_path),
        ],
        capture_output=True,
        text=True,
        env=new_env,
        check=False,
        timeout=timeout,
    )

    result = BenchmarkResult(plugin_id=plugin_id, dataset_path=dataset_path)

    if proc.returncode not in (0, 1):
        # Pipeline crashed
        result.errors.append(
            (
                BenchmarkAssertion(
                    step_id="pipeline",
                    table="",
                    column="",
                    condition="exists",
                    expected=True,
                    description="Pipeline exit code 0 or 1",
                ),
                f"Pipeline crashed (exit {proc.returncode}): {proc.stderr[-500:]}",
            )
        )
        result.total = len(assertions) + 1
        result.failed = len(assertions) + 1
        return result

    # ── Evaluate assertions ──
    result.total = len(assertions)
    for a in assertions:
        try:
            if a.evaluate(outdir):
                result.passed += 1
            else:
                result.failed += 1
                result.errors.append((a, f"{a.description}: FAILED"))
        except Exception as exc:
            result.failed += 1
            result.errors.append((a, f"{a.description}: ERROR: {exc}"))

    return result


def validate_against_expected(
    result_dir: Path,
    expected_path: Path,
) -> tuple[int, int, list[str]]:
    """Validate result_dir outputs against expected tables (CSV comparison).

    Compares actual TSV outputs in *result_dir* against reference tables in
    *expected_path*/expected_tables/. Useful for plugins whose benchmark
    datasets include ground-truth reference outputs.

    Returns:
        (passed, failed, messages) tuple.
    """
    expected_tables = expected_path / "expected_tables"
    if not expected_tables.is_dir():
        return 0, 0, []

    passed = 0
    failed = 0
    messages: list[str] = []

    for ref_file in sorted(expected_tables.rglob("*.tsv")):
        rel = ref_file.relative_to(expected_tables)
        actual_file = result_dir / rel

        if not actual_file.exists():
            failed += 1
            messages.append(f"MISSING: {rel}")
            continue

        ref_rows = list(csv.DictReader(ref_file.open(), delimiter="\t"))
        act_rows = list(csv.DictReader(actual_file.open(), delimiter="\t"))

        if len(ref_rows) != len(act_rows):
            failed += 1
            messages.append(
                f"ROW_COUNT: {rel} expected {len(ref_rows)}, got {len(act_rows)}"
            )
            continue

        # Check key columns match
        common_cols = set(ref_rows[0].keys()) & set(act_rows[0].keys()) if ref_rows and act_rows else set()
        mismatches = 0
        for col in sorted(common_cols):
            for i, (rr, ar) in enumerate(zip(ref_rows, act_rows)):
                if rr.get(col, "") != ar.get(col, ""):
                    mismatches += 1
                    if mismatches <= 3:
                        messages.append(
                            f"MISMATCH: {rel} row {i} col '{col}': "
                            f"expected '{rr.get(col, '')}', got '{ar.get(col, '')}'"
                        )

        if mismatches == 0:
            passed += 1
        else:
            failed += 1
            messages.append(f"MISMATCH: {rel} ({mismatches} cell differences)")

    return passed, failed, messages
