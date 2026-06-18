"""CLI for abi_sciplot — publication-grade scientific figure compiler.

Commands:
    validate    Check a FigureSpec for structural and data errors.
    render      Render a FigureSpec to publication-grade output files.
    lint        Run publication-quality checks on a rendered figure.
    list-plot-types   List supported figure types.
"""

from __future__ import annotations

import json as _json
from pathlib import Path
from typing import Optional

import typer

app = typer.Typer(
    name="abi-sciplot",
    help="ABI Scientific Figure Compiler — validate, render, lint, export.",
    no_args_is_help=True,
)


@app.command("validate")
def validate_spec(
    spec_path: str = typer.Option(
        ..., "--spec", "-s", help="Path to FigureSpec YAML or JSON file."
    ),
) -> None:
    """Validate a FigureSpec file for structural and data errors."""
    from abi.sciplot.api import load_spec
    from abi.sciplot.api import validate_spec as _validate

    try:
        spec = load_spec(spec_path)
    except Exception as exc:
        result = {
            "status": "error",
            "figure_id": None,
            "errors": [str(exc)],
            "warnings": [],
        }
        typer.echo(_json.dumps(result, indent=2, ensure_ascii=False))
        raise typer.Exit(code=1)

    result = _validate(spec)
    typer.echo(_json.dumps(result, indent=2, ensure_ascii=False))
    if result["status"] == "error":
        raise typer.Exit(code=1)


@app.command("render")
def render_figure(
    spec_path: str = typer.Option(
        ..., "--spec", "-s", help="Path to FigureSpec YAML or JSON file."
    ),
    output_dir: Optional[str] = typer.Option(
        None, "--output-dir", "-o", help="Override output directory."
    ),
    strict: bool = typer.Option(
        False, "--strict", help="Fail on lint WARNINGs in addition to ERRORs."
    ),
) -> None:
    """Render a FigureSpec to publication-grade figure files."""
    from abi.sciplot.api import load_spec
    from abi.sciplot.api import render_figure as _render

    try:
        spec = load_spec(spec_path)
    except Exception as exc:
        typer.echo(
            _json.dumps(
                {
                    "status": "error",
                    "figure_id": None,
                    "errors": [str(exc)],
                    "warnings": [],
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        raise typer.Exit(code=1)

    if output_dir:
        spec.export.output_dir = Path(output_dir)

    result = _render(spec)
    d = result.to_dict()

    if strict and result.warnings:
        d["status"] = "error"
        d["errors"] = d.get("errors", []) + result.warnings

    typer.echo(_json.dumps(d, indent=2, ensure_ascii=False))
    if d["status"] == "error":
        raise typer.Exit(code=1)


@app.command("lint")
def lint_figure(
    spec_path: str = typer.Option(
        ..., "--spec", "-s", help="Path to FigureSpec YAML or JSON file."
    ),
    figure_path: Optional[str] = typer.Option(
        None, "--figure", "-f", help="Path to a rendered figure file to check."
    ),
) -> None:
    """Run FigureLint rules on a FigureSpec and optionally its output files."""
    from abi.sciplot.api import lint_figure as _lint
    from abi.sciplot.api import load_spec

    try:
        spec = load_spec(spec_path)
    except Exception as exc:
        typer.echo(
            _json.dumps(
                {
                    "status": "error",
                    "figure_id": None,
                    "errors": [str(exc)],
                    "warnings": [],
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        raise typer.Exit(code=1)

    output_files = [Path(figure_path)] if figure_path else []
    report = _lint(spec, output_files)
    typer.echo(_json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
    if report.errors:
        raise typer.Exit(code=1)


@app.command("list-plot-types")
def list_plot_types() -> None:
    """List all supported figure types."""
    from abi.sciplot.api import list_plot_types as _list

    result = {"supported_plot_types": _list()}
    typer.echo(_json.dumps(result, indent=2, ensure_ascii=False))


def main() -> None:
    """Entry point for ``abi-sciplot`` console script."""
    app()


if __name__ == "__main__":
    main()
