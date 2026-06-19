"""FigureSpec — the core declarative figure description model.

A FigureSpec describes *what* to plot, not *how* to render it.
The rendering engine reads FigureSpec and produces publication-grade output.

Design principles / 设计原则:
- Pydantic v2 for strict runtime validation + JSON Schema generation
- Every field has a semantic meaning; no "extra" kwargs passthrough
- MappingSpec bridges raw column names → aesthetic dimensions (x, y, hue, etc.)
- StatSpec enforces that statistical annotations are declared before rendering
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator

# ── Figure type whitelist / 图形类型白名单 ─────────────────────────────────

SUPPORTED_FIGURE_TYPES: frozenset[str] = frozenset(
    {
        "barplot",
        "boxplot_with_points",
        "violin_with_box",
        "scatterplot",
        "ordination_plot",
        "stacked_barplot",
        "heatmap",
        "volcano_plot",
        "lineplot",
        # Biological-grade plot types (v1.4.0)
        "phylum_stacked_bar",
        "genus_heatmap",
        "pcoa_plot",
        "differential_volcano",
        "alpha_stats_boxplot",
        "phylogenetic_heatmap",
    }
)

# ── Sub-models / 子模型 ───────────────────────────────────────────────────


class DataSpec(BaseModel):
    """Data source specification.

    Describes the input table and the columns that must exist for rendering.
    """

    table: Path = Field(..., description="Path to the input data table.")
    format: Literal["csv", "tsv", "parquet"] = Field(
        "tsv", description="File format of the input table."
    )
    required_columns: list[str] = Field(
        default_factory=list,
        description="Columns that must exist in the input table.",
    )


class MappingSpec(BaseModel):
    """Aesthetic mapping — data columns → plot dimensions.

    Maps raw column names to visual aesthetics. Not all plots use all fields:
    - scatterplot: x, y, hue, label
    - boxplot_with_points: x, y, hue
    - volcano_plot: x (log2FC), y (padj/pvalue), label
    - heatmap: x (row labels); y is inferred from numeric columns
    """

    x: Optional[str] = Field(None, description="Column for x-axis.")
    y: Optional[str] = Field(None, description="Column for y-axis.")
    hue: Optional[str] = Field(None, description="Column for color grouping (replaces 'color').")
    label: Optional[str] = Field(None, description="Column for point/text labels.")
    group: Optional[str] = Field(
        None, description="Column for grouping on x-axis (boxplot, stacked_bar)."
    )
    value: Optional[str] = Field(None, description="Column for numeric values (long-format data).")


class SignificanceRule(BaseModel):
    """Thresholds for declaring statistical significance."""

    padj_lt: Optional[float] = Field(
        None, ge=0.0, le=1.0, description="Adjusted p-value threshold."
    )
    pvalue_lt: Optional[float] = Field(None, ge=0.0, le=1.0, description="Raw p-value threshold.")
    abs_log2fc_gt: Optional[float] = Field(
        None, ge=0.0, description="Absolute log2 fold-change threshold."
    )


class StatSpec(BaseModel):
    """Statistical test metadata.

    Every figure that displays significance markers (stars, colored points)
    MUST declare the underlying statistical test and correction method.
    This is enforced by FigureLint rule STAT001.
    """

    test: Optional[str] = Field(None, description="Statistical test name, e.g. 'DESeq2 Wald test'.")
    correction: Optional[str] = Field(
        None,
        description="Multiple-testing correction, e.g. 'Benjamini-Hochberg'.",
    )
    pvalue_column: Optional[str] = Field(
        None, description="Column containing p-values or adjusted p-values."
    )
    fold_change_column: Optional[str] = Field(
        None, description="Column containing fold-change values."
    )
    significance_rule: Optional[SignificanceRule] = Field(
        None, description="Thresholds applied to classify significance."
    )


class StyleSpec(BaseModel):
    """Visual style — theme, palette, dimensions.

    Separated from data mapping so the same data can be rendered in
    different styles (manuscript vs. talk vs. report).
    """

    theme: str = Field("abi_nature", description="Theme name from the theme registry.")
    palette: str = Field("colorblind_safe", description="Palette name from the palette registry.")
    width_mm: float = Field(90.0, gt=0.0, description="Figure width in millimetres.")
    height_mm: float = Field(70.0, gt=0.0, description="Figure height in millimetres.")
    dpi: int = Field(300, ge=72, description="Output resolution in dots per inch.")

    @property
    def figsize_inches(self) -> tuple[float, float]:
        """Convert mm to inches for matplotlib."""
        return (self.width_mm / 25.4, self.height_mm / 25.4)


class LabelSpec(BaseModel):
    """Figure text labels.

    All optional — missing labels trigger WARNING-level lint, not ERROR.
    """

    title: Optional[str] = Field(None, description="Figure title.")
    x_label: Optional[str] = Field(None, description="X-axis label.")
    y_label: Optional[str] = Field(None, description="Y-axis label.")
    legend_title: Optional[str] = Field(None, description="Legend title.")


class ExportSpec(BaseModel):
    """Output configuration — where and in what formats to save."""

    output_dir: Path = Field(..., description="Directory for output files.")
    basename: str = Field(..., description="Base filename (without extension).")
    formats: list[Literal["pdf", "svg", "png", "tiff"]] = Field(
        default=["pdf", "svg", "png"],
        description="Output formats to generate.",
    )
    transparent: bool = Field(False, description="Use transparent background for raster formats.")


class ProvenanceSpec(BaseModel):
    """Provenance metadata for reproducibility."""

    workflow_name: Optional[str] = Field(
        None, description="ABI workflow that produced the input data."
    )
    abi_version: Optional[str] = Field(None, description="ABI version used to generate the data.")
    input_data_role: Optional[str] = Field(
        None,
        description="Role of the input data, e.g. 'DESeq2 differential expression result'.",
    )


# ── Top-level model / 顶层模型 ────────────────────────────────────────────


class FigureSpec(BaseModel):
    """Complete declarative specification of a scientific figure.

    This is the top-level model that agents produce and the rendering
    engine consumes.  It is the single source of truth for one figure.

    Minimal valid spec (boxplot):
        figure_id: "alpha_diversity"
        figure_type: "boxplot_with_points"
        data:
          table: "alpha_diversity.tsv"
        mapping:
          x: "group"
          y: "shannon"
        export:
          output_dir: "figures/"
          basename: "alpha_diversity"
    """

    schema_version: str = Field(
        "0.1.0", description="FigureSpec schema version for forward compatibility."
    )

    figure_id: str = Field(
        ..., min_length=1, description="Unique figure identifier within the workflow."
    )
    figure_type: str = Field(
        ...,
        description="Figure type — must be one of the SUPPORTED_FIGURE_TYPES.",
    )

    data: DataSpec = Field(..., description="Input data specification.")
    mapping: MappingSpec = Field(
        default_factory=lambda: MappingSpec(),
        description="Column-to-aesthetic mapping.",
    )
    statistics: Optional[StatSpec] = Field(
        None, description="Statistical test metadata (required for significance markers)."
    )
    style: StyleSpec = Field(
        default_factory=lambda: StyleSpec(),
        description="Visual style configuration.",
    )
    labels: LabelSpec = Field(
        default_factory=lambda: LabelSpec(),
        description="Figure text labels.",
    )
    export: ExportSpec = Field(..., description="Output configuration.")
    provenance: ProvenanceSpec = Field(
        default_factory=lambda: ProvenanceSpec(),
        description="Reproducibility metadata.",
    )

    # ── Validators / 验证器 ─────────────────────────────────────────────

    @model_validator(mode="after")
    def _validate_figure_type(self) -> "FigureSpec":
        """Ensure figure_type is in the supported set."""
        if self.figure_type not in SUPPORTED_FIGURE_TYPES:
            raise ValueError(
                f"Unsupported figure_type '{self.figure_type}'. "
                f"Supported types: {sorted(SUPPORTED_FIGURE_TYPES)}"
            )
        return self

    @model_validator(mode="after")
    def _validate_mapping_has_axes(self) -> "FigureSpec":
        """Ensure at least x or y is specified for non-heatmap types."""
        # These types auto-detect columns or read from other sources
        if self.figure_type in {
            "heatmap",
            "ordination_plot",
            "genus_heatmap",
            "pcoa_plot",
            "phylogenetic_heatmap",
        }:
            return self
        if not self.mapping.x and not self.mapping.y:
            raise ValueError(
                f"Figure type '{self.figure_type}' requires at least one of "
                f"mapping.x or mapping.y to be set."
            )
        return self

    @model_validator(mode="after")
    def _validate_significance_consistency(self) -> "FigureSpec":
        """If statistics block has a test, pvalue_column should be set."""
        if self.statistics and self.statistics.test:
            if not self.statistics.pvalue_column and not self.statistics.fold_change_column:
                raise ValueError(
                    "statistics.test is set but neither pvalue_column nor "
                    "fold_change_column is specified."
                )
        return self
