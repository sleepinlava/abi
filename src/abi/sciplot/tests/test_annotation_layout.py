"""Regression tests for annotations obscuring plotted data points."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast
from unittest.mock import patch

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytest
from matplotlib.transforms import Bbox

from abi.sciplot.renderers.annotation_layout import annotate_points_without_overlap
from abi.sciplot.renderers.plots import PLOT_FUNCTIONS
from abi.sciplot.schema.palette_spec import PaletteRegistry
from abi.sciplot.schema.theme_spec import ThemeSpec

from .conftest import make_minimal_fig_spec
from .real_world_data import PLOT_TABLES, REAL_WORLD_BATCHES


@pytest.mark.parametrize(
    "plot_key",
    [
        "scatterplot",
        "ordination_plot",
        "volcano_plot",
        "differential_volcano",
        "alpha_stats_boxplot",
    ],
)
def test_annotations_do_not_cover_data_points(
    tmp_path: Path,
    plot_key: str,
    palette: PaletteRegistry,
    theme: ThemeSpec,
) -> None:
    """Text bounding boxes must not contain the centre of a plotted point."""
    batch = REAL_WORLD_BATCHES["antibiotic_cohort"]
    table_name, mapping = PLOT_TABLES[plot_key]
    columns, rows = batch["tables"][table_name]
    data = pd.DataFrame(rows, columns=columns)
    spec = make_minimal_fig_spec(tmp_path, plot_key, mapping=mapping)
    if plot_key == "ordination_plot":
        spec.mapping.hue = None

    with plt.style.context(theme.to_matplotlib_rcparams()):
        fig, ax = plt.subplots()
        try:
            PLOT_FUNCTIONS[plot_key](spec, data, ax, palette, theme)
            fig.canvas.draw()

            point_centres: list[np.ndarray] = []
            for collection in ax.collections:
                offsets = np.asarray(collection.get_offsets())
                if offsets.ndim != 2 or offsets.shape[1] != 2:
                    continue
                finite_offsets = offsets[np.isfinite(offsets).all(axis=1)]
                point_centres.extend(collection.get_offset_transform().transform(finite_offsets))

            renderer = cast(Any, fig.canvas).get_renderer()
            collisions = []
            text_bounds: list[Bbox] = []
            axes_bounds = ax.get_window_extent(renderer)
            for text in ax.texts:
                bounds = text.get_window_extent(renderer).padded(1.0)
                assert axes_bounds.contains(bounds.x0, bounds.y0)
                assert axes_bounds.contains(bounds.x1, bounds.y1)
                assert not any(bounds.overlaps(previous) for previous in text_bounds)
                text_bounds.append(bounds)
                for point in point_centres:
                    if bounds.contains(*point):
                        collisions.append(text.get_text())
                        break

            assert collisions == []
        finally:
            plt.close(fig)


def test_annotation_layout_draws_canvas_only_once(theme: ThemeSpec) -> None:
    """Dense plots must not trigger a complete redraw for every label candidate."""
    rng = np.random.default_rng(42)
    points = rng.normal(size=(10_000, 2))
    annotations = [
        (float(x), float(y), f"feature-{index}") for index, (x, y) in enumerate(points[:50])
    ]

    with plt.style.context(theme.to_matplotlib_rcparams()):
        fig, ax = plt.subplots()
        ax.scatter(points[:, 0], points[:, 1], s=4)
        try:
            with patch.object(fig.canvas, "draw", wraps=fig.canvas.draw) as draw:
                annotate_points_without_overlap(ax, annotations, points)
            assert draw.call_count == 1
        finally:
            plt.close(fig)


def test_mathtext_annotation_stays_inside_axes(theme: ThemeSpec) -> None:
    """Mathtext dimensions must use the same parser as the final annotation."""
    points = np.array([[0.95, 0.95], [0.5, 0.5]])

    with plt.style.context(theme.to_matplotlib_rcparams()):
        fig, ax = plt.subplots()
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.scatter(points[:, 0], points[:, 1])
        try:
            placed = annotate_points_without_overlap(
                ax,
                [(0.95, 0.95, r"$\alpha_{long\ label}$")],
                points,
            )
            fig.canvas.draw()
            renderer = cast(Any, fig.canvas).get_renderer()
            axes_bounds = ax.get_window_extent(renderer)
            assert len(placed) == 1
            bounds = placed[0].get_window_extent(renderer)
            assert axes_bounds.contains(bounds.x0, bounds.y0)
            assert axes_bounds.contains(bounds.x1, bounds.y1)
        finally:
            plt.close(fig)


def test_phylogenetic_note_is_not_drawn_over_heatmap_cells(
    tmp_path: Path,
    palette: PaletteRegistry,
    theme: ThemeSpec,
) -> None:
    """The phylogenetic feature-count note belongs outside the heatmap body."""
    batch = REAL_WORLD_BATCHES["antibiotic_cohort"]
    table_name, mapping = PLOT_TABLES["phylogenetic_heatmap"]
    columns, rows = batch["tables"][table_name]
    data = pd.DataFrame(rows, columns=columns)
    spec = make_minimal_fig_spec(tmp_path, "phylogenetic_heatmap", mapping=mapping)

    with plt.style.context(theme.to_matplotlib_rcparams()):
        fig, ax = plt.subplots()
        try:
            PLOT_FUNCTIONS["phylogenetic_heatmap"](spec, data, ax, palette, theme)
            assert not any("phylogenetic order" in text.get_text() for text in ax.texts)
        finally:
            plt.close(fig)
