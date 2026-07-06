"""Tests for the volcano_plot renderer."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

# Lazy import -- only if matplotlib is available
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
    SignificanceRule,
    StatSpec,
    StyleSpec,
)


def _make_synthetic_tsv(rows: list[dict]) -> Path:
    """Write synthetic data to a temp TSV and return the path.

    The caller is responsible for unlinking the file after use.
    """
    import tempfile

    df = pd.DataFrame(rows)
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".tsv", delete=False)
    df.to_csv(tmp.name, sep="\t", index=False)
    tmp.close()
    return Path(tmp.name)


@pytest.mark.skipif(not HAS_MPL, reason="matplotlib not installed")
class TestVolcano:
    def test_render_basic(self, palette, theme) -> None:
        """Smoke: basic volcano with up/down/NS points."""
        from abi.sciplot.renderers.plots.volcano_plot import plot_volcano

        tsv = _make_synthetic_tsv(
            [
                {"log2FoldChange": -2.0, "padj": 0.001},
                {"log2FoldChange": -0.5, "padj": 0.5},
                {"log2FoldChange": 0.0, "padj": 0.9},
                {"log2FoldChange": 1.5, "padj": 0.01},
                {"log2FoldChange": 3.0, "padj": 0.0001},
            ]
        )
        try:
            spec = FigureSpec(
                figure_id="test",
                figure_type="volcano_plot",
                data=DataSpec(table=tsv),
                mapping=MappingSpec(x="log2FoldChange", y="padj"),
                style=StyleSpec(palette="colorblind_safe"),
                export=ExportSpec(output_dir=Path("/tmp/out"), basename="test"),
            )
            data = pd.read_csv(tsv, sep="\t")
            fig, ax = plt.subplots()
            try:
                plot_volcano(spec, data, ax, palette, theme)
            finally:
                plt.close(fig)
        finally:
            tsv.unlink()

    def test_render_with_label_column(self, palette, theme) -> None:
        """Volcano with gene labels on top-N significant points."""
        from abi.sciplot.renderers.plots.volcano_plot import plot_volcano

        tsv = _make_synthetic_tsv(
            [
                {"log2FoldChange": -2.0, "padj": 0.001, "gene": "GeneA"},
                {"log2FoldChange": -0.5, "padj": 0.5, "gene": "GeneNS1"},
                {"log2FoldChange": 0.0, "padj": 0.9, "gene": "GeneNS2"},
                {"log2FoldChange": 1.5, "padj": 0.01, "gene": "GeneB"},
                {"log2FoldChange": 3.0, "padj": 0.0001, "gene": "GeneC"},
            ]
        )
        try:
            spec = FigureSpec(
                figure_id="test",
                figure_type="volcano_plot",
                data=DataSpec(table=tsv),
                mapping=MappingSpec(x="log2FoldChange", y="padj", label="gene"),
                style=StyleSpec(palette="colorblind_safe"),
                export=ExportSpec(output_dir=Path("/tmp/out"), basename="test"),
            )
            data = pd.read_csv(tsv, sep="\t")
            fig, ax = plt.subplots()
            try:
                plot_volcano(spec, data, ax, palette, theme)
            finally:
                plt.close(fig)
        finally:
            tsv.unlink()

    def test_render_all_nonsignificant(self, palette, theme) -> None:
        """All points are NS — no red/blue, all grey."""
        from abi.sciplot.renderers.plots.volcano_plot import plot_volcano

        tsv = _make_synthetic_tsv(
            [
                {"log2FoldChange": -0.3, "padj": 0.5},
                {"log2FoldChange": 0.1, "padj": 0.9},
                {"log2FoldChange": 0.5, "padj": 0.3},
            ]
        )
        try:
            spec = FigureSpec(
                figure_id="test",
                figure_type="volcano_plot",
                data=DataSpec(table=tsv),
                mapping=MappingSpec(x="log2FoldChange", y="padj"),
                style=StyleSpec(palette="colorblind_safe"),
                export=ExportSpec(output_dir=Path("/tmp/out"), basename="test"),
            )
            data = pd.read_csv(tsv, sep="\t")
            fig, ax = plt.subplots()
            try:
                plot_volcano(spec, data, ax, palette, theme)
            finally:
                plt.close(fig)
        finally:
            tsv.unlink()

    def test_render_missing_x_column_raises(self) -> None:
        """Missing log2FoldChange column raises ValueError."""
        from abi.sciplot.renderers.plots.volcano_plot import plot_volcano

        from abi.sciplot.schema.palette_spec import PaletteRegistry
        from abi.sciplot.schema.theme_spec import ThemeSpec

        tsv = _make_synthetic_tsv([{"padj": 0.01}])
        palette = PaletteRegistry()
        palette.load_builtins()
        theme = ThemeSpec(theme_name="test")
        try:
            spec = FigureSpec(
                figure_id="test",
                figure_type="volcano_plot",
                data=DataSpec(table=tsv),
                mapping=MappingSpec(x="log2FoldChange", y="padj"),
                style=StyleSpec(palette="colorblind_safe"),
                export=ExportSpec(output_dir=Path("/tmp/out"), basename="test"),
            )
            data = pd.read_csv(tsv, sep="\t")
            fig, ax = plt.subplots()
            with pytest.raises(ValueError, match="not found in data"):
                plot_volcano(spec, data, ax, palette, theme)
            plt.close(fig)
        finally:
            tsv.unlink()

    def test_render_missing_y_column_raises(self) -> None:
        """Missing padj column raises ValueError."""
        from abi.sciplot.renderers.plots.volcano_plot import plot_volcano

        from abi.sciplot.schema.palette_spec import PaletteRegistry
        from abi.sciplot.schema.theme_spec import ThemeSpec

        tsv = _make_synthetic_tsv([{"log2FoldChange": 1.0}])
        palette = PaletteRegistry()
        palette.load_builtins()
        theme = ThemeSpec(theme_name="test")
        try:
            spec = FigureSpec(
                figure_id="test",
                figure_type="volcano_plot",
                data=DataSpec(table=tsv),
                mapping=MappingSpec(x="log2FoldChange", y="padj"),
                style=StyleSpec(palette="colorblind_safe"),
                export=ExportSpec(output_dir=Path("/tmp/out"), basename="test"),
            )
            data = pd.read_csv(tsv, sep="\t")
            fig, ax = plt.subplots()
            with pytest.raises(ValueError, match="not found in data"):
                plot_volcano(spec, data, ax, palette, theme)
            plt.close(fig)
        finally:
            tsv.unlink()

    def test_render_custom_thresholds(self, palette, theme) -> None:
        """Custom fc_thresh and p_thresh from stat spec."""
        from abi.sciplot.renderers.plots.volcano_plot import plot_volcano

        # Defaults: fc_thresh=1.0, p_thresh=0.05
        # Custom:  fc_thresh=2.0, p_thresh=0.01
        # Point at FC=1.5, padj=0.03: significant under defaults, NS under custom
        tsv = _make_synthetic_tsv(
            [
                {"log2FoldChange": -3.0, "padj": 0.001},  # Down (both)
                {"log2FoldChange": -0.5, "padj": 0.5},   # NS (both)
                {"log2FoldChange": 1.5, "padj": 0.03},   # Up (default), NS (custom)
                {"log2FoldChange": 2.5, "padj": 0.001},  # Up (both)
            ]
        )
        try:
            spec = FigureSpec(
                figure_id="test",
                figure_type="volcano_plot",
                data=DataSpec(table=tsv),
                mapping=MappingSpec(x="log2FoldChange", y="padj"),
                statistics=StatSpec(
                    significance_rule=SignificanceRule(abs_log2fc_gt=2.0, padj_lt=0.01),
                ),
                style=StyleSpec(palette="colorblind_safe"),
                export=ExportSpec(output_dir=Path("/tmp/out"), basename="test"),
            )
            data = pd.read_csv(tsv, sep="\t")
            fig, ax = plt.subplots()
            try:
                plot_volcano(spec, data, ax, palette, theme)
            finally:
                plt.close(fig)
        finally:
            tsv.unlink()
