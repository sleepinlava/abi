from __future__ import annotations

import pytest

plt = pytest.importorskip("matplotlib.pyplot", exc_type=ImportError)
pd = pytest.importorskip("pandas", exc_type=ImportError)

from abi.sciplot.renderers.plots import PLOT_FUNCTIONS  # noqa: E402
from abi.sciplot.renderers.plots.lineplot import plot_lineplot  # noqa: E402
from abi.sciplot.schema.figure_spec import FigureSpec  # noqa: E402
from abi.sciplot.schema.palette_spec import PaletteRegistry  # noqa: E402
from abi.sciplot.schema.theme_spec import ThemeSpec  # noqa: E402


def _spec(tmp_path, *, hue: str | None = None) -> FigureSpec:
    return FigureSpec(
        figure_id="trend",
        figure_type="lineplot",
        data={"table": tmp_path / "data.tsv", "format": "tsv"},
        mapping={"x": "time", "y": "value", "hue": hue},
        labels={"legend_title": "Group"},
        export={"output_dir": tmp_path, "basename": "trend", "formats": ["png"]},
    )


def test_lineplot_is_registered_and_draws_grouped_lines(tmp_path):
    spec = _spec(tmp_path, hue="group")
    data = pd.DataFrame(
        {
            "time": [2, 1, 2, 1],
            "value": [4.0, 2.0, 3.0, 1.0],
            "group": ["B", "B", "A", "A"],
        }
    )
    palette = PaletteRegistry()
    palette.load_builtins()
    figure, ax = plt.subplots()
    try:
        plot_lineplot(spec, data, ax, palette, ThemeSpec(theme_name="test"))
        assert PLOT_FUNCTIONS["lineplot"] is plot_lineplot
        assert len(ax.lines) == 2
        assert list(ax.lines[0].get_xdata()) == [1, 2]
        assert ax.get_legend().get_title().get_text() == "Group"
    finally:
        plt.close(figure)


def test_lineplot_rejects_missing_columns(tmp_path):
    spec = _spec(tmp_path)
    figure, ax = plt.subplots()
    try:
        with pytest.raises(ValueError, match="value"):
            plot_lineplot(
                spec,
                pd.DataFrame({"time": [1, 2]}),
                ax,
                PaletteRegistry(),
                ThemeSpec(theme_name="test"),
            )
    finally:
        plt.close(figure)
