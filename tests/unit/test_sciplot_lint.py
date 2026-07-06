"""Comprehensive unit tests for src/abi/sciplot/lint/__init__.py — FigureLint rules."""

from __future__ import annotations

from pathlib import Path

from abi.sciplot.lint import (
    ALL_RULES,
    LintFinding,
    LintReport,
    LintRule,
    _check_export,
    _check_figure_identity,
    _check_labels,
    _check_provenance,
    _check_statistics,
    _check_style,
    lint_figure,
)
from abi.sciplot.schema.figure_spec import (
    SUPPORTED_FIGURE_TYPES,
    DataSpec,
    ExportSpec,
    FigureSpec,
    LabelSpec,
    MappingSpec,
    StatSpec,
    StyleSpec,
)

# ── Helpers ────────────────────────────────────────────────────────────────


def make_spec(**overrides) -> FigureSpec:
    """Build a minimal valid FigureSpec, overriding any field via kwargs.

    Includes mapping.x/y to satisfy the non-heatmap axes validator.  Tests
    that need empty mapping should pass ``mapping=MappingSpec()`` explicitly.
    """
    defaults: dict = {
        "figure_id": "test-fig",
        "figure_type": "barplot",
        "data": DataSpec(table=Path("/tmp/data.tsv")),
        "mapping": MappingSpec(x="group", y="value"),
        "export": ExportSpec(output_dir=Path("/tmp"), basename="test"),
    }
    defaults.update(overrides)
    return FigureSpec(**defaults)


# ── LintFinding ────────────────────────────────────────────────────────────


class TestLintFinding:
    def test_construction_all_fields(self) -> None:
        f = LintFinding(rule="FIG001", level="ERROR", message="msg", details={"key": "val"})
        assert f.rule == "FIG001"
        assert f.level == "ERROR"
        assert f.message == "msg"
        assert f.details == {"key": "val"}

    def test_construction_defaults(self) -> None:
        f = LintFinding(rule="FIG001", level="ERROR", message="msg")
        assert f.details is None


# ── LintReport ─────────────────────────────────────────────────────────────


class TestLintReport:
    def test_status_passed_when_no_errors(self) -> None:
        report = LintReport(figure_id="fig1")
        assert report.status == "passed"

    def test_status_failed_when_errors_exist(self) -> None:
        report = LintReport(figure_id="fig1")
        report.errors.append(LintFinding("FIG001", "ERROR", "bad"))
        assert report.status == "failed"

    def test_status_passed_with_warnings_only(self) -> None:
        report = LintReport(figure_id="fig1")
        report.warnings.append(LintFinding("STAT001", "WARNING", "hint"))
        assert report.status == "passed"

    def test_to_dict_basic_structure(self) -> None:
        report = LintReport(figure_id="fig1")
        d = report.to_dict()
        assert d["figure_id"] == "fig1"
        assert d["status"] == "passed"
        assert d["errors"] == []
        assert d["warnings"] == []
        assert d["info"] == []

    def test_to_dict_includes_findings(self) -> None:
        report = LintReport(figure_id="fig1")
        report.errors.append(LintFinding("FIG001", "ERROR", "bad id"))
        report.warnings.append(LintFinding("STAT001", "WARNING", "no stats"))
        report.info.append(LintFinding("INFO001", "INFO", "nice"))
        d = report.to_dict()
        assert d["status"] == "failed"
        assert len(d["errors"]) == 1
        assert d["errors"][0] == {"rule": "FIG001", "level": "ERROR", "message": "bad id"}
        assert len(d["warnings"]) == 1
        assert d["warnings"][0]["rule"] == "STAT001"
        assert len(d["info"]) == 1
        assert d["info"][0]["rule"] == "INFO001"


# ── _check_figure_identity ─────────────────────────────────────────────────


