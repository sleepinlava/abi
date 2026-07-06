"""Error-path and edge-case tests for plot renderers.

Each test validates that a renderer handles bad or unusual data gracefully —
raising clear errors where expected, and not crashing silently otherwise.
"""

from __future__ import annotations

from pathlib import Path

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

import tempfile

from abi.sciplot.schema.figure_spec import (
    DataSpec,
    ExportSpec,
    FigureSpec,
    MappingSpec,
    StatSpec,
    StyleSpec,
)


def _make_synthetic_tsv(rows: list[dict]) -> Path:
    """Write synthetic data to a temp TSV and return the path.

    The caller is responsible for unlinking the file after use.
    """
    df = pd.DataFrame(rows)
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".tsv", delete=False)
    df.to_csv(tmp.name, sep="\t", index=False)
    tmp.close()
    return Path(tmp.name)


# ── Barplot error paths ──────────────────────────────────────────────────


@pytest.mark.skipif(not HAS_MPL, reason="matplotlib not installed")
class TestBarplotErrorPaths:
    def test_missing_y_column(self, palette, theme) -> None:
        """mapping.y=None → should raise ValueError about mapping.y."""
        from abi.sciplot.renderers.plots.barplot import plot_barplot

        tsv = _make_synthetic_tsv(
            [
                {"label": "A", "value": 1.0},
            ]
        )
        try:
            spec = FigureSpec(
                figure_id="test",
                figure_type="barplot",
                data=DataSpec(table=tsv),
                mapping=MappingSpec(x="label"),  # y is None
                style=StyleSpec(palette="colorblind_safe"),
                export=ExportSpec(output_dir=Path("/tmp/out"), basename="test"),
            )
            data = pd.read_csv(tsv, sep="\t")
            fig, ax = plt.subplots()
            with pytest.raises(ValueError, match="mapping.y"):
                plot_barplot(spec, data, ax, palette, theme)
            plt.close(fig)
        finally:
            tsv.unlink()


# ── Boxplot error paths ──────────────────────────────────────────────────


