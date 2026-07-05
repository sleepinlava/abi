"""Unit tests for benchmark data structures in src/abi/testing/benchmark.py."""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from abi.testing.benchmark import (
    BenchmarkAssertion,
    BenchmarkResult,
    _kv_to_assertion,
    _parse_assertions,
    validate_against_expected,
)


# ── Helpers ──────────────────────────────────────────────────────────────────


def _write_tsv(path: Path, rows: list[dict]) -> None:
    """Write a list of dicts as a tab-separated file."""
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()), delimiter="\t")
        w.writeheader()
        w.writerows(rows)


# ═══════════════════════════════════════════════════════════════════════════════
# BenchmarkAssertion
# ═══════════════════════════════════════════════════════════════════════════════


class TestBenchmarkAssertion:
    """Tests for BenchmarkAssertion.evaluate()."""

    def test_exists_file(self, tmp_path: Path) -> None:
        file = tmp_path / "results.tsv"
        file.write_text("data\n", encoding="utf-8")

        assertion = BenchmarkAssertion(
            step_id="s1", table="results.tsv", column="", condition="exists", expected=True
        )
        assert assertion.evaluate(tmp_path) is True

    def test_exists_file_missing(self, tmp_path: Path) -> None:
        assertion = BenchmarkAssertion(
            step_id="s1",
            table="missing.tsv",
            column="",
            condition="exists",
            expected=True,
        )
        assert assertion.evaluate(tmp_path) is False

    def test_exists_column(self, tmp_path: Path) -> None:
        _write_tsv(tmp_path / "data.tsv", [{"a": "1", "b": "2"}])

        assertion = BenchmarkAssertion(
            step_id="s1",
            table="data.tsv",
            column="a",
            condition="exists",
            expected=True,
        )
        assert assertion.evaluate(tmp_path) is True

    def test_exists_column_missing(self, tmp_path: Path) -> None:
        _write_tsv(tmp_path / "data.tsv", [{"a": "1", "b": "2"}])

        assertion = BenchmarkAssertion(
            step_id="s1",
            table="data.tsv",
            column="z",
            condition="exists",
            expected=True,
        )
        assert assertion.evaluate(tmp_path) is False

    def test_condition_gte(self, tmp_path: Path) -> None:
        _write_tsv(
            tmp_path / "data.tsv",
            [{"value": "10"}, {"value": "20"}, {"value": "30"}],
        )

        assertion = BenchmarkAssertion(
            step_id="s1",
            table="data.tsv",
            column="value",
            condition=">=",
            expected=10,
        )
        assert assertion.evaluate(tmp_path) is True

    def test_condition_gte_fails(self, tmp_path: Path) -> None:
        _write_tsv(
            tmp_path / "data.tsv",
            [{"value": "5"}, {"value": "10"}, {"value": "15"}],
        )

        assertion = BenchmarkAssertion(
            step_id="s1",
            table="data.tsv",
            column="value",
            condition=">=",
            expected=20,
        )
        assert assertion.evaluate(tmp_path) is False

    def test_condition_gt(self, tmp_path: Path) -> None:
        _write_tsv(
            tmp_path / "data.tsv",
            [{"value": "10"}, {"value": "20"}],
        )

        assertion = BenchmarkAssertion(
            step_id="s1",
            table="data.tsv",
            column="value",
            condition=">",
            expected=5,
        )
        assert assertion.evaluate(tmp_path) is True

    def test_condition_lte(self, tmp_path: Path) -> None:
        _write_tsv(
            tmp_path / "data.tsv",
            [{"value": "1"}, {"value": "2"}, {"value": "3"}],
        )

        assertion = BenchmarkAssertion(
            step_id="s1",
            table="data.tsv",
            column="value",
            condition="<=",
            expected=3,
        )
        assert assertion.evaluate(tmp_path) is True

    def test_condition_lte_fails(self, tmp_path: Path) -> None:
        _write_tsv(
            tmp_path / "data.tsv",
            [{"value": "5"}, {"value": "6"}],
        )

        assertion = BenchmarkAssertion(
            step_id="s1",
            table="data.tsv",
            column="value",
            condition="<=",
            expected=4,
        )
        assert assertion.evaluate(tmp_path) is False

    def test_condition_between(self, tmp_path: Path) -> None:
        _write_tsv(
            tmp_path / "data.tsv",
            [{"value": "10"}, {"value": "15"}, {"value": "20"}],
        )

        assertion = BenchmarkAssertion(
            step_id="s1",
            table="data.tsv",
            column="value",
            condition="between",
            expected=[5, 25],
        )
        assert assertion.evaluate(tmp_path) is True

    def test_condition_between_fails(self, tmp_path: Path) -> None:
        _write_tsv(
            tmp_path / "data.tsv",
            [{"value": "10"}, {"value": "50"}],
        )

        assertion = BenchmarkAssertion(
            step_id="s1",
            table="data.tsv",
            column="value",
            condition="between",
            expected=[5, 25],
        )
        assert assertion.evaluate(tmp_path) is False

    def test_condition_contains(self, tmp_path: Path) -> None:
        (tmp_path / "report.txt").write_text("Hello World\n", encoding="utf-8")

        assertion = BenchmarkAssertion(
            step_id="s1",
            table="report.txt",
            column="",
            condition="contains",
            expected="world",
        )
        assert assertion.evaluate(tmp_path) is True


# ═══════════════════════════════════════════════════════════════════════════════
# BenchmarkResult
# ═══════════════════════════════════════════════════════════════════════════════


