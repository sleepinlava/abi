"""Stacked bar plot — compositional data visualization.

mapping.x: Bar groups (e.g. samples).
Remaining numeric columns are stacked components.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from matplotlib.axes import Axes

from abi.sciplot.schema.figure_spec import FigureSpec
from abi.sciplot.schema.palette_spec import PaletteRegistry
from abi.sciplot.schema.theme_spec import ThemeSpec


def plot_stacked_barplot(
    spec: FigureSpec,
    data: pd.DataFrame,
    ax: Axes,
    palette: PaletteRegistry,
    theme: ThemeSpec,
) -> None:
    """Draw a stacked bar chart for compositional data.

    mapping.x: Column for bar groups (x-axis labels).
    All remaining columns are treated as stack components.

    Normalizes each row to sum to 1 (100%) for relative abundance.
    """
    group_col = spec.mapping.x

    if data.empty:
        ax.text(0.5, 0.5, "No data available", transform=ax.transAxes, ha="center", va="center")
        return

    # Determine categories (bar labels)
    if group_col and group_col in data.columns:
        categories = [str(r) for r in data[group_col].values]
    else:
        categories = [str(i) for i in range(len(data))]

    # Detect stack columns (all columns except group_col)
    stack_cols = [c for c in data.columns if c != group_col]
    if not stack_cols:
        ax.text(
            0.5,
            0.5,
            "No stack columns found",
            transform=ax.transAxes,
            ha="center",
            va="center",
        )
        return

    # Limit to top N components, merge rest as "Others"
    max_components = 15
    if len(stack_cols) > max_components:
        # Compute column sums and keep top
        col_sums = {c: pd.to_numeric(data[c], errors="coerce").sum() for c in stack_cols}
        sorted_cols = sorted(col_sums, key=col_sums.get, reverse=True)  # type: ignore[arg-type]
        stack_cols = sorted_cols[:max_components]

    # Build data matrix
    matrix = np.array(
        [
            [max(pd.to_numeric(data[c].values[i], errors="coerce"), 0.0) for c in stack_cols]
            for i in range(len(data))
        ]
    )
    matrix = np.nan_to_num(matrix, nan=0.0)

    # Normalize to 100%
    row_sums = matrix.sum(axis=1, keepdims=True)
    row_sums[row_sums == 0] = 1
    matrix = matrix / row_sums * 100

    # Colours
    colors = palette.get_categorical(spec.style.palette, n=len(stack_cols))

    # Stack bars
    bottom = np.zeros(len(categories))
    x_pos = np.arange(len(categories))
    bar_width = 0.7

    for i, col in enumerate(stack_cols):
        vals = matrix[:, i]
        ax.bar(
            x_pos,
            vals,
            bottom=bottom,
            label=col,
            color=colors[i % len(colors)],
            edgecolor="white",
            linewidth=0.3,
            width=bar_width,
        )
        bottom += vals

    ax.set_xticks(x_pos)
    ax.set_xticklabels(categories, rotation=45, ha="right", fontsize=7)
    ax.set_ylabel("Relative abundance (%)")
    ax.set_ylim(0, 100)

    # Legend outside
    ax.legend(
        fontsize=6,
        bbox_to_anchor=(1.02, 1),
        loc="upper left",
        borderaxespad=0,
        ncol=max(1, len(stack_cols) // 20 + 1),
    )
