"""PCoA ordination plot from beta diversity distance matrix.

Computes Principal Coordinates Analysis from pairwise distance data and
renders a scatter plot with optional group colouring, confidence ellipses,
and axis labels showing variance explained.

Contract: plot_pcoa_plot(spec, data, ax, palette, theme) -> None
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from matplotlib.axes import Axes
from matplotlib.patches import Ellipse

from abi.sciplot.schema.figure_spec import FigureSpec
from abi.sciplot.schema.palette_spec import PaletteRegistry
from abi.sciplot.schema.theme_spec import ThemeSpec


def plot_pcoa_plot(
    spec: FigureSpec,
    data: pd.DataFrame,
    ax: Axes,
    palette: PaletteRegistry,
    theme: ThemeSpec,
) -> None:
    """PCoA ordination plot.

    Expects *data* to be a beta diversity table with columns:
    ``sample_a``, ``sample_b``, ``distance``.

    If sample metadata (group/condition) is needed for colouring, it must
    be in the mapping hue column or the data must include a hue column.
    """
    # Validate required columns
    required = {"sample_a", "sample_b", "distance"}
    missing = required - set(data.columns)
    if missing:
        raise ValueError(
            f"Beta diversity table missing columns: {sorted(missing)}. "
            f"Available: {sorted(data.columns)}"
        )

    # Build distance matrix
    samples = sorted(set(data["sample_a"].unique()) | set(data["sample_b"].unique()))
    n = len(samples)
    if n < 2:
        raise ValueError(f"Need ≥2 unique samples for PCoA, got {n}")

    idx_map = {s: i for i, s in enumerate(samples)}
    dist_mat = np.zeros((n, n))
    for _, row in data.iterrows():
        i = idx_map[row["sample_a"]]
        j = idx_map[row["sample_b"]]
        dist_mat[i, j] = float(row["distance"])
        dist_mat[j, i] = float(row["distance"])

    # PCoA via classical MDS
    # Double-centre the squared distance matrix
    d2 = dist_mat**2
    n_cols = d2.shape[0]
    h = np.eye(n_cols) - np.ones((n_cols, n_cols)) / n_cols
    b = -0.5 * h @ d2 @ h

    # Eigendecomposition
    eigenvalues, eigenvectors = np.linalg.eigh(b)
    # Sort descending
    idx_sort = np.argsort(eigenvalues)[::-1]
    eigenvalues = eigenvalues[idx_sort]
    eigenvectors = eigenvectors[:, idx_sort]

    # Keep only positive eigenvalues
    pos_mask = eigenvalues > 1e-10
    eigenvalues = eigenvalues[pos_mask]
    eigenvectors = eigenvectors[:, pos_mask]

    if len(eigenvalues) < 2:
        raise ValueError("Could not extract ≥2 PCoA axes — community distances may be zero.")

    pc1 = eigenvectors[:, 0] * np.sqrt(eigenvalues[0])
    pc2 = eigenvectors[:, 1] * np.sqrt(eigenvalues[1])

    var1 = eigenvalues[0] / eigenvalues.sum() * 100
    var2 = eigenvalues[1] / eigenvalues.sum() * 100

    # Build plot DataFrame
    plot_df = pd.DataFrame(
        {
            "sample_id": samples,
            "PC1": pc1,
            "PC2": pc2,
        }
    )

    # Group colouring
    hue_col = spec.mapping.hue
    if hue_col and hue_col in data.columns:
        # Map sample → group from the beta diversity table metadata columns
        sample_groups: dict = {}
        for _, row in data.iterrows():
            if "group" in data.columns:
                sample_groups[row["sample_a"]] = row.get("group", "unknown")
                sample_groups[row["sample_b"]] = row.get("group", "unknown")
        plot_df["group"] = plot_df["sample_id"].map(sample_groups).fillna("unknown")
        groups = sorted(plot_df["group"].unique())
    else:
        plot_df["group"] = "sample"
        groups = ["sample"]

    colors = palette.get_categorical(spec.style.palette, n=len(groups))
    group_colors = dict(zip(groups, colors))

    for group in groups:
        subset = plot_df[plot_df["group"] == group]
        ax.scatter(
            subset["PC1"],
            subset["PC2"],
            c=group_colors[group],
            label=group,
            s=40,
            edgecolors="black",
            linewidth=0.5,
            zorder=5,
        )
        # Confidence ellipse for groups with ≥3 points
        if len(subset) >= 3:
            _add_confidence_ellipse(
                ax,
                subset["PC1"].values,
                subset["PC2"].values,
                color=group_colors[group],
            )

    # Labels
    ax.set_xlabel(f"PCo1 ({var1:.1f}%)", fontsize=theme.font.label_size_pt)
    ax.set_ylabel(f"PCo2 ({var2:.1f}%)", fontsize=theme.font.label_size_pt)

    if len(groups) > 1:
        ax.legend(fontsize=theme.font.legend_size_pt, frameon=theme.legend.frame)

    # Reference lines at origin
    ax.axhline(0, color="grey", linewidth=0.5, linestyle="--", alpha=0.5)
    ax.axvline(0, color="grey", linewidth=0.5, linestyle="--", alpha=0.5)


def _add_confidence_ellipse(
    ax: Axes,
    x: np.ndarray,
    y: np.ndarray,
    color: str,
    n_std: float = 2.0,
    alpha: float = 0.15,
) -> None:
    """Add a 95% confidence ellipse for a group of points."""
    if len(x) < 2:
        return
    cov = np.cov(x, y)
    eigenvalues, eigenvectors = np.linalg.eigh(cov)
    angle = np.degrees(np.arctan2(eigenvectors[1, 0], eigenvectors[0, 0]))
    width, height = 2 * n_std * np.sqrt(eigenvalues)
    ellipse = Ellipse(
        xy=(np.mean(x), np.mean(y)),
        width=width,
        height=height,
        angle=angle,
        facecolor=color,
        alpha=alpha,
        edgecolor=color,
        linewidth=0.8,
        zorder=3,
    )
    ax.add_patch(ellipse)
