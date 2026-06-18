"""Volcano plot — differential expression/abundance visualization.

x-axis: log2 fold change (mapping.x)
y-axis: -log10 adjusted p-value (mapping.y)
Colour: NS (grey), Up (red), Down (blue) based on significance_rule
Labels: mapping.label column for top-N significant points
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from matplotlib.axes import Axes

from abi.sciplot.schema.figure_spec import FigureSpec
from abi.sciplot.schema.palette_spec import PaletteRegistry
from abi.sciplot.schema.theme_spec import ThemeSpec


def plot_volcano(
    spec: FigureSpec,
    data: pd.DataFrame,
    ax: Axes,
    palette: PaletteRegistry,
    theme: ThemeSpec,
) -> None:
    """Draw a volcano plot.

    x = log2 fold change, y = -log10(p-value).
    Points coloured by significance: NS (grey), Up (red), Down (blue).
    """
    x_col = spec.mapping.x or "log2FoldChange"
    y_col = spec.mapping.y or "padj"

    if x_col not in data.columns:
        raise ValueError(f"X column '{x_col}' not found in data.")
    if y_col not in data.columns:
        raise ValueError(f"Y column '{y_col}' not found in data.")

    x_vals = pd.to_numeric(data[x_col], errors="coerce").values
    p_vals = pd.to_numeric(data[y_col], errors="coerce").values

    # Clamp p-values
    p_vals = np.clip(p_vals, 1e-300, None)
    y_vals = -np.log10(p_vals)

    # Significance thresholds from stat spec
    fc_thresh = 1.0
    p_thresh = 0.05
    if spec.statistics and spec.statistics.significance_rule:
        if spec.statistics.significance_rule.abs_log2fc_gt is not None:
            fc_thresh = spec.statistics.significance_rule.abs_log2fc_gt
        if spec.statistics.significance_rule.padj_lt is not None:
            p_thresh = spec.statistics.significance_rule.padj_lt
        elif spec.statistics.significance_rule.pvalue_lt is not None:
            p_thresh = spec.statistics.significance_rule.pvalue_lt

    sig_up = (x_vals > fc_thresh) & (p_vals < p_thresh)
    sig_down = (x_vals < -fc_thresh) & (p_vals < p_thresh)
    nonsig = ~(sig_up | sig_down)

    # Scatter layers
    ax.scatter(
        x_vals[nonsig], y_vals[nonsig], color="grey", alpha=0.4, s=10, label="NS", edgecolor="none"
    )
    ax.scatter(
        x_vals[sig_up],
        y_vals[sig_up],
        color="#D62728",
        alpha=0.7,
        s=15,
        label="Up",
        edgecolor="none",
    )
    ax.scatter(
        x_vals[sig_down],
        y_vals[sig_down],
        color="#1F77B4",
        alpha=0.7,
        s=15,
        label="Down",
        edgecolor="none",
    )

    # Threshold lines
    ax.axhline(-np.log10(p_thresh), color="grey", linestyle="--", linewidth=0.5, alpha=0.5)
    ax.axvline(-fc_thresh, color="grey", linestyle="--", linewidth=0.5, alpha=0.5)
    ax.axvline(fc_thresh, color="grey", linestyle="--", linewidth=0.5, alpha=0.5)

    # Label top significant points
    label_col = spec.mapping.label
    if label_col and label_col in data.columns:
        sig_idx = np.where(sig_up | sig_down)[0]
        # Sort by significance
        order = np.argsort(p_vals[sig_idx])
        top_n = 50
        for idx in sig_idx[order[:top_n]]:
            label_text = str(data[label_col].values[idx])
            if label_text and label_text.lower() not in ("nan", "none", ""):
                ax.annotate(
                    label_text,
                    (x_vals[idx], y_vals[idx]),
                    fontsize=5,
                    alpha=0.8,
                    xytext=(5, 3),
                    textcoords="offset points",
                    arrowprops={"arrowstyle": "-", "color": "grey", "alpha": 0.3},
                )

    ax.legend(fontsize=theme.font.legend_size_pt, loc="upper right")
