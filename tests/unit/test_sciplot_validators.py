"""Tests for abi.sciplot.validators — DataValidationError, DataValidationReport,
load_data_table, and validate_data.
"""

from __future__ import annotations

import pytest

from abi.sciplot.schema.figure_spec import FigureSpec
from abi.sciplot.validators import (
    DataValidationError,
    DataValidationReport,
    load_data_table,
    validate_data,
)

# ── FigureSpec factory helpers ──────────────────────────────────────────


def _make_spec(
    tmp_path,
    *,
    table_filename: str = "data.tsv",
    table_content: str = "",
    figure_type: str = "barplot",
    x: str = "group",
    y: str = "value",
    required_columns: list[str] | None = None,
) -> FigureSpec:
    """Create a minimal FigureSpec pointing at a TSV table in tmp_path."""
    table_path = tmp_path / table_filename
    if table_content:
        table_path.write_text(table_content)

    return FigureSpec(
        figure_id="test_fig",
        figure_type=figure_type,
        data={
            "table": str(table_path),
            "format": "tsv",
            "required_columns": required_columns or [],
        },
        mapping={"x": x, "y": y},
        export={
            "output_dir": str(tmp_path / "figures"),
            "basename": "test_fig",
        },
    )


# ── DataValidationError ─────────────────────────────────────────────────


def test_data_validation_error_construction():
    """DataValidationError stores rule, message, and details."""
    err = DataValidationError("DATA001", "file not found", {"table": "/tmp/x.tsv"})
    assert err.rule == "DATA001"
    assert err.message == "file not found"
    assert err.details == {"table": "/tmp/x.tsv"}

    # Default details is empty dict
    err2 = DataValidationError("X", "msg")
    assert err2.details == {}


# ── DataValidationReport ────────────────────────────────────────────────


def test_report_empty_state():
    """Fresh report has no errors/warnings and is valid."""
    report = DataValidationReport()
    assert report.is_valid is True
    assert report.errors == []
    assert report.warnings == []
    assert report.to_dict() == {"status": "ok", "errors": [], "warnings": []}


def test_report_to_dict_with_errors():
    """to_dict includes errors and status=error when errors exist."""
    report = DataValidationReport()
    report.errors.append(DataValidationError("DATA001", "missing file", {"table": "t.tsv"}))
    report.warnings.append(DataValidationError("DATA004", "some NaN", {"col": "y"}))

    assert report.is_valid is False
    d = report.to_dict()
    assert d["status"] == "error"
    assert len(d["errors"]) == 1
    assert d["errors"][0]["rule"] == "DATA001"
    assert d["errors"][0]["message"] == "missing file"
    assert d["errors"][0]["details"] == {"table": "t.tsv"}
    assert len(d["warnings"]) == 1
    assert d["warnings"][0]["rule"] == "DATA004"


def test_report_to_dict_with_warnings_only():
    """Warnings only → status=ok."""
    report = DataValidationReport()
    report.warnings.append(DataValidationError("DATA004", "warning", {"col": "x"}))
    assert report.is_valid is True
    d = report.to_dict()
    assert d["status"] == "ok"
    assert len(d["warnings"]) == 1
    assert d["warnings"][0]["rule"] == "DATA004"


# ── load_data_table ─────────────────────────────────────────────────────


def test_load_data_table_missing_file_raises_data001(tmp_path):
    spec = _make_spec(tmp_path, table_filename="nonexistent.tsv")
    with pytest.raises(DataValidationError) as exc:
        load_data_table(spec)
    assert exc.value.rule == "DATA001"
    assert "does not exist" in exc.value.message


def test_load_data_table_happy_path_tsv(tmp_path):
    content = "x\ty\n1\t10\n2\t20\n"
    spec = _make_spec(tmp_path, table_content=content)
    df = load_data_table(spec)
    assert list(df.columns) == ["x", "y"]
    assert len(df) == 2
    assert df["y"].iloc[0] == 10


