"""End-to-end coverage for Unicode text in all registered plot types."""

from __future__ import annotations

import warnings
from pathlib import Path

import pandas as pd
import pytest
from matplotlib import font_manager
from matplotlib import image as mpimg

from abi.sciplot.renderers.matplotlib_renderer import MatplotlibRenderer
from abi.sciplot.schema.figure_spec import ExportSpec
from abi.sciplot.schema.theme_spec import FontSpec, ThemeSpec

from .conftest import make_minimal_fig_spec
from .real_world_data import PLOT_TABLES, REAL_WORLD_BATCHES

CJK_FONT_CANDIDATES = (
    "Noto Sans CJK SC",
    "Source Han Sans SC",
    "Microsoft YaHei",
    "PingFang SC",
    "WenQuanYi Zen Hei",
    "Droid Sans Fallback",
)


def _available_cjk_font() -> str | None:
    for family in CJK_FONT_CANDIDATES:
        try:
            font_manager.findfont(family, fallback_to_default=False)
        except ValueError:
            continue
        return family
    return None


CJK_FONT = _available_cjk_font()


@pytest.mark.parametrize("batch_name", REAL_WORLD_BATCHES)
@pytest.mark.parametrize("plot_key", PLOT_TABLES)
def test_two_real_world_batches_export_all_plot_types(
    tmp_path: Path,
    batch_name: str,
    plot_key: str,
) -> None:
    """Both realistic batches survive every renderer and final PNG export."""
    batch = REAL_WORLD_BATCHES[batch_name]
    if batch["requires_cjk"] and CJK_FONT is None:
        pytest.fail(
            "No supported CJK font is installed; install fonts-wqy-zenhei before running tests"
        )

    table_name, mapping = PLOT_TABLES[plot_key]
    columns, rows = batch["tables"][table_name]
    table = tmp_path / f"{batch_name}-{table_name}.tsv"
    pd.DataFrame(rows, columns=columns).to_csv(table, sep="\t", index=False, encoding="utf-8")
    spec = make_minimal_fig_spec(tmp_path, plot_key, mapping=mapping)
    spec.data.table = table
    spec.labels.title = batch["title"]
    spec.export = ExportSpec(
        output_dir=tmp_path / "figures",
        basename=f"{batch_name}-{plot_key}",
        formats=["png"],
    )
    theme = ThemeSpec(theme_name="unicode-test")

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        result = MatplotlibRenderer(theme=theme).render(spec)

    missing_glyphs = [warning for warning in caught if "Glyph" in str(warning.message)]
    assert result.errors == []
    assert missing_glyphs == []
    assert len(result.output_files) == 1
    image = mpimg.imread(result.output_files[0])
    assert image.shape[0] > 10 and image.shape[1] > 10
    assert image.var() > 0


def test_theme_passes_primary_and_fallback_fonts_to_matplotlib() -> None:
    """The configured fallback chain must reach Matplotlib rcParams."""
    theme = ThemeSpec(
        theme_name="font-chain-test",
        font=FontSpec(family="DejaVu Sans", fallback=["DejaVu Serif", "sans-serif"]),
    )

    rcparams = theme.to_matplotlib_rcparams()

    assert rcparams["font.family"] == ["DejaVu Sans", "DejaVu Serif", "sans-serif"]
