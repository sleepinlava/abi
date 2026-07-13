"""Small annotation-layout helpers shared by point-based renderers."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, cast

import numpy as np
from matplotlib import cbook
from matplotlib.axes import Axes
from matplotlib.font_manager import FontProperties
from matplotlib.text import Annotation
from matplotlib.transforms import Bbox

_CANDIDATE_OFFSETS = (
    (6, 6),
    (-6, 6),
    (6, -6),
    (-6, -6),
    (10, 0),
    (-10, 0),
    (0, 10),
    (0, -10),
    (14, 8),
    (-14, 8),
    (14, -8),
    (-14, -8),
)


def annotate_points_without_overlap(
    ax: Axes,
    annotations: Iterable[tuple[float, float, str]],
    points: np.ndarray,
    *,
    fontsize: float = 5,
    arrow: bool = False,
) -> list[Annotation]:
    """Place point labels without covering point centres or earlier labels."""
    figure = ax.figure
    figure.canvas.draw()
    renderer = cast(Any, figure.canvas).get_renderer()
    point_pixels = ax.transData.transform(np.asarray(points, dtype=float))
    axes_bounds = ax.get_window_extent(renderer).padded(-1.0)
    font_properties = FontProperties(size=fontsize)
    pixels_per_point = figure.dpi / 72.0
    placed: list[Annotation] = []
    occupied: list[Bbox] = []

    for x_value, y_value, label in annotations:
        chosen_bounds: Bbox | None = None
        chosen_offset: tuple[int, int] | None = None
        anchor_x, anchor_y = ax.transData.transform((x_value, y_value))
        width, height, _ = renderer.get_text_width_height_descent(
            label,
            font_properties,
            ismath=cbook.is_math_text(label),
        )
        for x_offset, y_offset in _CANDIDATE_OFFSETS:
            offset_x = x_offset * pixels_per_point
            offset_y = y_offset * pixels_per_point
            if x_offset >= 0:
                left, right = anchor_x + offset_x, anchor_x + offset_x + width
            else:
                left, right = anchor_x + offset_x - width, anchor_x + offset_x
            if y_offset >= 0:
                bottom, top = anchor_y + offset_y, anchor_y + offset_y + height
            else:
                bottom, top = anchor_y + offset_y - height, anchor_y + offset_y
            bounds = Bbox.from_extents(left, bottom, right, top).padded(1.0)
            inside_axes = axes_bounds.contains(bounds.x0, bounds.y0) and axes_bounds.contains(
                bounds.x1, bounds.y1
            )
            covers_point = bool(
                np.any(
                    (point_pixels[:, 0] >= bounds.x0)
                    & (point_pixels[:, 0] <= bounds.x1)
                    & (point_pixels[:, 1] >= bounds.y0)
                    & (point_pixels[:, 1] <= bounds.y1)
                )
            )
            covers_label = any(bounds.overlaps(previous) for previous in occupied)
            if inside_axes and not covers_point and not covers_label:
                chosen_bounds = bounds
                chosen_offset = (x_offset, y_offset)
                break

        if chosen_offset is None:
            continue

        assert chosen_bounds is not None
        x_offset, y_offset = chosen_offset
        chosen = ax.annotate(
            label,
            (x_value, y_value),
            fontsize=fontsize,
            alpha=0.8,
            xytext=chosen_offset,
            textcoords="offset points",
            ha="left" if x_offset >= 0 else "right",
            va="bottom" if y_offset >= 0 else "top",
            arrowprops=(
                {"arrowstyle": "-", "color": "grey", "alpha": 0.3, "linewidth": 0.5}
                if arrow
                else None
            ),
        )
        placed.append(chosen)
        occupied.append(chosen_bounds)

    return placed


def reserve_top_annotation_band(ax: Axes, fraction: float = 0.16) -> None:
    """Add an empty band above the current y-range for fixed annotations."""
    lower, upper = ax.get_ylim()
    span = upper - lower
    if span > 0:
        ax.set_ylim(lower, upper + span * fraction / (1.0 - fraction))
