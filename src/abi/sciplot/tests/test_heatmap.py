"""Tests for the heatmap renderer."""

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
class TestHeatmap:
    def test_render_basic(self, palette, theme) -> None:
        """Smoke: basic heatmap with 3 genes × 2 samples."""
        from abi.sciplot.renderers.plots.heatmap import plot_heatmap

        tsv = _make_synthetic_tsv(
            [
                {"gene": "GeneA", "Sample1": 1.0, "Sample2": 2.0},
                {"gene": "GeneB", "Sample1": 3.0, "Sample2": 1.5},
                {"gene": "GeneC", "Sample1": 0.5, "Sample2": 4.0},
            ]
        )
        try:
            spec = FigureSpec(
                figure_id="test",
                figure_type="heatmap",
                data=DataSpec(table=tsv),
                mapping=MappingSpec(x="gene"),
                style=StyleSpec(palette="viridis"),
                export=ExportSpec(output_dir=Path("/tmp/out"), basename="test"),
            )
            data = pd.read_csv(tsv, sep="\t")
            fig, ax = plt.subplots()
            try:
                plot_heatmap(spec, data, ax, palette, theme)
            finally:
                plt.close(fig)
        finally:
            tsv.unlink()

    def test_render_empty_data(self, palette, theme) -> None:
        """Empty DataFrame → 'No data available' text, no crash."""
        from abi.sciplot.renderers.plots.heatmap import plot_heatmap

        tsv = _make_synthetic_tsv(
            [
                {"gene": "GeneA", "Sample1": 1.0},
            ]
        )
        try:
            spec = FigureSpec(
                figure_id="test",
                figure_type="heatmap",
                data=DataSpec(table=tsv),
                mapping=MappingSpec(x="gene"),
                style=StyleSpec(palette="viridis"),
                export=ExportSpec(output_dir=Path("/tmp/out"), basename="test"),
            )
            # Read then filter to empty
            data = pd.read_csv(tsv, sep="\t")
            data = data[data["gene"] == "nonexistent"]  # empty DataFrame
            fig, ax = plt.subplots()
            try:
                plot_heatmap(spec, data, ax, palette, theme)
            finally:
                plt.close(fig)
        finally:
            tsv.unlink()

    def test_render_no_numeric_columns(self, palette, theme) -> None:
        """Only non-numeric columns → graceful handling."""
        from abi.sciplot.renderers.plots.heatmap import plot_heatmap

        tsv = _make_synthetic_tsv(
            [
                {"gene": "GeneA", "category": "A", "notes": "foo"},
                {"gene": "GeneB", "category": "B", "notes": "bar"},
            ]
        )
        try:
            spec = FigureSpec(
                figure_id="test",
                figure_type="heatmap",
                data=DataSpec(table=tsv),
                mapping=MappingSpec(x="gene"),
                style=StyleSpec(palette="viridis"),
                export=ExportSpec(output_dir=Path("/tmp/out"), basename="test"),
            )
            data = pd.read_csv(tsv, sep="\t")
            fig, ax = plt.subplots()
            try:
                plot_heatmap(spec, data, ax, palette, theme)
            finally:
                plt.close(fig)
        finally:
            tsv.unlink()

    def test_render_many_rows_top50(self, palette, theme) -> None:
        """>50 rows → only top 50 by row sum displayed."""
        from abi.sciplot.renderers.plots.heatmap import plot_heatmap

        rows = [
            {"gene": f"Gene{i}", "Sample1": float(i), "Sample2": float(100 - i)} for i in range(60)
        ]
        tsv = _make_synthetic_tsv(rows)
        try:
            spec = FigureSpec(
                figure_id="test",
                figure_type="heatmap",
                data=DataSpec(table=tsv),
                mapping=MappingSpec(x="gene"),
                style=StyleSpec(palette="viridis"),
                export=ExportSpec(output_dir=Path("/tmp/out"), basename="test"),
            )
            data = pd.read_csv(tsv, sep="\t")
            fig, ax = plt.subplots()
            try:
                plot_heatmap(spec, data, ax, palette, theme)
                # Should have ≤50 y-tick labels (truncated)
                yticks = ax.get_yticklabels()
                assert len(yticks) <= 50
            finally:
                plt.close(fig)
        finally:
            tsv.unlink()

    def test_render_no_row_col(self, palette, theme) -> None:
        """No mapping.x → uses row indices as labels."""
        from abi.sciplot.renderers.plots.heatmap import plot_heatmap

        tsv = _make_synthetic_tsv(
            [
                {"Sample1": 1.0, "Sample2": 2.0},
                {"Sample1": 3.0, "Sample2": 1.5},
            ]
        )
        try:
            spec = FigureSpec(
                figure_id="test",
                figure_type="heatmap",
                data=DataSpec(table=tsv),
                mapping=MappingSpec(x=None),
                style=StyleSpec(palette="viridis"),
                export=ExportSpec(output_dir=Path("/tmp/out"), basename="test"),
            )
            data = pd.read_csv(tsv, sep="\t")
            fig, ax = plt.subplots()
            try:
                plot_heatmap(spec, data, ax, palette, theme)
            finally:
                plt.close(fig)
        finally:
            tsv.unlink()
