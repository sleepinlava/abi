"""ABI figure engine — declarative figure generation from standard tables.

# Usage / 用法
    from abi.figures import FigureEngine, FigureSpec

    engine = FigureEngine(table_schemas, tables_dir, figures_dir)
    engine.load_specs("plugins/rnaseq/figure_specs.yaml")
    rendered = engine.render_all()
    # {"qc_read_counts": Path("figures/qc_read_counts.png"), ...}

# Extension / 扩展
To add a new figure type:
1. Implement a renderer function ``_render_<type>(spec, rows, ax)``.
2. Add it to ``_RENDERERS`` in ``base.py``.
3. Add the type name to ``VALID_FIGURE_TYPES``.
"""

from abi.figures.base import (
    VALID_FIGURE_TYPES,
    FigureEngine,
    FigureError,
    FigureSpec,
    render_figure,
)

__all__ = [
    "FigureEngine",
    "FigureError",
    "FigureSpec",
    "VALID_FIGURE_TYPES",
    "render_figure",
]