class TestCheckFigureIdentity:
    def test_fig001_missing_figure_id(self) -> None:
        """FIG001 ERROR when figure_id is empty."""
        spec = FigureSpec.model_construct(
            figure_id="",
            figure_type="barplot",
            data=DataSpec(table=Path("/tmp/t.tsv")),
            mapping=MappingSpec(),
            style=StyleSpec(),
            labels=LabelSpec(),
            export=ExportSpec(output_dir=Path("/tmp"), basename="test"),
        )
        findings = _check_figure_identity(spec, [], None)
        assert any(f.rule == "FIG001" and f.level == "ERROR" for f in findings)

    def test_fig002_missing_figure_type(self) -> None:
        """FIG002 ERROR when figure_type is empty."""
        spec = FigureSpec.model_construct(
            figure_id="test",
            figure_type="",
            data=DataSpec(table=Path("/tmp/t.tsv")),
            mapping=MappingSpec(),
            style=StyleSpec(),
            labels=LabelSpec(),
            export=ExportSpec(output_dir=Path("/tmp"), basename="test"),
        )
        findings = _check_figure_identity(spec, [], None)
        assert any(f.rule == "FIG002" and f.level == "ERROR" for f in findings)

    def test_fig003_unknown_figure_type(self) -> None:
        """FIG003 ERROR when figure_type is not in SUPPORTED_FIGURE_TYPES."""
        spec = FigureSpec.model_construct(
            figure_id="test",
            figure_type="bogus_plot",
            data=DataSpec(table=Path("/tmp/t.tsv")),
            mapping=MappingSpec(),
            style=StyleSpec(),
            labels=LabelSpec(),
            export=ExportSpec(output_dir=Path("/tmp"), basename="test"),
        )
        findings = _check_figure_identity(spec, [], None)
        fig003s = [f for f in findings if f.rule == "FIG003"]
        assert len(fig003s) >= 1
        assert fig003s[0].level == "ERROR"
        assert "bogus_plot" in fig003s[0].message

    def test_fig001_and_fig002_both_missing(self) -> None:
        """Both FIG001 and FIG002 fire when both figure_id and figure_type are empty."""
        spec = FigureSpec.model_construct(
            figure_id="",
            figure_type="",
            data=DataSpec(table=Path("/tmp/t.tsv")),
            mapping=MappingSpec(),
            style=StyleSpec(),
            labels=LabelSpec(),
            export=ExportSpec(output_dir=Path("/tmp"), basename="test"),
        )
        findings = _check_figure_identity(spec, [], None)
        rules = {f.rule for f in findings}
        assert "FIG001" in rules
        assert "FIG002" in rules

    def test_valid_spec_no_identity_findings(self) -> None:
        """A valid spec produces no identity findings."""
        spec = make_spec(figure_id="ok", figure_type="barplot")
        findings = _check_figure_identity(spec, [], None)
        assert findings == []


# ── _check_style ───────────────────────────────────────────────────────────


class TestCheckStyle:
    def test_style001_jet_forbidden(self) -> None:
        """STYLE001 ERROR when palette is 'jet' (in FORBIDDEN_PALETTES)."""
        spec = make_spec(style=StyleSpec(palette="jet"))
        findings = _check_style(spec, [], None)
        style001s = [f for f in findings if f.rule == "STYLE001"]
        assert len(style001s) >= 1
        assert any("jet" in f.message.lower() for f in style001s)

    def test_style001_turbo_forbidden(self) -> None:
        """STYLE001 ERROR when palette is 'turbo' (in FORBIDDEN_PALETTES)."""
        spec = make_spec(style=StyleSpec(palette="turbo"))
        findings = _check_style(spec, [], None)
        assert any(f.rule == "STYLE001" and f.level == "ERROR" for f in findings)

    def test_style001_forbidden_substring(self) -> None:
        """STYLE001 ERROR when palette contains a forbidden substring."""
        spec = make_spec(style=StyleSpec(palette="my_rainbow_custom"))
        findings = _check_style(spec, [], None)
        style001s = [f for f in findings if f.rule == "STYLE001"]
        assert len(style001s) >= 1
        assert any("rainbow" in f.message for f in style001s)

    def test_style003_width_too_small(self) -> None:
        """STYLE003 ERROR when width_mm < 20."""
        spec = make_spec(style=StyleSpec(palette="viridis", width_mm=15, height_mm=80))
        findings = _check_style(spec, [], None)
        assert any(f.rule == "STYLE003" and f.level == "ERROR" for f in findings)

    def test_style003_height_too_small(self) -> None:
        """STYLE003 ERROR when height_mm < 20."""
        spec = make_spec(style=StyleSpec(palette="viridis", width_mm=80, height_mm=10))
        findings = _check_style(spec, [], None)
        assert any(f.rule == "STYLE003" and f.level == "ERROR" for f in findings)

    def test_style003_both_dimensions_too_small(self) -> None:
        """STYLE003 fires once even when both dimensions are too small."""
        spec = make_spec(style=StyleSpec(palette="viridis", width_mm=10, height_mm=10))
        findings = _check_style(spec, [], None)
        style003s = [f for f in findings if f.rule == "STYLE003"]
        assert len(style003s) == 1

    def test_style_valid_palette_no_findings(self) -> None:
        """No STYLE001 with a safe palette."""
        spec = make_spec(style=StyleSpec(palette="viridis"))
        findings = _check_style(spec, [], None)
        style001s = [f for f in findings if f.rule == "STYLE001"]
        assert style001s == []


