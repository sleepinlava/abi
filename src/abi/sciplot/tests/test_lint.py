"""Tests for FigureLint rules."""

from __future__ import annotations

from pathlib import Path

import pytest

from abi.sciplot.lint import (
    LintReport,
    lint_figure,
)
from abi.sciplot.schema.figure_spec import (
    DataSpec,
    ExportSpec,
    FigureSpec,
    MappingSpec,
)


def _make_spec(**overrides) -> FigureSpec:
    """Build a spec for lint testing."""
    kwargs = {
        "figure_id": "lint_test",
        "figure_type": "volcano_plot",
        "data": DataSpec(table=Path("/tmp/data.tsv")),
        "mapping": MappingSpec(x="log2FC", y="padj"),
        "export": ExportSpec(output_dir=Path("/tmp/out"), basename="lint_test"),
    }
    kwargs.update(overrides)
    return FigureSpec(**kwargs)


class TestLintRules:
    """FigureLint rule enforcement."""

    def test_fig001_missing_id_rejected(self) -> None:
        """FIG001: A spec without figure_id should fail construction."""
        # Pydantic enforces this at construction time
        with pytest.raises(Exception):
            FigureSpec(
                figure_id="",  # empty string should fail min_length
                figure_type="volcano_plot",
                data=DataSpec(table=Path("/tmp/data.tsv")),
                mapping=MappingSpec(),
                export=ExportSpec(output_dir=Path("/tmp/out"), basename="x"),
            )

    def test_fig003_unknown_type(self) -> None:
        """FIG003: Unknown figure_type is caught by Pydantic validators."""
        with pytest.raises(ValueError, match="Unsupported figure_type"):
            _make_spec(figure_type="unknown_type")

    def test_style001_forbidden_palette(self) -> None:
        """STYLE001: Using 'jet' palette → ERROR."""
        spec = _make_spec()
        spec.style.palette = "jet"
        report = lint_figure(spec, [])
        assert any("STYLE001" in f.rule for f in report.errors)

    def test_stat001_no_test_for_volcano(self) -> None:
        """STAT001: Volcano without statistics → WARNING."""
        spec = _make_spec()
        spec.statistics = None
        report = lint_figure(spec, [])
        # Volcano with no stats gets a WARNING (not ERROR)
        assert any("STAT001" in f.rule for f in report.warnings)

    def test_export001_low_dpi(self) -> None:
        """EXPORT001: Low DPI PNG → ERROR."""
        spec = _make_spec()
        spec.style.dpi = 72
        output_files = [Path("/tmp/out/lint_test.png")]
        report = lint_figure(spec, output_files)
        assert any("EXPORT001" in f.rule for f in report.errors)

    def test_export002_no_vector(self) -> None:
        """EXPORT002: No vector format → WARNING."""
        spec = _make_spec()
        output_files = [Path("/tmp/out/lint_test.png"), Path("/tmp/out/lint_test.tiff")]
        report = lint_figure(spec, output_files)
        assert any("EXPORT002" in f.rule for f in report.warnings)

    def test_prov001_no_provenance(self) -> None:
        """PROV001: No provenance → ERROR."""
        spec = _make_spec()
        report = lint_figure(spec, [])
        assert any("PROV001" in f.rule for f in report.errors)

    def test_prov001_with_provenance(self) -> None:
        """PROV001: With provenance → no error."""
        spec = _make_spec()
        prov = Path("/tmp/out/lint_test.provenance.json")
        prov.parent.mkdir(parents=True, exist_ok=True)
        prov.write_text("{}")
        report = lint_figure(spec, [], prov)
        assert not any("PROV001" in f.rule for f in report.errors)
        prov.unlink()

    def test_lint_report_to_dict(self) -> None:
        """LintReport.to_dict() returns expected structure."""
        report = LintReport(figure_id="test")
        d = report.to_dict()
        assert d["figure_id"] == "test"
        assert d["status"] == "passed"
        assert "errors" in d
        assert "warnings" in d
