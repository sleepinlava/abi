"""Unit tests for abi.workflow.validation — WorkflowValidator + check_required_artifacts."""

from __future__ import annotations

import json
from pathlib import Path

from abi.workflow.validation import WorkflowValidator, check_required_artifacts

# ── WorkflowValidator: construction ──────────────────────────────────────


def test_validator_initial_state(tmp_path: Path) -> None:
    """Validator starts with empty errors/warnings and is_valid=True."""
    v = WorkflowValidator(tmp_path)
    assert v.errors == []
    assert v.warnings == []
    assert v.is_valid is True


def test_validator_errors_is_copy(tmp_path: Path) -> None:
    """Validator.errors returns a copy, not the internal list."""
    v = WorkflowValidator(tmp_path)
    v.errors.append("mutation test")
    assert v.errors == []  # internal list unaffected


def test_validator_warnings_is_copy(tmp_path: Path) -> None:
    """Validator.warnings returns a copy, not the internal list."""
    v = WorkflowValidator(tmp_path)
    v.warnings.append("mutation test")
    assert v.warnings == []


# ── check_provenance ─────────────────────────────────────────────────────


def test_check_provenance_missing_dir(tmp_path: Path) -> None:
    """Error when provenance/ directory does not exist."""
    v = WorkflowValidator(tmp_path)
    v.check_provenance()
    assert any("provenance/ directory missing" in e for e in v.errors)
    assert not v.is_valid


def test_check_provenance_missing_files(tmp_path: Path) -> None:
    """Errors for each missing required provenance file."""
    prov = tmp_path / "provenance"
    prov.mkdir()
    v = WorkflowValidator(tmp_path)
    v.check_provenance()
    # All 6 required files are missing
    assert len(v.errors) == 6
    expected = [
        "commands.tsv",
        "resolved_inputs.tsv",
        "tool_versions.tsv",
        "run_summary.json",
        "checksums.json",
        "progress.jsonl",
    ]
    for fname in expected:
        assert any(fname in e for e in v.errors)


def test_check_provenance_all_present(tmp_path: Path) -> None:
    """No errors when all provenance files exist."""
    prov = tmp_path / "provenance"
    prov.mkdir()
    for fname in (
        "commands.tsv",
        "resolved_inputs.tsv",
        "tool_versions.tsv",
        "run_summary.json",
        "checksums.json",
        "progress.jsonl",
    ):
        (prov / fname).write_text("")
    v = WorkflowValidator(tmp_path)
    v.check_provenance()
    assert v.errors == []
    assert v.is_valid


# ── check_tables ─────────────────────────────────────────────────────────


def test_check_tables_missing_dir(tmp_path: Path) -> None:
    """Error when tables/ directory is missing."""
    v = WorkflowValidator(tmp_path)
    v.check_tables({"asv_table": ["asv_id", "sample_id"]})
    assert any("tables/ directory missing" in e for e in v.errors)


def test_check_tables_missing_file(tmp_path: Path) -> None:
    """Error when a required table TSV is missing."""
    tables = tmp_path / "tables"
    tables.mkdir()
    v = WorkflowValidator(tmp_path)
    v.check_tables({"asv_table": ["asv_id", "sample_id"]})
    assert any("asv_table.tsv missing" in e for e in v.errors)


def test_check_tables_missing_columns(tmp_path: Path) -> None:
    """Error when table TSV exists but is missing expected columns."""
    tables = tmp_path / "tables"
    tables.mkdir()
    (tables / "asv_table.tsv").write_text("asv_id\textra_col\n")
    v = WorkflowValidator(tmp_path)
    v.check_tables({"asv_table": ["asv_id", "sample_id"]})
    assert any("missing columns" in e for e in v.errors)
    assert any("sample_id" in e for e in v.errors)


def test_check_tables_all_present(tmp_path: Path) -> None:
    """No errors when all tables exist with correct columns."""
    tables = tmp_path / "tables"
    tables.mkdir()
    (tables / "asv_table.tsv").write_text("asv_id\tsample_id\tcount\n")
    (tables / "taxonomy.tsv").write_text("asv_id\tkingdom\tphylum\n")
    v = WorkflowValidator(tmp_path)
    v.check_tables(
        {
            "asv_table": ["asv_id", "sample_id", "count"],
            "taxonomy": ["asv_id", "kingdom", "phylum"],
        }
    )
    assert v.errors == []


def test_check_tables_empty(tmp_path: Path) -> None:
    """No errors when table_schemas is empty."""
    tables = tmp_path / "tables"
    tables.mkdir()
    v = WorkflowValidator(tmp_path)
    v.check_tables({})
    assert v.errors == []


# ── check_report ─────────────────────────────────────────────────────────


def test_check_report_missing_dir(tmp_path: Path) -> None:
    """Warning (not error) when report/ directory is missing."""
    v = WorkflowValidator(tmp_path)
    v.check_report()
    assert any("report/ directory missing" in w for w in v.warnings)
    assert len(v.errors) == 0  # report is optional


def test_check_report_missing_files(tmp_path: Path) -> None:
    """Warnings for missing report.md and report.html."""
    report = tmp_path / "report"
    report.mkdir()
    v = WorkflowValidator(tmp_path)
    v.check_report()
    assert any("report.md missing" in w for w in v.warnings)
    assert any("report.html missing" in w for w in v.warnings)


def test_check_report_all_present(tmp_path: Path) -> None:
    """No warnings when report files exist."""
    report = tmp_path / "report"
    report.mkdir()
    (report / "report.md").write_text("# Report")
    (report / "report.html").write_text("<h1>Report</h1>")
    v = WorkflowValidator(tmp_path)
    v.check_report()
    assert v.warnings == []


# ── check_resource_manifest ──────────────────────────────────────────────


