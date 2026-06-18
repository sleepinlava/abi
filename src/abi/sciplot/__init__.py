"""abi_sciplot — ABI Scientific Figure Compiler.

A publication-grade scientific figure rendering system for ABI workflows.
Agent describes the figure; abi_sciplot validates, renders, exports, lints,
and records provenance.

Core protocol: FigureSpec -> Validate -> Render -> Export -> Lint -> Provenance

# Public API

    from abi.sciplot import load_spec, validate_spec, render_figure, lint_figure

# CLI

    abi-sciplot validate --spec figure.yaml
    abi-sciplot render --spec figure.yaml
    abi-sciplot lint --spec figure.yaml
    abi-sciplot list-plot-types
"""

from __future__ import annotations

from abi.sciplot.api import (
    lint_figure,
    list_plot_types,
    load_spec,
    render_figure,
    validate_spec,
)
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

__all__ = [
    # API
    "load_spec",
    "validate_spec",
    "render_figure",
    "lint_figure",
    "list_plot_types",
    # Schema
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
]

__version__ = "0.1.0"
