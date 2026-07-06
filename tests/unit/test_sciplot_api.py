"""Tests for abi.sciplot.api — load_spec, validate_spec, render_figure,
lint_figure, list_plot_types.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

from abi.sciplot.api import (
    lint_figure,
    list_plot_types,
    load_spec,
    render_figure,
    validate_spec,
)
from abi.sciplot.lint import LintReport
from abi.sciplot.schema.figure_spec import FigureSpec

# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def minimal_spec_dict() -> dict:
    """Minimal valid FigureSpec as a dict for YAML/JSON serialization."""
    return {
        "figure_id": "test_fig",
        "figure_type": "barplot",
        "data": {
            "table": "data.tsv",
            "format": "tsv",
        },
        "mapping": {
            "x": "group",
            "y": "value",
        },
        "export": {
            "output_dir": "figures",
            "basename": "test_fig",
        },
    }


@pytest.fixture
def minimal_spec(minimal_spec_dict: dict, tmp_path: Path) -> FigureSpec:
    """Create a minimal FigureSpec backed by a real data table on disk."""
    table_path = tmp_path / "data.tsv"
    table_path.write_text("group\tvalue\nA\t10\nB\t20\nC\t15\n")
    spec_dict = {**minimal_spec_dict}
    spec_dict["data"]["table"] = str(table_path)
    spec_dict["export"]["output_dir"] = str(tmp_path / "figures")
    return FigureSpec(**spec_dict)


# ═══════════════════════════════════════════════════════════════════════════════
# load_spec
# ═══════════════════════════════════════════════════════════════════════════════


def test_load_spec_valid_yaml(tmp_path: Path, minimal_spec_dict: dict) -> None:
    """load_spec loads a valid YAML file into a FigureSpec."""
    spec_file = tmp_path / "figure.yaml"
    spec_file.write_text(yaml.dump(minimal_spec_dict))
    spec = load_spec(spec_file)
    assert isinstance(spec, FigureSpec)
    assert spec.figure_id == "test_fig"
    assert spec.figure_type == "barplot"


def test_load_spec_file_not_found() -> None:
    """load_spec raises FileNotFoundError for a non-existent path."""
    with pytest.raises(FileNotFoundError, match="Figure spec not found"):
        load_spec("/nonexistent/path/figure.yaml")


def test_load_spec_empty_file(tmp_path: Path) -> None:
    """load_spec raises ValueError for an empty file (YAML-parsed as None)."""
    spec_file = tmp_path / "empty.yaml"
    spec_file.write_text("")
    with pytest.raises(ValueError, match="empty"):
        load_spec(spec_file)


def test_load_spec_invalid_yaml(tmp_path: Path) -> None:
    """load_spec raises an exception when YAML content cannot be parsed into a FigureSpec."""
    spec_file = tmp_path / "invalid.yaml"
    spec_file.write_text("- not a mapping\n- just a list\n")
    with pytest.raises((ValueError, TypeError)):
        load_spec(spec_file)


def test_load_spec_json_file(tmp_path: Path, minimal_spec_dict: dict) -> None:
    """load_spec loads a .json file into a FigureSpec."""
    spec_file = tmp_path / "figure.json"
    spec_file.write_text(json.dumps(minimal_spec_dict))
    spec = load_spec(spec_file)
    assert isinstance(spec, FigureSpec)
    assert spec.figure_id == "test_fig"


def test_load_spec_missing_required_fields(tmp_path: Path) -> None:
    """load_spec raises a validation error when required fields are absent."""
    spec_file = tmp_path / "bad.yaml"
    spec_file.write_text("figure_id: 123\n")
    with pytest.raises(ValueError):
        load_spec(spec_file)


def test_load_spec_none_content(tmp_path: Path) -> None:
    """load_spec raises ValueError when the YAML file contains only null."""
    spec_file = tmp_path / "null.yaml"
    spec_file.write_text("null\n")
    with pytest.raises(ValueError, match="empty"):
        load_spec(spec_file)


def test_load_spec_pathlib_path(tmp_path: Path, minimal_spec_dict: dict) -> None:
    """load_spec accepts a pathlib.Path argument."""
    spec_file = tmp_path / "figure.yaml"
    spec_file.write_text(yaml.dump(minimal_spec_dict))
    spec = load_spec(Path(spec_file))
    assert isinstance(spec, FigureSpec)


# ═══════════════════════════════════════════════════════════════════════════════
# validate_spec
# ═══════════════════════════════════════════════════════════════════════════════


def test_validate_spec_valid(minimal_spec: FigureSpec) -> None:
    """validate_spec returns status 'ok' when data table exists and is well-formed."""
    result = validate_spec(minimal_spec)
    assert result["status"] == "ok"
    assert result["figure_id"] == "test_fig"
    assert isinstance(result["errors"], list)
    assert isinstance(result["warnings"], list)


def test_validate_spec_with_missing_table(tmp_path: Path) -> None:
    """validate_spec returns status 'error' when the input table is missing."""
    spec = FigureSpec(
        figure_id="bad_fig",
        figure_type="barplot",
        data={"table": str(tmp_path / "nope.tsv"), "format": "tsv"},
        mapping={"x": "group", "y": "value"},
        export={"output_dir": str(tmp_path / "figs"), "basename": "bad_fig"},
    )
    result = validate_spec(spec)
    assert result["status"] == "error"
    assert len(result["errors"]) > 0
    assert any("does not exist" in e for e in result["errors"])


def test_validate_spec_result_keys(minimal_spec: FigureSpec) -> None:
    """validate_spec result dict has the expected top-level keys."""
    result = validate_spec(minimal_spec)
    for key in ("status", "figure_id", "errors", "warnings"):
        assert key in result


# ═══════════════════════════════════════════════════════════════════════════════
# lint_figure
# ═══════════════════════════════════════════════════════════════════════════════


def test_lint_figure_valid_spec_no_output_files(minimal_spec: FigureSpec) -> None:
    """lint_figure returns a LintReport for a valid spec (may have provenance warnings)."""
    report = lint_figure(minimal_spec)
    assert isinstance(report, LintReport)
    assert report.figure_id == "test_fig"
    d = report.to_dict()
    assert isinstance(d, dict)
    assert "errors" in d
    assert "warnings" in d
    assert "info" in d


def test_lint_figure_with_output_files_and_provenance(
    minimal_spec: FigureSpec, tmp_path: Path
) -> None:
    """lint_figure accepts output files and provenance path, avoiding PROV001."""
    pdf = tmp_path / "output.pdf"
    pdf.write_text("fake pdf content")
    png = tmp_path / "output.png"
    png.write_text("fake png content")
    prov = tmp_path / "provenance.json"
    prov.write_text("{}")

    report = lint_figure(
        minimal_spec,
        output_files=[pdf, png],
        provenance_path=prov,
    )
    d = report.to_dict()
    # With .pdf as output, EXPORT002 (no vector format) should not fire
    export002_errors = [e for e in d["errors"] if e["rule"] == "EXPORT002"]
    assert len(export002_errors) == 0
    # With provenance_path present, PROV001 should not fire
    prov001_errors = [e for e in d["errors"] if e["rule"] == "PROV001"]
    assert len(prov001_errors) == 0


def test_lint_figure_report_keys(minimal_spec: FigureSpec) -> None:
    """LintReport.to_dict() returns all expected sections."""
    report = lint_figure(minimal_spec)
    d = report.to_dict()
    assert d["figure_id"] == "test_fig"
    assert d["status"] in ("passed", "failed")
    for key in ("figure_id", "status", "errors", "warnings", "info"):
        assert key in d


def test_lint_figure_status_failed_on_errors(minimal_spec: FigureSpec) -> None:
    """report.status is 'failed' when errors exist (no provenance)."""
    report = lint_figure(minimal_spec)
    assert report.status == "failed"  # PROV001 fires without provenance_path


# ═══════════════════════════════════════════════════════════════════════════════
# render_figure  (MatplotlibRenderer mocked — no matplotlib needed)
# ═══════════════════════════════════════════════════════════════════════════════


def test_render_figure_mocked(minimal_spec: FigureSpec) -> None:
    """render_figure returns a RenderResult when MatplotlibRenderer is mocked."""
    with patch("abi.sciplot.renderers.matplotlib_renderer.MatplotlibRenderer") as mock_renderer_cls:
        from abi.sciplot.renderers import RenderResult

        mock_instance = MagicMock()
        mock_instance.render.return_value = RenderResult(
            figure_id="test_fig",
            output_files=[Path("/tmp/test_fig.pdf")],
            lint_report_path=Path("/tmp/test_fig.lint.json"),
            provenance_path=Path("/tmp/test_fig.prov.json"),
        )
        mock_renderer_cls.return_value = mock_instance

        result = render_figure(minimal_spec)
        assert isinstance(result, RenderResult)
        assert result.figure_id == "test_fig"
        assert len(result.output_files) == 1
        mock_instance.render.assert_called_once_with(minimal_spec)


def test_render_figure_error_result(minimal_spec: FigureSpec) -> None:
    """render_figure propagates errors from the renderer into the RenderResult."""
    with patch("abi.sciplot.renderers.matplotlib_renderer.MatplotlibRenderer") as mock_renderer_cls:
        from abi.sciplot.renderers import RenderResult

        mock_instance = MagicMock()
        mock_instance.render.return_value = RenderResult(
            figure_id="test_fig",
            errors=["Rendering pipeline failed"],
            warnings=["Low resolution warning"],
        )
        mock_renderer_cls.return_value = mock_instance

        result = render_figure(minimal_spec)
        assert result.status == "error"
        assert result.errors == ["Rendering pipeline failed"]
        assert result.warnings == ["Low resolution warning"]


def test_render_figure_to_dict(minimal_spec: FigureSpec) -> None:
    """RenderResult.to_dict() produces expected structure."""
    with patch("abi.sciplot.renderers.matplotlib_renderer.MatplotlibRenderer") as mock_renderer_cls:
        from abi.sciplot.renderers import RenderResult

        mock_instance = MagicMock()
        mock_instance.render.return_value = RenderResult(
            figure_id="test_fig",
            output_files=[Path("/tmp/out.pdf"), Path("/tmp/out.png")],
            lint_report_path=Path("/tmp/lint.json"),
            provenance_path=Path("/tmp/prov.json"),
        )
        mock_renderer_cls.return_value = mock_instance

        result = render_figure(minimal_spec)
        d = result.to_dict()
        assert d["status"] == "ok"
        assert d["figure_id"] == "test_fig"
        assert len(d["outputs"]) == 2
        assert d["lint_report"] == "/tmp/lint.json"
        assert d["provenance"] == "/tmp/prov.json"


# ═══════════════════════════════════════════════════════════════════════════════
# list_plot_types
# ═══════════════════════════════════════════════════════════════════════════════


def test_list_plot_types_returns_list() -> None:
    """list_plot_types returns a list of strings."""
    types = list_plot_types()
    assert isinstance(types, list)
    assert all(isinstance(t, str) for t in types)


def test_list_plot_types_non_empty() -> None:
    """list_plot_types returns at least one supported type."""
    types = list_plot_types()
    assert len(types) > 0


def test_list_plot_types_contains_barplot() -> None:
    """barplot is a supported figure type."""
    types = list_plot_types()
    assert "barplot" in types


def test_list_plot_types_sorted() -> None:
    """list_plot_types returns a sorted list."""
    types = list_plot_types()
    assert types == sorted(types)
