"""Tests for FigureSpec, ThemeSpec, and PaletteSpec schemas."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from abi.sciplot.schema.figure_spec import (
    DataSpec,
    ExportSpec,
    FigureSpec,
    LabelSpec,
    MappingSpec,
    ProvenanceSpec,
    StatSpec,
    StyleSpec,
)
from abi.sciplot.schema.palette_spec import (
    CategoricalPalette,
    PaletteRegistry,
)
from abi.sciplot.schema.theme_spec import ThemeSpec

# ── FigureSpec construction tests ────────────────────────────────────────


def _make_minimal_spec(figure_type: str = "volcano_plot") -> FigureSpec:
    """Build a minimal valid FigureSpec for testing."""
    return FigureSpec(
        figure_id="test_figure",
        figure_type=figure_type,
        data=DataSpec(
            table=Path("/tmp/test_data.tsv"),
            required_columns=["gene_id", "log2FoldChange", "padj"],
        ),
        mapping=MappingSpec(x="log2FoldChange", y="padj", label="gene_id"),
        statistics=StatSpec(
            test="DESeq2 Wald test",
            correction="Benjamini-Hochberg",
            pvalue_column="padj",
            fold_change_column="log2FoldChange",
        ),
        style=StyleSpec(theme="abi_nature", palette="colorblind_safe"),
        labels=LabelSpec(x_label="log2 fold change", y_label="-log10 adj p-value"),
        export=ExportSpec(output_dir=Path("/tmp/figures"), basename="test_figure"),
        provenance=ProvenanceSpec(workflow_name="test_workflow"),
    )


class TestFigureSpec:
    """FigureSpec construction and validation."""

    def test_minimal_valid_spec(self) -> None:
        """A minimal spec should construct without error."""
        spec = FigureSpec(
            figure_id="minimal",
            figure_type="boxplot_with_points",
            data=DataSpec(table=Path("/tmp/data.tsv")),
            mapping=MappingSpec(x="group", y="value"),
            export=ExportSpec(output_dir=Path("/tmp/out"), basename="minimal"),
        )
        assert spec.figure_id == "minimal"
        assert spec.figure_type == "boxplot_with_points"

    def test_rejects_unknown_figure_type(self) -> None:
        """An unknown figure_type should raise ValidationError."""
        with pytest.raises(ValueError, match="Unsupported figure_type"):
            FigureSpec(
                figure_id="bad",
                figure_type="pie_chart",
                data=DataSpec(table=Path("/tmp/data.tsv")),
                mapping=MappingSpec(x="a", y="b"),
                export=ExportSpec(output_dir=Path("/tmp/out"), basename="bad"),
            )

    def test_requires_at_least_one_axis(self) -> None:
        """scatterplot with no x or y should fail."""
        with pytest.raises(ValueError, match="at least one of mapping.x or mapping.y"):
            FigureSpec(
                figure_id="bad_axes",
                figure_type="scatterplot",
                data=DataSpec(table=Path("/tmp/data.tsv")),
                mapping=MappingSpec(),
                export=ExportSpec(output_dir=Path("/tmp/out"), basename="bad_axes"),
            )

    def test_heatmap_allows_no_axes(self) -> None:
        """Heatmap should be allowed without explicit x/y."""
        spec = FigureSpec(
            figure_id="heatmap_ok",
            figure_type="heatmap",
            data=DataSpec(table=Path("/tmp/data.tsv")),
            mapping=MappingSpec(),
            export=ExportSpec(output_dir=Path("/tmp/out"), basename="heatmap_ok"),
        )
        assert spec.figure_type == "heatmap"

    def test_stat_test_without_pvalue_column_fails(self) -> None:
        """Statistics.test set but no pvalue_column → validation error."""
        with pytest.raises(ValueError, match="neither pvalue_column nor"):
            FigureSpec(
                figure_id="bad_stats",
                figure_type="volcano_plot",
                data=DataSpec(table=Path("/tmp/data.tsv")),
                mapping=MappingSpec(x="log2FC", y="padj"),
                statistics=StatSpec(test="t-test"),
                export=ExportSpec(output_dir=Path("/tmp/out"), basename="bad_stats"),
            )

    def test_figsize_inches_conversion(self) -> None:
        """StyleSpec.figsize_inches converts mm to inches correctly."""
        style = StyleSpec(width_mm=90, height_mm=70)
        w, h = style.figsize_inches
        assert abs(w - 90 / 25.4) < 0.01
        assert abs(h - 70 / 25.4) < 0.01

    def test_volcano_spec_is_valid(self) -> None:
        """A full volcano plot spec should validate."""
        spec = _make_minimal_spec("volcano_plot")
        assert spec.figure_id == "test_figure"
        assert spec.statistics is not None
        assert spec.statistics.test == "DESeq2 Wald test"

    def test_all_supported_types_construct(self) -> None:
        """All supported figure types should construct with valid minimal args."""
        for ftype in [
            "boxplot_with_points",
            "violin_with_box",
            "scatterplot",
            "ordination_plot",
            "stacked_barplot",
            "heatmap",
            "volcano_plot",
            "lineplot",
        ]:
            spec = FigureSpec(
                figure_id=f"test_{ftype}",
                figure_type=ftype,
                data=DataSpec(table=Path("/tmp/data.tsv")),
                mapping=MappingSpec(x="x_col", y="y_col"),
                export=ExportSpec(output_dir=Path("/tmp/out"), basename=f"test_{ftype}"),
            )
            assert spec.figure_type == ftype


# ── ThemeSpec tests ──────────────────────────────────────────────────────


class TestThemeSpec:
    """ThemeSpec loading and rcParams conversion."""

    def test_default_theme_valid(self) -> None:
        """Default ThemeSpec should construct."""
        theme = ThemeSpec(theme_name="test")
        assert theme.theme_name == "test"
        assert theme.font.base_size_pt == 7.0

    def test_to_rcparams(self) -> None:
        """to_matplotlib_rcparams returns a valid rcParams dict."""
        theme = ThemeSpec(theme_name="test")
        rc = theme.to_matplotlib_rcparams()
        assert "font.family" in rc
        assert "font.size" in rc
        assert "axes.spines.top" in rc
        assert rc["axes.spines.top"] is False

    def test_load_from_yaml(self) -> None:
        """Load a ThemeSpec from a YAML file."""
        theme_path = Path(__file__).parent.parent / "themes" / "abi_nature.yaml"
        theme = ThemeSpec.from_yaml(theme_path)
        assert theme.theme_name == "abi_nature"
        assert theme.font.family == "DejaVu Sans"
        assert theme.figure.dpi == 300


# ── PaletteRegistry tests ────────────────────────────────────────────────


class TestPaletteRegistry:
    """PaletteRegistry loading, validation, and lookup."""

    def test_load_builtins(self) -> None:
        """Built-in palettes should load without error."""
        reg = PaletteRegistry()
        reg.load_builtins()
        assert "colorblind_safe_8" in reg.categorical_names
        assert "viridis" in reg.continuous_names
        assert "vik" in reg.diverging_names

    def test_rejects_jet(self) -> None:
        """jet palette should be rejected."""
        reg = PaletteRegistry()
        with pytest.raises(ValueError, match="forbidden"):
            reg.register(
                CategoricalPalette(
                    name="jet", type="categorical", max_categories=8, colors=["#ff0000"] * 8
                )
            )

    def test_rejects_rainbow(self) -> None:
        """rainbow palette should be rejected."""
        reg = PaletteRegistry()
        with pytest.raises(ValueError, match="forbidden"):
            reg.register(
                CategoricalPalette(
                    name="rainbow", type="categorical", max_categories=8, colors=["#ff0000"] * 8
                )
            )

    def test_categorical_lookup(self) -> None:
        """get_categorical returns correct colours."""
        reg = PaletteRegistry()
        reg.load_builtins()
        colors = reg.get_categorical("colorblind_safe_8", n=3)
        assert len(colors) == 3
        assert colors[0] == "#0072B2"

    def test_exceeds_max_categories(self) -> None:
        """Requesting more categories than max_categories raises ValueError."""
        reg = PaletteRegistry()
        reg.load_builtins()
        with pytest.raises(ValueError, match="supports at most"):
            reg.get_categorical("colorblind_safe_8", n=20)

    def test_continuous_fallback(self) -> None:
        """Unknown continuous palette falls back to viridis."""
        reg = PaletteRegistry()
        reg.load_builtins()
        assert reg.get_continuous("nonexistent") == "viridis"

    def test_is_allowed(self) -> None:
        """is_allowed rejects forbidden palettes."""
        reg = PaletteRegistry()
        reg.load_builtins()
        assert reg.is_allowed("viridis")
        assert not reg.is_allowed("jet")
        assert not reg.is_allowed("rainbow")


# ── Data validation tests ────────────────────────────────────────────────


class TestDataValidation:
    """Data validation with real TSV files."""

    def test_missing_table(self) -> None:
        """DATA001: Non-existent table → error."""
        from abi.sciplot.validators import validate_data

        spec = FigureSpec(
            figure_id="test",
            figure_type="scatterplot",
            data=DataSpec(table=Path("/tmp/nonexistent_xyz.tsv")),
            mapping=MappingSpec(x="x", y="y"),
            export=ExportSpec(output_dir=Path("/tmp/out"), basename="test"),
        )
        report = validate_data(spec)
        assert not report.is_valid
        assert any("DATA001" in e.rule for e in report.errors)

    def test_missing_column(self) -> None:
        """DATA002: Missing mapping column → error."""
        from abi.sciplot.validators import validate_data

        with tempfile.NamedTemporaryFile(mode="w", suffix=".tsv", delete=False) as fh:
            fh.write("col_a\tcol_b\n1\t2\n3\t4\n")
            tmp_path = Path(fh.name)

        try:
            spec = FigureSpec(
                figure_id="test",
                figure_type="scatterplot",
                data=DataSpec(table=tmp_path, required_columns=["missing_col"]),
                mapping=MappingSpec(x="missing_col", y="col_a"),
                export=ExportSpec(output_dir=Path("/tmp/out"), basename="test"),
            )
            report = validate_data(spec)
            assert not report.is_valid
            assert any("DATA002" in e.rule for e in report.errors)
        finally:
            tmp_path.unlink()

    def test_valid_table_passes(self) -> None:
        """Valid table with all columns → success."""
        from abi.sciplot.validators import validate_data

        with tempfile.NamedTemporaryFile(mode="w", suffix=".tsv", delete=False) as fh:
            fh.write("gene_id\tlog2FoldChange\tpadj\nG1\t1.5\t0.001\nG2\t-2.0\t0.04\n")
            tmp_path = Path(fh.name)

        try:
            spec = FigureSpec(
                figure_id="test",
                figure_type="volcano_plot",
                data=DataSpec(
                    table=tmp_path,
                    required_columns=["gene_id", "log2FoldChange", "padj"],
                ),
                mapping=MappingSpec(x="log2FoldChange", y="padj", label="gene_id"),
                statistics=StatSpec(
                    test="DESeq2",
                    correction="BH",
                    pvalue_column="padj",
                    fold_change_column="log2FoldChange",
                ),
                export=ExportSpec(output_dir=Path("/tmp/out"), basename="test"),
            )
            report = validate_data(spec)
            assert report.is_valid, str(report.to_dict())
        finally:
            tmp_path.unlink()
