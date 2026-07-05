"""Tests for the PCoA renderer."""

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
class TestPcoa:
    def test_render_basic(self, palette, theme) -> None:
        """Smoke: 3 samples, 3 pairwise distances."""
        from abi.sciplot.renderers.plots.pcoa_plot import plot_pcoa_plot

        tsv = _make_synthetic_tsv(
            [
                {"sample_a": "A", "sample_b": "B", "distance": 0.3},
                {"sample_a": "A", "sample_b": "C", "distance": 0.6},
                {"sample_a": "B", "sample_b": "C", "distance": 0.5},
            ]
        )
        try:
            spec = FigureSpec(
                figure_id="test",
                figure_type="pcoa_plot",
                data=DataSpec(table=tsv),
                mapping=MappingSpec(),
                style=StyleSpec(palette="colorblind_safe"),
                export=ExportSpec(output_dir=Path("/tmp/out"), basename="test"),
            )
            data = pd.read_csv(tsv, sep="\t")
            fig, ax = plt.subplots()
            try:
                plot_pcoa_plot(spec, data, ax, palette, theme)
            finally:
                plt.close(fig)
        finally:
            tsv.unlink()

    def test_render_with_hue_coloring(self, palette, theme) -> None:
        """Hue column for group coloring."""
        from abi.sciplot.renderers.plots.pcoa_plot import plot_pcoa_plot

        tsv = _make_synthetic_tsv(
            [
                {"sample_a": "A", "sample_b": "B", "distance": 0.3, "group": "Control"},
                {"sample_a": "A", "sample_b": "C", "distance": 0.6, "group": "Treatment"},
                {"sample_a": "B", "sample_b": "C", "distance": 0.5, "group": "Treatment"},
            ]
        )
        try:
            spec = FigureSpec(
                figure_id="test",
                figure_type="pcoa_plot",
                data=DataSpec(table=tsv),
                mapping=MappingSpec(hue="group"),
                style=StyleSpec(palette="colorblind_safe"),
                export=ExportSpec(output_dir=Path("/tmp/out"), basename="test"),
            )
            data = pd.read_csv(tsv, sep="\t")
            fig, ax = plt.subplots()
            try:
                plot_pcoa_plot(spec, data, ax, palette, theme)
            finally:
                plt.close(fig)
        finally:
            tsv.unlink()

    def test_render_less_than_two_samples_raises(self) -> None:
        """<2 unique samples → ValueError."""
        from abi.sciplot.renderers.plots.pcoa_plot import plot_pcoa_plot

        from abi.sciplot.schema.palette_spec import PaletteRegistry
        from abi.sciplot.schema.theme_spec import ThemeSpec

        tsv = _make_synthetic_tsv(
            [
                {"sample_a": "A", "sample_b": "A", "distance": 0.0},
            ]
        )
        palette = PaletteRegistry()
        palette.load_builtins()
        theme = ThemeSpec(theme_name="test")
        try:
            spec = FigureSpec(
                figure_id="test",
                figure_type="pcoa_plot",
                data=DataSpec(table=tsv),
                mapping=MappingSpec(),
                style=StyleSpec(palette="colorblind_safe"),
                export=ExportSpec(output_dir=Path("/tmp/out"), basename="test"),
            )
            data = pd.read_csv(tsv, sep="\t")
            fig, ax = plt.subplots()
            with pytest.raises(ValueError, match="2 unique samples"):
                plot_pcoa_plot(spec, data, ax, palette, theme)
            plt.close(fig)
        finally:
            tsv.unlink()

    def test_render_missing_columns_raises(self) -> None:
        """Missing required columns → ValueError."""
        from abi.sciplot.renderers.plots.pcoa_plot import plot_pcoa_plot

        from abi.sciplot.schema.palette_spec import PaletteRegistry
        from abi.sciplot.schema.theme_spec import ThemeSpec

        tsv = _make_synthetic_tsv(
            [
                {"sample_a": "A", "distance": 0.1},
            ]
        )
        palette = PaletteRegistry()
        palette.load_builtins()
        theme = ThemeSpec(theme_name="test")
        try:
            spec = FigureSpec(
                figure_id="test",
                figure_type="pcoa_plot",
                data=DataSpec(table=tsv),
                mapping=MappingSpec(),
                style=StyleSpec(palette="colorblind_safe"),
                export=ExportSpec(output_dir=Path("/tmp/out"), basename="test"),
            )
            data = pd.read_csv(tsv, sep="\t")
            fig, ax = plt.subplots()
            with pytest.raises(ValueError, match="missing columns"):
                plot_pcoa_plot(spec, data, ax, palette, theme)
            plt.close(fig)
        finally:
            tsv.unlink()

    def test_render_larger_dataset(self, palette, theme) -> None:
        """6 samples, comprehensive test."""
        from abi.sciplot.renderers.plots.pcoa_plot import plot_pcoa_plot

        # 6 samples → 15 pairwise distances
        rows = [
            {"sample_a": "S1", "sample_b": "S2", "distance": 0.10},
            {"sample_a": "S1", "sample_b": "S3", "distance": 0.25},
            {"sample_a": "S1", "sample_b": "S4", "distance": 0.40},
            {"sample_a": "S1", "sample_b": "S5", "distance": 0.15},
            {"sample_a": "S1", "sample_b": "S6", "distance": 0.50},
            {"sample_a": "S2", "sample_b": "S3", "distance": 0.20},
            {"sample_a": "S2", "sample_b": "S4", "distance": 0.35},
            {"sample_a": "S2", "sample_b": "S5", "distance": 0.12},
            {"sample_a": "S2", "sample_b": "S6", "distance": 0.45},
            {"sample_a": "S3", "sample_b": "S4", "distance": 0.30},
            {"sample_a": "S3", "sample_b": "S5", "distance": 0.22},
            {"sample_a": "S3", "sample_b": "S6", "distance": 0.38},
            {"sample_a": "S4", "sample_b": "S5", "distance": 0.42},
            {"sample_a": "S4", "sample_b": "S6", "distance": 0.18},
            {"sample_a": "S5", "sample_b": "S6", "distance": 0.48},
        ]
        tsv = _make_synthetic_tsv(rows)
        try:
            spec = FigureSpec(
                figure_id="test",
                figure_type="pcoa_plot",
                data=DataSpec(table=tsv),
                mapping=MappingSpec(),
                style=StyleSpec(palette="colorblind_safe"),
                export=ExportSpec(output_dir=Path("/tmp/out"), basename="test"),
            )
            data = pd.read_csv(tsv, sep="\t")
            fig, ax = plt.subplots()
            try:
                plot_pcoa_plot(spec, data, ax, palette, theme)
                # 6 samples in single group → 1 scatter collection
                assert len(ax.collections) >= 1
            finally:
                plt.close(fig)
        finally:
            tsv.unlink()
