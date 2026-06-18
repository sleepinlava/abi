"""Adapter: converts old-format FigureSpec (dataclass) → abi_sciplot FigureSpec (Pydantic).

This module bridges the legacy `FigureEngine` figure declaration schema (flat,
dataclass-based) to the new `abi_sciplot` protocol (nested, Pydantic-based).

Usage:
    from abi.sciplot.adapters import adapt_spec

    old_spec = {"id": "qc_reads", "type": "bar", "source_table": "qc_summary", ...}
    new_spec = adapt_spec(old_spec, tables_dir, figures_dir)
    result = render_figure(new_spec)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Optional

from abi.sciplot.schema.figure_spec import (
    DataSpec,
    ExportSpec,
    FigureSpec,
    LabelSpec,
    MappingSpec,
    ProvenanceSpec,
    StatSpec,
    StyleSpec,
)

# ── Type mapping / 类型映射 ──────────────────────────────────────────────

# Old FigureEngine types → abi_sciplot types
TYPE_MAP: dict[str, str] = {
    "bar": "barplot",
    "scatter": "scatterplot",
    "volcano": "volcano_plot",
    "heatmap": "heatmap",
    "boxplot": "boxplot_with_points",
    "stacked_bar": "stacked_barplot",
    "pca": "ordination_plot",
}


def _map_type(old_type: str) -> str:
    """Map an old FigureEngine figure type to an abi_sciplot figure type."""
    mapped = TYPE_MAP.get(old_type)
    if mapped is None:
        raise ValueError(
            f"Unknown legacy figure type '{old_type}'. Known types: {sorted(TYPE_MAP.keys())}"
        )
    return mapped


# ── Main adapter / 主转换器 ──────────────────────────────────────────────


def adapt_spec(
    old_spec: Mapping[str, Any],
    tables_dir: Path,
    figures_dir: Path,
    *,
    plugin_name: Optional[str] = None,
    abi_version: Optional[str] = None,
) -> FigureSpec:
    """Convert a legacy FigureEngine figure spec dict to an abi_sciplot FigureSpec.

    Args:
        old_spec: Legacy flat dict with keys like id, type, source_table, x, y, etc.
        tables_dir: Directory where TSV table files live.
        figures_dir: Directory where output figures should be written.
        plugin_name: Optional workflow name for provenance.
        abi_version: Optional ABI version for provenance.

    Returns:
        A validated abi_sciplot FigureSpec ready for rendering.
    """
    figure_type = _map_type(old_spec["type"])

    # ── Data ──
    source_table = old_spec.get("source_table", "")
    required_columns: list[str] = []
    for key in ("x", "y", "label", "color", "group"):
        if key in old_spec and old_spec[key]:
            required_columns.append(old_spec[key])

    data = DataSpec(
        table=tables_dir / f"{source_table}.tsv",
        format="tsv",
        required_columns=required_columns,
    )

    # ── Mapping ──
    mapping = MappingSpec(
        x=old_spec.get("x", ""),
        y=old_spec.get("y", ""),
        hue=old_spec.get("color", ""),
        label=old_spec.get("label", ""),
        group=old_spec.get("group", ""),
    )

    # ── Style ──
    figsize = old_spec.get("figsize", (10.0, 6.0))
    if isinstance(figsize, (list, tuple)) and len(figsize) == 2:
        width_mm = figsize[0] * 25.4
        height_mm = figsize[1] * 25.4
    else:
        width_mm, height_mm = 90.0, 70.0

    colormap = old_spec.get("colormap", "viridis")
    # colormap names like RdBu_r, tab20, Reds — these are safe
    palette_name = colormap if colormap not in ("jet", "rainbow") else "viridis"

    style = StyleSpec(
        theme="abi_nature",
        palette=palette_name,
        width_mm=round(width_mm, 1),
        height_mm=round(height_mm, 1),
        dpi=old_spec.get("dpi", 300),
    )

    # ── Labels ──
    labels = LabelSpec(
        title=old_spec.get("title", ""),
        x_label=old_spec.get("xlabel", ""),
        y_label=old_spec.get("ylabel", ""),
    )

    # ── Statistics (best-effort from volcano plots) ──
    statistics = None
    if figure_type == "volcano_plot":
        statistics = StatSpec(
            test="Wald test",
            correction="Benjamini-Hochberg",
            pvalue_column=old_spec.get("y", "padj"),
            fold_change_column=old_spec.get("x", "log2FoldChange"),
        )

    # ── Export ──
    spec_id = old_spec["id"]
    export = ExportSpec(
        output_dir=figures_dir / spec_id,
        basename=spec_id,
        formats=["pdf", "svg", "png"],
        transparent=False,
    )

    # ── Provenance ──
    provenance = ProvenanceSpec(
        workflow_name=plugin_name or "",
        abi_version=abi_version or "",
        input_data_role=source_table,
    )

    return FigureSpec(
        figure_id=spec_id,
        figure_type=figure_type,
        data=data,
        mapping=mapping,
        statistics=statistics,
        style=style,
        labels=labels,
        export=export,
        provenance=provenance,
    )


def adapt_all_specs(
    old_specs: list[dict[str, Any]],
    tables_dir: Path,
    figures_dir: Path,
    **kwargs: Any,
) -> list[FigureSpec]:
    """Convert a list of legacy figure specs to abi_sciplot FigureSpecs.

    Returns only successfully-adapted specs.  Adaptation errors are logged
    to stderr and the offending spec is skipped.
    """
    from sys import stderr

    new_specs: list[FigureSpec] = []
    for old in old_specs:
        try:
            new_specs.append(adapt_spec(old, tables_dir, figures_dir, **kwargs))
        except Exception as exc:
            print(
                f"[abi_sciplot.adapters] Skipping figure '{old.get('id', '?')}': {exc}",
                file=stderr,
            )
    return new_specs
