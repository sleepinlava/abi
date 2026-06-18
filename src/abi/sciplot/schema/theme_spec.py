"""ThemeSpec — publication-ready figure styling.

Three built-in themes:
- abi_nature: Compact, single/double-column manuscript figures. 7pt base font.
- abi_cell: Multi-panel mechanism figures with larger labels and panel markers.
- abi_report: HTML/PDF report figures optimized for screen readability.

Theme YAML files are loaded and converted to matplotlib rcParams at render time.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field


class FontSpec(BaseModel):
    """Font configuration for a theme."""

    family: str = Field("Arial", description="Primary font family.")
    fallback: list[str] = Field(
        default_factory=lambda: ["Helvetica", "DejaVu Sans"],
        description="Fallback font families in priority order.",
    )
    base_size_pt: float = Field(7.0, ge=4.0, le=24.0, description="Base font size in points.")
    title_size_pt: float = Field(8.0, ge=4.0, le=32.0, description="Title font size.")
    label_size_pt: float = Field(7.0, ge=4.0, le=24.0, description="Axis label font size.")
    tick_size_pt: float = Field(6.0, ge=4.0, le=24.0, description="Tick label font size.")
    legend_size_pt: float = Field(6.0, ge=4.0, le=24.0, description="Legend font size.")


class FigureDims(BaseModel):
    """Default figure dimensions."""

    width_single_column_mm: float = Field(90.0, description="Single-column width in mm.")
    width_double_column_mm: float = Field(180.0, description="Double-column width in mm.")
    default_width_mm: float = Field(90.0, description="Default width in mm.")
    default_height_mm: float = Field(70.0, description="Default height in mm.")
    dpi: int = Field(300, description="Default DPI.")


class AxesSpec(BaseModel):
    """Axes styling."""

    linewidth_pt: float = Field(0.6, ge=0.2, description="Axis spine line width.")
    show_top_spine: bool = Field(False, description="Show top spine.")
    show_right_spine: bool = Field(False, description="Show right spine.")
    grid: bool = Field(False, description="Show grid lines.")


class LegendSpec(BaseModel):
    """Legend styling."""

    frame: bool = Field(False, description="Draw a frame around the legend.")
    location: str = Field("best", description="Legend location.")


class LinesSpec(BaseModel):
    """Line and marker styling."""

    linewidth_pt: float = Field(0.8, ge=0.2, description="Line width.")
    marker_size_pt: float = Field(3.0, ge=1.0, description="Marker size.")


class ExportThemeSpec(BaseModel):
    """Export-related theme settings."""

    raster_dpi: int = Field(300, description="DPI for raster exports.")
    vector_formats: list[str] = Field(
        default_factory=lambda: ["pdf", "svg"], description="Recommended vector formats."
    )
    raster_formats: list[str] = Field(
        default_factory=lambda: ["png", "tiff"], description="Recommended raster formats."
    )


class ThemeSpec(BaseModel):
    """Complete theme specification.

    Loaded from YAML files in the themes/ directory.
    """

    theme_name: str = Field(..., description="Unique theme identifier.")
    figure: FigureDims = Field(default_factory=lambda: FigureDims())
    font: FontSpec = Field(default_factory=lambda: FontSpec())
    axes: AxesSpec = Field(default_factory=lambda: AxesSpec())
    lines: LinesSpec = Field(default_factory=lambda: LinesSpec())
    legend: LegendSpec = Field(default_factory=lambda: LegendSpec())
    export: ExportThemeSpec = Field(default_factory=lambda: ExportThemeSpec())

    # ── Factory methods / 工厂方法 ──────────────────────────────────────

    @classmethod
    def from_yaml(cls, path: str | Path) -> "ThemeSpec":
        """Load a ThemeSpec from a YAML file."""
        with open(path, "r") as fh:
            data = yaml.safe_load(fh)
        if data is None:
            raise ValueError(f"Theme YAML at {path} is empty.")
        return cls(**data)

    # ── Conversion / 转换 ───────────────────────────────────────────────

    def to_matplotlib_rcparams(self) -> dict:
        """Convert this theme to matplotlib rcParams dict.

        Used by MatplotlibRenderer before creating figures so all plot
        functions inherit the theme automatically via plt.style.context().
        """
        return {
            # Font
            "font.family": self.font.family,
            "font.size": self.font.base_size_pt,
            "axes.titlesize": self.font.title_size_pt,
            "axes.labelsize": self.font.label_size_pt,
            "xtick.labelsize": self.font.tick_size_pt,
            "ytick.labelsize": self.font.tick_size_pt,
            "legend.fontsize": self.font.legend_size_pt,
            # Axes
            "axes.linewidth": self.axes.linewidth_pt,
            "axes.spines.top": self.axes.show_top_spine,
            "axes.spines.right": self.axes.show_right_spine,
            "axes.grid": self.axes.grid,
            # Lines
            "lines.linewidth": self.lines.linewidth_pt,
            "lines.markersize": self.lines.marker_size_pt,
            # Legend
            "legend.frameon": self.legend.frame,
            "legend.loc": self.legend.location,
            # Figure
            "figure.dpi": self.figure.dpi,
            "savefig.dpi": self.export.raster_dpi,
            "savefig.bbox": "tight",
        }
