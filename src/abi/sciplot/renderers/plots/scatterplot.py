"""Scatter plot.

Supports coloured groups via mapping.hue and point labels via mapping.label.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from matplotlib.axes import Axes

from abi.sciplot.renderers.annotation_layout import annotate_points_without_overlap
from abi.sciplot.schema.figure_spec import FigureSpec
from abi.sciplot.schema.palette_spec import PaletteRegistry
from abi.sciplot.schema.theme_spec import ThemeSpec


def plot_scatterplot(
    spec: FigureSpec,
    data: pd.DataFrame,
    ax: Axes,
    palette: PaletteRegistry,
    theme: ThemeSpec,
) -> None:
    """Draw a scatter plot.

    mapping.x: X-axis numeric column.
    mapping.y: Y-axis numeric column.
    mapping.hue: Optional categorical column for colour grouping.
    mapping.label: Optional column for point text labels.
    """
    x_col = spec.mapping.x
    y_col = spec.mapping.y

    if x_col is None or y_col is None:
        raise ValueError("scatterplot requires both mapping.x and mapping.y.")

    if x_col not in data.columns:
        raise ValueError(f"X column '{x_col}' not found in data.")
    if y_col not in data.columns:
        raise ValueError(f"Y column '{y_col}' not found in data.")

    x_vals = pd.to_numeric(data[x_col], errors="coerce").values
    y_vals = pd.to_numeric(data[y_col], errors="coerce").values

    # Mask NaN
    valid = ~(np.isnan(x_vals) | np.isnan(y_vals))
    x_vals = x_vals[valid]
    y_vals = y_vals[valid]

    hue_col = spec.mapping.hue
    label_col = spec.mapping.label

    if hue_col and hue_col in data.columns:
        hue_vals = data[hue_col].values[valid]
        groups = sorted(set(hue_vals))
        colors = palette.get_categorical(spec.style.palette, n=len(groups))
        for i, g in enumerate(groups):
            idx = hue_vals == g
            ax.scatter(
                x_vals[idx],
                y_vals[idx],
                label=str(g),
                color=colors[i % len(colors)],
                alpha=0.7,
                s=20,
                edgecolor="white",
                linewidth=0.3,
            )
        ax.legend(fontsize=theme.font.legend_size_pt)
    else:
        ax.scatter(
            x_vals,
            y_vals,
            alpha=0.7,
            s=20,
            color="#4472C4",
            edgecolor="white",
            linewidth=0.3,
        )

    # Label top points if label column is set
    if label_col and label_col in data.columns:
        label_vals = data[label_col].values[valid]
        annotations = [
            (float(x_vals[j]), float(y_vals[j]), str(label_vals[j]))
            for j in range(min(len(label_vals), 50))
        ]
        annotate_points_without_overlap(
            ax,
            annotations,
            np.column_stack((x_vals, y_vals)),
        )
