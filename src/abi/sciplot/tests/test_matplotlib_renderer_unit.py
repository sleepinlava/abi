"""Unit tests for MatplotlibRenderer.render() method.

Tests exercise the full render pipeline end-to-end for the P0 matplotlib
backend, including error paths (unsupported type, missing data) and happy
paths (barplot smoke, labels, hue/legend).
"""

from __future__ import annotations

import threading
from pathlib import Path
from unittest.mock import patch

import matplotlib

matplotlib.use("Agg")

import pandas as pd

from abi.sciplot.renderers import RenderResult
from abi.sciplot.renderers.matplotlib_renderer import MatplotlibRenderer
from abi.sciplot.renderers.plots import PLOT_FUNCTIONS
from abi.sciplot.schema.figure_spec import (
    DataSpec,
    ExportSpec,
    FigureSpec,
    LabelSpec,
    MappingSpec,
    StyleSpec,
)
from abi.sciplot.schema.palette_spec import PaletteRegistry
from abi.sciplot.schema.theme_spec import ThemeSpec

from .conftest import make_minimal_fig_spec

# ── Thread-local storage for capturing axes during render() ──────────────

_ax_store = threading.local()


def _capturing_barplot(spec, data, ax, palette, theme):
    """Barplot wrapper that captures the axes reference for assertions."""
    from abi.sciplot.renderers.plots.barplot import plot_barplot

    _ax_store.captured = ax
    return plot_barplot(spec, data, ax, palette, theme)


def _capturing_scatter(spec, data, ax, palette, theme):
    """Scatterplot wrapper that captures the axes reference for assertions."""
    from abi.sciplot.renderers.plots.scatterplot import plot_scatterplot

    _ax_store.captured = ax
    return plot_scatterplot(spec, data, ax, palette, theme)


# ── Helpers ──────────────────────────────────────────────────────────────


def _write_tsv(path: Path, rows: list[dict]) -> None:
    """Write a list of dicts as a TSV file."""
    df = pd.DataFrame(rows)
    df.to_csv(str(path), sep="\t", index=False)


def _build_spec(
    tmp_path: Path,
    figure_type: str,
    tsv_path: Path,
    *,
    mapping: MappingSpec | None = None,
    labels: LabelSpec | None = None,
    output_dir: str | None = None,
) -> FigureSpec:
    """Create a FigureSpec with a real data file."""
    return FigureSpec(
        figure_id=figure_type,
        figure_type=figure_type,
        data=DataSpec(table=tsv_path),
        mapping=mapping or MappingSpec(),
        labels=labels or LabelSpec(),
        style=StyleSpec(palette="colorblind_safe"),
        export=ExportSpec(
            output_dir=Path(output_dir) if output_dir else (tmp_path / "figures"),
            basename=figure_type,
            formats=["png"],
        ),
    )


# ── Tests ────────────────────────────────────────────────────────────────


class TestSupportsKnownTypes:
    """Test MatplotlibRenderer.supports() for known and unknown types."""

    def test_supports_known_types(self) -> None:
        renderer = MatplotlibRenderer()
        assert renderer.supports("barplot") is True
        assert renderer.supports("scatterplot") is True
        assert renderer.supports("unknown_type") is False


class TestInitDefaults:
    """Test MatplotlibRenderer initialisation defaults."""

    def test_init_defaults(self) -> None:
        renderer = MatplotlibRenderer()
        assert isinstance(renderer._palette_registry, PaletteRegistry)
        assert renderer._palette_registry.categorical_names, (
            "Expected builtin palettes to be loaded"
        )


class TestInitCustomTheme:
    """Test MatplotlibRenderer with a custom ThemeSpec."""

    def test_init_custom_theme(self) -> None:
        custom = ThemeSpec(theme_name="custom_test")
        renderer = MatplotlibRenderer(theme=custom)
        assert renderer._theme is custom


class TestRenderUnsupportedType:
    """Test render() gracefully handles an unsupported figure type."""

    def test_render_unsupported_type(self, tmp_path: Path) -> None:
        renderer = MatplotlibRenderer()
        # Create a valid-looking spec; we mock supports() to reject it.
        # barplot requires mapping.x or mapping.y (FigureSpec validator).
        spec = make_minimal_fig_spec(tmp_path, "barplot", mapping=MappingSpec(x="dummy"))
        with patch.object(renderer, "supports", return_value=False):
            result = renderer.render(spec)
        assert isinstance(result, RenderResult)
        assert result.errors, "Expected errors for unsupported type"
        assert "does not support" in result.errors[0].lower()


