"""FigureLint rules — publication-quality checks for scientific figures.

Each rule has:
- id: Unique rule identifier (FIG001, DATA001, etc.)
- level: ERROR (blocking), WARNING (advisory), or INFO (suggestion)
- description: Human-readable rule description
- check: Function that inspects a FigureSpec + rendered output
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from abi.sciplot.schema.figure_spec import FigureSpec

# ── Data structures / 数据结构 ────────────────────────────────────────────


@dataclass
class LintFinding:
    """A single lint finding."""

    rule: str
    level: str  # "ERROR", "WARNING", "INFO"
    message: str
    details: Optional[Dict[str, Any]] = None


@dataclass
class LintReport:
    """Complete lint report for one figure."""

    figure_id: str
    errors: list[LintFinding] = field(default_factory=list)
    warnings: list[LintFinding] = field(default_factory=list)
    info: list[LintFinding] = field(default_factory=list)

    @property
    def status(self) -> str:
        if self.errors:
            return "failed"
        return "passed"

    def to_dict(self) -> dict:
        return {
            "figure_id": self.figure_id,
            "status": self.status,
            "errors": [
                {"rule": f.rule, "level": f.level, "message": f.message} for f in self.errors
            ],
            "warnings": [
                {"rule": f.rule, "level": f.level, "message": f.message} for f in self.warnings
            ],
            "info": [{"rule": f.rule, "level": f.level, "message": f.message} for f in self.info],
        }


# ── Rule definitions / 规则定义 ──────────────────────────────────────────


class LintRule:
    """A single lint rule with its check function."""

    def __init__(
        self, id: str, level: str, description: str, check: Callable[..., List[LintFinding]]
    ) -> None:
        self.id = id
        self.level = level
        self.description = description
        self._check = check

    def apply(
        self, spec: FigureSpec, output_files: List[Path], provenance_path: Optional[Path] = None
    ) -> List[LintFinding]:
        """Run this rule and return findings."""
        try:
            return self._check(spec, output_files, provenance_path)
        except Exception as exc:
            return [
                LintFinding(
                    rule=self.id,
                    level="ERROR",
                    message=f"Rule {self.id} raised: {exc}",
                )
            ]


# ── Check functions / 检查函数 ───────────────────────────────────────────


def _check_figure_identity(
    spec: FigureSpec, output_files: List[Path], provenance_path: Optional[Path]
) -> List[LintFinding]:
    """FIG001-FIG003: Basic figure identity checks."""
    findings: List[LintFinding] = []
    # FIG001 - figure_id
    if not spec.figure_id:
        findings.append(LintFinding("FIG001", "ERROR", "figure_id is required."))
    # FIG002 - figure_type
    if not spec.figure_type:
        findings.append(LintFinding("FIG002", "ERROR", "figure_type is required."))
    # FIG003 - figure_type in whitelist
    from abi.sciplot.schema.figure_spec import SUPPORTED_FIGURE_TYPES

    if spec.figure_type and spec.figure_type not in SUPPORTED_FIGURE_TYPES:
        findings.append(
            LintFinding(
                "FIG003",
                "ERROR",
                f"Unknown figure_type '{spec.figure_type}'. "
                f"Supported: {sorted(SUPPORTED_FIGURE_TYPES)}",
            )
        )
    return findings


def _check_style(
    spec: FigureSpec, output_files: List[Path], provenance_path: Optional[Path]
) -> List[LintFinding]:
    """STYLE001-STYLE003: Style-related checks."""
    findings: List[LintFinding] = []
    palette_lower = spec.style.palette.lower()
    # STYLE001 - forbidden palette
    from abi.sciplot.schema.palette_spec import FORBIDDEN_PALETTES, FORBIDDEN_SUBSTRINGS

    if palette_lower in FORBIDDEN_PALETTES:
        findings.append(
            LintFinding(
                "STYLE001",
                "ERROR",
                f"Palette '{spec.style.palette}' is forbidden. "
                f"Use a perceptually uniform alternative like 'viridis' or 'colorblind_safe_8'.",
            )
        )
    for substr in FORBIDDEN_SUBSTRINGS:
        if substr in palette_lower:
            findings.append(
                LintFinding(
                    "STYLE001",
                    "ERROR",
                    f"Palette '{spec.style.palette}' matches forbidden pattern '{substr}'.",
                )
            )
            break
    # STYLE003 - font size too small
    if spec.style.width_mm < 20 or spec.style.height_mm < 20:
        findings.append(
            LintFinding(
                "STYLE003",
                "ERROR",
                f"Figure dimensions too small: {spec.style.width_mm}x{spec.style.height_mm}mm. "
                f"Minimum is 20x20mm.",
            )
        )
    return findings


def _check_statistics(
    spec: FigureSpec, output_files: List[Path], provenance_path: Optional[Path]
) -> List[LintFinding]:
    """STAT001-STAT002: Statistical annotation checks."""
    findings: List[LintFinding] = []
    # STAT001 - significance markers require statistical test
    figure_types_that_need_stats = {"volcano_plot", "boxplot_with_points", "violin_with_box"}
    if spec.figure_type in figure_types_that_need_stats:
        if not spec.statistics or not spec.statistics.test:
            findings.append(
                LintFinding(
                    "STAT001",
                    "WARNING",
                    f"Figure type '{spec.figure_type}' typically shows group comparisons "
                    f"but no statistical test is declared in the statistics block.",
                )
            )
    if spec.statistics and spec.statistics.test:
        if not spec.statistics.pvalue_column:
            findings.append(
                LintFinding(
                    "STAT001",
                    "ERROR",
                    "statistics.test is declared but pvalue_column is not set.",
                )
            )
        # STAT002 - multiple-testing correction
        if not spec.statistics.correction:
            findings.append(
                LintFinding(
                    "STAT002",
                    "WARNING",
                    "Statistical test declared without multiple-testing correction. "
                    "If multiple comparisons were performed, declare the correction method.",
                )
            )
    return findings


def _check_labels(
    spec: FigureSpec, output_files: List[Path], provenance_path: Optional[Path]
) -> List[LintFinding]:
    """LABEL001-LABEL002: Label checks."""
    findings: List[LintFinding] = []
    if spec.figure_type != "heatmap":
        if not spec.labels.x_label and not spec.mapping.x:
            findings.append(
                LintFinding(
                    "LABEL001",
                    "WARNING",
                    "x-axis label is empty.",
                )
            )
        if not spec.labels.y_label and not spec.mapping.y:
            findings.append(
                LintFinding(
                    "LABEL001",
                    "WARNING",
                    "y-axis label is empty.",
                )
            )
    return findings


def _check_export(
    spec: FigureSpec, output_files: List[Path], provenance_path: Optional[Path]
) -> List[LintFinding]:
    """EXPORT001-EXPORT002: Export format checks."""
    findings: List[LintFinding] = []
    out_names = {p.suffix.lower() for p in output_files}
    # EXPORT001 - raster DPI
    for fmt in ("png", "tiff"):
        if f".{fmt}" in out_names and spec.style.dpi < 300:
            findings.append(
                LintFinding(
                    "EXPORT001",
                    "ERROR",
                    f"{fmt.upper()} export at {spec.style.dpi} dpi is below the 300 dpi minimum.",
                )
            )
    # EXPORT002 - missing vector format
    if ".pdf" not in out_names and ".svg" not in out_names:
        findings.append(
            LintFinding(
                "EXPORT002",
                "WARNING",
                "No vector format (PDF/SVG) in export. "
                "Vector formats are recommended for publication.",
            )
        )
    return findings


def _check_provenance(
    spec: FigureSpec, output_files: List[Path], provenance_path: Optional[Path]
) -> List[LintFinding]:
    """PROV001-PROV002: Provenance checks."""
    findings: List[LintFinding] = []
    if provenance_path is None:
        findings.append(
            LintFinding(
                "PROV001",
                "ERROR",
                "No provenance file was generated.",
            )
        )
    elif not Path(provenance_path).exists():
        findings.append(
            LintFinding(
                "PROV001",
                "ERROR",
                f"Provenance file not found: {provenance_path}",
            )
        )
    return findings


# ── Registry / 注册表 ────────────────────────────────────────────────────

ALL_RULES: List[LintRule] = [
    LintRule("FIG001", "ERROR", "figure_id is required", _check_figure_identity),
    LintRule("FIG002", "ERROR", "figure_type is required", _check_figure_identity),
    LintRule("FIG003", "ERROR", "figure_type in whitelist", _check_figure_identity),
    LintRule("STYLE001", "ERROR", "No forbidden palettes", _check_style),
    LintRule("STYLE003", "ERROR", "Minimum font size", _check_style),
    LintRule("STAT001", "ERROR", "Statistical test declared for significance", _check_statistics),
    LintRule("STAT002", "WARNING", "Multiple-testing correction declared", _check_statistics),
    LintRule("LABEL001", "WARNING", "Axis labels present", _check_labels),
    LintRule("EXPORT001", "ERROR", "Raster DPI minimum", _check_export),
    LintRule("EXPORT002", "WARNING", "Vector format present", _check_export),
    LintRule("PROV001", "ERROR", "Provenance file exists", _check_provenance),
]


def lint_figure(
    spec: FigureSpec, output_files: List[Path], provenance_path: Optional[Path] = None
) -> LintReport:
    """Run all lint rules against a rendered figure.

    Returns a LintReport with errors, warnings, and info findings.
    """
    report = LintReport(figure_id=spec.figure_id)
    for rule in ALL_RULES:
        findings = rule.apply(spec, output_files, provenance_path)
        for f in findings:
            if f.level == "ERROR":
                report.errors.append(f)
            elif f.level == "WARNING":
                report.warnings.append(f)
            else:
                report.info.append(f)
    return report
