"""Boxplot with overlaid data points.

Groups data by mapping.x (or mapping.group), plots boxes for mapping.y values,
and overlays individual data points with jitter for transparency.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from matplotlib.axes import Axes

from abi.sciplot.schema.figure_spec import FigureSpec
from abi.sciplot.schema.palette_spec import PaletteRegistry
from abi.sciplot.schema.theme_spec import ThemeSpec


def plot_boxplot_with_points(
    spec: FigureSpec,
    data: pd.DataFrame,
    ax: Axes,
    palette: PaletteRegistry,
    theme: ThemeSpec,
) -> None:
    """Draw grouped boxplots with individual data points overlaid.

    mapping.x: Grouping column (categorical).
    mapping.y: Numeric values.
    mapping.hue: Optional subgroup colouring.
    """
    group_col = spec.mapping.x or spec.mapping.group or data.columns[0]
    value_col = spec.mapping.y

    if value_col is None:
        raise ValueError("boxplot_with_points requires mapping.y to be set.")

    if group_col not in data.columns:
        raise ValueError(f"Group column '{group_col}' not found in data.")
    if value_col not in data.columns:
        raise ValueError(f"Value column '{value_col}' not found in data.")

    groups = sorted(data[group_col].dropna().unique())
    n_groups = len(groups)

    # Prepare boxplot data
    box_data = [data.loc[data[group_col] == g, value_col].dropna().values for g in groups]

    # Colours
    colors = palette.get_categorical(spec.style.palette, n=max(n_groups, 1))

    # Boxplot
    bp = ax.boxplot(
        box_data,
        labels=[str(g) for g in groups],
        patch_artist=True,
        widths=0.5,
        flierprops={"marker": "o", "markerfacecolor": "grey", "markersize": 3, "alpha": 0.4},
        medianprops={"color": "black", "linewidth": 1},
    )
    for i, patch in enumerate(bp["boxes"]):
        patch.set_facecolor(colors[i % len(colors)])
        patch.set_alpha(0.6)

    # Overlay points with jitter
    for i, g in enumerate(groups):
        vals = data.loc[data[group_col] == g, value_col].dropna().values
        if len(vals) > 0:
            jitter = np.random.normal(0, 0.05, size=len(vals))
            ax.scatter(
                np.full(len(vals), i + 1) + jitter,
                vals,
                s=15,
                alpha=0.5,
                color=colors[i % len(colors)],
                edgecolor="white",
                linewidth=0.3,
                zorder=3,
            )

    ax.set_xticklabels([str(g) for g in groups], rotation=45, ha="right")
