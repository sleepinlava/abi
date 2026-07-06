"""Unit tests for abi.report.html — write_html_report (figures, citations)."""

from __future__ import annotations

from pathlib import Path

from abi.report.html import write_html_report


class _FakePlan:
    def to_dict(self):
        return {
            "project_name": "test-project",
            "analysis_type": "rnaseq",
            "steps": [
                {"step_id": "S1_qc", "tool_id": "fastp", "category": "qc", "sample_id": "S1"},
            ],
        }


# ── Figures section ──────────────────────────────────────────────────────


def test_write_html_report_with_rendered_figures(tmp_path: Path) -> None:
    """L134-154: rendered_figures section with real PNG paths."""
    result_dir = tmp_path
    figures_dir = tmp_path / "figures"
    figures_dir.mkdir()

    # Create a real PNG file under result_dir so relative_to works
    png = figures_dir / "qc_read_counts.png"
    png.write_text("fake-png-content")

    rendered_figures = {"qc_read_counts": png}

    path = write_html_report(
        result_dir,
        plan=_FakePlan(),
        table_summary={},
        rendered_figures=rendered_figures,
    )
    content = path.read_text(encoding="utf-8")
    assert "<section>\n<h2>Figures</h2>" in content
    assert 'id="fig-qc_read_counts"' in content
    assert 'src="../figures/qc_read_counts.png"' in content


def test_write_html_report_figure_outside_result_dir(tmp_path: Path) -> None:
    """Figure path NOT under result_dir → ValueError branch (L144)."""
    result_dir = tmp_path / "results"
    result_dir.mkdir()
    # Path outside result_dir
    external_png = tmp_path / "external_figure.png"
    external_png.write_text("external")

    rendered_figures = {"external_fig": external_png}

    path = write_html_report(
        result_dir,
        plan=_FakePlan(),
        table_summary={},
        rendered_figures=rendered_figures,
    )
    content = path.read_text(encoding="utf-8")
    assert 'id="fig-external_fig"' in content
    # Should use the absolute or full path reference
    assert 'src="../' in content


# ── Citations: edge cases ────────────────────────────────────────────────


def test_write_html_report_citation_no_tool_stage() -> None:
    """L203: citation with no tool and no stage → bare <li>citation</li>."""
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        result_dir = Path(tmp)
        citations = [
            {"tool": "", "stage": "", "citation": "Just a reference."},
        ]
        path = write_html_report(
            result_dir,
            plan=_FakePlan(),
            table_summary={},
            citations=citations,
        )
        content = path.read_text(encoding="utf-8")
        assert "<h2>References</h2>" in content
        assert "<li>Just a reference.</li>" in content


def test_write_html_report_citation_tool_only() -> None:
    """Citation with tool but no stage."""
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        result_dir = Path(tmp)
        citations = [
            {"tool": "fastp", "stage": "", "citation": "Chen et al. 2018"},
        ]
        path = write_html_report(
            result_dir,
            plan=_FakePlan(),
            table_summary={},
            citations=citations,
        )
        content = path.read_text(encoding="utf-8")
        assert "<strong>fastp</strong>: Chen et al. 2018" in content


# ── Methods section ────────────────────────────────────────────────────────


def test_write_html_report_with_methods_md(tmp_path: Path) -> None:
    """L157-165: Methods section with pre-rendered methods markdown."""
    result_dir = tmp_path
    path = write_html_report(
        result_dir,
        plan=_FakePlan(),
        table_summary={},
        methods_md="# Methods\n\nSome methods content.",
    )
    content = path.read_text(encoding="utf-8")
    assert "<h2>Methods</h2>" in content
    assert "Some methods content." in content


# ── Limitations section ────────────────────────────────────────────────────


def test_write_html_report_with_limitations(tmp_path: Path) -> None:
    """L168-183: Limitations section."""
    result_dir = tmp_path
    path = write_html_report(
        result_dir,
        plan=_FakePlan(),
        table_summary={},
        limitations_yaml=["Limitation 1", "Limitation 2"],
    )
    content = path.read_text(encoding="utf-8")
    assert "<h2>Known Limitations</h2>" in content
    assert "<li>Limitation 1</li>" in content
    assert "<li>Limitation 2</li>" in content


# ── No figures / no optional sections ──────────────────────────────────────


def test_write_html_report_no_figures(tmp_path: Path) -> None:
    """No rendered_figures → no Figures section."""
    result_dir = tmp_path
    path = write_html_report(
        result_dir,
        plan=_FakePlan(),
        table_summary={},
    )
    content = path.read_text(encoding="utf-8")
    assert "<h2>Figures</h2>" not in content


def test_write_html_report_table_summary_rows(tmp_path: Path) -> None:
    """L116-122: Table summary with actual rows/count data."""
    result_dir = tmp_path
    path = write_html_report(
        result_dir,
        plan=_FakePlan(),
        table_summary={
            "qc": {"rows": 42, "path": "tables/qc.tsv"},
        },
    )
    content = path.read_text(encoding="utf-8")
    assert "<td>42</td>" in content
    assert "qc.tsv" in content


# ── Plan without steps ─────────────────────────────────────────────────────


def test_write_html_report_empty_steps(tmp_path: Path) -> None:
    """Plan with no steps → 'none' for tools used."""

    class EmptyPlan:
        def to_dict(self):
            return {
                "project_name": "empty",
                "analysis_type": "test",
                "steps": [],
            }

    result_dir = tmp_path
    path = write_html_report(
        result_dir,
        plan=EmptyPlan(),
        table_summary={},
    )
    content = path.read_text(encoding="utf-8")
    assert "none" in content
