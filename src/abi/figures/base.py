"""Figure engine for ABI — generates publication-ready figures from standard tables.

# Purpose / 目的
The figure engine provides a declarative, plugin-agnostic way to generate
figures from ABI standard tables. Plugins declare figure specs in YAML;
the engine validates them against table schemas and renders them with
matplotlib (primary) or plotly (interactive fallback).

# Design / 设计
- **Declarative**: Plugins declare *what* to plot, not *how* to render.
- **Schema-validated**: Figure specs are validated against standard table schemas
  before rendering — no runtime KeyError from a renamed column.
- **Lazy imports**: matplotlib and plotly are imported at render time so plugins
  that don't use figures never pay the import cost.
- **Consistent styling**: All figures share a default style; plugins can
  override via spec fields (title, xlabel, ylabel, figsize, colormap).

# Figure types / 图表类型
- ``bar``: Vertical bar chart from a table column.
- ``scatter``: Scatter plot (x, y, optional label, optional color).
- ``volcano``: Volcano plot (x=log2FC, y=-log10(padj), labeled points).
- ``heatmap``: Matrix heatmap from a pivotable table.
- ``boxplot``: Box-and-whisker from grouped data.
- ``stacked_bar``: Stacked bar chart for compositional data.
- ``pca``: PCA scatter from a matrix table.
"""

from __future__ import annotations

from dataclasses import dataclass
from inspect import signature
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from abi._shared import _read_tsv

__all__ = [
    "FigureSpec",
    "FigureEngine",
    "VALID_FIGURE_TYPES",
    "render_figure",
]

VALID_FIGURE_TYPES = frozenset(
    {"bar", "scatter", "volcano", "heatmap", "boxplot", "stacked_bar", "pca"}
)


# ── Data model / 数据模型 ──────────────────────────────────────────────────


@dataclass
class FigureSpec:
    """Declaration of a single figure to generate.

    Mirrors the YAML ``figures:`` block in a plugin's ``figure_specs.yaml``.
    对应插件 ``figure_specs.yaml`` 中 ``figures:`` 块的声明。
    """

    id: str
    """Unique figure identifier within the plugin (e.g. ``qc_read_counts``)."""

    type: str
    """Figure type — one of ``bar``, ``scatter``, ``volcano``, ``heatmap``,
    ``boxplot``, ``stacked_bar``, ``pca``."""

    source_table: str
    """Standard table name (without ``.tsv``) to read data from."""

    x: str = ""
    """Column name for the x-axis."""

    y: str = ""
    """Column name for the y-axis."""

    label: str = ""
    """Column name for point labels (volcano, scatter with labels)."""

    color: str = ""
    """Column name for color grouping (scatter, boxplot)."""

    title: str = ""
    """Figure title. Defaults to ``id`` if empty."""

    xlabel: str = ""
    """X-axis label. Defaults to ``x`` column name if empty."""

    ylabel: str = ""
    """Y-axis label. Defaults to ``y`` column name if empty."""

    required: bool = False
    """If True, a missing or empty source table is an error; if False,
    the figure is skipped with a warning."""

    figsize: Tuple[float, float] = (10.0, 6.0)
    """Figure dimensions in inches (width, height)."""

    colormap: str = "viridis"
    """Matplotlib colormap name for heatmaps and grouped plots."""

    dpi: int = 150
    """Output resolution."""

    group: str = ""
    """Column name for grouping on the x-axis (boxplot, stacked_bar)."""

    top_n: int = 50
    """For volcano/heatmap: only label/render the top N significant points."""

    sort_by: str = ""
    """Column to sort by before plotting (for bar charts)."""

    ascending: bool = True
    """Sort direction for sort_by."""

    log_y: bool = False
    """Use log scale for y-axis."""

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "FigureSpec":
        """Build a FigureSpec from a YAML-parsed dict, ignoring unknown keys."""
        valid_fields = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        kwargs = {k: v for k, v in data.items() if k in valid_fields}
        if "figsize" in kwargs and isinstance(kwargs["figsize"], list):
            kwargs["figsize"] = tuple(kwargs["figsize"])
        return cls(**kwargs)

    def validate_against_schema(self, table_schemas: Mapping[str, Iterable[str]]) -> Optional[str]:
        """Return an error message if this spec references unknown tables/columns.

        Returns None if validation passes.
        """
        if self.source_table not in table_schemas:
            return (
                f"Figure '{self.id}' references unknown table "
                f"'{self.source_table}'. Known tables: "
                f"{sorted(table_schemas.keys())}"
            )
        columns = set(table_schemas[self.source_table])
        for field_name in ("x", "y", "label", "color", "group", "sort_by"):
            col = getattr(self, field_name)
            if col and col not in columns:
                return (
                    f"Figure '{self.id}' references unknown column "
                    f"'{col}' in table '{self.source_table}'. "
                    f"Known columns: {sorted(columns)}"
                )
        if self.type not in VALID_FIGURE_TYPES:
            return (
                f"Figure '{self.id}' has unknown type '{self.type}'. "
                f"Valid types: {sorted(VALID_FIGURE_TYPES)}"
            )
        return None


