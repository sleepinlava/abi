"""Contract tests — every plot function in PLOT_FUNCTIONS conforms to the renderer interface.

Verifies:
- All 15 plot functions are registered
- Every value is callable
- Every function accepts 5 positional arguments (spec, data, ax, palette, theme)
- Every function is importable from its submodule
- Every function renders without error on synthetic data (MPL smoke)
"""

from __future__ import annotations

import importlib
import inspect
from pathlib import Path

import matplotlib
import numpy as np
import pandas as pd
import pytest

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from abi.sciplot.renderers.plots import PLOT_FUNCTIONS

# ── matplotlib guard ─────────────────────────────────────────────────────────

try:
    import matplotlib  # noqa: F811

    HAS_MPL = True
except ImportError:
    HAS_MPL = False

# ── Expected plot keys / 期望的绘图键 ─────────────────────────────────────────

_EXPECTED_PLOT_KEYS: set[str] = {
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

# Map PLOT_FUNCTIONS key → submodule function name (differs for ordination / volcano).
_KEY_TO_FN_NAME: dict[str, str] = {
    "ordination_plot": "plot_ordination",
    "volcano_plot": "plot_volcano",
}
for _k in _EXPECTED_PLOT_KEYS:
    if _k not in _KEY_TO_FN_NAME:
        _KEY_TO_FN_NAME[_k] = f"plot_{_k}"


# ── Helper: build a minimal FigureSpec for a given type / 最简 FigureSpec ─────


def _make_minimal_fig_spec(
    tmp_path: Path,
    figure_type: str,
    mapping: dict | None = None,
):
    """Create a ``FigureSpec`` with a placeholder table and optional mapping."""
    from abi.sciplot.schema.figure_spec import (
        DataSpec,
        ExportSpec,
        FigureSpec,
        MappingSpec,
    )

    table = tmp_path / f"{figure_type}.tsv"
    table.write_text("placeholder\n", encoding="utf-8")

    return FigureSpec(
        figure_id=figure_type,
        figure_type=figure_type,
        data=DataSpec(table=table),
        mapping=MappingSpec(**(mapping or {})),
        export=ExportSpec(
            output_dir=tmp_path / "figures",
            basename=figure_type,
        ),
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Test 1: All 15 plot functions are registered
# ═══════════════════════════════════════════════════════════════════════════════


def test_all_plot_functions_registered() -> None:
    """len(PLOT_FUNCTIONS) == 15 and every expected key is present."""
    assert len(PLOT_FUNCTIONS) == len(_EXPECTED_PLOT_KEYS), (
        f"Expected {len(_EXPECTED_PLOT_KEYS)} plot functions, got {len(PLOT_FUNCTIONS)}"
    )

    registered = set(PLOT_FUNCTIONS.keys())
    missing = _EXPECTED_PLOT_KEYS - registered
    extra = registered - _EXPECTED_PLOT_KEYS

    assert not missing, f"Missing plot keys: {sorted(missing)}"
    assert not extra, f"Unexpected plot keys: {sorted(extra)}"


# ═══════════════════════════════════════════════════════════════════════════════
# Test 2: Every value is callable
# ═══════════════════════════════════════════════════════════════════════════════


def test_all_plot_functions_are_callable() -> None:
    """Every value in PLOT_FUNCTIONS is callable."""
    for key, fn in PLOT_FUNCTIONS.items():
        assert callable(fn), f"PLOT_FUNCTIONS['{key}'] is not callable (type={type(fn).__name__})"


# ═══════════════════════════════════════════════════════════════════════════════
# Test 3: Every function accepts 5 positional arguments
# ═══════════════════════════════════════════════════════════════════════════════


def test_all_plot_functions_accept_correct_signature() -> None:
    """Every function accepts exactly 5 parameters (spec, data, ax, palette, theme)."""
    for key, fn in PLOT_FUNCTIONS.items():
        sig = inspect.signature(fn)
        params = list(sig.parameters.values())

        # Count parameters excluding positional-only separator and *args/**kwargs
        named = [
            p
            for p in params
            if p.kind
            in (
                inspect.Parameter.POSITIONAL_ONLY,
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                inspect.Parameter.KEYWORD_ONLY,
            )
        ]

        assert len(named) == 5, (
            f"'{key}' has {len(named)} named parameters, expected 5. Signature: {sig}"
        )

        expected_names = ["spec", "data", "ax", "palette", "theme"]
        for param, expected in zip(named, expected_names):
            assert param.name == expected, (
                f"'{key}' parameter mismatch: expected '{expected}', got '{param.name}'. "
                f"Signature: {sig}"
            )


# ═══════════════════════════════════════════════════════════════════════════════
# Test 4: Every plot function is importable from its submodule
# ═══════════════════════════════════════════════════════════════════════════════


def test_all_plot_functions_importable_from_package() -> None:
    """Every plot function can be imported by name from its submodule."""
    for key, expected_fn_name in _KEY_TO_FN_NAME.items():
        module_path = f"abi.sciplot.renderers.plots.{key}"
        try:
            mod = importlib.import_module(module_path)
        except ImportError as exc:
            pytest.fail(f"Could not import module '{module_path}' for key '{key}': {exc}")

        fn = getattr(mod, expected_fn_name, None)
        assert fn is not None, (
            f"Function '{expected_fn_name}' not found in module '{module_path}' (key='{key}')"
        )
        assert callable(fn), f"'{expected_fn_name}' in '{module_path}' is not callable"


# ═══════════════════════════════════════════════════════════════════════════════
# Test 5: Smoke render — every plot function succeeds with synthetic data
# ═══════════════════════════════════════════════════════════════════════════════

# Synthetic data + mapping dispatch per figure type / 各图形类型的合成数据
_SPEC_DATA_DISPATCH: dict[str, tuple[pd.DataFrame, dict[str, str]]] = {}


def _register(
    figure_type: str,
    columns: list[str],
    rows: list[list],
    mapping: dict[str, str],
) -> None:
    _SPEC_DATA_DISPATCH[figure_type] = (pd.DataFrame(rows, columns=columns), mapping)


# -- Basic plot types --
_register(
    "barplot", ["label", "value"], [["A", 1], ["B", 2], ["C", 3]], {"x": "label", "y": "value"}
)
_register(
    "boxplot_with_points",
    ["group", "value"],
    [["A", 1.0], ["A", 2.0], ["B", 3.0], ["B", 4.0], ["C", 5.0]],
    {"x": "group", "y": "value"},
)
_register(
    "violin_with_box",
    ["group", "value"],
    [["A", 1.0], ["A", 2.0], ["B", 3.0], ["B", 4.0], ["C", 5.0]],
    {"x": "group", "y": "value"},
)
_register(
    "scatterplot", ["x", "y"], [[1, 2], [2, 4], [3, 6], [4, 8], [5, 10]], {"x": "x", "y": "y"}
)
_register(
    "ordination_plot",
    ["sample", "PC1", "PC2", "group"],
    [["S1", 1.0, 2.0, "A"], ["S2", 2.0, 4.0, "B"], ["S3", 3.0, 6.0, "A"]],
    {"x": "sample", "hue": "group"},
)
_register(
    "stacked_barplot",
    ["sample", "value1", "value2"],
    [["S1", 10, 20], ["S2", 15, 25]],
    {"x": "sample"},
)
_register(
    "heatmap", ["sample", "col1", "col2"], [["S1", 1.0, 2.0], ["S2", 3.0, 4.0]], {"x": "sample"}
)
_register("lineplot", ["x", "y"], [[1, 2], [2, 4], [3, 6], [4, 8], [5, 10]], {"x": "x", "y": "y"})

# -- Volcano plot: 100 rows of random differential expression --
_volc_rng = np.random.default_rng(99)
_volc_data = pd.DataFrame(
    {
        "gene_id": [f"GENE_{i:04d}" for i in range(100)],
        "log2FoldChange": _volc_rng.normal(0, 1.5, size=100),
        "padj": 10 ** _volc_rng.uniform(-3, 0, size=100),
    }
)
_SPEC_DATA_DISPATCH["volcano_plot"] = (
    _volc_data,
    {"x": "log2FoldChange", "y": "padj", "label": "gene_id"},
)

# -- Biological-grade plot types --
_register(
    "phylum_stacked_bar",
    ["sample_id", "phylum", "abundance"],
    [["S1", "P1", 8], ["S1", "P2", 2], ["S2", "P1", 3], ["S2", "P2", 7]],
    {"x": "sample_id", "y": "abundance", "hue": "phylum"},
)
_register(
    "genus_heatmap",
    ["sample_id", "genus", "abundance"],
    [["S1", "G1", 8], ["S2", "G1", 2], ["S1", "G2", 3], ["S2", "G2", 7]],
    {"x": "sample_id", "y": "abundance"},
)
_register(
    "pcoa_plot",
    ["sample_a", "sample_b", "distance"],
    [["a", "b", 0.5], ["a", "c", 0.3], ["b", "c", 0.4]],
    {},
)
_register(
    "differential_volcano",
    ["feature", "log2fc", "padj"],
    [["A", 2.0, 0.01], ["B", -2.0, 0.02], ["C", 0.0, 0.8]],
    {"x": "log2fc", "y": "padj", "label": "feature"},
)
_register(
    "alpha_stats_boxplot",
    ["sample_id", "shannon", "group"],
    [["S1", 1.0, "A"], ["S2", 1.2, "A"], ["S3", 2.0, "B"], ["S4", 2.2, "B"]],
    {"x": "sample_id", "y": "shannon", "hue": "group"},
)
_register(
    "phylogenetic_heatmap",
    ["sample_id", "asv_id", "abundance"],
    [["S1", "A", 3], ["S2", "A", 4], ["S1", "B", 8], ["S2", "B", 2]],
    {"x": "sample_id", "y": "abundance", "label": "asv_id"},
)


@pytest.mark.skipif(not HAS_MPL, reason="matplotlib is not installed")
@pytest.mark.parametrize(
    "figure_type,plot_function",
    [(key, PLOT_FUNCTIONS[key]) for key in sorted(PLOT_FUNCTIONS.keys())],
)
def test_all_plot_functions_render_smoke(
    figure_type: str,
    plot_function,
    tmp_path: Path,
    palette,
    theme,
) -> None:
    """Every plot function renders on synthetic data without error and adds artists to axes."""
    assert figure_type in _SPEC_DATA_DISPATCH, (
        f"No synthetic data registered for '{figure_type}'. "
        f"Available: {sorted(_SPEC_DATA_DISPATCH.keys())}"
    )

    data, mapping = _SPEC_DATA_DISPATCH[figure_type]
    spec = _make_minimal_fig_spec(tmp_path, figure_type, mapping)

    fig, ax = plt.subplots()
    try:
        plot_function(spec, data, ax, palette, theme)
        assert ax.has_data(), f"'{figure_type}' rendered but ax.has_data() is False"
    finally:
        plt.close(fig)
