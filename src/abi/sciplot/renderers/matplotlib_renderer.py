"""Matplotlib renderer — the primary P0 rendering backend.

Imports matplotlib lazily so the import cost is only paid when a figure
is actually rendered.  Uses ThemeSpec → rcParams for consistent styling.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import pandas as pd

from abi.sciplot.renderers import BaseRenderer, RenderResult
from abi.sciplot.renderers.plots import PLOT_FUNCTIONS
from abi.sciplot.schema.figure_spec import FigureSpec
from abi.sciplot.schema.palette_spec import PaletteRegistry
from abi.sciplot.schema.theme_spec import ThemeSpec
from abi.sciplot.validators import validate_data


class MatplotlibRenderer(BaseRenderer):
    """Render FigureSpecs into publication-grade matplotlib figures.

    Supported figure types: boxplot_with_points, violin_with_box,
    scatterplot, ordination_plot, stacked_barplot, heatmap, volcano_plot,
    lineplot.

    Lifecycle for each render() call:
        1. Apply theme via matplotlib rcParams
        2. Validate and load the input data table
        3. Dispatch to the appropriate plot function
        4. Export to all requested formats (PDF/SVG/PNG/TIFF)
        5. Write provenance.json
        6. Run FigureLint
        7. Return RenderResult
    """

    SUPPORTED_TYPES = frozenset(
        {
            "barplot",
            "boxplot_with_points",
            "violin_with_box",
            "scatterplot",
            "ordination_plot",
            "stacked_barplot",
            "heatmap",
            "volcano_plot",
            "lineplot",
            # Biological-grade plot types (v1.4.0)
            "phylum_stacked_bar",
            "genus_heatmap",
            "pcoa_plot",
            "differential_volcano",
            "alpha_stats_boxplot",
            "phylogenetic_heatmap",
        }
    )

    def __init__(
        self,
        theme: Optional[ThemeSpec] = None,
        palette_registry: Optional[PaletteRegistry] = None,
    ) -> None:
        self._theme = theme
        self._palette_registry = palette_registry or PaletteRegistry()
        if not self._palette_registry.categorical_names:
            self._palette_registry.load_builtins()

    def supports(self, figure_type: str) -> bool:
        return figure_type in self.SUPPORTED_TYPES

    def render(self, spec: FigureSpec) -> RenderResult:
        """Render a FigureSpec and return structured results."""
        errors: list[str] = []
        warnings: list[str] = []

        # 1. Validate figure type
        if not self.supports(spec.figure_type):
            return RenderResult(
                figure_id=spec.figure_id,
                errors=[
                    f"MatplotlibRenderer does not support figure_type '{spec.figure_type}'. "
                    f"Supported: {sorted(self.SUPPORTED_TYPES)}"
                ],
            )

        # 2. Validate data
        data_report = validate_data(spec)
        if not data_report.is_valid:
            return RenderResult(
                figure_id=spec.figure_id,
                errors=[e.message for e in data_report.errors],
                warnings=[w.message for w in data_report.warnings],
            )
        for w in data_report.warnings:
            warnings.append(w.message)

        # 3. Load data
        df = pd.read_csv(spec.data.table, sep="\t" if spec.data.format == "tsv" else ",")

        # 4. Apply theme and render
        try:
            import matplotlib

            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
        except ImportError as exc:
            return RenderResult(
                figure_id=spec.figure_id,
                errors=[f"Cannot import matplotlib: {exc}"],
            )

        # Load theme
        theme = self._theme
        if theme is None:
            from abi.sciplot.schema.theme_spec import ThemeSpec

            theme = ThemeSpec(theme_name=spec.style.theme)

        rcparams = theme.to_matplotlib_rcparams()
        figsize = spec.style.figsize_inches

        try:
            with plt.style.context(rcparams):
                fig, ax = plt.subplots(figsize=figsize, dpi=spec.style.dpi)

                # Dispatch to plot function
                plot_fn = PLOT_FUNCTIONS.get(spec.figure_type)
                if plot_fn is None:
                    return RenderResult(
                        figure_id=spec.figure_id,
                        errors=[f"No plot function for '{spec.figure_type}'"],
                    )

                plot_fn(spec, df, ax, self._palette_registry, theme)

                # Apply labels
                if spec.labels.title:
                    ax.set_title(spec.labels.title)
                if spec.labels.x_label:
                    ax.set_xlabel(spec.labels.x_label)
                elif spec.mapping.x:
                    ax.set_xlabel(spec.mapping.x)
                if spec.labels.y_label:
                    ax.set_ylabel(spec.labels.y_label)
                elif spec.mapping.y:
                    ax.set_ylabel(spec.mapping.y)
                legend = ax.get_legend()
                if spec.labels.legend_title and legend:
                    legend.set_title(spec.labels.legend_title)

                fig.tight_layout()

                # 5. Export
                output_dir = spec.export.output_dir
                output_dir.mkdir(parents=True, exist_ok=True)
                output_files: list[Path] = []

                for fmt in spec.export.formats:
                    out_path = output_dir / f"{spec.export.basename}.{fmt}"
                    if fmt in ("pdf", "svg"):
                        fig.savefig(
                            out_path,
                            format=fmt,
                            bbox_inches="tight",
                            transparent=spec.export.transparent,
                        )
                    else:
                        fig.savefig(
                            out_path,
                            format=fmt,
                            dpi=spec.style.dpi,
                            bbox_inches="tight",
                            transparent=spec.export.transparent,
                        )
                    output_files.append(out_path)

                plt.close(fig)

        except Exception as exc:
            return RenderResult(
                figure_id=spec.figure_id,
                errors=[f"Render error: {exc}"],
                warnings=warnings,
            )

        # 6. Write provenance
        from abi.sciplot.provenance import write_provenance

        provenance_path = write_provenance(spec, output_dir)

        # 7. Run lint
        from abi.sciplot.lint import lint_figure as run_lint

        lint_report = run_lint(spec, output_files, provenance_path)
        for le in lint_report.errors:
            errors.append(f"[{le.rule}] {le.message}")
        for lw in lint_report.warnings:
            warnings.append(f"[{lw.rule}] {lw.message}")

        # Write lint report
        lint_path = output_dir / f"{spec.export.basename}.lint.json"
        lint_path.write_text(
            json.dumps(lint_report.to_dict(), indent=2),
            encoding="utf-8",
        )

        return RenderResult(
            figure_id=spec.figure_id,
            output_files=output_files,
            lint_report_path=lint_path,
            provenance_path=provenance_path,
            errors=errors,
            warnings=warnings,
        )