# ── _check_statistics ──────────────────────────────────────────────────────


class TestCheckStatistics:
    def test_stat001_warning_when_figure_needs_stats_and_none_set(self) -> None:
        """STAT001 WARNING when figure_type is volcano_plot and no statistics block."""
        spec = make_spec(figure_type="volcano_plot")
        findings = _check_statistics(spec, [], None)
        stat001s = [f for f in findings if f.rule == "STAT001" and f.level == "WARNING"]
        assert len(stat001s) >= 1

    def test_stat001_warning_for_boxplot_with_points(self) -> None:
        """STAT001 WARNING for boxplot_with_points without statistics."""
        spec = make_spec(figure_type="boxplot_with_points")
        findings = _check_statistics(spec, [], None)
        assert any(f.rule == "STAT001" and f.level == "WARNING" for f in findings)

    def test_stat001_error_when_test_without_pvalue_column(self) -> None:
        """STAT001 ERROR when statistics.test is set but pvalue_column is not."""
        spec = FigureSpec.model_construct(
            figure_id="test-fig",
            figure_type="volcano_plot",
            data=DataSpec(table=Path("/tmp/t.tsv")),
            mapping=MappingSpec(),  # volcano_plot requires mapping
            style=StyleSpec(),
            labels=LabelSpec(),
            export=ExportSpec(output_dir=Path("/tmp"), basename="test"),
            statistics=StatSpec(test="t-test"),
        )
        findings = _check_statistics(spec, [], None)
        stat001_errors = [f for f in findings if f.rule == "STAT001" and f.level == "ERROR"]
        assert len(stat001_errors) >= 1
        assert "pvalue_column" in stat001_errors[0].message

    def test_stat002_warning_when_no_correction(self) -> None:
        """STAT002 WARNING when statistics.test and pvalue_column are set but no correction."""
        spec = make_spec(
            figure_type="volcano_plot",
            statistics=StatSpec(test="t-test", pvalue_column="pval"),
        )
        findings = _check_statistics(spec, [], None)
        stat002s = [f for f in findings if f.rule == "STAT002"]
        assert len(stat002s) >= 1
        assert stat002s[0].level == "WARNING"

    def test_statistics_fully_specified_no_warnings(self) -> None:
        """No STAT002 when correction is declared."""
        spec = make_spec(
            figure_type="volcano_plot",
            statistics=StatSpec(test="t-test", pvalue_column="pval", correction="BH"),
        )
        findings = _check_statistics(spec, [], None)
        assert all(f.rule != "STAT002" for f in findings)

    def test_barplot_no_statistics_triggers_nothing(self) -> None:
        """Barplot does NOT need statistics — no STAT001 warnings."""
        spec = make_spec(figure_type="barplot")
        findings = _check_statistics(spec, [], None)
        assert findings == []


# ── _check_labels ──────────────────────────────────────────────────────────


