"""Focused tests for the barplot renderer."""

from __future__ import annotations

import matplotlib
import pandas as pd
import pytest

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from abi.sciplot.renderers.plots.barplot import plot_barplot
from abi.sciplot.schema.figure_spec import DataSpec, ExportSpec, FigureSpec, MappingSpec
from abi.sciplot.schema.palette_spec import PaletteRegistry
from abi.sciplot.schema.theme_spec import ThemeSpec


def _spec(tmp_path, *, y: str | None = "percent", hue: str | None = "group") -> FigureSpec:
    return FigureSpec(
        figure_id="grouped_evidence_rates",
        figure_type="barplot",
        data=DataSpec(table=tmp_path / "data.tsv"),
        mapping=MappingSpec(x="evidence", y=y, hue=hue),
        export=ExportSpec(output_dir=tmp_path, basename="rates"),
    )


def _palette() -> PaletteRegistry:
    palette = PaletteRegistry()
    palette.load_builtins()
    return palette


def test_barplot_renders_hue_as_side_by_side_groups(tmp_path) -> None:
    data = pd.DataFrame(
        {
            "evidence": ["Circular", "Circular", "Replicon", "Replicon"],
            "group": ["TP", "FP", "TP", "FP"],
            "percent": [50, 25, 75, 10],
        }
    )
    figure, axis = plt.subplots()
    try:
        plot_barplot(_spec(tmp_path), data, axis, _palette(), ThemeSpec(theme_name="test"))
        assert len(axis.patches) == 4
        assert [tick.get_text() for tick in axis.get_xticklabels()] == ["Circular", "Replicon"]
        assert [text.get_text() for text in axis.get_legend().get_texts()] == ["TP", "FP"]
        assert sorted(patch.get_height() for patch in axis.patches) == [10, 25, 50, 75]
    finally:
        plt.close(figure)


def test_barplot_rejects_hue_without_value_mapping(tmp_path) -> None:
    figure, axis = plt.subplots()
    try:
        with pytest.raises(ValueError, match="mapping.hue requires mapping.y"):
            plot_barplot(
                _spec(tmp_path, y=None),
                pd.DataFrame({"evidence": ["Circular"], "group": ["TP"]}),
                axis,
                _palette(),
                ThemeSpec(theme_name="test"),
            )
    finally:
        plt.close(figure)
