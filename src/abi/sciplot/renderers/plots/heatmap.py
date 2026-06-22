"""Heatmap — matrix visualization for abundance, distance, or expression data.

Rows are labelled by mapping.x column; columns are auto-detected numeric columns.
Values are colour-mapped using the specified continuous palette.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from matplotlib.axes import Axes

from abi.sciplot.schema.figure_spec import FigureSpec
from abi.sciplot.schema.palette_spec import PaletteRegistry
from abi.sciplot.schema.theme_spec import ThemeSpec


def plot_heatmap(
    spec: FigureSpec,
    data: pd.DataFrame,
    ax: Axes,
    palette: PaletteRegistry,
    theme: ThemeSpec,
) -> None:
    """Draw a heatmap from a table.

    mapping.x: Column for row labels.
    Remaining numeric columns form the matrix.

    If the matrix has >50 rows, only the top 50 (by row sum) are shown.
    """
    row_col = spec.mapping.x

    if data.empty:
        ax.text(0.5, 0.5, "No data available", transform=ax.transAxes, ha="center", va="center")
        return

    # Determine row labels
    if row_col and row_col in data.columns:
        row_ids = [str(r) for r in data[row_col].values]
    else:
        row_ids = [str(i) for i in range(len(data))]

    # Detect numeric columns
    numeric_cols = []
    for col in data.columns:
        if col == row_col:
            continue
        try:
            pd.to_numeric(data[col], errors="raise")
            numeric_cols.append(col)
        except (ValueError, TypeError):
            continue

    if not numeric_cols:
        ax.text(
            0.5,
            0.5,
            "No numeric columns for heatmap",
            transform=ax.transAxes,
            ha="center",
            va="center",
        )
        return

    # Build matrix
    matrix = np.array(
        [
            [pd.to_numeric(data[col].values[i], errors="coerce") for col in numeric_cols]
            for i in range(len(data))
        ]
    )
    # Replace NaN with 0
    matrix = np.nan_to_num(matrix, nan=0.0)

    # Limit rows if needed
    max_rows = 50
    if matrix.shape[0] > max_rows:
        row_sums = matrix.sum(axis=1)
        top_idx = np.argsort(row_sums)[-max_rows:]
        matrix = matrix[top_idx]
        row_ids = [row_ids[i] for i in top_idx]

    # Colour map
    cmap_name = palette.get_matplotlib_colormap(spec.style.palette)
    im = ax.imshow(matrix, aspect="auto", cmap=cmap_name, interpolation="nearest")

    # Labels
    ax.set_yticks(range(len(row_ids)))
    ax.set_yticklabels(row_ids, fontsize=6)
    ax.set_xticks(range(len(numeric_cols)))
    ax.set_xticklabels(numeric_cols, rotation=90, fontsize=6)

    # Colour bar
    from matplotlib.pyplot import colorbar

    colorbar(im, ax=ax, shrink=0.8, aspect=30)
