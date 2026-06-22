"""P0 plot functions for abi_sciplot.

Each plot function follows the same contract:

    def plot_<type>(spec: FigureSpec, data: pd.DataFrame, ax: Axes,
                    palette: PaletteRegistry, theme: ThemeSpec) -> None

The function draws on *ax* and returns None.  The caller (MatplotlibRenderer)
handles figure creation, theme application, label setting, export, provenance,
and linting.

Plot functions MUST NOT:
- Read files (data is passed as a DataFrame)
- Save files (export is handled by the renderer)
- Write provenance
- Apply themes

They SHOULD:
- Validate that the required mapping columns exist in the DataFrame
- Raise clear, descriptive errors when data is insufficient
"""

from __future__ import annotations

from typing import Callable, Dict

from abi.sciplot.renderers.plots.alpha_stats_boxplot import plot_alpha_stats_boxplot
from abi.sciplot.renderers.plots.barplot import plot_barplot
from abi.sciplot.renderers.plots.boxplot_with_points import plot_boxplot_with_points
from abi.sciplot.renderers.plots.differential_volcano import plot_differential_volcano
from abi.sciplot.renderers.plots.genus_heatmap import plot_genus_heatmap
from abi.sciplot.renderers.plots.heatmap import plot_heatmap
from abi.sciplot.renderers.plots.lineplot import plot_lineplot
from abi.sciplot.renderers.plots.ordination_plot import plot_ordination
from abi.sciplot.renderers.plots.pcoa_plot import plot_pcoa_plot
from abi.sciplot.renderers.plots.phylogenetic_heatmap import plot_phylogenetic_heatmap
from abi.sciplot.renderers.plots.phylum_stacked_bar import plot_phylum_stacked_bar
from abi.sciplot.renderers.plots.scatterplot import plot_scatterplot
from abi.sciplot.renderers.plots.stacked_barplot import plot_stacked_barplot
from abi.sciplot.renderers.plots.violin_with_box import plot_violin_with_box
from abi.sciplot.renderers.plots.volcano_plot import plot_volcano

PLOT_FUNCTIONS: Dict[str, Callable[..., None]] = {
    "barplot": plot_barplot,
    "boxplot_with_points": plot_boxplot_with_points,
    "violin_with_box": plot_violin_with_box,
    "scatterplot": plot_scatterplot,
    "ordination_plot": plot_ordination,
    "stacked_barplot": plot_stacked_barplot,
    "heatmap": plot_heatmap,
    "volcano_plot": plot_volcano,
    "lineplot": plot_lineplot,
    # Biological-grade plot types (v1.4.0)
    "phylum_stacked_bar": plot_phylum_stacked_bar,
    "genus_heatmap": plot_genus_heatmap,
    "pcoa_plot": plot_pcoa_plot,
    "differential_volcano": plot_differential_volcano,
    "alpha_stats_boxplot": plot_alpha_stats_boxplot,
    "phylogenetic_heatmap": plot_phylogenetic_heatmap,
}

__all__ = [
    "PLOT_FUNCTIONS",
    "plot_barplot",
    "plot_boxplot_with_points",
    "plot_violin_with_box",
    "plot_scatterplot",
    "plot_ordination",
    "plot_stacked_barplot",
    "plot_heatmap",
    "plot_volcano",
    "plot_lineplot",
    "plot_phylum_stacked_bar",
    "plot_genus_heatmap",
    "plot_pcoa_plot",
    "plot_differential_volcano",
    "plot_alpha_stats_boxplot",
    "plot_phylogenetic_heatmap",
]