def test_check_resource_manifest_missing(tmp_path: Path) -> None:
    """Warning when resource_manifest.json is missing."""
    v = WorkflowValidator(tmp_path)
    v.check_resource_manifest()
    assert any("resource_manifest.json missing" in w for w in v.warnings)
    assert len(v.errors) == 0


def test_check_resource_manifest_invalid_json(tmp_path: Path) -> None:
    """Error when resource_manifest.json contains invalid JSON."""
    prov = tmp_path / "provenance"
    prov.mkdir()
    (prov / "resource_manifest.json").write_text("not json{")
    v = WorkflowValidator(tmp_path)
    v.check_resource_manifest()
    assert any("resource_manifest.json:" in e for e in v.errors)


def test_check_resource_manifest_not_a_dict(tmp_path: Path) -> None:
    """Error when resource_manifest.json is not a JSON object."""
    prov = tmp_path / "provenance"
    prov.mkdir()
    (prov / "resource_manifest.json").write_text("[1, 2, 3]")
    v = WorkflowValidator(tmp_path)
    v.check_resource_manifest()
    assert any("not a JSON object" in e for e in v.errors)


def test_check_resource_manifest_resources_not_a_list(tmp_path: Path) -> None:
    """Error when 'resources' key is not a list."""
    prov = tmp_path / "provenance"
    prov.mkdir()
    (prov / "resource_manifest.json").write_text('{"resources": "not_a_list"}')
    v = WorkflowValidator(tmp_path)
    v.check_resource_manifest()
    assert any("not a list" in e for e in v.errors)


def test_check_resource_manifest_resource_missing_id(tmp_path: Path) -> None:
    """Error when a resource entry is missing 'id'."""
    prov = tmp_path / "provenance"
    prov.mkdir()
    (prov / "resource_manifest.json").write_text(
        json.dumps({"resources": [{"name": "db", "version": "1.0"}]})
    )
    v = WorkflowValidator(tmp_path)
    v.check_resource_manifest()
    assert any("missing 'id'" in e for e in v.errors)


def test_check_resource_manifest_resource_not_a_dict(tmp_path: Path) -> None:
    """Error when a resource entry is not an object."""
    prov = tmp_path / "provenance"
    prov.mkdir()
    (prov / "resource_manifest.json").write_text(
        json.dumps({"resources": ["not_an_object"]})
    )
    v = WorkflowValidator(tmp_path)
    v.check_resource_manifest()
    assert any("not an object" in e for e in v.errors)


def test_check_resource_manifest_valid(tmp_path: Path) -> None:
    """No errors for a valid resource manifest."""
    prov = tmp_path / "provenance"
    prov.mkdir()
    (prov / "resource_manifest.json").write_text(
        json.dumps(
            {
                "resources": [
                    {"id": "genome_index", "name": "E. coli STAR index", "version": "1.0"},
                    {"id": "annotation_gtf", "name": "E. coli GTF", "version": "1.0"},
                ]
            }
        )
    )
    v = WorkflowValidator(tmp_path)
    v.check_resource_manifest()
    assert v.errors == []


# ── check_figures ────────────────────────────────────────────────────────


def test_check_figures_missing_dir(tmp_path: Path) -> None:
    """Warning when figures/ directory is missing."""
    v = WorkflowValidator(tmp_path)
    v.check_figures(["fig1", "fig2"])
    assert any("figures/ directory missing" in w for w in v.warnings)
    assert len(v.errors) == 0


def test_check_figures_missing_file(tmp_path: Path) -> None:
    """Error when an expected figure PNG is missing."""
    figures = tmp_path / "figures"
    figures.mkdir()
    (figures / "fig1.png").write_text("")
    v = WorkflowValidator(tmp_path)
    v.check_figures(["fig1", "fig2"])
    assert any("fig2.png missing" in e for e in v.errors)


def test_check_figures_all_present(tmp_path: Path) -> None:
    """No errors when all expected figures exist."""
    figures = tmp_path / "figures"
    figures.mkdir()
    (figures / "fig1.png").write_text("")
    (figures / "fig2.png").write_text("")
    v = WorkflowValidator(tmp_path)
    v.check_figures(["fig1", "fig2"])
    assert v.errors == []


def test_check_figures_empty_ids(tmp_path: Path) -> None:
    """No errors when expected_figures is empty."""
    figures = tmp_path / "figures"
    figures.mkdir()
    v = WorkflowValidator(tmp_path)
    v.check_figures([])
    assert v.errors == []
    assert v.warnings == []


# ── check_required_artifacts (one-shot helper) ───────────────────────────


def test_check_required_artifacts_all_missing(tmp_path: Path) -> None:
    """Returns errors for missing provenance, optional warnings for report."""
    errors, warnings = check_required_artifacts(tmp_path)
    assert len(errors) > 0
    assert any("provenance" in e for e in errors)
    assert any("report" in w for w in warnings)


def test_check_required_artifacts_with_tables(tmp_path: Path) -> None:
    """Passes table_schemas through to check_tables."""
    tables = tmp_path / "tables"
    tables.mkdir()
    (tables / "asv_table.tsv").write_text("asv_id\tsample_id\n")
    schemas = {"asv_table": ["asv_id", "sample_id"]}
    errors, _ = check_required_artifacts(tmp_path, table_schemas=schemas)
    # Tables pass, but provenance is still missing
    assert not any("table" in e.lower() for e in errors)


def test_check_required_artifacts_with_figures(tmp_path: Path) -> None:
    """Passes expected_figures through to check_figures."""
    figures = tmp_path / "figures"
    figures.mkdir()
    errors, _ = check_required_artifacts(tmp_path, expected_figures=["fig1"])
    assert any("fig1.png missing" in e for e in errors)
