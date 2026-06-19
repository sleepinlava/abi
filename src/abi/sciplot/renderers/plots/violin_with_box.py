"""Violin plot with embedded box plots.

Shows full data distribution with a mini box plot inside each violin.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from matplotlib.axes import Axes

from abi.sciplot.schema.figure_spec import FigureSpec
from abi.sciplot.schema.palette_spec import PaletteRegistry
from abi.sciplot.schema.theme_spec import ThemeSpec


def plot_violin_with_box(
    spec: FigureSpec,
    data: pd.DataFrame,
    ax: Axes,
    palette: PaletteRegistry,
    theme: ThemeSpec,
) -> None:
    """Draw violin plots with embedded box plots.

    mapping.x: Grouping column (categorical).
    mapping.y: Numeric values.
    mapping.hue: Optional subgroup (creates split violins).
    """
    group_col = spec.mapping.x or spec.mapping.group
    value_col = spec.mapping.y

    if value_col is None:
        raise ValueError("violin_with_box requires mapping.y to be set.")
    if group_col is None:
        raise ValueError("violin_with_box requires mapping.x or mapping.group to be set.")

    if group_col not in data.columns:
        raise ValueError(f"Group column '{group_col}' not found in data.")
    if value_col not in data.columns:
        raise ValueError(f"Value column '{value_col}' not found in data.")

    groups = sorted(data[group_col].dropna().unique())
    n_groups = len(groups)

    # Prepare data
    violin_data = [data.loc[data[group_col] == g, value_col].dropna().values for g in groups]

    # Colours
    colors = palette.get_categorical(spec.style.palette, n=n_groups)

    # Violin plot
    positions = np.arange(1, n_groups + 1)
    vp = ax.violinplot(
        violin_data,
        positions=positions,
        showmeans=False,
        showmedians=False,
        showextrema=False,
        widths=0.6,
    )

    bodies: Any = vp["bodies"]
    for i, body in enumerate(bodies):
        body.set_facecolor(colors[i % len(colors)])
        body.set_alpha(0.6)
        body.set_edgecolor("black")
        body.set_linewidth(0.5)

    # Embedded boxplot (smaller, inside violins)
    bp = ax.boxplot(
        violin_data,
        positions=positions,
        widths=0.15,
        patch_artist=True,
        flierprops={"marker": "o", "markerfacecolor": "black", "markersize": 2, "alpha": 0.5},
        medianprops={"color": "black", "linewidth": 1},
        whiskerprops={"linewidth": 0.5},
        capprops={"linewidth": 0.5},
    )
    for patch in bp["boxes"]:
        patch.set_facecolor("white")
        patch.set_alpha(0.9)

    # Overlay individual points with jitter
    for i, g in enumerate(groups):
        vals = data.loc[data[group_col] == g, value_col].dropna().values
        if len(vals) > 0:
            jitter = np.random.normal(0, 0.04, size=len(vals))
            ax.scatter(
                positions[i] + jitter,
                vals,
                s=10,
                alpha=0.4,
                color="black",
                edgecolor="none",
                zorder=3,
            )

    ax.set_xticks(positions)
    ax.set_xticklabels([str(g) for g in groups], rotation=45, ha="right")
