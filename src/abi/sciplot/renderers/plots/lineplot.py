"""Line plot renderer with optional categorical grouping."""

from __future__ import annotations

import pandas as pd
from matplotlib.axes import Axes

from abi.sciplot.schema.figure_spec import FigureSpec
from abi.sciplot.schema.palette_spec import PaletteRegistry
from abi.sciplot.schema.theme_spec import ThemeSpec


def plot_lineplot(
    spec: FigureSpec,
    data: pd.DataFrame,
    ax: Axes,
    palette: PaletteRegistry,
    theme: ThemeSpec,
) -> None:
    """Draw a line from ``mapping.x`` and ``mapping.y`` values.

    ``mapping.hue`` optionally creates one independently sorted line per
    category. Non-numeric y values are discarded instead of being coerced to
    zero, which avoids inventing observations in scientific plots.
    """
    del theme  # Styling is applied by MatplotlibRenderer.
    x_col = spec.mapping.x
    y_col = spec.mapping.y
    hue_col = spec.mapping.hue

    if x_col is None or y_col is None:
        raise ValueError("lineplot requires both mapping.x and mapping.y.")
    missing = [column for column in (x_col, y_col, hue_col) if column and column not in data]
    if missing:
        raise ValueError(f"Lineplot column(s) not found in data: {', '.join(missing)}")

    frame = data[[x_col, y_col, *([hue_col] if hue_col else [])]].copy()
    frame[y_col] = pd.to_numeric(frame[y_col], errors="coerce")
    frame = frame.dropna(subset=[x_col, y_col])
    if frame.empty:
        raise ValueError("lineplot has no valid x/y observations after numeric conversion.")

    if hue_col:
        groups = list(frame.groupby(hue_col, sort=True, dropna=False))
        colors = palette.get_categorical(spec.style.palette, n=len(groups))
        for index, (group_name, group) in enumerate(groups):
            group = group.sort_values(x_col)
            ax.plot(
                group[x_col],
                group[y_col],
                label=str(group_name),
                color=colors[index % len(colors)],
                marker="o",
                markersize=3,
                linewidth=1.2,
            )
        ax.legend(title=spec.labels.legend_title)
    else:
        frame = frame.sort_values(x_col)
        color = palette.get_categorical(spec.style.palette, n=1)[0]
        ax.plot(
            frame[x_col],
            frame[y_col],
            color=color,
            marker="o",
            markersize=3,
            linewidth=1.2,
        )