def test_load_data_table_csv(tmp_path):
    content = "a,b\n1,2\n"
    table_path = tmp_path / "data.csv"
    table_path.write_text(content)
    spec = FigureSpec(
        figure_id="csv_test",
        figure_type="barplot",
        data={"table": str(table_path), "format": "csv"},
        mapping={"x": "a", "y": "b"},
        export={"output_dir": str(tmp_path / "figures"), "basename": "csv_test"},
    )
    df = load_data_table(spec)
    assert list(df.columns) == ["a", "b"]
    assert df["b"].iloc[0] == 2


# ── validate_data ───────────────────────────────────────────────────────


def test_validate_data_data001_missing_table(tmp_path):
    """Missing file → DATA001 error with early return."""
    spec = _make_spec(tmp_path, table_filename="nope.tsv")
    report = validate_data(spec)
    assert not report.is_valid
    assert len(report.errors) == 1
    assert report.errors[0].rule == "DATA001"
    assert len(report.warnings) == 0


def test_validate_data_data002_missing_column(tmp_path):
    """Column referenced in mapping but not in table → DATA002."""
    content = "x\ty\n1\t10\n"
    spec = _make_spec(tmp_path, table_content=content, x="group", y="value")
    report = validate_data(spec)
    errors = [e.rule for e in report.errors]
    assert "DATA002" in errors
    # Check that the error mentions the missing column
    data002 = next(e for e in report.errors if e.rule == "DATA002")
    assert "group" in data002.message or "group" in str(data002.details)


def test_validate_data_data003_no_axis_mapping_non_heatmap(tmp_path):
    """Non-heatmap type with no x and no y → ValidationError at spec creation."""
    from pydantic import ValidationError

    content = "col_a\tcol_b\n1\t2\n"
    table_path = tmp_path / "data.tsv"
    table_path.write_text(content)
    with pytest.raises(ValidationError, match="requires at least one of mapping.x or mapping.y"):
        FigureSpec(
            figure_id="test_fig",
            figure_type="barplot",
            data={
                "table": str(table_path),
                "format": "tsv",
                "required_columns": [],
            },
            mapping={"x": None, "y": None},
            export={
                "output_dir": str(tmp_path / "figures"),
                "basename": "test_fig",
            },
        )


def test_validate_data_data003_skipped_for_heatmap(tmp_path):
    """Heatmap type skips DATA003 even if x and y are empty."""
    content = "gene_id\tsample1\tsample2\ng1\t1\t2\n"
    spec = _make_spec(
        tmp_path,
        table_content=content,
        figure_type="heatmap",
        x="",
        y="",
    )
    report = validate_data(spec)
    rules = {e.rule for e in report.errors}
    assert "DATA003" not in rules


def test_validate_data_data004_over_50pct_nan(tmp_path):
    """>50% NaN in y column → DATA004 error."""
    content = "x\ty\na\tx\nb\tx\nc\t3\n"
    spec = _make_spec(tmp_path, table_content=content, x="x", y="y")
    report = validate_data(spec)
    errors = [e.rule for e in report.errors]
    assert "DATA004" in errors
    data004 = next(e for e in report.errors if e.rule == "DATA004")
    assert ">50%" in data004.message or "50%" in data004.message


def test_validate_data_data004_20_to_50_pct_nan_warning(tmp_path):
    """20-50% NaN in y column → DATA004 warning (not error)."""
    content = "x\ty\na\tx\nb\tx\nc\t3\nd\t4\ne\t5\n"
    # 2/5 = 40% NaN
    spec = _make_spec(tmp_path, table_content=content, x="x", y="y")
    report = validate_data(spec)
    data004_errors = [e for e in report.errors if e.rule == "DATA004"]
    data004_warnings = [w for w in report.warnings if w.rule == "DATA004"]
    assert len(data004_errors) == 0
    assert len(data004_warnings) >= 1
    assert "non-numeric" in data004_warnings[0].message


def test_validate_data_happy_path(tmp_path):
    """All checks pass for a well-formed dataset."""
    content = "group\tvalue\nA\t10\nB\t20\nC\t15\n"
    spec = _make_spec(
        tmp_path,
        table_content=content,
        figure_type="barplot",
        x="group",
        y="value",
        required_columns=["group"],
    )
    report = validate_data(spec)
    assert report.is_valid
    assert len(report.errors) == 0
    assert len(report.warnings) == 0
    assert report.to_dict()["status"] == "ok"
