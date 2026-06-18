"""Schema definitions for abi_sciplot.

Public types:
    FigureSpec, DataSpec, MappingSpec, StatSpec, SignificanceRule,
    StyleSpec, LabelSpec, ExportSpec, ProvenanceSpec,
    ThemeSpec, FontSpec, AxesSpec, FigureDims, LegendSpec, LinesSpec,
    PaletteSpec, CategoricalPalette, ContinuousPalette, DivergingPalette
"""

from abi.sciplot.schema.figure_spec import (
    SUPPORTED_FIGURE_TYPES,
    DataSpec,
    ExportSpec,
    FigureSpec,
    LabelSpec,
    MappingSpec,
    ProvenanceSpec,
    SignificanceRule,
    StatSpec,
    StyleSpec,
)
from abi.sciplot.schema.palette_spec import (
    CategoricalPalette,
    ContinuousPalette,
    DivergingPalette,
    PaletteRegistry,
    PaletteSpec,
)
from abi.sciplot.schema.theme_spec import (
    AxesSpec,
    ExportThemeSpec,
    FigureDims,
    FontSpec,
    LegendSpec,
    LinesSpec,
    ThemeSpec,
)

__all__ = [
    # Figure spec
    "FigureSpec",
    "DataSpec",
    "MappingSpec",
    "StatSpec",
    "SignificanceRule",
    "StyleSpec",
    "LabelSpec",
    "ExportSpec",
    "ProvenanceSpec",
    "SUPPORTED_FIGURE_TYPES",
    # Theme spec
    "ThemeSpec",
    "FontSpec",
    "FigureDims",
    "AxesSpec",
    "LegendSpec",
    "LinesSpec",
    "ExportThemeSpec",
    # Palette spec
    "PaletteSpec",
    "PaletteRegistry",
    "CategoricalPalette",
    "ContinuousPalette",
    "DivergingPalette",
]
