"""Phylum-level stacked bar chart.

Aggregates taxonomy abundances to phylum level and renders a stacked bar
chart showing community composition per sample.  Expects data from the
taxonomy standard table joined with asv_table abundance data.

Contract: plot_phylum_stacked_bar(spec, data, ax, palette, theme) -> None
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from matplotlib.axes import Axes

from abi.sciplot.schema.figure_spec import FigureSpec
from abi.sciplot.schema.palette_spec import PaletteRegistry
from abi.sciplot.schema.theme_spec import ThemeSpec


def plot_phylum_stacked_bar(
    spec: FigureSpec,
    data: pd.DataFrame,
    ax: Axes,
    palette: PaletteRegistry,
    theme: ThemeSpec,
) -> None:
    """Phylum-level stacked bar chart.

    If the data has ``phylum`` and ``abundance`` columns (joined taxonomy +
    asv_table), aggregates to phylum level per sample and plots.  If the data
    is already aggregated (sample_id, phylum, abundance), plots directly.

    ``top_n`` is read from a ``top_n`` hint in the legacy spec style dict;
    defaults to 10 if unset.
    """
    x_col = spec.mapping.x or "sample_id"
    hue_col = spec.mapping.hue or "phylum"
    y_col = spec.mapping.y or "abundance"

    # Required columns
    for col in (x_col, hue_col, y_col):
        if col not in data.columns:
            raise ValueError(f"Column '{col}' not found in data. Available: {sorted(data.columns)}")

    # Aggregate: sum abundance per sample + phylum
    if "abundance" in data.columns and "phylum" in data.columns:
        # Joined taxonomy + asv_table format
        agg = data.groupby([x_col, hue_col])[y_col].sum().reset_index()
    else:
        # Already aggregated
        agg = data[[x_col, hue_col, y_col]].copy()

    # Compute relative abundance per sample
    sample_totals = agg.groupby(x_col)[y_col].transform("sum")
    agg["rel_abund"] = agg[y_col] / sample_totals.replace(0, np.nan)

    # Select top N phyla by mean abundance
    top_n = _resolve_top_n(spec)
    mean_abund = agg.groupby(hue_col)["rel_abund"].mean().sort_values(ascending=False)
    top_phyla = list(mean_abund.head(top_n).index)
    agg["display_phylum"] = agg[hue_col].where(agg[hue_col].isin(top_phyla), "Other")

    # Pivot to wide format for stacked bars
    pivot = agg.pivot_table(
        index=x_col,
        columns="display_phylum",
        values="rel_abund",
        aggfunc="sum",
        fill_value=0,
    )

    # Ensure "Other" is last
    cols = [c for c in top_phyla if c in pivot.columns]
    if "Other" in pivot.columns:
        cols.append("Other")
    pivot = pivot[cols]

    # Colors
    n_colors = len(cols)
    colors = palette.get_categorical(spec.style.palette, n=n_colors)

    # Stacked bar
    x_positions = range(len(pivot.index))
    bottom = np.zeros(len(pivot.index))
    bars = []
    for i, col_name in enumerate(cols):
        bar = ax.bar(
            x_positions,
            pivot[col_name].values,
            bottom=bottom,
            color=colors[i],
            label=col_name,
            width=0.7,
            edgecolor="white",
            linewidth=0.3,
        )
        bars.append(bar)
        bottom += pivot[col_name].values

    ax.set_xticks(x_positions)
    ax.set_xticklabels(pivot.index, rotation=45, ha="right", fontsize=theme.font.tick_size_pt)
    ax.set_ylabel("Relative Abundance", fontsize=theme.font.label_size_pt)
    ax.set_ylim(0, 1.02)
    ax.legend(
        fontsize=theme.font.legend_size_pt,
        frameon=theme.legend.frame,
        loc="center left",
        bbox_to_anchor=(1.02, 0.5),
        title="Phylum",
    )


def _resolve_top_n(spec: FigureSpec) -> int:
    """Resolve top_n from spec hints; default 10."""
    # Check for top_n in various places
    top_n = getattr(spec, "_legacy_top_n", None)
    if top_n is None and hasattr(spec.style, "palette"):
        pass  # not on style
    return int(top_n) if top_n else 10
