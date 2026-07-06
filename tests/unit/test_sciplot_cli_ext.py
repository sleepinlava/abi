"""Tests for abi.sciplot.cli — Typer CLI commands via CliRunner.

Covers: validate, render, lint, list-plot-types, and error paths.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import yaml
from typer.testing import CliRunner

from abi.sciplot.cli import app

runner = CliRunner()


# ── Helpers ──────────────────────────────────────────────────────────────────


def _write_spec_files(
    tmp_path: Path,
    spec_filename: str = "figure.yaml",
    table_filename: str = "data.tsv",
    table_content: str = "group\tvalue\nA\t10\nB\t20\n",
) -> tuple[Path, Path]:
    """Write a YAML spec + TSV data file into tmp_path.  Returns (spec_path, table_path)."""
    table_path = tmp_path / table_filename
    table_path.write_text(table_content)

    spec_dict = {
        "figure_id": "test_fig",
        "figure_type": "barplot",
        "data": {"table": str(table_path), "format": "tsv"},
        "mapping": {"x": "group", "y": "value"},
        "export": {"output_dir": str(tmp_path / "figures"), "basename": "test_fig"},
    }
    spec_path = tmp_path / spec_filename
    spec_path.write_text(yaml.dump(spec_dict))
    return spec_path, table_path


def _write_yaml_file(path: Path, content: dict) -> Path:
    """Write a dict as YAML to *path* and return the path."""
    path.write_text(yaml.dump(content))
    return path


# ═══════════════════════════════════════════════════════════════════════════════
# validate
# ═══════════════════════════════════════════════════════════════════════════════


def test_validate_valid_spec(tmp_path: Path) -> None:
    """validate exits 0 for a spec whose data table exists and has correct columns."""
    spec_path, _table_path = _write_spec_files(tmp_path)
    result = runner.invoke(app, ["validate", "--spec", str(spec_path)])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["status"] == "ok"
    assert data["figure_id"] == "test_fig"


def test_validate_missing_data_table(tmp_path: Path) -> None:
    """validate exits 1 when the data table referenced in the spec does not exist."""
    spec_dict = {
        "figure_id": "bad_fig",
        "figure_type": "barplot",
        "data": {"table": str(tmp_path / "nope.tsv"), "format": "tsv"},
        "mapping": {"x": "group", "y": "value"},
        "export": {"output_dir": str(tmp_path / "figs"), "basename": "bad_fig"},
    }
    spec_path = _write_yaml_file(tmp_path / "bad.yaml", spec_dict)
    result = runner.invoke(app, ["validate", "--spec", str(spec_path)])
    assert result.exit_code == 1
    data = json.loads(result.stdout)
    assert data["status"] == "error"
    assert len(data["errors"]) > 0


def test_validate_spec_file_not_found(tmp_path: Path) -> None:
    """validate exits 1 when the spec file itself does not exist."""
    result = runner.invoke(app, ["validate", "--spec", str(tmp_path / "missing.yaml")])
    assert result.exit_code == 1
    data = json.loads(result.stdout)
    assert data["status"] == "error"
    assert "not found" in data["errors"][0].lower()


def test_validate_bad_yaml(tmp_path: Path) -> None:
    """validate exits 1 when the spec file contains unparseable YAML."""
    spec_path = tmp_path / "broken.yaml"
    spec_path.write_text("::: not valid yaml :::")
    result = runner.invoke(app, ["validate", "--spec", str(spec_path)])
    assert result.exit_code == 1
    data = json.loads(result.stdout)
    assert data["status"] == "error"


# ═══════════════════════════════════════════════════════════════════════════════
# render  (render_figure mocked — no matplotlib required)
# ═══════════════════════════════════════════════════════════════════════════════


def test_render_valid_spec(tmp_path: Path) -> None:
    """render exits 0 when render_figure succeeds (mocked)."""
    spec_path, _table_path = _write_spec_files(tmp_path)
    with patch("abi.sciplot.api.render_figure") as mock_render:
        from abi.sciplot.renderers import RenderResult

        mock_render.return_value = RenderResult(
            figure_id="test_fig",
            output_files=[tmp_path / "test_fig.pdf"],
        )
        result = runner.invoke(app, ["render", "--spec", str(spec_path)])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["status"] == "ok"


def test_render_with_output_dir(tmp_path: Path) -> None:
    """render --output-dir updates spec.export.output_dir (mocked)."""
    spec_path, _table_path = _write_spec_files(tmp_path)
    custom_dir = tmp_path / "custom_output"

    with patch("abi.sciplot.api.render_figure") as mock_render:
        from abi.sciplot.renderers import RenderResult

        mock_render.return_value = RenderResult(
            figure_id="test_fig",
            output_files=[custom_dir / "test_fig.pdf"],
        )
        result = runner.invoke(
            app,
            ["render", "--spec", str(spec_path), "--output-dir", str(custom_dir)],
        )
        assert result.exit_code == 0
        # Verify the spec passed to render has the updated output_dir
        call_spec = mock_render.call_args[0][0]
        assert call_spec.export.output_dir == custom_dir


def test_render_with_strict_and_warnings(tmp_path: Path) -> None:
    """render --strict fails (exit 1) when there are warnings."""
    spec_path, _table_path = _write_spec_files(tmp_path)
    with patch("abi.sciplot.api.render_figure") as mock_render:
        from abi.sciplot.renderers import RenderResult

        mock_render.return_value = RenderResult(
            figure_id="test_fig",
            warnings=["DPI is below 300"],
        )
        result = runner.invoke(
            app,
            ["render", "--spec", str(spec_path), "--strict"],
        )
        assert result.exit_code == 1
        data = json.loads(result.stdout)
        assert data["status"] == "error"


def test_render_with_strict_no_warnings(tmp_path: Path) -> None:
    """render --strict succeeds when there are no warnings."""
    spec_path, _table_path = _write_spec_files(tmp_path)
    with patch("abi.sciplot.api.render_figure") as mock_render:
        from abi.sciplot.renderers import RenderResult

        mock_render.return_value = RenderResult(
            figure_id="test_fig",
            output_files=[tmp_path / "out.pdf"],
        )
        result = runner.invoke(
            app,
            ["render", "--spec", str(spec_path), "--strict"],
        )
        assert result.exit_code == 0


def test_render_missing_spec_file(tmp_path: Path) -> None:
    """render exits 1 when the spec file does not exist."""
    result = runner.invoke(app, ["render", "--spec", str(tmp_path / "nope.yaml")])
    assert result.exit_code == 1


def test_render_bad_yaml(tmp_path: Path) -> None:
    """render exits 1 with unparseable spec YAML."""
    spec_path = tmp_path / "broken.yaml"
    spec_path.write_text("{invalid yaml")
    result = runner.invoke(app, ["render", "--spec", str(spec_path)])
    assert result.exit_code == 1


# ═══════════════════════════════════════════════════════════════════════════════
# lint
# ═══════════════════════════════════════════════════════════════════════════════


def test_lint_valid_spec(tmp_path: Path) -> None:
    """lint exits 0 when the lint report has no errors (mocked)."""
    spec_path, _table_path = _write_spec_files(tmp_path)
    with patch("abi.sciplot.api.lint_figure") as mock_lint:
        from abi.sciplot.lint import LintReport

        mock_lint.return_value = LintReport(figure_id="test_fig")
        result = runner.invoke(app, ["lint", "--spec", str(spec_path)])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["figure_id"] == "test_fig"
        assert data["status"] == "passed"


def test_lint_with_figure_path(tmp_path: Path) -> None:
    """lint --figure passes the figure path as an output file (mocked)."""
    spec_path, _table_path = _write_spec_files(tmp_path)
    fig_path = tmp_path / "rendered.pdf"
    fig_path.write_text("fake pdf")

    with patch("abi.sciplot.api.lint_figure") as mock_lint:
        from abi.sciplot.lint import LintReport

        mock_lint.return_value = LintReport(figure_id="test_fig")
        result = runner.invoke(
            app,
            ["lint", "--spec", str(spec_path), "--figure", str(fig_path)],
        )
        assert result.exit_code == 0
        # Verify the figure path was passed as an output file
        call_args = mock_lint.call_args
        assert call_args is not None
        # lint_figure(spec, output_files) — second positional arg
        output_files = call_args[0][1]
        assert len(output_files) == 1
        assert output_files[0] == fig_path


def test_lint_with_errors(tmp_path: Path) -> None:
    """lint exits 1 when the lint report contains errors."""
    spec_path, _table_path = _write_spec_files(tmp_path)
    with patch("abi.sciplot.api.lint_figure") as mock_lint:
        from abi.sciplot.lint import LintFinding, LintReport

        report = LintReport(figure_id="test_fig")
        report.errors.append(LintFinding(rule="FIG001", level="ERROR", message="figure_id missing"))
        mock_lint.return_value = report
        result = runner.invoke(app, ["lint", "--spec", str(spec_path)])
        assert result.exit_code == 1


def test_lint_missing_spec_file(tmp_path: Path) -> None:
    """lint exits 1 when the spec file does not exist."""
    result = runner.invoke(app, ["lint", "--spec", str(tmp_path / "nope.yaml")])
    assert result.exit_code == 1


# ═══════════════════════════════════════════════════════════════════════════════
# list-plot-types
# ═══════════════════════════════════════════════════════════════════════════════


def test_list_plot_types_basic() -> None:
    """list-plot-types exits 0 and prints supported plot types."""
    result = runner.invoke(app, ["list-plot-types"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert "supported_plot_types" in data
    assert isinstance(data["supported_plot_types"], list)
    assert len(data["supported_plot_types"]) > 0


def test_list_plot_types_includes_barplot() -> None:
    """list-plot-types output includes barplot."""
    result = runner.invoke(app, ["list-plot-types"])
    data = json.loads(result.stdout)
    assert "barplot" in data["supported_plot_types"]


# ═══════════════════════════════════════════════════════════════════════════════
# General CLI error cases
# ═══════════════════════════════════════════════════════════════════════════════


def test_cli_no_args_shows_help() -> None:
    """Invoking app with no arguments shows help text."""
    result = runner.invoke(app)
    assert result.exit_code != 0
    assert "Usage:" in result.stdout


def test_cli_unknown_command() -> None:
    """Invoking an unknown command returns non-zero and shows error."""
    result = runner.invoke(app, ["nonexistent"])
    assert result.exit_code != 0
