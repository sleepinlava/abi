"""Simple vertical bar chart.

The simplest figure type — one bar per row, x-axis from mapping.x (labels),
y-axis from mapping.y (values). Optionally sorted by a column.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from matplotlib.axes import Axes

from abi.sciplot.schema.figure_spec import FigureSpec
from abi.sciplot.schema.palette_spec import PaletteRegistry
from abi.sciplot.schema.theme_spec import ThemeSpec


def plot_barplot(
    spec: FigureSpec,
    data: pd.DataFrame,
    ax: Axes,
    palette: PaletteRegistry,
    theme: ThemeSpec,
) -> None:
    """Draw a vertical bar chart.

    mapping.x: Column for bar labels (x-axis).
    mapping.y: Column for bar heights.
    mapping.hue: Optional grouping column for stacked/side-by-side bars.
    """
    x_col = spec.mapping.x
    y_col = spec.mapping.y

    if y_col is None:
        raise ValueError("barplot requires mapping.y to be set (bar heights).")

    if x_col and x_col in data.columns:
        labels = [str(r) for r in data[x_col].values]
    else:
        labels = [str(i) for i in range(len(data))]

    values = pd.to_numeric(data[y_col], errors="coerce").fillna(0).values

    # Truncate if too many bars
    max_bars = 60
    if len(labels) > max_bars:
        labels = labels[:max_bars]
        values = values[:max_bars]

    x_pos = np.arange(len(labels))
    colors = palette.get_categorical(spec.style.palette, n=1)

    ax.bar(
        x_pos,
        values,
        color=colors[0],
        edgecolor="white",
        linewidth=0.3,
        width=0.7,
    )

    ax.set_xticks(x_pos)
    ax.set_xticklabels(labels, rotation=45, ha="right", fontsize=7)

    # Hide labels if too many
    if len(labels) > 30:
        for tick in ax.get_xticklabels():
            tick.set_visible(False)
        ax.set_xlabel(f"{len(labels)} items (labels hidden)")