# ── Engine / 引擎 ─────────────────────────────────────────────────────────


class FigureEngine:
    """Validates figure specs and renders figures from standard tables.

    # Usage / 用法
        engine = FigureEngine(table_schemas, tables_dir, output_dir)
        engine.load_specs(plugin_root / "figure_specs.yaml")
        results = engine.render_all()

    # Error handling / 错误处理
    - Required figures with missing source data raise ``FigureError``.
    - Optional figures with missing data are skipped with a warning log.
    - Empty tables produce an empty figure with "No data available" text.
    """

    def __init__(
        self,
        table_schemas: Mapping[str, Iterable[str]],
        tables_dir: str | Path,
        figures_dir: str | Path,
    ) -> None:
        self._table_schemas = {name: list(cols) for name, cols in table_schemas.items()}
        self._tables_dir = Path(tables_dir)
        self._figures_dir = Path(figures_dir)
        self._figures_dir.mkdir(parents=True, exist_ok=True)
        self._specs: List[FigureSpec] = []
        self._errors: List[str] = []
        self._skipped: List[str] = []
        self._rendered: List[str] = []

    @property
    def specs(self) -> List[FigureSpec]:
        """Loaded figure specifications."""
        return list(self._specs)

    @property
    def errors(self) -> List[str]:
        """Validation and rendering errors."""
        return list(self._errors)

    def load_specs(self, source: str | Path | Sequence[Mapping[str, Any]]) -> None:
        """Load figure specs from a YAML path or a list of dicts.

        Accepts a path to a ``figure_specs.yaml`` file or a pre-parsed list
        of figure declaration dicts.  This dual interface lets plugins load
        from disk (typical) or construct specs programmatically (testing).
        """
        if isinstance(source, (str, Path)):
            from abi.config import load_yaml

            data = load_yaml(Path(source))
            items: Sequence[Mapping[str, Any]] = data.get("figures", [])
        else:
            items = source
        for item in items:
            spec = FigureSpec.from_dict(item)
            error = spec.validate_against_schema(self._table_schemas)
            if error:
                self._errors.append(error)
            else:
                self._specs.append(spec)

    def render_all(self) -> Dict[str, Path]:
        """Render all loaded specs. Returns ``{spec_id: output_path}``."""
        results: Dict[str, Path] = {}
        for spec in self._specs:
            try:
                path = render_figure(
                    spec,
                    tables_dir=self._tables_dir,
                    figures_dir=self._figures_dir,
                )
                if path is not None:
                    results[spec.id] = path
                    self._rendered.append(spec.id)
                else:
                    self._skipped.append(spec.id)
            except Exception as exc:
                msg = f"Figure '{spec.id}': {exc}"
                self._errors.append(msg)
                if spec.required:
                    raise FigureError(msg) from exc
        return results

    @property
    def rendered_count(self) -> int:
        return len(self._rendered)

    @property
    def skipped_count(self) -> int:
        return len(self._skipped)


class FigureError(Exception):
    """Raised when a required figure cannot be rendered."""


# ── Render dispatch / 渲染调度 ────────────────────────────────────────────