@pytest.mark.skipif(not HAS_MPL, reason="matplotlib not installed")
class TestBoxplotErrorPaths:
    def test_missing_group_column(self, palette, theme) -> None:
        """mapping.x not in data columns → should raise ValueError."""
        from abi.sciplot.renderers.plots.boxplot_with_points import plot_boxplot_with_points

        tsv = _make_synthetic_tsv(
            [
                {"col1": "A", "value": 1.0},
                {"col1": "B", "value": 2.0},
            ]
        )
        try:
            spec = FigureSpec(
                figure_id="test",
                figure_type="boxplot_with_points",
                data=DataSpec(table=tsv),
                mapping=MappingSpec(x="nonexistent", y="value"),
                style=StyleSpec(palette="colorblind_safe"),
                export=ExportSpec(output_dir=Path("/tmp/out"), basename="test"),
            )
            data = pd.read_csv(tsv, sep="\t")
            fig, ax = plt.subplots()
            with pytest.raises(ValueError, match="Group column"):
                plot_boxplot_with_points(spec, data, ax, palette, theme)
            plt.close(fig)
        finally:
            tsv.unlink()

    def test_nan_values(self, palette, theme) -> None:
        """Data with NaN in value column — should not crash."""
        from abi.sciplot.renderers.plots.boxplot_with_points import plot_boxplot_with_points

        tsv = _make_synthetic_tsv(
            [
                {"group": "A", "value": 1.0},
                {"group": "A", "value": float("nan")},
                {"group": "B", "value": 3.0},
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
        finally:
            tsv.unlink()


# ── Scatterplot error paths ──────────────────────────────────────────────


@pytest.mark.skipif(not HAS_MPL, reason="matplotlib not installed")
class TestScatterplotErrorPaths:
    def test_missing_x_column(self, palette, theme) -> None:
        """x column not in data → should raise ValueError."""
        from abi.sciplot.renderers.plots.scatterplot import plot_scatterplot

        tsv = _make_synthetic_tsv(
            [
                {"col": 1.0, "y": 2.0},
                {"col": 3.0, "y": 4.0},
            ]
        )
        try:
            spec = FigureSpec(
                figure_id="test",
                figure_type="scatterplot",
                data=DataSpec(table=tsv),
                mapping=MappingSpec(x="nonexistent", y="y"),
                style=StyleSpec(palette="colorblind_safe"),
                export=ExportSpec(output_dir=Path("/tmp/out"), basename="test"),
            )
            data = pd.read_csv(tsv, sep="\t")
            fig, ax = plt.subplots()
            with pytest.raises(ValueError, match="not found in data"):
                plot_scatterplot(spec, data, ax, palette, theme)
            plt.close(fig)
        finally:
            tsv.unlink()


# ── Volcano error paths ──────────────────────────────────────────────────


@pytest.mark.skipif(not HAS_MPL, reason="matplotlib not installed")
class TestVolcanoErrorPaths:
    def test_all_nan_pvalues(self, palette, theme) -> None:
        """All padj values are NaN — should handle gracefully, not crash."""
        from abi.sciplot.renderers.plots.volcano_plot import plot_volcano

        tsv = _make_synthetic_tsv(
            [
                {"gene": "G1", "log2FoldChange": 1.0, "padj": float("nan")},
                {"gene": "G2", "log2FoldChange": -1.0, "padj": float("nan")},
                {"gene": "G3", "log2FoldChange": 0.5, "padj": float("nan")},
            ]
        )
        try:
            spec = FigureSpec(
                figure_id="test",
                figure_type="volcano_plot",
                data=DataSpec(table=tsv),
                mapping=MappingSpec(x="log2FoldChange", y="padj", label="gene"),
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

    def test_no_significant(self, palette, theme) -> None:
        """All pvalues well above threshold — should still render."""
        from abi.sciplot.renderers.plots.volcano_plot import plot_volcano

        tsv = _make_synthetic_tsv(
            [
                {"gene": "G1", "log2FoldChange": 0.5, "padj": 0.5},
                {"gene": "G2", "log2FoldChange": -0.5, "padj": 0.3},
                {"gene": "G3", "log2FoldChange": 0.2, "padj": 0.8},
            ]
        )
        try:
            spec = FigureSpec(
                figure_id="test",
                figure_type="volcano_plot",
                data=DataSpec(table=tsv),
                mapping=MappingSpec(x="log2FoldChange", y="padj", label="gene"),
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


# ── Heatmap error paths ──────────────────────────────────────────────────


@pytest.mark.skipif(not HAS_MPL, reason="matplotlib not installed")
class TestHeatmapErrorPaths:
    def test_single_row(self, palette, theme) -> None:
        """Only 1 row — should render without error."""
        from abi.sciplot.renderers.plots.heatmap import plot_heatmap

        tsv = _make_synthetic_tsv(
            [
                {"sample": "S1", "gene_a": 10.0, "gene_b": 20.0},
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

    def test_empty_frame(self, palette, theme) -> None:
        """Empty DataFrame — should handle gracefully, not crash."""
        from abi.sciplot.renderers.plots.heatmap import plot_heatmap

        tsv = _make_synthetic_tsv(
            [
                {"sample": "S1", "gene_a": 10.0},
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
            data = data.iloc[0:0]  # empty DataFrame with same columns
            fig, ax = plt.subplots()
            plot_heatmap(spec, data, ax, palette, theme)
            plt.close(fig)
        finally:
            tsv.unlink()


# ── Stacked barplot error paths ──────────────────────────────────────────


@pytest.mark.skipif(not HAS_MPL, reason="matplotlib not installed")
class TestStackedBarplotErrorPaths:
    def test_missing_data_columns(self, palette, theme) -> None:
        """Columns referenced via mapping not in data — should not crash."""
        from abi.sciplot.renderers.plots.stacked_barplot import plot_stacked_barplot

        tsv = _make_synthetic_tsv(
            [
                {"col1": "A", "col2": 10.0},
                {"col1": "B", "col2": 20.0},
            ]
        )
        try:
            spec = FigureSpec(
                figure_id="test",
                figure_type="stacked_barplot",
                data=DataSpec(table=tsv),
                mapping=MappingSpec(x="nonexistent"),  # not in data
                style=StyleSpec(palette="colorblind_safe"),
                export=ExportSpec(output_dir=Path("/tmp/out"), basename="test"),
            )
            data = pd.read_csv(tsv, sep="\t")
            fig, ax = plt.subplots()
            plot_stacked_barplot(spec, data, ax, palette, theme)
            plt.close(fig)
        finally:
            tsv.unlink()


# ── Ordination plot error paths ──────────────────────────────────────────


@pytest.mark.skipif(not HAS_MPL, reason="matplotlib not installed")
class TestOrdinationPlotErrorPaths:
    def test_missing_coordinate_columns(self, palette, theme) -> None:
        """PC1/PC2 not in data — should handle gracefully, not crash."""
        from abi.sciplot.renderers.plots.ordination_plot import plot_ordination

        tsv = _make_synthetic_tsv(
            [
                {"label": "S1", "col1": "not_numeric", "col2": "also_not"},
                {"label": "S2", "col1": "text", "col2": "more_text"},
            ]
        )
        try:
            spec = FigureSpec(
                figure_id="test",
                figure_type="ordination_plot",
                data=DataSpec(table=tsv),
                mapping=MappingSpec(label="label"),
                style=StyleSpec(palette="colorblind_safe"),
                export=ExportSpec(output_dir=Path("/tmp/out"), basename="test"),
            )
            data = pd.read_csv(tsv, sep="\t")
            fig, ax = plt.subplots()
            plot_ordination(spec, data, ax, palette, theme)
            plt.close(fig)
        finally:
            tsv.unlink()


# ── Violin error paths ───────────────────────────────────────────────────


@pytest.mark.skipif(not HAS_MPL, reason="matplotlib not installed")
class TestViolinErrorPaths:
    def test_single_group(self, palette, theme) -> None:
        """Only one group — should still render."""
        from abi.sciplot.renderers.plots.violin_with_box import plot_violin_with_box

        tsv = _make_synthetic_tsv(
            [
                {"group": "A", "value": 1.0},
                {"group": "A", "value": 2.0},
                {"group": "A", "value": 3.0},
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
