"""Top-N genus abundance heatmap with z-score normalisation.

Aggregates taxonomy table to genus level, selects the top N genera
by mean abundance, z-score normalises each genus across samples,
and renders as a diverging-colour heatmap.

Contract: plot_genus_heatmap(spec, data, ax, palette, theme) -> None
"""

from __future__ import annotations

import pandas as pd
from matplotlib.axes import Axes

from abi.sciplot.schema.figure_spec import FigureSpec
from abi.sciplot.schema.palette_spec import PaletteRegistry
from abi.sciplot.schema.theme_spec import ThemeSpec


def plot_genus_heatmap(
    spec: FigureSpec,
    data: pd.DataFrame,
    ax: Axes,
    palette: PaletteRegistry,
    theme: ThemeSpec,
) -> None:
    """Top-N genus heatmap with z-score normalisation.

    Reads ``top_n`` from the legacy spec colormap hint (default 50).
    Uses a diverging colormap (RdBu_r by default) so that over/under-
    represented genera are visually distinct.
    """
    x_col = spec.mapping.x or "sample_id"

    if x_col not in data.columns:
        raise ValueError(f"Column '{x_col}' not found. Available: {sorted(data.columns)}")

    # Detect format: joined taxonomy+asv_table vs pre-aggregated
    if "genus" in data.columns and "abundance" in data.columns:
        agg = data.groupby([x_col, "genus"])["abundance"].sum().reset_index()
    elif "genus" in data.columns:
        # Try using value column
        val_col = spec.mapping.y or spec.mapping.value or "abundance"
        if val_col in data.columns:
            agg = data.groupby([x_col, "genus"])[val_col].sum().reset_index()
        else:
            raise ValueError(
                "Data must have 'genus' and 'abundance' columns, "
                f"or a value column. Available: {sorted(data.columns)}"
            )
    else:
        raise ValueError(
            f"Taxonomy data must have a 'genus' column. Available: {sorted(data.columns)}"
        )

    # Select top N genera
    top_n = int(getattr(spec.style, "top_n", 50) if hasattr(spec.style, "top_n") else 50)
    mean_abund = agg.groupby("genus")["abundance"].mean().sort_values(ascending=False)
    top_genera = list(mean_abund.head(top_n).index)

    # Filter and pivot
    agg_top = agg[agg["genus"].isin(top_genera)]
    pivot = agg_top.pivot_table(
        index="genus", columns=x_col, values="abundance", aggfunc="sum", fill_value=0
    )

    if pivot.empty:
        raise ValueError("No data after filtering to top genera. Check input.")

    # Z-score normalise across samples (rows)
    row_means = pivot.mean(axis=1)
    row_stds = pivot.std(axis=1).replace(0, 1.0)
    z_scores = pivot.sub(row_means, axis=0).div(row_stds, axis=0)

    # Colormap — default to RdBu_r for diverging z-scores
    cmap_name = getattr(spec.style, "colormap_name", None)
    if cmap_name is None:
        cmap_name = "RdBu_r"
    cmap_name = palette.get_diverging(cmap_name)

    # Render heatmap
    im = ax.imshow(z_scores.values, aspect="auto", cmap=cmap_name, interpolation="nearest")

    # Labels
    ax.set_xticks(range(len(pivot.columns)))
    ax.set_xticklabels(pivot.columns, rotation=45, ha="right", fontsize=theme.font.tick_size_pt)
    ax.set_yticks(range(len(pivot.index)))
    ax.set_yticklabels(pivot.index, fontsize=theme.font.tick_size_pt)

    # Colour bar
    cbar = ax.figure.colorbar(im, ax=ax, shrink=0.8, pad=0.02)
    cbar.set_label("Z-Score", fontsize=theme.font.label_size_pt)