def render_figure(
    spec: FigureSpec,
    *,
    tables_dir: Path,
    figures_dir: Path,
) -> Optional[Path]:
    """Render a single figure spec to a .png file.

    Returns the output path on success, or None if the figure was skipped
    (optional figure with missing/empty source table).
    """
    figures_dir.mkdir(parents=True, exist_ok=True)
    output_path = figures_dir / f"{spec.id}.png"

    rows = _read_tsv(tables_dir / f"{spec.source_table}.tsv")
    if not rows:
        if spec.required:
            raise FigureError(
                f"Required figure '{spec.id}': source table "
                f"'{spec.source_table}.tsv' is empty or missing"
            )
        return None

    _render_with_matplotlib(spec, rows, output_path)
    return output_path


def _render_with_matplotlib(
    spec: FigureSpec,
    rows: List[Dict[str, str]],
    output_path: Path,
) -> None:
    """Render *spec* using matplotlib."""
    try:
        import matplotlib  # type: ignore[import-untyped]  # noqa: F401

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt  # type: ignore[import-untyped]  # noqa: F401
    except ImportError as exc:
        raise FigureError(
            "matplotlib is required for figure rendering. "
            "Install with: pip install abi-agent[report]"
        ) from exc

    renderer = _RENDERERS.get(spec.type)
    if renderer is None:
        raise FigureError(f"Unknown figure type: {spec.type!r}")
    fig, ax = plt.subplots(figsize=spec.figsize, dpi=spec.dpi)
    renderer(spec, rows, ax)
    ax.set_title(spec.title or spec.id)
    xlabel = spec.xlabel or spec.x
    ylabel = spec.ylabel or spec.y
    if xlabel:
        ax.set_xlabel(xlabel)
    if ylabel:
        ax.set_ylabel(ylabel)
    if spec.log_y:
        ax.set_yscale("log")
    fig.tight_layout()
    fig.savefig(output_path, dpi=spec.dpi, bbox_inches="tight")
    plt.close(fig)


# ── Per-type renderers / 各类型渲染器 ─────────────────────────────────────


def _render_bar(
    spec: FigureSpec,
    rows: List[Dict[str, str]],
    ax: Any,
) -> None:
    """Vertical bar chart."""
    import numpy as np  # type: ignore[import-untyped]

    if spec.sort_by:
        rows = sorted(
            rows, key=lambda r: _numeric(r.get(spec.sort_by, "0")), reverse=not spec.ascending
        )
    labels = [r.get(spec.x, "") for r in rows]
    values = [_numeric(r.get(spec.y, "0")) for r in rows]
    x = np.arange(len(labels))
    ax.bar(x, values, color="#4472C4", edgecolor="white", linewidth=0.5)
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=45, ha="right", fontsize=8)
    if len(labels) > 30:
        for tick in ax.get_xticklabels():
            tick.set_visible(False)
        ax.set_xlabel(f"{len(labels)} items (labels hidden)")


def _render_scatter(
    spec: FigureSpec,
    rows: List[Dict[str, str]],
    ax: Any,
) -> None:
    """Scatter plot."""
    x_vals = [_numeric(r.get(spec.x, "0")) for r in rows]
    y_vals = [_numeric(r.get(spec.y, "0")) for r in rows]
    if spec.color:
        groups = sorted({r.get(spec.color, "") for r in rows})
        cmap = _get_colormap(spec.colormap, len(groups))
        for i, group in enumerate(groups):
            idx = [j for j, r in enumerate(rows) if r.get(spec.color) == group]
            ax.scatter(
                [x_vals[j] for j in idx],
                [y_vals[j] for j in idx],
                label=str(group),
                color=cmap[i % len(cmap)] if cmap else None,
                alpha=0.7,
                s=20,
            )
        ax.legend(fontsize=7)
    else:
        ax.scatter(x_vals, y_vals, alpha=0.7, s=20, color="#4472C4")