class TestBenchmarkResult:
    """Tests for BenchmarkResult.pass_rate and .summary()."""

    def test_pass_rate_normal(self) -> None:
        result = BenchmarkResult(
            plugin_id="p", dataset_path=Path("/tmp"), total=10, passed=8
        )
        assert result.pass_rate == 0.8

    def test_pass_rate_zero_total(self) -> None:
        result = BenchmarkResult(
            plugin_id="p", dataset_path=Path("/tmp"), total=0, passed=0
        )
        assert result.pass_rate == 0.0

    def test_pass_rate_all_pass(self) -> None:
        result = BenchmarkResult(
            plugin_id="p", dataset_path=Path("/tmp"), total=5, passed=5
        )
        assert result.pass_rate == 1.0

    def test_summary_format(self) -> None:
        result = BenchmarkResult(
            plugin_id="test",
            dataset_path=Path("/tmp"),
            total=10,
            passed=8,
            failed=2,
        )
        summary = result.summary()
        assert "test: 8/10 passed (80%), 2 failed" in summary


# ═══════════════════════════════════════════════════════════════════════════════
# _kv_to_assertion
# ═══════════════════════════════════════════════════════════════════════════════


class TestKvToAssertion:
    """Tests for _kv_to_assertion() YAML key-value conversion."""

    def test_bool_to_exists(self) -> None:
        a = _kv_to_assertion("step1", "results.tsv", True)
        assert a is not None
        assert a.condition == "exists"
        assert a.table == "results.tsv"
        assert a.column == ""
        assert a.expected is True

    def test_int_to_gte(self) -> None:
        a = _kv_to_assertion("step1", "row_count", 100)
        assert a is not None
        assert a.condition == ">="
        assert a.column == "row_count"
        assert a.expected == 100

    def test_float_to_gte(self) -> None:
        a = _kv_to_assertion("step1", "pct", 0.95)
        assert a is not None
        assert a.condition == ">="
        assert a.expected == 0.95

    def test_str_to_contains(self) -> None:
        a = _kv_to_assertion("step1", "status", "complete")
        assert a is not None
        assert a.condition == "contains"
        assert a.expected == "complete"

    def test_list_two_numbers_to_between(self) -> None:
        a = _kv_to_assertion("step1", "range", [0.5, 1.5])
        assert a is not None
        assert a.condition == "between"
        assert a.column == "range"
        assert a.expected == [0.5, 1.5]

    def test_list_non_numbers_returns_none(self) -> None:
        a = _kv_to_assertion("step1", "labels", ["a", "b", "c"])
        assert a is None


# ═══════════════════════════════════════════════════════════════════════════════
# _parse_assertions
# ═══════════════════════════════════════════════════════════════════════════════


class TestParseAssertions:
    """Tests for _parse_assertions()."""

    def test_parses_yaml_dict(self) -> None:
        expected = {
            "plugin": {
                "step1": {
                    "output.tsv": True,
                    "count": 100,
                },
            },
        }
        assertions = _parse_assertions(expected)
        assert len(assertions) == 2

        # First assertion: exists check for output.tsv
        exists_a = next(a for a in assertions if a.condition == "exists")
        assert exists_a.table == "output.tsv"
        assert exists_a.step_id == "step1"

        # Second assertion: gte check for count
        gte_a = next(a for a in assertions if a.condition == ">=")
        assert gte_a.column == "count"
        assert gte_a.expected == 100


# ═══════════════════════════════════════════════════════════════════════════════
# validate_against_expected
# ═══════════════════════════════════════════════════════════════════════════════


class TestValidateAgainstExpected:
    """Tests for validate_against_expected()."""

    def test_no_expected_tables_dir(self, tmp_path: Path) -> None:
        expected_path = tmp_path / "expected"
        expected_path.mkdir()
        # No expected_tables/ subdirectory

        passed, failed, messages = validate_against_expected(
            result_dir=tmp_path / "results",
            expected_path=expected_path,
        )
        assert passed == 0
        assert failed == 0
        assert messages == []

    def test_missing_actual_file(self, tmp_path: Path) -> None:
        expected_path = tmp_path / "expected"
        expected_tables = expected_path / "expected_tables"
        expected_tables.mkdir(parents=True)

        # Create a reference TSV
        _write_tsv(expected_tables / "data.tsv", [{"a": "1", "b": "2"}])

        result_dir = tmp_path / "results"
        result_dir.mkdir()
        # No data.tsv in result_dir

        passed, failed, messages = validate_against_expected(
            result_dir=result_dir,
            expected_path=expected_path,
        )
        assert passed == 0
        assert failed == 1
        assert any("MISSING" in m for m in messages)

    def test_row_count_mismatch(self, tmp_path: Path) -> None:
        expected_path = tmp_path / "expected"
        expected_tables = expected_path / "expected_tables"
        expected_tables.mkdir(parents=True)

        # Expected: 3 rows
        _write_tsv(
            expected_tables / "data.tsv",
            [{"a": "1"}, {"a": "2"}, {"a": "3"}],
        )

        result_dir = tmp_path / "results"
        result_dir.mkdir()
        # Actual: 2 rows
        _write_tsv(
            result_dir / "data.tsv",
            [{"a": "1"}, {"a": "2"}],
        )

        passed, failed, messages = validate_against_expected(
            result_dir=result_dir,
            expected_path=expected_path,
        )
        assert passed == 0
        assert failed == 1
        assert any("ROW_COUNT" in m for m in messages)
