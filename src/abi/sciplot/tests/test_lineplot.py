"""Tests for the lineplot renderer."""

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
    LabelSpec,
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
class TestLineplot:
    def test_render_basic(self, palette, theme) -> None:
        """Smoke test: basic lineplot with x/y columns and 5 data points."""
        from abi.sciplot.renderers.plots.lineplot import plot_lineplot

        tsv = _make_synthetic_tsv(
            [
                {"time": 0, "value": 1.0},
                {"time": 1, "value": 1.5},
                {"time": 2, "value": 2.0},
                {"time": 3, "value": 1.8},
                {"time": 4, "value": 2.5},
            ]
        )
        try:
            spec = FigureSpec(
                figure_id="test",
                figure_type="lineplot",
                data=DataSpec(table=tsv),
                mapping=MappingSpec(x="time", y="value"),
                style=StyleSpec(palette="colorblind_safe"),
                export=ExportSpec(output_dir=Path("/tmp/out"), basename="test"),
            )
            data = pd.read_csv(tsv, sep="\t")
            fig, ax = plt.subplots()
            plot_lineplot(spec, data, ax, palette, theme)
            plt.close(fig)
        finally:
            tsv.unlink()

    def test_render_with_hue(self, palette, theme) -> None:
        """Lineplot with hue grouping -- should produce a legend."""
        from abi.sciplot.renderers.plots.lineplot import plot_lineplot

        tsv = _make_synthetic_tsv(
            [
                {"time": 0, "value": 1.0, "group": "Control"},
                {"time": 1, "value": 1.5, "group": "Control"},
                {"time": 0, "value": 3.0, "group": "Treatment"},
                {"time": 1, "value": 3.5, "group": "Treatment"},
            ]
        )
        try:
            spec = FigureSpec(
                figure_id="test",
                figure_type="lineplot",
                data=DataSpec(table=tsv),
                mapping=MappingSpec(x="time", y="value", hue="group"),
                labels=LabelSpec(legend_title="Groups"),
                style=StyleSpec(palette="colorblind_safe"),
                export=ExportSpec(output_dir=Path("/tmp/out"), basename="test"),
            )
            data = pd.read_csv(tsv, sep="\t")
            fig, ax = plt.subplots()
            plot_lineplot(spec, data, ax, palette, theme)
            assert ax.get_legend() is not None
            plt.close(fig)
        finally:
            tsv.unlink()

    def test_missing_x_column(self, palette, theme) -> None:
        """Mapping.x is None -> raises ValueError."""
        from abi.sciplot.renderers.plots.lineplot import plot_lineplot

        tsv = _make_synthetic_tsv([{"y": 1.0}])
        try:
            spec = FigureSpec(
                figure_id="test",
                figure_type="lineplot",
                data=DataSpec(table=tsv),
                mapping=MappingSpec(x=None, y="y"),
                style=StyleSpec(palette="colorblind_safe"),
                export=ExportSpec(output_dir=Path("/tmp/out"), basename="test"),
            )
            data = pd.read_csv(tsv, sep="\t")
            fig, ax = plt.subplots()
            with pytest.raises(ValueError, match="requires both mapping.x and mapping.y"):
                plot_lineplot(spec, data, ax, palette, theme)
            plt.close(fig)
        finally:
            tsv.unlink()

    def test_missing_y_column(self, palette, theme) -> None:
        """Mapping.y column not in data -> raises ValueError."""
        from abi.sciplot.renderers.plots.lineplot import plot_lineplot

        tsv = _make_synthetic_tsv([{"x": 1.0, "y": 2.0}])
        try:
            spec = FigureSpec(
                figure_id="test",
                figure_type="lineplot",
                data=DataSpec(table=tsv),
                mapping=MappingSpec(x="x", y="nonexistent"),
                style=StyleSpec(palette="colorblind_safe"),
                export=ExportSpec(output_dir=Path("/tmp/out"), basename="test"),
            )
            data = pd.read_csv(tsv, sep="\t")
            fig, ax = plt.subplots()
            with pytest.raises(ValueError, match=r"column\(s\) not found in data"):
                plot_lineplot(spec, data, ax, palette, theme)
            plt.close(fig)
        finally:
            tsv.unlink()

    def test_non_numeric_y_coerced(self, palette, theme) -> None:
        """Non-numeric y values are coerced to NaN and dropped; should not crash."""
        from abi.sciplot.renderers.plots.lineplot import plot_lineplot

        tsv = _make_synthetic_tsv(
            [
                {"time": 0, "value": "1.0"},
                {"time": 1, "value": "2.5"},
                {"time": 2, "value": "N/A"},
                {"time": 3, "value": "3.0"},
                {"time": 4, "value": "bad"},
            ]
        )
        try:
            spec = FigureSpec(
                figure_id="test",
                figure_type="lineplot",
                data=DataSpec(table=tsv),
                mapping=MappingSpec(x="time", y="value"),
                style=StyleSpec(palette="colorblind_safe"),
                export=ExportSpec(output_dir=Path("/tmp/out"), basename="test"),
            )
            data = pd.read_csv(tsv, sep="\t")
            fig, ax = plt.subplots()
            plot_lineplot(spec, data, ax, palette, theme)
            plt.close(fig)
        finally:
            tsv.unlink()

    def test_empty_after_coercion(self, palette, theme) -> None:
        """All y values non-numeric -> frame is empty -> raises ValueError."""
        from abi.sciplot.renderers.plots.lineplot import plot_lineplot

        tsv = _make_synthetic_tsv(
            [
                {"time": 0, "value": "N/A"},
                {"time": 1, "value": "bad"},
                {"time": 2, "value": "-"},
            ]
        )
        try:
            spec = FigureSpec(
                figure_id="test",
                figure_type="lineplot",
                data=DataSpec(table=tsv),
                mapping=MappingSpec(x="time", y="value"),
                style=StyleSpec(palette="colorblind_safe"),
                export=ExportSpec(output_dir=Path("/tmp/out"), basename="test"),
            )
            data = pd.read_csv(tsv, sep="\t")
            fig, ax = plt.subplots()
            with pytest.raises(ValueError, match="no valid x/y"):
                plot_lineplot(spec, data, ax, palette, theme)
            plt.close(fig)
        finally:
            tsv.unlink()