def _render_volcano(
    spec: FigureSpec,
    rows: List[Dict[str, str]],
    ax: Any,
) -> None:
    """Volcano plot: x=log2FC, y=-log10(padj)."""
    import numpy as np  # type: ignore[import-untyped]

    x_vals = np.array([_numeric(r.get(spec.x, "0")) for r in rows])
    pvals = np.array([max(_numeric(r.get(spec.y, "1")), 1e-300) for r in rows])
    y_vals = -np.log10(pvals)
    # Significance thresholds
    sig_up = (x_vals > 1) & (pvals < 0.05)
    sig_down = (x_vals < -1) & (pvals < 0.05)
    nonsig = ~(sig_up | sig_down)
    ax.scatter(x_vals[nonsig], y_vals[nonsig], color="grey", alpha=0.4, s=10, label="NS")
    ax.scatter(x_vals[sig_up], y_vals[sig_up], color="#D62728", alpha=0.7, s=15, label="Up")
    ax.scatter(x_vals[sig_down], y_vals[sig_down], color="#1F77B4", alpha=0.7, s=15, label="Down")
    ax.axhline(-np.log10(0.05), color="grey", linestyle="--", linewidth=0.5)
    ax.axvline(-1, color="grey", linestyle="--", linewidth=0.5)
    ax.axvline(1, color="grey", linestyle="--", linewidth=0.5)
    if spec.label:
        # Label top N by significance
        order = np.argsort(pvals)
        for idx in order[: min(spec.top_n, len(rows))]:
            label_text = str(rows[idx].get(spec.label, ""))
            if label_text:
                ax.annotate(
                    label_text,
                    (x_vals[idx], y_vals[idx]),
                    fontsize=6,
                    alpha=0.8,
                    arrowprops=dict(arrowstyle="-", color="grey", alpha=0.3),
                )
    ax.legend(fontsize=7)


def _render_heatmap(
    spec: FigureSpec,
    rows: List[Dict[str, str]],
    ax: Any,
) -> None:
    """Heatmap from a table with row labels in *spec.x* and columns inferred."""
    import numpy as np  # type: ignore[import-untyped]

    if not rows:
        ax.text(0.5, 0.5, "No data available", transform=ax.transAxes, ha="center")
        return
    # Pivot: rows by spec.x, numeric columns become the matrix
    row_ids = [r.get(spec.x, str(i)) for i, r in enumerate(rows)]
    # Find numeric columns (skip the label column)
    numeric_cols = []
    for key in rows[0]:
        if key == spec.x:
            continue
        try:
            _numeric(rows[0][key])
            numeric_cols.append(key)
        except (ValueError, TypeError):
            continue
    if not numeric_cols:
        ax.text(0.5, 0.5, "No numeric columns for heatmap", transform=ax.transAxes, ha="center")
        return
    matrix = np.array([[_numeric(r.get(c, "0")) for c in numeric_cols] for r in rows])
    if spec.top_n and matrix.shape[0] > spec.top_n:
        # Keep top N rows by sum
        row_sums = matrix.sum(axis=1)
        top_idx = np.argsort(row_sums)[-spec.top_n :]
        matrix = matrix[top_idx]
        row_ids = [row_ids[i] for i in top_idx]
    im = ax.imshow(matrix, aspect="auto", cmap=spec.colormap)
    ax.set_yticks(range(len(row_ids)))
    ax.set_yticklabels(row_ids, fontsize=6)
    ax.set_xticks(range(len(numeric_cols)))
    ax.set_xticklabels(numeric_cols, rotation=90, fontsize=6)
    from matplotlib.pyplot import colorbar  # type: ignore[import-untyped]

    colorbar(im, ax=ax, shrink=0.8)


def _render_boxplot(
    spec: FigureSpec,
    rows: List[Dict[str, str]],
    ax: Any,
) -> None:
    """Boxplot grouped by spec.x, y values from spec.y."""

    groups: Dict[str, List[float]] = {}
    for r in rows:
        g = r.get(spec.x, "")
        v = _numeric(r.get(spec.y, "0"))
        groups.setdefault(g, []).append(v)
    group_names = sorted(groups.keys())
    data = [groups[g] for g in group_names]
    boxplot_kwargs: Dict[str, Any] = {"patch_artist": True}
    label_param = "tick_labels" if "tick_labels" in signature(ax.boxplot).parameters else "labels"
    boxplot_kwargs[label_param] = group_names
    bp = ax.boxplot(data, **boxplot_kwargs)
    for patch in bp["boxes"]:
        patch.set_facecolor("#4472C4")
        patch.set_alpha(0.6)
    ax.set_xticklabels(group_names, rotation=45, ha="right", fontsize=8)