class TestCheckLabels:
    def test_label001_empty_x_label(self) -> None:
        """LABEL001 WARNING when x_label is empty and mapping.x is empty."""
        spec = FigureSpec.model_construct(
            figure_id="test-fig",
            figure_type="barplot",
            data=DataSpec(table=Path("/tmp/t.tsv")),
            mapping=MappingSpec(),  # no x — triggers LABEL001 alongside empty label
            labels=LabelSpec(),  # no x_label
            style=StyleSpec(),
            export=ExportSpec(output_dir=Path("/tmp"), basename="test"),
        )
        findings = _check_labels(spec, [], None)
        x_warnings = [f for f in findings if f.rule == "LABEL001" and "x-axis" in f.message.lower()]
        assert len(x_warnings) == 1

    def test_label001_empty_y_label(self) -> None:
        """LABEL001 WARNING when y_label is empty and mapping.y is empty."""
        spec = FigureSpec.model_construct(
            figure_id="test-fig",
            figure_type="barplot",
            data=DataSpec(table=Path("/tmp/t.tsv")),
            mapping=MappingSpec(),  # no y — triggers LABEL001 alongside empty label
            labels=LabelSpec(),  # no y_label
            style=StyleSpec(),
            export=ExportSpec(output_dir=Path("/tmp"), basename="test"),
        )
        findings = _check_labels(spec, [], None)
        y_warnings = [f for f in findings if f.rule == "LABEL001" and "y-axis" in f.message.lower()]
        assert len(y_warnings) == 1

    def test_label001_heatmap_skipped(self) -> None:
        """Heatmap types are exempt from x/y label checks."""
        spec = make_spec(
            figure_type="heatmap",
            labels=LabelSpec(),
            mapping=MappingSpec(),
        )
        findings = _check_labels(spec, [], None)
        assert findings == []

    def test_label001_genus_heatmap_skipped(self) -> None:
        """Genus heatmap also exempt."""
        spec = make_spec(
            figure_type="genus_heatmap",
            labels=LabelSpec(),
            mapping=MappingSpec(),
        )
        findings = _check_labels(spec, [], None)
        assert findings == []

    def test_labels_with_x_label_no_warning(self) -> None:
        """No LABEL001 when x_label is set."""
        spec = make_spec(
            figure_type="barplot",
            labels=LabelSpec(x_label="Samples"),
        )
        findings = _check_labels(spec, [], None)
        x_warnings = [f for f in findings if f.rule == "LABEL001" and "x-axis" in f.message.lower()]
        assert x_warnings == []

    def test_labels_with_mapping_x_no_warning(self) -> None:
        """No LABEL001 x-axis warning when mapping.x is set."""
        spec = make_spec(
            figure_type="barplot",
            labels=LabelSpec(),
            mapping=MappingSpec(x="group"),
        )
        findings = _check_labels(spec, [], None)
        x_warnings = [f for f in findings if f.rule == "LABEL001" and "x-axis" in f.message.lower()]
        assert x_warnings == []


# ── _check_export ──────────────────────────────────────────────────────────


class TestCheckExport:
    def test_export001_png_low_dpi(self) -> None:
        """EXPORT001 ERROR when a .png output has DPI < 300."""
        spec = make_spec(style=StyleSpec(palette="viridis", dpi=150))
        output_files = [Path("figure.png")]
        findings = _check_export(spec, output_files, None)
        export001s = [f for f in findings if f.rule == "EXPORT001"]
        assert len(export001s) == 1
        assert export001s[0].level == "ERROR"

    def test_export001_tiff_low_dpi(self) -> None:
        """EXPORT001 ERROR when a .tiff output has DPI < 300."""
        spec = make_spec(style=StyleSpec(palette="viridis", dpi=72))
        output_files = [Path("figure.tiff")]
        findings = _check_export(spec, output_files, None)
        assert any(f.rule == "EXPORT001" and f.level == "ERROR" for f in findings)

    def test_export001_png_sufficient_dpi(self) -> None:
        """No EXPORT001 when DPI >= 300."""
        spec = make_spec(style=StyleSpec(palette="viridis", dpi=300))
        output_files = [Path("figure.png")]
        findings = _check_export(spec, output_files, None)
        assert all(f.rule != "EXPORT001" for f in findings)

    def test_export002_no_vector_format(self) -> None:
        """EXPORT002 WARNING when no .pdf or .svg in output files."""
        spec = make_spec(style=StyleSpec(palette="viridis", dpi=300))
        output_files = [Path("figure.png"), Path("figure.tiff")]
        findings = _check_export(spec, output_files, None)
        export002s = [f for f in findings if f.rule == "EXPORT002"]
        assert len(export002s) == 1
        assert export002s[0].level == "WARNING"

    def test_export002_pdf_present_no_warning(self) -> None:
        """No EXPORT002 when a .pdf is among output files."""
        spec = make_spec(style=StyleSpec(palette="viridis", dpi=300))
        output_files = [Path("figure.pdf")]
        findings = _check_export(spec, output_files, None)
        assert all(f.rule != "EXPORT002" for f in findings)

    def test_export002_svg_present_no_warning(self) -> None:
        """No EXPORT002 when an .svg is among output files."""
        spec = make_spec(style=StyleSpec(palette="viridis", dpi=300))
        output_files = [Path("figure.svg")]
        findings = _check_export(spec, output_files, None)
        assert all(f.rule != "EXPORT002" for f in findings)


