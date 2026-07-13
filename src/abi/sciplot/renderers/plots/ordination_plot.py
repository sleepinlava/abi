"""Ordination plot — PCA, PCoA, NMDS scatter.

First two numeric columns after the label column are treated as axis 1 and axis 2.
Supports colour grouping via mapping.hue and point labels via mapping.label.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from matplotlib.axes import Axes

from abi.sciplot.renderers.annotation_layout import annotate_points_without_overlap
from abi.sciplot.schema.figure_spec import FigureSpec
from abi.sciplot.schema.palette_spec import PaletteRegistry
from abi.sciplot.schema.theme_spec import ThemeSpec


def plot_ordination(
    spec: FigureSpec,
    data: pd.DataFrame,
    ax: Axes,
    palette: PaletteRegistry,
    theme: ThemeSpec,
) -> None:
    """Draw an ordination plot (PCA/PCoA/NMDS).

    The first two numeric columns (after any label column) are used as axes.
    mapping.hue: Optional column for colour grouping.
    mapping.label: Optional column for point labels.
    """
    # Detect label column and numeric columns
    label_col = spec.mapping.label or spec.mapping.x
    if label_col and label_col in data.columns:
        numeric_cols = [c for c in data.columns if c != label_col]
    else:
        numeric_cols = list(data.columns)
        label_col = None

    # Filter to numeric columns
    numeric_cols = [
        c for c in numeric_cols if pd.to_numeric(data[c], errors="coerce").notna().sum() > 0
    ]

    if len(numeric_cols) < 2:
        ax.text(
            0.5,
            0.5,
            "Need >= 2 numeric columns for ordination",
            transform=ax.transAxes,
            ha="center",
            va="center",
        )
        return

    x_vals = pd.to_numeric(data[numeric_cols[0]], errors="coerce").values
    y_vals = pd.to_numeric(data[numeric_cols[1]], errors="coerce").values

    # Labels
    if label_col and label_col in data.columns:
        labels = [str(r) for r in data[label_col].values]
    else:
        labels = [str(i) for i in range(len(data))]

    # Colour grouping
    hue_col = spec.mapping.hue
    if hue_col and hue_col in data.columns:
        hue_vals = data[hue_col].values
        groups = sorted(set(str(v) for v in hue_vals))
        colors = palette.get_categorical(spec.style.palette, n=len(groups))
        for i, g in enumerate(groups):
            idx = [j for j in range(len(data)) if str(hue_vals[j]) == g]
            ax.scatter(
                x_vals[idx],
                y_vals[idx],
                label=g,
                color=colors[i % len(colors)],
                s=40,
                alpha=0.8,
                edgecolor="white",
                linewidth=0.5,
            )
        ax.legend(fontsize=theme.font.legend_size_pt)
    else:
        ax.scatter(
            x_vals,
            y_vals,
            s=40,
            alpha=0.8,
            color="#4472C4",
            edgecolor="white",
            linewidth=0.5,
        )
        # Label points if label column
        annotations = [
            (float(x_vals[j]), float(y_vals[j]), str(labels[j]))
            for j in range(min(len(labels), 50))
        ]
        annotate_points_without_overlap(
            ax,
            annotations,
            np.column_stack((x_vals, y_vals)),
        )

    ax.set_xlabel(numeric_cols[0])
    ax.set_ylabel(numeric_cols[1])

    # Add percentage variance if columns look like PC names
    ax.set_xlabel(f"{numeric_cols[0]}")
    ax.set_ylabel(f"{numeric_cols[1]}")