def _render_stacked_bar(
    spec: FigureSpec,
    rows: List[Dict[str, str]],
    ax: Any,
) -> None:
    """Stacked bar chart for compositional data."""
    import numpy as np  # type: ignore[import-untyped]

    if not rows:
        return
    # spec.x = bar groups, remaining columns = stack components
    categories = [r.get(spec.x, str(i)) for i, r in enumerate(rows)]
    stack_cols = [k for k in rows[0] if k != spec.x]
    if not stack_cols:
        return
    data = np.array([[_numeric(r.get(c, "0")) for c in stack_cols] for r in rows])
    bottom = np.zeros(len(categories))
    cmap = _get_colormap(spec.colormap, len(stack_cols))
    for i, col in enumerate(stack_cols):
        vals = data[:, i]
        ax.bar(
            categories,
            vals,
            bottom=bottom,
            label=col,
            color=cmap[i % len(cmap)] if cmap else None,
            edgecolor="white",
            linewidth=0.3,
        )
        bottom += vals
    ax.legend(fontsize=7, bbox_to_anchor=(1.05, 1), loc="upper left")
    ax.set_xticklabels(categories, rotation=45, ha="right", fontsize=8)


def _render_pca(
    spec: FigureSpec,
    rows: List[Dict[str, str]],
    ax: Any,
) -> None:
    """PCA scatter: first two columns after the label column are PC1, PC2."""

    label_col = spec.label or spec.x
    numeric_cols = [k for k in rows[0] if k != label_col]
    if len(numeric_cols) < 2:
        ax.text(
            0.5,
            0.5,
            "Need ≥2 numeric columns for PCA plot",
            transform=ax.transAxes,
            ha="center",
        )
        return
    pc1 = [_numeric(r.get(numeric_cols[0], "0")) for r in rows]
    pc2 = [_numeric(r.get(numeric_cols[1], "0")) for r in rows]
    labels = [r.get(label_col, "") for r in rows]
    if spec.color:
        groups = sorted({r.get(spec.color, "") for r in rows})
        cmap = _get_colormap(spec.colormap, len(groups))
        for i, group in enumerate(groups):
            idx = [j for j, r in enumerate(rows) if r.get(spec.color) == group]
            ax.scatter(
                [pc1[j] for j in idx],
                [pc2[j] for j in idx],
                label=str(group),
                color=cmap[i % len(cmap)] if cmap else None,
                s=40,
                alpha=0.8,
            )
        ax.legend(fontsize=7)
    else:
        ax.scatter(pc1, pc2, s=40, alpha=0.8, color="#4472C4")
        for i, label in enumerate(labels):
            if label and i < spec.top_n:
                ax.annotate(str(label), (pc1[i], pc2[i]), fontsize=6, alpha=0.7)
    ax.set_xlabel(numeric_cols[0])
    ax.set_ylabel(numeric_cols[1])


# ── Registry / 注册表 ─────────────────────────────────────────────────────


_RENDERERS: Dict[str, Any] = {
    "bar": _render_bar,
    "scatter": _render_scatter,
    "volcano": _render_volcano,
    "heatmap": _render_heatmap,
    "boxplot": _render_boxplot,
    "stacked_bar": _render_stacked_bar,
    "pca": _render_pca,
}


# ── Helpers / 辅助 ────────────────────────────────────────────────────────


def _numeric(value: str) -> float:
    """Parse a string to float, returning 0.0 for empty/missing values."""
    if not value or str(value).strip() in ("", "NA", "N/A", "NaN", "nan", "None"):
        return 0.0
    try:
        return float(value)
    except (ValueError, TypeError):
        return 0.0


def _get_colormap(name: str, n: int) -> Optional[List[Any]]:
    """Return a list of *n* RGBA colors from a named matplotlib colormap."""
    try:
        import matplotlib.pyplot as plt  # type: ignore[import-untyped]

        cmap = plt.get_cmap(name)
        return [cmap(i / max(n - 1, 1)) for i in range(n)]
    except (ImportError, ValueError):
        return None
