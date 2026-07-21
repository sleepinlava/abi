"""Unit tests for abi.results — validate_abi_result_dir edge cases."""

from __future__ import annotations

import json
from pathlib import Path
from unittest import mock

from abi.results import validate_abi_result_dir

# ── Helpers ────────────────────────────────────────────────────────────────


def _make_result_dir(tmp_path: Path, analysis_type: str = "rnaseq_expression") -> Path:
    """Create a minimal valid result directory structure."""
    result_dir = tmp_path / "result"
    prov = result_dir / "provenance"
    prov.mkdir(parents=True)
    (result_dir / "report").mkdir()
    (result_dir / "tables").mkdir()

    (result_dir / "execution_plan.json").write_text(
        json.dumps({"analysis_type": analysis_type, "project_name": "test"}),
        encoding="utf-8",
    )
    (prov / "run_summary.json").write_text(
        json.dumps({"status": "success"}),
        encoding="utf-8",
    )
    (prov / "commands.tsv").write_text(
        "step_id\tsample_id\tstatus\ns1\tX\tstep_completed\n",
        encoding="utf-8",
    )
    (prov / "resolved_inputs.tsv").write_text("step_id\n", encoding="utf-8")
    (prov / "tool_versions.tsv").write_text("tool_id\tversion\n", encoding="utf-8")
    (prov / "resources.json").write_text("{}", encoding="utf-8")
    (prov / "progress.jsonl").write_text("", encoding="utf-8")
    (result_dir / "report" / "report.md").write_text("# report\n", encoding="utf-8")
    (result_dir / "report" / "report.html").write_text("<html></html>\n", encoding="utf-8")
    return result_dir


def _mock_plugin(table_schemas_result=None):
    """Return a mock plugin with table_schemas()."""
    plugin = mock.Mock()
    plugin.table_schemas.return_value = table_schemas_result or {}
    return plugin


# ── Zero-byte artifact ─────────────────────────────────────────────────────


def test_validate_zero_byte_artifact(tmp_path: Path) -> None:
    """L190: zero-byte artifact file → error."""
    result_dir = _make_result_dir(tmp_path)
    # Make a required artifact zero-byte
    zero = result_dir / "report" / "report.html"
    zero.write_text("")  # zero bytes

    with mock.patch("abi.plugins.get_plugin") as mock_gp:
        mock_gp.return_value = _mock_plugin()
        result = validate_abi_result_dir(result_dir)

    assert result["valid"] is False
    assert any("Empty artifact" in e for e in result["errors"])


# ── Failed steps in commands.tsv ───────────────────────────────────────────


def test_validate_commands_failed_steps(tmp_path: Path) -> None:
    """L204-205: commands.tsv with failed steps → error."""
    result_dir = _make_result_dir(tmp_path)
    (result_dir / "provenance" / "commands.tsv").write_text(
        "step_id\tsample_id\tstatus\ns1\tX\tfailed\ns2\tY\tfailed\n",
        encoding="utf-8",
    )

    with mock.patch("abi.plugins.get_plugin") as mock_gp:
        mock_gp.return_value = _mock_plugin()
        result = validate_abi_result_dir(result_dir)

    assert result["valid"] is False
    assert "commands.tsv contains 2 failed step(s)" in result["errors"]


# ── Missing standard table files ───────────────────────────────────────────


def test_validate_missing_standard_tables(tmp_path: Path) -> None:
    """L220-222: missing standard table files → error."""
    result_dir = _make_result_dir(tmp_path)

    with mock.patch("abi.plugins.get_plugin") as mock_gp:
        mock_gp.return_value = _mock_plugin({"samples": ["id", "platform"]})
        result = validate_abi_result_dir(result_dir)

    assert result["valid"] is False
    assert any("Missing standard table(s)" in e for e in result["errors"])


# ── Missing required columns ───────────────────────────────────────────────


def test_validate_table_missing_columns(tmp_path: Path) -> None:
    """L224-231: table missing required columns → error."""
    result_dir = _make_result_dir(tmp_path)
    # Create a table file but with missing expected columns
    (result_dir / "tables" / "samples.tsv").write_text(
        "id\tstuff\nS1\tx\n",
        encoding="utf-8",
    )

    with mock.patch("abi.plugins.get_plugin") as mock_gp:
        mock_gp.return_value = _mock_plugin({"samples": ["id", "platform"]})
        result = validate_abi_result_dir(result_dir)

    assert result["valid"] is False
    assert any("samples.tsv missing field(s)" in e for e in result["errors"])


# ── Empty table with allow_empty_tables=False ──────────────────────────────


def test_validate_empty_table_not_allowed(tmp_path: Path) -> None:
    """L233-238: empty table with allow_empty_tables=False → error."""
    result_dir = _make_result_dir(tmp_path)
    # Create a header-only table (0 data rows)
    (result_dir / "tables" / "samples.tsv").write_text(
        "id\tplatform\n",
        encoding="utf-8",
    )

    with mock.patch("abi.plugins.get_plugin") as mock_gp:
        mock_gp.return_value = _mock_plugin({"samples": ["id", "platform"]})
        result = validate_abi_result_dir(result_dir, allow_empty_tables=False)

    assert result["valid"] is False
    assert any("Empty standard table" in e for e in result["errors"])


def test_validate_uses_plugin_specific_nonempty_policy(tmp_path: Path) -> None:
    result_dir = _make_result_dir(tmp_path, analysis_type="metagenomic_plasmid")
    (result_dir / "tables" / "active.tsv").write_text("id\n", encoding="utf-8")
    (result_dir / "tables" / "optional.tsv").write_text("id\n", encoding="utf-8")
    plugin = _mock_plugin({"active": ["id"], "optional": ["id"]})
    plugin.validate_result_dir.return_value = {
        "errors": ["Empty active-module standard table(s): active"]
    }

    with mock.patch("abi.plugins.get_plugin", return_value=plugin):
        result = validate_abi_result_dir(result_dir, allow_empty_tables=False)

    assert "Empty active-module standard table(s): active" in result["errors"]
    assert all("optional" not in error for error in result["errors"])


# ── Missing (non-existent) result directory ────────────────────────────────


def test_validate_missing_result_dir(tmp_path: Path) -> None:
    """L172-183: result directory does not exist → status 'missing'."""
    result = validate_abi_result_dir(tmp_path / "nonexistent")
    assert result["valid"] is False
    assert result["status"] == "missing"
    assert any("does not exist" in e for e in result["errors"])


# ── Missing analysis_type ──────────────────────────────────────────────────


def test_validate_missing_analysis_type(tmp_path: Path) -> None:
    """L209-210: cannot determine analysis_type → error."""
    result_dir = _make_result_dir(tmp_path, analysis_type="")
    (result_dir / "execution_plan.json").write_text(
        json.dumps({"project_name": "test"}),
        encoding="utf-8",
    )

    with mock.patch("abi.plugins.get_plugin") as mock_gp:
        mock_gp.return_value = _mock_plugin()
        result = validate_abi_result_dir(result_dir)

    assert result["valid"] is False
    assert any("Cannot determine analysis_type" in e for e in result["errors"])