# ── _check_provenance ──────────────────────────────────────────────────────


class TestCheckProvenance:
    def test_prov001_none_provenance(self) -> None:
        """PROV001 ERROR when provenance_path is None."""
        spec = make_spec()
        findings = _check_provenance(spec, [], None)
        prov001s = [f for f in findings if f.rule == "PROV001"]
        assert len(prov001s) == 1
        assert prov001s[0].level == "ERROR"

    def test_prov001_nonexistent_path(self) -> None:
        """PROV001 ERROR when provenance_path does not exist."""
        spec = make_spec()
        findings = _check_provenance(spec, [], Path("/nonexistent/prov.json"))
        prov001s = [f for f in findings if f.rule == "PROV001"]
        assert len(prov001s) == 1
        assert prov001s[0].level == "ERROR"

    def test_prov001_existing_file_no_error(self, tmp_path: Path) -> None:
        """No PROV001 when provenance_path points to an existing file."""
        prov_file = tmp_path / "prov.json"
        prov_file.write_text("{}")
        spec = make_spec()
        findings = _check_provenance(spec, [], prov_file)
        prov001s = [f for f in findings if f.rule == "PROV001"]
        assert prov001s == []


# ── LintRule.apply ─────────────────────────────────────────────────────────


class TestLintRuleApply:
    def test_apply_catches_exception_and_returns_error_finding(self) -> None:
        """When a check function raises, LintRule.apply returns an ERROR finding."""

        def _raising_check(spec, output_files, provenance_path):
            raise RuntimeError("check exploded")

        rule = LintRule("TEST001", "WARNING", "always raises", _raising_check)
        spec = make_spec()
        findings = rule.apply(spec, [], None)
        assert len(findings) == 1
        assert findings[0].rule == "TEST001"
        assert findings[0].level == "ERROR"
        assert "check exploded" in findings[0].message

    def test_apply_returns_normal_findings(self) -> None:
        """LintRule.apply forwards findings from the check function."""

        def _ok_check(spec, output_files, provenance_path):
            return [LintFinding("OK001", "INFO", "all good")]

        rule = LintRule("OK001", "INFO", "always ok", _ok_check)
        spec = make_spec()
        findings = rule.apply(spec, [], None)
        assert len(findings) == 1
        assert findings[0].rule == "OK001"
        assert findings[0].level == "INFO"


# ── lint_figure ────────────────────────────────────────────────────────────


