"""Parameterized smoke test for all 15 registered plot functions.

Exercises every entry in :data:`PLOT_FUNCTIONS
<abi.sciplot.renderers.plots.PLOT_FUNCTIONS>` with minimal synthetic data
and verifies the registration covers exactly the expected set of plot types.
"""

from __future__ import annotations

import pandas as pd
import pytest

try:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    HAS_MPL = True
except ImportError:
    HAS_MPL = False

from abi.sciplot.renderers.plots import PLOT_FUNCTIONS
from abi.sciplot.schema.figure_spec import MappingSpec

from .conftest import _make_synthetic_tsv, make_minimal_fig_spec

# (plot_key, columns, rows, mapping) tuples -- one per registered plot function.
_plot_data: list[tuple[str, list[str], list[tuple], MappingSpec | None]] = [
    (
        "barplot",
        ["category", "value"],
        [("A", 3), ("B", 7), ("C", 5)],
        MappingSpec(x="category", y="value"),
    ),
    (
        "boxplot_with_points",
        ["group", "value"],
        [("A", 1), ("A", 2), ("B", 3), ("B", 4), ("C", 2), ("C", 5)],
        MappingSpec(x="group", y="value"),
    ),
    (
        "violin_with_box",
        ["group", "value"],
        [("A", 1.0), ("A", 1.5), ("B", 3.0), ("B", 3.5), ("C", 5.0)],
        MappingSpec(x="group", y="value"),
    ),
    (
        "scatterplot",
        ["x", "y"],
        [(1, 2), (2, 4), (3, 6), (4, 8), (5, 10)],
        MappingSpec(x="x", y="y"),
    ),
    (
        "ordination_plot",
        ["label", "x", "y"],
        [("a", 1.0, 3.0), ("b", 2.0, 6.0), ("c", 3.0, 9.0)],
        None,  # exempt from mapping validator
    ),
    (
        "stacked_barplot",
        ["sample", "A", "B"],
        [("S1", 10, 20), ("S2", 20, 30)],
        MappingSpec(x="sample"),
    ),
    (
        "heatmap",
        ["gene", "S1", "S2"],
        [("g1", 1.0, 4.0), ("g2", 2.0, 5.0), ("g3", 3.0, 6.0)],
        None,  # exempt
    ),
    (
        "volcano_plot",
        ["log2FoldChange", "padj"],
        [(-2.0, 0.001), (0.0, 0.5), (2.0, 0.002)],
        MappingSpec(x="log2FoldChange", y="padj"),
    ),
    (
        "lineplot",
        ["x", "y"],
        [(1, 1.0), (2, 1.5), (3, 2.0), (4, 1.8), (5, 2.5)],
        MappingSpec(x="x", y="y"),
    ),
    (
        "phylum_stacked_bar",
        ["sample_id", "phylum", "abundance"],
        [
            ("S1", "Firmicutes", 30),
            ("S1", "Bacteroidetes", 70),
            ("S2", "Firmicutes", 40),
            ("S2", "Bacteroidetes", 60),
        ],
        MappingSpec(x="sample_id", y="abundance"),
    ),
    (
        "genus_heatmap",
        ["sample_id", "genus", "abundance"],
        [
            ("S1", "Escherichia", 10),
            ("S1", "Bacillus", 5),
            ("S2", "Escherichia", 20),
            ("S2", "Bacillus", 15),
        ],
        None,  # exempt
    ),
    (
        "pcoa_plot",
        ["sample_a", "sample_b", "distance"],
        # Four-sample non-degenerate configuration — must yield ≥2 PCoA axes.
        [
            ("A", "B", 0.5),
            ("A", "C", 1.0),
            ("A", "D", 0.3),
            ("B", "C", 0.7),
            ("B", "D", 0.6),
            ("C", "D", 0.8),
        ],
        None,  # exempt
    ),
    (
        "differential_volcano",
        ["log2_fold_change", "adjusted_pvalue"],
        [(-2.0, 0.001), (1.5, 0.01), (-0.5, 0.5), (3.0, 0.0001)],
        MappingSpec(x="log2_fold_change", y="adjusted_pvalue"),
    ),
    (
        "alpha_stats_boxplot",
        ["sample_id", "shannon_entropy"],
        [("A", 3.2), ("B", 4.1), ("A", 2.8), ("B", 3.5), ("C", 2.1)],
        MappingSpec(x="sample_id", y="shannon_entropy"),
    ),
    (
        "phylogenetic_heatmap",
        ["sample_id", "asv_id", "abundance"],
        [("S1", "f1", 2), ("S1", "f2", 8), ("S2", "f1", 15), ("S2", "f2", 3)],
        None,  # exempt; defaults feature_col="asv_id"
    ),
]


@pytest.mark.skipif(not HAS_MPL, reason="matplotlib not installed")
@pytest.mark.parametrize("plot_key,columns,rows,mapping", _plot_data)
def test_smoke_all_renderers(plot_key, columns, rows, mapping, palette, theme):
    """Every registered plot function renders without error on synthetic data."""
    plot_fn = PLOT_FUNCTIONS[plot_key]
    tsv = _make_synthetic_tsv([dict(zip(columns, r)) for r in rows])
    try:
        spec = make_minimal_fig_spec(
            tmp_path=tsv.parent,
            figure_type=plot_key,
            mapping=mapping,
        )
        # Override data table to our synthetic TSV
        spec.data.table = tsv
        data = pd.read_csv(tsv, sep="\t")
        fig, ax = plt.subplots()
        try:
            plot_fn(spec, data, ax, palette, theme)
        finally:
            plt.close(fig)
    finally:
        tsv.unlink()


def test_all_plot_types_registered():
    """All 15 plot functions are registered in PLOT_FUNCTIONS."""
    expected = {
        "barplot",
        "boxplot_with_points",
        "violin_with_box",
        "scatterplot",
        "ordination_plot",
        "stacked_barplot",
        "heatmap",
        "volcano_plot",
        "lineplot",
        "phylum_stacked_bar",
        "genus_heatmap",
        "pcoa_plot",
        "differential_volcano",
        "alpha_stats_boxplot",
        "phylogenetic_heatmap",
    }
    assert set(PLOT_FUNCTIONS.keys()) == expected
