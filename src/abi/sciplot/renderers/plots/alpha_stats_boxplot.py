"""Alpha diversity boxplot with statistical test annotations.

Groups samples by a metadata column (hue) and renders a boxplot of
alpha diversity metrics with individual data points overlaid as a
strip/swarm plot.  Adds Kruskal-Wallis H-test p-value annotation.

Contract: plot_alpha_stats_boxplot(spec, data, ax, palette, theme) -> None
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from matplotlib.axes import Axes

from abi.sciplot.renderers.annotation_layout import reserve_top_annotation_band
from abi.sciplot.schema.figure_spec import FigureSpec
from abi.sciplot.schema.palette_spec import PaletteRegistry
from abi.sciplot.schema.theme_spec import ThemeSpec


def plot_alpha_stats_boxplot(
    spec: FigureSpec,
    data: pd.DataFrame,
    ax: Axes,
    palette: PaletteRegistry,
    theme: ThemeSpec,
) -> None:
    """Alpha diversity boxplot with statistical annotations.

    Expects data with columns: sample_id, a numeric metric column (shannon_entropy,
    observed_features, chao1, etc.), and optionally a group column for hue.

    If *hue* is set and exists in the data, samples are grouped and coloured
    accordingly.  A Kruskal-Wallis test is run when ≥3 groups are present.
    """
    x_col = spec.mapping.x or "sample_id"
    y_col = spec.mapping.y or "shannon_entropy"
    hue_col = spec.mapping.hue

    for col in (x_col, y_col):
        if col not in data.columns:
            raise ValueError(f"Column '{col}' not found. Available: {sorted(data.columns)}")

    y_vals = pd.to_numeric(data[y_col], errors="coerce")
    data = data.assign(_y_numeric=y_vals).dropna(subset=["_y_numeric"])

    if data.empty:
        raise ValueError(f"No numeric data in column '{y_col}'.")

    # Determine groups
    if hue_col and hue_col in data.columns:
        groups = sorted(data[hue_col].unique())
        group_data = [data.loc[data[hue_col] == g, "_y_numeric"].values for g in groups]
        colors = palette.get_categorical(spec.style.palette, n=len(groups))
    else:
        groups = ["All"]
        group_data = [data["_y_numeric"].values]
        colors = ["#4477AA"]

    # Boxplot
    positions = list(range(1, len(groups) + 1))
    bp = ax.boxplot(
        group_data,
        positions=positions,
        patch_artist=True,
        widths=0.5,
        boxprops={"linewidth": 0.8},
        whiskerprops={"linewidth": 0.8},
        capprops={"linewidth": 0.8},
        medianprops={"linewidth": 1.0, "color": "black"},
        flierprops={"marker": "o", "markersize": 3, "markerfacecolor": "grey"},
    )
    for patch, color in zip(bp["boxes"], colors):
        patch.set_facecolor(color)
        patch.set_alpha(0.5)

    # Strip plot overlay — jitter individual points
    for i, (g_data, color) in enumerate(zip(group_data, colors)):
        if len(g_data) > 0:
            jitter = np.random.default_rng(42).uniform(-0.12, 0.12, size=len(g_data))
            ax.scatter(
                np.full_like(g_data, positions[i]) + jitter,
                g_data,
                c=color,
                alpha=0.6,
                s=20,
                edgecolors="black",
                linewidth=0.3,
                zorder=5,
            )

    # Kruskal-Wallis test for ≥3 groups
    if len(groups) >= 3:
        from scipy.stats import kruskal as kw_test

        try:
            stat, pval = kw_test(*group_data)
            sig_str = _format_pvalue(pval)
            reserve_top_annotation_band(ax)
            ax.text(
                0.5,
                0.97,
                f"Kruskal-Wallis H-test: p = {sig_str}",
                transform=ax.transAxes,
                ha="center",
                va="top",
                fontsize=8,
                fontstyle="italic",
            )
        except Exception:
            pass  # KW test may fail with small groups

    # Axis formatting
    ax.set_xticks(positions)
    ax.set_xticklabels(groups, fontsize=theme.font.tick_size_pt)
    ax.set_ylabel(y_col.replace("_", " ").title(), fontsize=theme.font.label_size_pt)


def _format_pvalue(p: float) -> str:
    """Format a p-value for display."""
    if p < 0.0001:
        return "< 0.0001"
    elif p < 0.001:
        return f"{p:.4f}"
    elif p < 0.01:
        return f"{p:.3f}"
    else:
        return f"{p:.2f}"