class TestRenderMissingDataFile:
    """Test render() returns errors when the data file does not exist."""

    def test_render_missing_data_file(self, tmp_path: Path) -> None:
        renderer = MatplotlibRenderer()
        nonexistent = tmp_path / "nonexistent.tsv"
        assert not nonexistent.exists()
        spec = FigureSpec(
            figure_id="missing_data",
            figure_type="barplot",
            data=DataSpec(table=nonexistent),
            mapping=MappingSpec(x="cat", y="val"),
            style=StyleSpec(palette="colorblind_safe"),
            export=ExportSpec(output_dir=tmp_path / "out", basename="missing"),
        )
        result = renderer.render(spec)
        assert isinstance(result, RenderResult)
        assert result.errors, "Expected errors for missing data file"


class TestRenderBarplotSmoke:
    """Smoke test: full render() pipeline with real barplot data."""

    def test_render_barplot_smoke(
        self, tmp_path: Path, palette: PaletteRegistry, theme: ThemeSpec
    ) -> None:
        tsv_path = tmp_path / "barplot_data.tsv"
        _write_tsv(
            tsv_path,
            [
                {"category": "A", "value": 10.0},
                {"category": "B", "value": 20.0},
                {"category": "C", "value": 15.0},
            ],
        )
        spec = _build_spec(
            tmp_path,
            "barplot",
            tsv_path,
            mapping=MappingSpec(x="category", y="value"),
        )

        renderer = MatplotlibRenderer(theme=theme, palette_registry=palette)
        result = renderer.render(spec)

        assert result.errors == [], f"Unexpected errors: {result.errors}"
        assert result.output_files, "Expected at least one output file"
        png_files = [p for p in result.output_files if p.suffix == ".png"]
        assert png_files, "Expected a PNG output file"
        assert png_files[0].exists(), f"PNG file not found: {png_files[0]}"


class TestRenderWithLabels:
    """Test render() applies labels (title, x_label, y_label) correctly."""

    def test_render_with_labels(
        self,
        tmp_path: Path,
        palette: PaletteRegistry,
        theme: ThemeSpec,
    ) -> None:
        tsv_path = tmp_path / "labelled_barplot.tsv"
        _write_tsv(
            tsv_path,
            [
                {"category": "Alpha", "value": 5.0},
                {"category": "Beta", "value": 12.0},
                {"category": "Gamma", "value": 8.0},
            ],
        )
        spec = _build_spec(
            tmp_path,
            "barplot",
            tsv_path,
            mapping=MappingSpec(x="category", y="value"),
            labels=LabelSpec(
                title="Unit Test Title",
                x_label="Category Axis",
                y_label="Value Axis",
            ),
        )

        patched = dict(PLOT_FUNCTIONS)
        patched["barplot"] = _capturing_barplot

        with patch("abi.sciplot.renderers.matplotlib_renderer.PLOT_FUNCTIONS", patched):
            renderer = MatplotlibRenderer(theme=theme, palette_registry=palette)
            result = renderer.render(spec)

        assert result.errors == [], f"Unexpected errors: {result.errors}"
        ax = _ax_store.captured
        assert ax is not None, "Axes not captured"
        assert ax.get_title() == "Unit Test Title", (
            f"Expected 'Unit Test Title', got '{ax.get_title()}'"
        )
        assert ax.get_xlabel() == "Category Axis", (
            f"Expected 'Category Axis', got '{ax.get_xlabel()}'"
        )
        assert ax.get_ylabel() == "Value Axis", f"Expected 'Value Axis', got '{ax.get_ylabel()}'"


class TestRenderWithHue:
    """Test render() with a scatterplot that has a hue mapping."""

    def test_render_with_hue(
        self,
        tmp_path: Path,
        palette: PaletteRegistry,
        theme: ThemeSpec,
    ) -> None:
        tsv_path = tmp_path / "hue_scatter.tsv"
        _write_tsv(
            tsv_path,
            [
                {"x": 1.0, "y": 2.0, "group": "Control"},
                {"x": 3.0, "y": 4.0, "group": "Treatment"},
                {"x": 5.0, "y": 6.0, "group": "Control"},
            ],
        )
        spec = _build_spec(
            tmp_path,
            "scatterplot",
            tsv_path,
            mapping=MappingSpec(x="x", y="y", hue="group"),
        )

        patched = dict(PLOT_FUNCTIONS)
        patched["scatterplot"] = _capturing_scatter

        with patch("abi.sciplot.renderers.matplotlib_renderer.PLOT_FUNCTIONS", patched):
            renderer = MatplotlibRenderer(theme=theme, palette_registry=palette)
            result = renderer.render(spec)

        assert result.errors == [], f"Unexpected errors: {result.errors}"
        ax = _ax_store.captured
        assert ax is not None, "Axes not captured"
        assert ax.get_legend() is not None, "Expected a legend when hue is used"
