"""Differential abundance volcano plot.

Renders a volcano plot with log2 fold-change on the x-axis and
-log10 adjusted p-value on the y-axis.  Significant features are
coloured by direction (up/down/NS), and top-N features are labelled.

Contract: plot_differential_volcano(spec, data, ax, palette, theme) -> None
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from matplotlib.axes import Axes

from abi.sciplot.schema.figure_spec import FigureSpec
from abi.sciplot.schema.palette_spec import PaletteRegistry
from abi.sciplot.schema.theme_spec import ThemeSpec


def plot_differential_volcano(
    spec: FigureSpec,
    data: pd.DataFrame,
    ax: Axes,
    palette: PaletteRegistry,
    theme: ThemeSpec,
) -> None:
    """Differential abundance volcano plot.

    Expects columns: log2_fold_change (or log2FoldChange), adjusted_pvalue (or padj).

    Colours points:
      - Red:  log2FC > threshold AND padj < alpha  (up)
      - Blue: log2FC < -threshold AND padj < alpha (down)
      - Grey: not significant

    Labels top-N most significant features by name.
    """
    x_col = spec.mapping.x or "log2_fold_change"
    y_col = spec.mapping.y or "adjusted_pvalue"
    label_col = spec.mapping.label

    # Map common column name aliases
    if x_col not in data.columns and "log2FoldChange" in data.columns:
        x_col = "log2FoldChange"
    if y_col not in data.columns and "padj" in data.columns:
        y_col = "padj"

    for col in (x_col, y_col):
        if col not in data.columns:
            raise ValueError(f"Column '{col}' not found. Available: {sorted(data.columns)}")

    # Coerce to numeric
    x_vals = pd.to_numeric(data[x_col], errors="coerce")
    y_vals = pd.to_numeric(data[y_col], errors="coerce")

    # Remove NaN
    mask = x_vals.notna() & y_vals.notna()
    x_vals = x_vals[mask]
    y_vals = y_vals[mask]
    df_clean = data.loc[mask].copy()

    # -log10 transform p-values
    y_transformed = -np.log10(y_vals.replace(0, 1e-300))

    # Significance thresholds
    sig = spec.statistics
    if sig and sig.significance_rule:
        fc_thresh = sig.significance_rule.abs_log2fc_gt or 1.0
        p_thresh = sig.significance_rule.padj_lt or sig.significance_rule.pvalue_lt or 0.05
    else:
        fc_thresh = 1.0
        p_thresh = 0.05

    # Classify points
    is_up = (x_vals >= fc_thresh) & (y_vals < p_thresh)
    is_down = (x_vals <= -fc_thresh) & (y_vals < p_thresh)
    is_ns = ~(is_up | is_down)

    # Colours from palette
    colors = palette.get_categorical(spec.style.palette, n=3)

    for mask_group, color, zorder, lbl in [
        (is_ns, "#aaaaaa", 2, "NS"),
        (is_down, colors[0] if len(colors) > 0 else "#2166ac", 3, "Down"),
        (is_up, colors[1] if len(colors) > 1 else "#b2182b", 4, "Up"),
    ]:
        if mask_group.any():
            ax.scatter(
                x_vals[mask_group],
                y_transformed[mask_group],
                c=color,
                alpha=0.5,
                s=12,
                edgecolors="none",
                label=lbl,
                zorder=zorder,
            )

    # Threshold lines
    ax.axhline(-np.log10(p_thresh), color="grey", linewidth=0.8, linestyle="--", alpha=0.7)
    ax.axvline(fc_thresh, color="grey", linewidth=0.5, linestyle="--", alpha=0.5)
    ax.axvline(-fc_thresh, color="grey", linewidth=0.5, linestyle="--", alpha=0.5)

    # Label top N significant features
    if label_col and label_col in df_clean.columns:
        sig_mask = is_up | is_down
        sig_df = df_clean.loc[sig_mask].copy()
        sig_df["_neglogp"] = y_transformed[sig_mask].values
        top_n = min(20, len(sig_df))
        top = sig_df.nlargest(top_n, "_neglogp")
        for _, row in top.iterrows():
            ax.annotate(
                str(row[label_col]),
                (float(row[x_col]), -np.log10(max(float(row[y_col]), 1e-300))),
                fontsize=5,
                alpha=0.8,
                xytext=(5, 3),
                textcoords="offset points",
            )

    ax.legend(fontsize=theme.font.legend_size_pt, frameon=theme.legend.frame)

    # Annotation of total counts
    ax.text(
        0.98,
        0.95,
        f"Up: {is_up.sum()}  Down: {is_down.sum()}  NS: {is_ns.sum()}",
        transform=ax.transAxes,
        ha="right",
        va="top",
        fontsize=7,
        bbox={"boxstyle": "round,pad=0.3", "facecolor": "white", "alpha": 0.8},
    )
