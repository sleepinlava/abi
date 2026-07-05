"""Tests for plot rendering functions.

Each test generates synthetic data and verifies that the plot function
produces a matplotlib Figure without error.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# Lazy import — only if matplotlib is available
try:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    HAS_MPL = True
except ImportError:
    HAS_MPL = False

from abi.sciplot.schema.figure_spec import (
    DataSpec,
    ExportSpec,
    FigureSpec,
    MappingSpec,
    StatSpec,
    StyleSpec,
)
from abi.sciplot.schema.palette_spec import PaletteRegistry
from abi.sciplot.schema.theme_spec import ThemeSpec


@pytest.fixture(scope="module")
def palette() -> PaletteRegistry:
    reg = PaletteRegistry()
    reg.load_builtins()
    return reg


@pytest.fixture(scope="module")
def theme() -> ThemeSpec:
    return ThemeSpec(theme_name="test")


def _make_synthetic_tsv(rows: list[dict]) -> Path:
    """Write synthetic data to a temp TSV and return the path."""
    df = pd.DataFrame(rows)
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".tsv", delete=False)
    df.to_csv(tmp.name, sep="\t", index=False)
    tmp.close()
    return Path(tmp.name)


# ── Boxplot with points ─────────────────────────────────────────────────


@pytest.mark.skipif(not HAS_MPL, reason="matplotlib not installed")
class TestBoxplotWithPoints:
    def test_render(self, palette, theme) -> None:
        from abi.sciplot.renderers.plots.boxplot_with_points import plot_boxplot_with_points

        tsv = _make_synthetic_tsv(
            [
                {"group": "A", "value": 1.0},
                {"group": "A", "value": 2.0},
                {"group": "B", "value": 3.0},
                {"group": "B", "value": 4.0},
                {"group": "C", "value": 5.0},
            ]
        )
        try:
            spec = FigureSpec(
                figure_id="test",
                figure_type="boxplot_with_points",
                data=DataSpec(table=tsv),
                mapping=MappingSpec(x="group", y="value"),
                style=StyleSpec(palette="colorblind_safe"),
                export=ExportSpec(output_dir=Path("/tmp/out"), basename="test"),
            )
            data = pd.read_csv(tsv, sep="\t")
            fig, ax = plt.subplots()
            plot_boxplot_with_points(spec, data, ax, palette, theme)
            plt.close(fig)
            assert ax.get_title() == ""  # No title set by plot function
        finally:
            tsv.unlink()


# ── Scatterplot ──────────────────────────────────────────────────────────


@pytest.mark.skipif(not HAS_MPL, reason="matplotlib not installed")
class TestScatterplot:
    def test_render(self, palette, theme) -> None:
        from abi.sciplot.renderers.plots.scatterplot import plot_scatterplot

        tsv = _make_synthetic_tsv(
            [
                {"x": 1.0, "y": 2.0, "label": "A"},
                {"x": 3.0, "y": 4.0, "label": "B"},
                {"x": 5.0, "y": 6.0, "label": "C"},
            ]
        )
        try:
            spec = FigureSpec(
                figure_id="test",
                figure_type="scatterplot",
                data=DataSpec(table=tsv),
                mapping=MappingSpec(x="x", y="y", label="label"),
                style=StyleSpec(palette="colorblind_safe"),
                export=ExportSpec(output_dir=Path("/tmp/out"), basename="test"),
            )
            data = pd.read_csv(tsv, sep="\t")
            fig, ax = plt.subplots()
            plot_scatterplot(spec, data, ax, palette, theme)
            plt.close(fig)
        finally:
            tsv.unlink()

    def test_with_hue(self, palette, theme) -> None:
        from abi.sciplot.renderers.plots.scatterplot import plot_scatterplot

        tsv = _make_synthetic_tsv(
            [
                {"x": 1.0, "y": 2.0, "group": "Control"},
                {"x": 3.0, "y": 4.0, "group": "Treatment"},
                {"x": 5.0, "y": 6.0, "group": "Control"},
            ]
        )
        try:
            spec = FigureSpec(
                figure_id="test",
                figure_type="scatterplot",
                data=DataSpec(table=tsv),
                mapping=MappingSpec(x="x", y="y", hue="group"),
                style=StyleSpec(palette="colorblind_safe"),
                export=ExportSpec(output_dir=Path("/tmp/out"), basename="test"),
            )
            data = pd.read_csv(tsv, sep="\t")
            fig, ax = plt.subplots()
            plot_scatterplot(spec, data, ax, palette, theme)
            # Should have a legend
            assert ax.get_legend() is not None
            plt.close(fig)
        finally:
            tsv.unlink()


# ── Volcano plot ─────────────────────────────────────────────────────────


@pytest.mark.skipif(not HAS_MPL, reason="matplotlib not installed")
class TestVolcanoPlot:
    def test_render(self, palette, theme) -> None:
        from abi.sciplot.renderers.plots.volcano_plot import plot_volcano

        np.random.seed(42)
        n = 100
        tsv = _make_synthetic_tsv(
            [
                {
                    "gene_id": f"G{i}",
                    "log2FoldChange": np.random.normal(0, 1.5),
                    "padj": np.random.beta(1, 3),
                }
                for i in range(n)
            ]
        )
        try:
            spec = FigureSpec(
                figure_id="test",
                figure_type="volcano_plot",
                data=DataSpec(table=tsv),
                mapping=MappingSpec(x="log2FoldChange", y="padj", label="gene_id"),
                statistics=StatSpec(
                    test="DESeq2 Wald test",
                    correction="Benjamini-Hochberg",
                    pvalue_column="padj",
                    fold_change_column="log2FoldChange",
                ),
                style=StyleSpec(palette="colorblind_safe"),
                export=ExportSpec(output_dir=Path("/tmp/out"), basename="test"),
            )
            data = pd.read_csv(tsv, sep="\t")
            fig, ax = plt.subplots()
            plot_volcano(spec, data, ax, palette, theme)
            plt.close(fig)
        finally:
            tsv.unlink()


# ── Heatmap ──────────────────────────────────────────────────────────────


@pytest.mark.skipif(not HAS_MPL, reason="matplotlib not installed")
class TestHeatmap:
    def test_render(self, palette, theme) -> None:
        from abi.sciplot.renderers.plots.heatmap import plot_heatmap

        tsv = _make_synthetic_tsv(
            [
                {"sample": "S1", "gene_a": 10.0, "gene_b": 20.0, "gene_c": 5.0},
                {"sample": "S2", "gene_a": 15.0, "gene_b": 25.0, "gene_c": 3.0},
            ]
        )
        try:
            spec = FigureSpec(
                figure_id="test",
                figure_type="heatmap",
                data=DataSpec(table=tsv),
                mapping=MappingSpec(x="sample"),
                style=StyleSpec(palette="viridis"),
                export=ExportSpec(output_dir=Path("/tmp/out"), basename="test"),
            )
            data = pd.read_csv(tsv, sep="\t")
            fig, ax = plt.subplots()
            plot_heatmap(spec, data, ax, palette, theme)
            plt.close(fig)
        finally:
            tsv.unlink()


# ── Stacked barplot ──────────────────────────────────────────────────────


@pytest.mark.skipif(not HAS_MPL, reason="matplotlib not installed")
class TestStackedBarplot:
    def test_render(self, palette, theme) -> None:
        from abi.sciplot.renderers.plots.stacked_barplot import plot_stacked_barplot

        tsv = _make_synthetic_tsv(
            [
                {"sample": "S1", "Bacteria": 60.0, "Archaea": 10.0, "Fungi": 30.0},
                {"sample": "S2", "Bacteria": 70.0, "Archaea": 5.0, "Fungi": 25.0},
            ]
        )
        try:
            spec = FigureSpec(
                figure_id="test",
                figure_type="stacked_barplot",
                data=DataSpec(table=tsv),
                mapping=MappingSpec(x="sample"),
                style=StyleSpec(palette="colorblind_safe"),
                export=ExportSpec(output_dir=Path("/tmp/out"), basename="test"),
            )
            data = pd.read_csv(tsv, sep="\t")
            fig, ax = plt.subplots()
            plot_stacked_barplot(spec, data, ax, palette, theme)
            plt.close(fig)
        finally:
            tsv.unlink()


# ── Ordination plot ──────────────────────────────────────────────────────


@pytest.mark.skipif(not HAS_MPL, reason="matplotlib not installed")
class TestOrdinationPlot:
    def test_render(self, palette, theme) -> None:
        from abi.sciplot.renderers.plots.ordination_plot import plot_ordination

        tsv = _make_synthetic_tsv(
            [
                {"sample": "S1", "PC1": -1.0, "PC2": 0.5, "group": "A"},
                {"sample": "S2", "PC1": 1.0, "PC2": -0.5, "group": "B"},
                {"sample": "S3", "PC1": 0.0, "PC2": 1.5, "group": "A"},
            ]
        )
        try:
            spec = FigureSpec(
                figure_id="test",
                figure_type="ordination_plot",
                data=DataSpec(table=tsv),
                mapping=MappingSpec(label="sample", hue="group"),
                style=StyleSpec(palette="colorblind_safe"),
                export=ExportSpec(output_dir=Path("/tmp/out"), basename="test"),
            )
            data = pd.read_csv(tsv, sep="\t")
            fig, ax = plt.subplots()
            plot_ordination(spec, data, ax, palette, theme)
            plt.close(fig)
        finally:
            tsv.unlink()


# ── Violin with box ──────────────────────────────────────────────────────


@pytest.mark.skipif(not HAS_MPL, reason="matplotlib not installed")
class TestViolinWithBox:
    def test_render(self, palette, theme) -> None:
        from abi.sciplot.renderers.plots.violin_with_box import plot_violin_with_box

        tsv = _make_synthetic_tsv(
            [
                {"group": "A", "value": 1.0},
                {"group": "A", "value": 2.0},
                {"group": "A", "value": 1.5},
                {"group": "B", "value": 3.0},
                {"group": "B", "value": 4.0},
                {"group": "B", "value": 3.5},
            ]
        )
        try:
            spec = FigureSpec(
                figure_id="test",
                figure_type="violin_with_box",
                data=DataSpec(table=tsv),
                mapping=MappingSpec(x="group", y="value"),
                style=StyleSpec(palette="colorblind_safe"),
                export=ExportSpec(output_dir=Path("/tmp/out"), basename="test"),
            )
            data = pd.read_csv(tsv, sep="\t")
            fig, ax = plt.subplots()
            plot_violin_with_box(spec, data, ax, palette, theme)
            plt.close(fig)
        finally:
            tsv.unlink()


# ── RenderResult dataclass ─────────────────────────────────────────────


class TestRenderResult:
    """Unit tests for the RenderResult dataclass."""

    def test_status_ok_when_no_errors(self) -> None:
        from abi.sciplot.renderers import RenderResult

        rr = RenderResult(figure_id="fig1")
        assert rr.status == "ok"
        assert rr.errors == []
        assert rr.warnings == []

    def test_status_error_when_errors_present(self) -> None:
        from abi.sciplot.renderers import RenderResult

        rr = RenderResult(figure_id="fig1", errors=["something broke"])
        assert rr.status == "error"

    def test_to_dict_empty(self) -> None:
        from abi.sciplot.renderers import RenderResult

        rr = RenderResult(figure_id="fig1")
        d = rr.to_dict()
        assert d == {
            "status": "ok",
            "figure_id": "fig1",
            "outputs": [],
            "lint_report": None,
            "provenance": None,
            "errors": [],
            "warnings": [],
        }

    def test_to_dict_with_output(self) -> None:
        from pathlib import Path

        from abi.sciplot.renderers import RenderResult

        rr = RenderResult(
            figure_id="fig2",
            output_files=[Path("/tmp/fig2.png"), Path("/tmp/fig2.svg")],
            lint_report_path=Path("/tmp/fig2.lint.json"),
            provenance_path=Path("/tmp/fig2.prov.json"),
            errors=["E1"],
            warnings=["W1"],
        )
        d = rr.to_dict()
        assert d["status"] == "error"
        assert d["figure_id"] == "fig2"
        assert d["outputs"] == ["/tmp/fig2.png", "/tmp/fig2.svg"]
        assert d["lint_report"] == "/tmp/fig2.lint.json"
        assert d["provenance"] == "/tmp/fig2.prov.json"
        assert d["errors"] == ["E1"]
        assert d["warnings"] == ["W1"]

    def test_warnings_only_is_ok(self) -> None:
        from abi.sciplot.renderers import RenderResult

        rr = RenderResult(figure_id="fig1", warnings=["mild concern"])
        assert rr.status == "ok"

    def test_default_factories(self) -> None:
        from abi.sciplot.renderers import RenderResult

        rr = RenderResult(figure_id="test")
        assert isinstance(rr.output_files, list)
        assert isinstance(rr.errors, list)
        assert isinstance(rr.warnings, list)


# ── BaseRenderer ABC ────────────────────────────────────────────────────


class TestBaseRenderer:
    """Unit tests for the BaseRenderer abstract base class."""

    def test_cannot_instantiate_abstract(self) -> None:
        import pytest

        from abi.sciplot.renderers import BaseRenderer

        with pytest.raises(TypeError, match="abstract"):
            BaseRenderer()  # type: ignore[abstract]

    def test_concrete_subclass_works(self) -> None:
        from abi.sciplot.renderers import BaseRenderer, RenderResult

        class DummyRenderer(BaseRenderer):
            def supports(self, figure_type: str) -> bool:
                return figure_type == "dummy"

            def render(self, spec) -> RenderResult:
                return RenderResult(figure_id="ok")

        renderer = DummyRenderer()
        assert renderer.supports("dummy") is True
        assert renderer.supports("other") is False
        result = renderer.render(None)
        assert result.status == "ok"

    def test_supports_must_be_implemented(self) -> None:
        import pytest

        from abi.sciplot.renderers import BaseRenderer, RenderResult

        class MissingSupports(BaseRenderer):
            def render(self, spec) -> RenderResult:
                return RenderResult(figure_id="ok")

        with pytest.raises(TypeError, match="abstract"):
            MissingSupports()  # type: ignore[abstract]

    def test_render_must_be_implemented(self) -> None:
        import pytest

        from abi.sciplot.renderers import BaseRenderer

        class MissingRender(BaseRenderer):
            def supports(self, figure_type: str) -> bool:
                return True

        with pytest.raises(TypeError, match="abstract"):
            MissingRender()  # type: ignore[abstract]
