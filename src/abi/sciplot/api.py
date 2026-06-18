"""Public API for abi_sciplot.

The API is the stable interface for both Python callers and ABI tool contracts.
It wraps schema validation, rendering, linting, and provenance in one call site.

Usage:
    from abi.sciplot import load_spec, validate_spec, render_figure, lint_figure

    spec = load_spec("figure.yaml")
    errors = validate_spec(spec)
    if errors:
        print(errors)
    result = render_figure(spec)
    print(result.to_dict())
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from abi.sciplot.lint import LintReport
from abi.sciplot.lint import lint_figure as _run_lint
from abi.sciplot.renderers import RenderResult
from abi.sciplot.renderers.matplotlib_renderer import MatplotlibRenderer
from abi.sciplot.schema.figure_spec import FigureSpec


def load_spec(path: str | Path) -> FigureSpec:
    """Load a FigureSpec from a YAML or JSON file.

    Args:
        path: Path to a .yaml, .yml, or .json file.

    Returns:
        A validated FigureSpec Pydantic model.

    Raises:
        FileNotFoundError: If the path does not exist.
        ValueError: If the file cannot be parsed or validated.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Figure spec not found: {path}")

    with open(path, "r", encoding="utf-8") as fh:
        if path.suffix in (".json",):
            data = json.load(fh)
        else:
            data = yaml.safe_load(fh)

    if data is None:
        raise ValueError(f"Figure spec file is empty: {path}")

    return FigureSpec(**data)


def validate_spec(spec: FigureSpec) -> Dict[str, Any]:
    """Validate a FigureSpec against all validation rules.

    Returns a dict with keys: status, errors, warnings.
    """
    errors: List[str] = []
    warnings: List[str] = []

    # Schema validation is handled by Pydantic at construction time.
    # Here we do data validation.
    from abi.sciplot.validators import validate_data

    report = validate_data(spec)
    for e in report.errors:
        errors.append(f"[{e.rule}] {e.message}")
    for w in report.warnings:
        warnings.append(f"[{w.rule}] {w.message}")

    return {
        "status": "ok" if not errors else "error",
        "figure_id": spec.figure_id,
        "errors": errors,
        "warnings": warnings,
    }


def render_figure(spec: FigureSpec) -> RenderResult:
    """Render a figure from a validated FigureSpec.

    This is the main entry point for programmatic rendering.
    Returns a RenderResult with output file paths, lint, and provenance.

    Args:
        spec: A validated FigureSpec.

    Returns:
        RenderResult with output_files, lint_report_path, provenance_path.
    """
    renderer = MatplotlibRenderer()
    return renderer.render(spec)


def lint_figure(
    spec: FigureSpec,
    output_files: Optional[List[Path]] = None,
    provenance_path: Optional[Path] = None,
) -> LintReport:
    """Run all FigureLint rules against a spec and its outputs.

    Args:
        spec: The FigureSpec used for rendering.
        output_files: Paths to rendered output files.
        provenance_path: Path to the provenance.json file.

    Returns:
        LintReport with errors, warnings, and info findings.
    """
    return _run_lint(spec, output_files or [], provenance_path)


def list_plot_types() -> List[str]:
    """Return the list of supported figure types."""
    from abi.sciplot.schema.figure_spec import SUPPORTED_FIGURE_TYPES

    return sorted(SUPPORTED_FIGURE_TYPES)
