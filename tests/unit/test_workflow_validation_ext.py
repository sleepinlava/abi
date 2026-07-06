"""Extended unit tests for abi.workflow.validation — error/edge paths."""

from __future__ import annotations

from pathlib import Path

from abi.workflow.validation import WorkflowValidator


# ── check_tables(): Exception catch when file read fails ────────────────


def test_check_tables_exception_catch_on_read_failure(tmp_path: Path) -> None:
    """check_tables catches Exception when file read fails (e.g. directory given as path)."""
    tables = tmp_path / "tables"
    tables.mkdir()
    # Create a subdirectory with the name of the table, so read_text fails
    (tables / "qc_summary.tsv").mkdir()

    v = WorkflowValidator(tmp_path)
    v.check_tables({"qc_summary": ["sample_id", "raw_reads"]})

    # The exception should be caught and recorded as an error message
    assert any("qc_summary.tsv:" in e for e in v.errors)
