"""Tests for abi.sciplot.schema.theme_spec — ThemeSpec from_yaml and to_matplotlib_rcparams."""

from __future__ import annotations

import pytest
import yaml

from abi.sciplot.schema.theme_spec import ThemeSpec


# ── from_yaml ────────────────────────────────────────────────────────────

def test_from_yaml_happy_path(tmp_path):
    """Load a ThemeSpec from a valid YAML file with all sections."""
    yaml_content = {
        "theme_name": "my_theme",
        "figure": {
            "width_single_column_mm": 90.0,
            "width_double_column_mm": 180.0,
            "default_width_mm": 90.0,
            "default_height_mm": 70.0,
            "dpi": 300,
        },
        "font": {
            "family": "DejaVu Sans",
            "base_size_pt": 8.0,
            "title_size_pt": 10.0,
            "label_size_pt": 8.0,
            "tick_size_pt": 7.0,
            "legend_size_pt": 7.0,
        },
        "axes": {
            "linewidth_pt": 0.8,
            "show_top_spine": False,
            "show_right_spine": False,
            "grid": True,
        },
        "lines": {
            "linewidth_pt": 1.0,
            "marker_size_pt": 4.0,
        },
        "legend": {
            "frame": True,
            "location": "upper right",
        },
        "export": {
            "raster_dpi": 600,
            "vector_formats": ["pdf", "svg"],
            "raster_formats": ["png", "tiff"],
        },
    }
    yaml_path = tmp_path / "theme.yaml"
    yaml_path.write_text(yaml.dump(yaml_content))

    theme = ThemeSpec.from_yaml(yaml_path)
    assert theme.theme_name == "my_theme"
    assert theme.figure.dpi == 300
    assert theme.font.family == "DejaVu Sans"
    assert theme.font.base_size_pt == 8.0
    assert theme.axes.grid is True
    assert theme.axes.linewidth_pt == 0.8
    assert theme.legend.frame is True
    assert theme.legend.location == "upper right"
    assert theme.lines.linewidth_pt == 1.0
    assert theme.lines.marker_size_pt == 4.0
    assert theme.export.raster_dpi == 600
    assert "pdf" in theme.export.vector_formats


def test_from_yaml_empty_file_raises_valueerror(tmp_path):
    """Empty YAML file → ValueError because data is None."""
    yaml_path = tmp_path / "empty.yaml"
    yaml_path.write_text("")  # Empty file

    with pytest.raises(ValueError, match="empty"):
        ThemeSpec.from_yaml(yaml_path)


def test_from_yaml_minimal_valid(tmp_path):
    """Minimal YAML with only theme_name is valid (defaults for everything else)."""
    yaml_path = tmp_path / "minimal.yaml"
    yaml_path.write_text(yaml.dump({"theme_name": "minimal"}))

    theme = ThemeSpec.from_yaml(yaml_path)
    assert theme.theme_name == "minimal"
    assert theme.figure.dpi == 300  # default
    assert theme.font.family == "DejaVu Sans"  # default


# ── to_matplotlib_rcparams ──────────────────────────────────────────────

def test_to_matplotlib_rcparams_full_dict():
    """Verify all expected rcParams keys and their values from a ThemeSpec."""
    theme = ThemeSpec(
        theme_name="test_rc",
        figure={
            "dpi": 300,
            "default_width_mm": 100.0,
            "default_height_mm": 80.0,
        },
        font={
            "family": "Arial",
            "base_size_pt": 10.0,
            "title_size_pt": 12.0,
            "label_size_pt": 10.0,
            "tick_size_pt": 8.0,
            "legend_size_pt": 9.0,
        },
        axes={
            "linewidth_pt": 1.2,
            "show_top_spine": True,
            "show_right_spine": True,
            "grid": True,
        },
        lines={
            "linewidth_pt": 1.5,
            "marker_size_pt": 5.0,
        },
        legend={
            "frame": True,
            "location": "upper left",
        },
    )

    rc = theme.to_matplotlib_rcparams()

    # Font
    assert rc["font.family"] == "Arial"
    assert rc["font.size"] == 10.0
    assert rc["axes.titlesize"] == 12.0
    assert rc["axes.labelsize"] == 10.0
    assert rc["xtick.labelsize"] == 8.0
    assert rc["ytick.labelsize"] == 8.0
    assert rc["legend.fontsize"] == 9.0

    # Axes
    assert rc["axes.linewidth"] == 1.2
    assert rc["axes.spines.top"] is True
    assert rc["axes.spines.right"] is True
    assert rc["axes.grid"] is True

    # Lines
    assert rc["lines.linewidth"] == 1.5
    assert rc["lines.markersize"] == 5.0

    # Legend
    assert rc["legend.frameon"] is True
    assert rc["legend.loc"] == "upper left"

    # Figure
    assert rc["figure.dpi"] == 300
    assert rc["savefig.dpi"] == 300  # from export defaults
    assert rc["savefig.bbox"] == "tight"


def test_to_matplotlib_rcparams_defaults():
    """Default ThemeSpec produces reasonable rcParams."""
    theme = ThemeSpec(theme_name="default_test")
    rc = theme.to_matplotlib_rcparams()
    assert rc["font.family"] == "DejaVu Sans"
    assert rc["font.size"] == 7.0
    assert rc["axes.spines.top"] is False
    assert rc["axes.spines.right"] is False
    assert rc["savefig.bbox"] == "tight"
