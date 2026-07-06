"""Additional tests for abi.sciplot.adapters covering uncovered lines.

Covers: _map_type unknown type, figsize edge case, continuous palette fallback,
volcano_plot stat spec, and adapt_all_specs.
"""

from __future__ import annotations

import io
import sys
from pathlib import Path

import pytest

from abi.sciplot.adapters import (
    _map_type,
    adapt_all_specs,
    adapt_spec,
)
from abi.sciplot.schema.figure_spec import SUPPORTED_FIGURE_TYPES


# -- _map_type -------------------------------------------------------------

def test_map_type_maps_legacy_types():
    assert _map_type("bar") == "barplot"
    assert _map_type("scatter") == "scatterplot"
    assert _map_type("volcano") == "volcano_plot"
    assert _map_type("heatmap") == "heatmap"
    assert _map_type("boxplot") == "boxplot_with_points"
    assert _map_type("stacked_bar") == "stacked_barplot"


def test_map_type_passthrough_known_sciplot_types():
    """Already-valid sciplot types are returned as-is."""
    for t in SUPPORTED_FIGURE_TYPES:
        assert _map_type(t) == t


def test_map_type_unknown_raises_valueerror():
    """Unknown type raises ValueError with helpful message."""
    with pytest.raises(ValueError, match="Unknown figure type"):
        _map_type("totally_made_up_type")


# -- adapt_spec: figsize fallback -----------------------------------------

def test_adapt_spec_figsize_not_2_element_fallback(tmp_path):
    """Non-2-element figsize leads to fallback 90x70 mm."""
    spec = adapt_spec(
        {
            "id": "test_fig",
            "type": "bar",
            "source_table": "metrics",
            "x": "x",
            "y": "y",
            "figsize": "not_a_tuple",
        },
        tables_dir=tmp_path,
        figures_dir=tmp_path / "figures",
    )
    assert spec.style.width_mm == 90.0
    assert spec.style.height_mm == 70.0


def test_adapt_spec_figsize_empty_list_fallback(tmp_path):
    """Empty list figsize leads to fallback 90x70 mm."""
    spec = adapt_spec(
        {
            "id": "test_fig",
            "type": "bar",
            "source_table": "metrics",
            "x": "x",
            "y": "y",
            "figsize": [],
        },
        tables_dir=tmp_path,
        figures_dir=tmp_path / "figures",
    )
    assert spec.style.width_mm == 90.0
    assert spec.style.height_mm == 70.0


def test_adapt_spec_figsize_3_element_fallback(tmp_path):
    """3-element figsize leads to fallback 90x70 mm."""
    spec = adapt_spec(
        {
            "id": "test_fig",
            "type": "bar",
            "source_table": "metrics",
            "x": "x",
            "y": "y",
            "figsize": (1, 2, 3),
        },
        tables_dir=tmp_path,
        figures_dir=tmp_path / "figures",
    )
    assert spec.style.width_mm == 90.0
    assert spec.style.height_mm == 70.0


# -- adapt_spec: continuous palette fallback ------------------------------

def test_adapt_spec_continuous_palette_fallback(tmp_path):
    """Non-categorical, non-diverging colormap - continuous palette path."""
    spec = adapt_spec(
        {
            "id": "heat",
            "type": "heatmap",
            "source_table": "expr",
            "x": "gene",
            "colormap": "inferno",
        },
        tables_dir=tmp_path,
        figures_dir=tmp_path / "figures",
    )
    assert spec.style.palette == "inferno"


def test_adapt_spec_continuous_palette_unknown_fallback(tmp_path):
    """Unknown colormap outside aliases - viridis fallback."""
    spec = adapt_spec(
        {
            "id": "heat",
            "type": "heatmap",
            "source_table": "expr",
            "x": "gene",
            "colormap": "some_unknown_cmap",
        },
        tables_dir=tmp_path,
        figures_dir=tmp_path / "figures",
    )
    assert spec.style.palette == "viridis"


def test_adapt_spec_continuous_reds_aliased_to_magma(tmp_path):
    """'Reds' in CONTINUOUS_PALETTE_ALIASES - mapped to magma."""
    spec = adapt_spec(
        {
            "id": "heat",
            "type": "heatmap",
            "source_table": "expr",
            "x": "gene",
            "colormap": "Reds",
        },
        tables_dir=tmp_path,
        figures_dir=tmp_path / "figures",
    )
    assert spec.style.palette == "magma"


# -- adapt_spec: volcano_plot stat spec -----------------------------------

def test_adapt_spec_volcano_plot_stat_spec(tmp_path):
    """Volcano plot creates a StatSpec from old_spec fields."""
    spec = adapt_spec(
        {
            "id": "volcano_fig",
            "type": "volcano",
            "source_table": "de_results",
            "x": "log2FoldChange",
            "y": "padj",
        },
        tables_dir=tmp_path,
        figures_dir=tmp_path / "figures",
    )
    assert spec.statistics is not None
    assert spec.statistics.test == "Wald test"
    assert spec.statistics.correction == "Benjamini-Hochberg"
    assert spec.statistics.pvalue_column == "padj"
    assert spec.statistics.fold_change_column == "log2FoldChange"


def test_adapt_spec_non_volcano_no_stat_spec(tmp_path):
    """Non-volcano plot types do not create a StatSpec."""
    spec = adapt_spec(
        {
            "id": "bar_fig",
            "type": "bar",
            "source_table": "data",
            "x": "group",
            "y": "value",
        },
        tables_dir=tmp_path,
        figures_dir=tmp_path / "figures",
    )
    assert spec.statistics is None


# -- adapt_all_specs ------------------------------------------------------

def test_adapt_all_specs_happy_path(tmp_path):
    """adapt_all_specs converts a list of valid specs."""
    old_specs = [
        {"id": "fig1", "type": "bar", "source_table": "t", "x": "x", "y": "y"},
        {"id": "fig2", "type": "scatter", "source_table": "t", "x": "x", "y": "y"},
    ]
    new_specs = adapt_all_specs(old_specs, tmp_path, tmp_path / "figures")
    assert len(new_specs) == 2
    assert new_specs[0].figure_id == "fig1"
    assert new_specs[1].figure_id == "fig2"


def test_adapt_all_specs_skips_bad_spec(tmp_path):
    """One bad spec is skipped with stderr output; good specs still adapt."""
    old_specs = [
        {"id": "good1", "type": "bar", "source_table": "t", "x": "x", "y": "y"},
        {"id": "bad1", "type": "INVALID_TYPE", "source_table": "t"},
        {"id": "good2", "type": "scatter", "source_table": "t", "x": "x", "y": "y"},
    ]

    # Capture stderr to verify the skip message
    captured_err = io.StringIO()
    saved_stderr = sys.stderr
    sys.stderr = captured_err
    try:
        new_specs = adapt_all_specs(old_specs, tmp_path, tmp_path / "figures")
    finally:
        sys.stderr = saved_stderr

    assert len(new_specs) == 2
    assert new_specs[0].figure_id == "good1"
    assert new_specs[1].figure_id == "good2"

    err_output = captured_err.getvalue()
    assert "Skipping figure" in err_output
    assert "bad1" in err_output


def test_adapt_all_specs_empty_list(tmp_path):
    """Empty input yields empty output."""
    assert adapt_all_specs([], tmp_path, tmp_path / "figures") == []
