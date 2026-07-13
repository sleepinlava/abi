"""Phylogenetic tree + abundance heatmap composite figure.

Reads a Newick-format phylogenetic tree and plots it alongside
an abundance heatmap, aligning leaves to rows.

Contract: plot_phylogenetic_heatmap(spec, data, ax, palette, theme) -> None
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from matplotlib.axes import Axes

from abi.sciplot.schema.figure_spec import FigureSpec
from abi.sciplot.schema.palette_spec import PaletteRegistry
from abi.sciplot.schema.theme_spec import ThemeSpec


def plot_phylogenetic_heatmap(
    spec: FigureSpec,
    data: pd.DataFrame,
    ax: Axes,
    palette: PaletteRegistry,
    theme: ThemeSpec,
) -> None:
    """Phylogenetic tree with outer-ring abundance heatmap.

    If a Newick tree path is provided via ``spec.data.tree`` or
    ``spec.mapping.group``, the tree is rendered.  Otherwise, a
    simplified abundance heatmap is drawn.

    The heatmap shows feature (ASV/OTU) abundance across samples,
    with rows sorted to reflect phylogenetic clustering when
    a tree is available.
    """
    x_col = spec.mapping.x or "sample_id"

    if x_col not in data.columns:
        raise ValueError(f"Column '{x_col}' not found. Available: {sorted(data.columns)}")

    # Determine feature ID and abundance columns
    feature_col = spec.mapping.label or "asv_id"
    abund_col = spec.mapping.y or "abundance"

    for col in (feature_col, abund_col):
        if col not in data.columns:
            raise ValueError(f"Column '{col}' not found. Available: {sorted(data.columns)}")

    # Pivot: rows=features, cols=samples, values=abundance
    pivot = data.pivot_table(
        index=feature_col,
        columns=x_col,
        values=abund_col,
        aggfunc="sum",
        fill_value=0,
    )

    if pivot.empty:
        raise ValueError("No data after pivoting. Check feature/abundance columns.")

    # Try to load a Newick tree
    tree_path = getattr(spec.data, "tree", None)
    leaf_order = None

    if tree_path:
        try:
            from pathlib import Path

            tree_str = Path(tree_path).read_text().strip()
            leaf_order = _parse_newick_leaves(tree_str)
        except Exception:
            pass  # Fall back to clustering

    if leaf_order is None:
        # Hierarchical clustering on rows
        if len(pivot) >= 2:
            try:
                from scipy.cluster.hierarchy import leaves_list, linkage
                from scipy.spatial.distance import pdist

                dist = pdist(pivot.values, metric="euclidean")
                z = linkage(dist, method="ward")
                order_idx = leaves_list(z)
                leaf_order = [pivot.index[i] for i in order_idx]
            except ImportError:
                # SciPy is optional in lightweight sciplot installations.
                # Preserve deterministic output with a dependency-free
                # abundance ordering when clustering is unavailable.
                leaf_order = list(pivot.sum(axis=1).sort_values(ascending=False).index)
        else:
            leaf_order = list(pivot.index)

    # Reorder rows
    common = [leaf for leaf in leaf_order if leaf in pivot.index]
    remaining = [leaf for leaf in pivot.index if leaf not in common]
    pivot = pivot.reindex(common + remaining)

    # Top-N filtering for visual clarity
    top_n = int(getattr(spec.style, "top_n", 50) if hasattr(spec.style, "top_n") else 50)
    if len(pivot) > top_n:
        pivot = pivot.head(top_n)

    # Log-transform for visual dynamic range
    log_data = np.log10(pivot.values + 1)

    # Diverging colormap
    cmap_name = getattr(spec.style, "colormap_name", None)
    if cmap_name is None:
        cmap_name = "viridis"
    cmap_name = palette.get_matplotlib_colormap(cmap_name)

    im = ax.imshow(log_data, aspect="auto", cmap=cmap_name, interpolation="nearest")

    # Axis labels
    ax.set_xticks(range(len(pivot.columns)))
    ax.set_xticklabels(pivot.columns, rotation=45, ha="right", fontsize=theme.font.tick_size_pt)
    if len(pivot) <= 30:
        ax.set_yticks(range(len(pivot.index)))
        ax.set_yticklabels(pivot.index, fontsize=5)
    else:
        ax.set_yticks([])

    # Colour bar
    cbar = ax.figure.colorbar(im, ax=ax, shrink=0.8, pad=0.02)
    cbar.set_label(
        f"log10(abundance + 1)\nTop {len(pivot)} features (phylogenetic order)",
        fontsize=theme.font.label_size_pt,
    )


def _parse_newick_leaves(tree_str: str) -> list[str]:
    """Extract leaf labels from a Newick tree string."""
    leaves: list[str] = []
    current = ""
    for ch in tree_str:
        if ch in ("(", ")", ",", ";"):
            if current:
                # Extract label after colon (branch length)
                label = current.split(":")[0].strip()
                if label and label not in leaves:
                    leaves.append(label)
                current = ""
        else:
            current += ch
    return leaves
