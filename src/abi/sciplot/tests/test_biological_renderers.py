from __future__ import annotations

from pathlib import Path

import matplotlib
import pandas as pd
from typer.testing import CliRunner

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from abi.sciplot.api import load_spec, render_figure, validate_spec
from abi.sciplot.cli import app
from abi.sciplot.renderers.plots.alpha_stats_boxplot import plot_alpha_stats_boxplot
from abi.sciplot.renderers.plots.barplot import plot_barplot
from abi.sciplot.renderers.plots.differential_volcano import plot_differential_volcano
from abi.sciplot.renderers.plots.genus_heatmap import plot_genus_heatmap
from abi.sciplot.renderers.plots.pcoa_plot import plot_pcoa_plot
from abi.sciplot.renderers.plots.phylogenetic_heatmap import plot_phylogenetic_heatmap
from abi.sciplot.renderers.plots.phylum_stacked_bar import plot_phylum_stacked_bar
from abi.sciplot.schema.figure_spec import DataSpec, ExportSpec, FigureSpec, MappingSpec
from abi.sciplot.schema.palette_spec import PaletteRegistry
from abi.sciplot.schema.theme_spec import ThemeSpec


def _registry() -> PaletteRegistry:
    registry = PaletteRegistry()
    registry.load_builtins()
    return registry


def _spec(tmp_path: Path, figure_type: str, mapping: MappingSpec) -> FigureSpec:
    table = tmp_path / f"{figure_type}.tsv"
    table.write_text("placeholder\n", encoding="utf-8")
    return FigureSpec(
        figure_id=figure_type,
        figure_type=figure_type,
        data=DataSpec(table=table),
        mapping=mapping,
        export=ExportSpec(output_dir=tmp_path / "figures", basename=figure_type),
    )


def test_all_previously_uncovered_biological_renderers(tmp_path):
    cases = [
        (
            plot_pcoa_plot,
            "pcoa_plot",
            pd.DataFrame(
                {
                    "sample_a": ["S1", "S1", "S2"],
                    "sample_b": ["S2", "S3", "S3"],
                    "distance": [0.5, 0.5, 0.5],
                }
            ),
            MappingSpec(),
        ),
        (
            plot_phylogenetic_heatmap,
            "phylogenetic_heatmap",
            pd.DataFrame(
                {
                    "sample_id": ["S1", "S2", "S1", "S2"],
                    "asv_id": ["A", "A", "B", "B"],
                    "abundance": [3, 4, 8, 2],
                }
            ),
            MappingSpec(x="sample_id", y="abundance", label="asv_id"),
        ),
        (
            plot_differential_volcano,
            "differential_volcano",
            pd.DataFrame(
                {"feature": ["A", "B", "C"], "log2fc": [2, -2, 0], "padj": [0.01, 0.02, 0.8]}
            ),
            MappingSpec(x="log2fc", y="padj", label="feature"),
        ),
        (
            plot_alpha_stats_boxplot,
            "alpha_stats_boxplot",
            pd.DataFrame(
                {
                    "sample_id": ["S1", "S2", "S3", "S4"],
                    "shannon": [1.0, 1.2, 2.0, 2.2],
                    "group": ["A", "A", "B", "B"],
                }
            ),
            MappingSpec(x="sample_id", y="shannon", hue="group"),
        ),
        (
            plot_phylum_stacked_bar,
            "phylum_stacked_bar",
            pd.DataFrame(
                {
                    "sample_id": ["S1", "S1", "S2", "S2"],
                    "phylum": ["P1", "P2", "P1", "P2"],
                    "abundance": [8, 2, 3, 7],
                }
            ),
            MappingSpec(x="sample_id", y="abundance", hue="phylum"),
        ),
        (
            plot_genus_heatmap,
            "genus_heatmap",
            pd.DataFrame(
                {
                    "sample_id": ["S1", "S2", "S1", "S2"],
                    "genus": ["G1", "G1", "G2", "G2"],
                    "abundance": [8, 2, 3, 7],
                }
            ),
            MappingSpec(x="sample_id", y="abundance"),
        ),
        (
            plot_barplot,
            "barplot",
            pd.DataFrame({"label": ["A", "B"], "value": [1, 2]}),
            MappingSpec(x="label", y="value"),
        ),
    ]
    palette = _registry()
    theme = ThemeSpec(theme_name="test")
    for plot_function, figure_type, data, mapping in cases:
        fig, ax = plt.subplots()
        plot_function(_spec(tmp_path, figure_type, mapping), data, ax, palette, theme)
        assert ax.has_data()
        plt.close(fig)


def test_public_api_and_cli_render_path(tmp_path):
    table = tmp_path / "data.tsv"
    table.write_text("label\tvalue\nA\t1\nB\t2\n", encoding="utf-8")
    spec_path = tmp_path / "figure.yaml"
    spec_path.write_text(
        "\n".join(
            [
                "figure_id: api_bar",
                "figure_type: barplot",
                "data:",
                f"  table: {table}",
                "mapping:",
                "  x: label",
                "  y: value",
                "export:",
                f"  output_dir: {tmp_path / 'rendered'}",
                "  basename: api_bar",
                "  formats: [png]",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    spec = load_spec(spec_path)
    assert validate_spec(spec)["status"] == "ok"
    result = render_figure(spec)
    assert result.errors == []
    assert (tmp_path / "rendered" / "api_bar.png").exists()
    cli_result = CliRunner().invoke(app, ["list-plot-types"])
    assert cli_result.exit_code == 0
    assert "lineplot" in cli_result.stdout
