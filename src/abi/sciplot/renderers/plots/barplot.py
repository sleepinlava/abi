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

    # Auto-count mode: when y is not specified, count occurrences of x values
    hue_col = spec.mapping.hue
    if hue_col and not y_col:
        raise ValueError("barplot mapping.hue requires mapping.y.")

    if not y_col:
        if x_col and x_col in data.columns:
            counts = data[x_col].value_counts().reset_index()
            counts.columns = ["label", "count"]
            labels = counts["label"].astype(str).values
            values = counts["count"].values
            if spec.labels and not spec.labels.y_label:
                spec.labels.y_label = "Count"
        else:
            raise ValueError(
                "barplot requires either mapping.y (bar heights) or a valid "
                "mapping.x column for auto-counting."
            )
    elif hue_col and hue_col in data.columns and x_col and x_col in data.columns:
        numeric = data.assign(**{y_col: pd.to_numeric(data[y_col], errors="coerce")})
        x_levels = list(dict.fromkeys(numeric[x_col].astype(str)))
        hue_levels = list(dict.fromkeys(numeric[hue_col].astype(str)))
        pivot = numeric.pivot_table(
            index=x_col,
            columns=hue_col,
            values=y_col,
            aggfunc="first",
            observed=False,
        )
        pivot.index = pivot.index.astype(str)
        pivot.columns = pivot.columns.astype(str)
        pivot = pivot.reindex(index=x_levels, columns=hue_levels)
        x_pos = np.arange(len(x_levels))
        group_width = 0.8
        bar_width = group_width / max(1, len(hue_levels))
        colors = palette.get_categorical(spec.style.palette, n=len(hue_levels))
        for index, hue_level in enumerate(hue_levels):
            offset = (index - (len(hue_levels) - 1) / 2) * bar_width
            values = pivot[hue_level].fillna(0).to_numpy()
            ax.bar(
                x_pos + offset,
                values,
                label=hue_level,
                color=colors[index % len(colors)],
                edgecolor="white",
                linewidth=0.3,
                width=bar_width,
            )
        ax.set_xticks(x_pos)
        ax.set_xticklabels(x_levels, rotation=45, ha="right", fontsize=7)
        ax.legend(fontsize=theme.font.legend_size_pt)
        return
    else:
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
