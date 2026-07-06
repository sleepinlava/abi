"""Tests for the stacked barplot renderer."""

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
class TestStackedBar:
    def test_render_basic(self, palette, theme) -> None:
        """Smoke: 3 samples, 2 component columns."""
        from abi.sciplot.renderers.plots.stacked_barplot import plot_stacked_barplot

        tsv = _make_synthetic_tsv(
            [
                {"sample": "S1", "A": 10.0, "B": 5.0},
                {"sample": "S2", "A": 3.0, "B": 12.0},
                {"sample": "S3", "A": 7.0, "B": 7.0},
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
            try:
                plot_stacked_barplot(spec, data, ax, palette, theme)
            finally:
                plt.close(fig)
        finally:
            tsv.unlink()

    def test_render_empty_data(self, palette, theme) -> None:
        """Empty DataFrame -> 'No data available'."""
        from abi.sciplot.renderers.plots.stacked_barplot import plot_stacked_barplot

        tsv = _make_synthetic_tsv(
            [
                {"sample": "S1", "A": 10.0, "B": 5.0},
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
            data = data[data["sample"] == "nonexistent"]
            fig, ax = plt.subplots()
            try:
                plot_stacked_barplot(spec, data, ax, palette, theme)
            finally:
                plt.close(fig)
        finally:
            tsv.unlink()

    def test_render_no_stack_columns(self, palette, theme) -> None:
        """Only group column, no numeric cols -> 'No stack columns'."""
        from abi.sciplot.renderers.plots.stacked_barplot import plot_stacked_barplot

        tsv = _make_synthetic_tsv(
            [
                {"sample": "S1"},
                {"sample": "S2"},
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
            try:
                plot_stacked_barplot(spec, data, ax, palette, theme)
            finally:
                plt.close(fig)
        finally:
            tsv.unlink()

    def test_render_normalization(self, palette, theme) -> None:
        """Row sums != 1 -> still renders (normalized internally)."""
        from abi.sciplot.renderers.plots.stacked_barplot import plot_stacked_barplot

        tsv = _make_synthetic_tsv(
            [
                {"sample": "S1", "A": 500.0, "B": 500.0},
                {"sample": "S2", "A": 100.0, "B": 900.0},
                {"sample": "S3", "A": 700.0, "B": 300.0},
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
            try:
                plot_stacked_barplot(spec, data, ax, palette, theme)
            finally:
                plt.close(fig)
        finally:
            tsv.unlink()

    def test_render_many_categories(self, palette, theme) -> None:
        """8 stacking columns, moderate data."""
        from abi.sciplot.renderers.plots.stacked_barplot import plot_stacked_barplot

        tsv = _make_synthetic_tsv(
            [
                {
                    "sample": "S1",
                    "CompA": 5.0,
                    "CompB": 3.0,
                    "CompC": 2.0,
                    "CompD": 1.0,
                    "CompE": 4.0,
                    "CompF": 6.0,
                    "CompG": 2.0,
                    "CompH": 1.0,
                },
                {
                    "sample": "S2",
                    "CompA": 2.0,
                    "CompB": 4.0,
                    "CompC": 3.0,
                    "CompD": 5.0,
                    "CompE": 1.0,
                    "CompF": 3.0,
                    "CompG": 5.0,
                    "CompH": 2.0,
                },
                {
                    "sample": "S3",
                    "CompA": 3.0,
                    "CompB": 3.0,
                    "CompC": 3.0,
                    "CompD": 3.0,
                    "CompE": 3.0,
                    "CompF": 3.0,
                    "CompG": 3.0,
                    "CompH": 3.0,
                },
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
            try:
                plot_stacked_barplot(spec, data, ax, palette, theme)
            finally:
                plt.close(fig)
        finally:
            tsv.unlink()
