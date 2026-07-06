"""Extended unit tests for abi.workflow.figure_specs — load & validation."""

from __future__ import annotations

import pytest

from abi.figures.base import FigureSpec
from abi.workflow.figure_specs import load_figure_specs, validate_figure_specs

# Reusable schema for tests
TABLE_SCHEMAS = {
    "qc_read_counts": ["sample_id", "raw_reads", "clean_reads"],
    "genome_assembly_stats": ["sample_id", "total_length", "n50", "gc_content"],
    "gene_counts": ["gene_id", "count", "log2fc", "pvalue"],
}


# ── load_figure_specs() with pre-parsed list (not YAML path) ───────────


def test_load_figure_specs_with_pre_parsed_list_returns_specs() -> None:
    """load_figure_specs() accepts a list of dicts and returns FigureSpec objects."""
    items = [
        {
            "id": "qc_bar",
            "type": "bar",
            "source_table": "qc_read_counts",
            "x": "sample_id",
            "y": "clean_reads",
        }
    ]
    specs = load_figure_specs(items, table_schemas=TABLE_SCHEMAS)
    assert len(specs) == 1
    assert isinstance(specs[0], FigureSpec)
    assert specs[0].id == "qc_bar"


# ── load_figure_specs() with invalid figure spec → validation error ─────


def test_load_figure_specs_invalid_spec_raises_value_error() -> None:
    """load_figure_specs() raises ValueError when a spec references unknown table."""
    items = [
        {
            "id": "bad_fig",
            "type": "bar",
            "source_table": "nonexistent_table",
            "x": "col1",
            "y": "col2",
        }
    ]
    with pytest.raises(ValueError, match="Invalid figure specs"):
        load_figure_specs(items, table_schemas=TABLE_SCHEMAS)


# ── load_figure_specs(): multiple invalid specs → aggregated ValueError ─


def test_load_figure_specs_multiple_invalid_specs_aggregates_errors() -> None:
    """load_figure_specs() collects all errors before raising ValueError."""
    items = [
        {
            "id": "bad_1",
            "type": "bar",
            "source_table": "nonexistent_1",
            "x": "col1",
            "y": "col2",
        },
        {
            "id": "bad_2",
            "type": "scatter",
            "source_table": "nonexistent_2",
            "x": "col1",
            "y": "col2",
        },
    ]
    with pytest.raises(ValueError) as exc_info:
        load_figure_specs(items, table_schemas=TABLE_SCHEMAS)
    # The error message should mention 2 errors
    assert "2 error" in str(exc_info.value)
    assert "bad_1" in str(exc_info.value)
    assert "bad_2" in str(exc_info.value)


# ── validate_figure_specs(): valid specs → empty errors list ────────────


def test_validate_figure_specs_valid_specs_returns_empty_errors() -> None:
    """validate_figure_specs() returns [] when all specs are valid."""
    spec = FigureSpec(
        id="qc_bar",
        type="bar",
        source_table="qc_read_counts",
        x="sample_id",
        y="clean_reads",
    )
    errors = validate_figure_specs([spec], table_schemas=TABLE_SCHEMAS)
    assert errors == []


# ── validate_figure_specs(): invalid specs → errors collected ───────────


def test_validate_figure_specs_invalid_specs_returns_errors() -> None:
    """validate_figure_specs() collects error messages for invalid specs."""
    spec = FigureSpec(
        id="bad_fig",
        type="bar",
        source_table="unknown_table",
        x="col1",
        y="col2",
    )
    errors = validate_figure_specs([spec], table_schemas=TABLE_SCHEMAS)
    assert len(errors) == 1
    assert "unknown_table" in errors[0]
    assert "bad_fig" in errors[0]


# ── validate_figure_specs(): mixed valid/invalid → partial errors ───────


def test_validate_figure_specs_mixed_valid_invalid_returns_partial_errors() -> None:
    """validate_figure_specs() returns errors only for invalid specs."""
    valid_spec = FigureSpec(
        id="qc_bar",
        type="bar",
        source_table="qc_read_counts",
        x="sample_id",
        y="clean_reads",
    )
    invalid_spec = FigureSpec(
        id="bad_fig",
        type="scatter",
        source_table="unknown_table",
        x="col1",
        y="col2",
    )
    errors = validate_figure_specs([valid_spec, invalid_spec], table_schemas=TABLE_SCHEMAS)
    assert len(errors) == 1
    assert "bad_fig" in errors[0]