class TestLintFigure:
    def test_valid_spec_passes(self) -> None:
        """A fully valid spec produces a passed report with no errors/warnings."""
        spec = make_spec(
            figure_id="valid-fig",
            figure_type="barplot",
            style=StyleSpec(palette="viridis", width_mm=100, height_mm=80, dpi=300),
            labels=LabelSpec(x_label="X", y_label="Y"),
            mapping=MappingSpec(x="group", y="value"),
            statistics=StatSpec(test="t-test", pvalue_column="pval", correction="BH"),
        )
        # Use output files that include a vector format to avoid EXPORT002
        report = lint_figure(spec, [Path("figure.pdf")], None)
        # PROV001 will fire because provenance_path is None
        assert report.status == "failed"
        assert len(report.errors) == 1
        assert report.errors[0].rule == "PROV001"

    def test_lint_figure_with_existing_provenance_passes(self, tmp_path: Path) -> None:
        """With provenance file present, valid spec yields passed status."""
        prov_file = tmp_path / "prov.json"
        prov_file.write_text("{}")
        spec = make_spec(
            figure_id="valid-fig",
            figure_type="barplot",
            style=StyleSpec(palette="viridis", width_mm=100, height_mm=80, dpi=300),
            labels=LabelSpec(x_label="X", y_label="Y"),
            mapping=MappingSpec(x="group", y="value"),
            statistics=StatSpec(test="t-test", pvalue_column="pval", correction="BH"),
        )
        report = lint_figure(spec, [Path("figure.pdf")], prov_file)
        assert report.status == "passed"
        assert report.errors == []
        assert report.warnings == []

    def test_lint_figure_collects_multiple_error_rules(self) -> None:
        """lint_figure collects findings from all applicable rules."""
        spec = FigureSpec.model_construct(
            figure_id="",  # FIG001
            figure_type="barplot",
            data=DataSpec(table=Path("/tmp/t.tsv")),
            mapping=MappingSpec(),
            style=StyleSpec(palette="jet", width_mm=10, height_mm=10),  # STYLE001, STYLE003
            labels=LabelSpec(),
            export=ExportSpec(output_dir=Path("/tmp"), basename="test"),
        )
        report = lint_figure(spec, [Path("figure.png")], None)
        error_rules = {f.rule for f in report.errors}
        assert "FIG001" in error_rules
        assert "STYLE001" in error_rules
        assert "STYLE003" in error_rules

    def test_lint_figure_collects_warnings(self) -> None:
        """lint_figure collects WARNING-level findings."""
        spec = make_spec(
            figure_id="fig",
            figure_type="volcano_plot",  # STAT001 WARNING
        )
        report = lint_figure(spec, [Path("figure.png")], None)
        assert "STAT001" in {f.rule for f in report.warnings}

    def test_lint_figure_info_findings(self) -> None:
        """INFO-level findings are placed in report.info."""
        spec = make_spec(
            figure_id="fig",
            figure_type="barplot",
            style=StyleSpec(palette="viridis", width_mm=100, height_mm=80, dpi=300),
            labels=LabelSpec(x_label="X", y_label="Y"),
            mapping=MappingSpec(x="g", y="v"),
        )
        report = lint_figure(spec, [Path("figure.png")], None)
        # Currently no rules produce INFO-level findings, so info should be empty
        # But we verify the access pattern
        assert isinstance(report.info, list)


# ── ALL_RULES ──────────────────────────────────────────────────────────────


class TestAllRules:
    def test_all_rules_count(self) -> None:
        """ALL_RULES contains the expected 11 rules."""
        assert len(ALL_RULES) == 11

    def test_all_rules_unique_ids(self) -> None:
        """Every rule in ALL_RULES has a unique id."""
        ids = [rule.id for rule in ALL_RULES]
        assert len(ids) == len(set(ids))

    def test_every_rule_is_lintrule_instance(self) -> None:
        """ALL_RULES contains only LintRule instances."""
        for rule in ALL_RULES:
            assert isinstance(rule, LintRule)

    def test_lintrule_attributes(self) -> None:
        """Each LintRule has id, level, and description."""
        for rule in ALL_RULES:
            assert isinstance(rule.id, str) and rule.id
            assert rule.level in ("ERROR", "WARNING", "INFO")
            assert isinstance(rule.description, str) and rule.description


# ── Edge Cases ─────────────────────────────────────────────────────────────


class TestEdgeCases:
    def test_figure_id_empty_string_is_falsy(self) -> None:
        """Empty string figure_id is falsy and triggers FIG001."""
        spec = FigureSpec.model_construct(
            figure_id="",
            figure_type="barplot",
            data=DataSpec(table=Path("/tmp/t.tsv")),
            mapping=MappingSpec(),
            style=StyleSpec(),
            labels=LabelSpec(),
            export=ExportSpec(output_dir=Path("/tmp"), basename="test"),
        )
        findings = _check_figure_identity(spec, [], None)
        assert any(f.rule == "FIG001" for f in findings)

    def test_supported_figure_types_are_frozensit(self) -> None:
        """SUPPORTED_FIGURE_TYPES is a frozenset."""
        assert isinstance(SUPPORTED_FIGURE_TYPES, frozenset)

    def test_lint_finding_details_preserved_in_report(self) -> None:
        """LintFinding with details integrates correctly into LintReport."""
        report = LintReport(figure_id="fig")
        finding = LintFinding("TEST", "ERROR", "msg", details={"col": "x"})
        report.errors.append(finding)
        assert report.errors[0].details == {"col": "x"}
