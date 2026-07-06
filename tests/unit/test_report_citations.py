"""Unit tests for abi.report.citations — CitationRegistry, load_citations, formatters."""

from __future__ import annotations

from pathlib import Path
import yaml

from abi.report.citations import (
    CitationRegistry,
    format_citations_html,
    format_citations_markdown,
    load_citations,
)


# ── CitationRegistry ───────────────────────────────────────────────────────


def test_citation_registry_from_yaml_non_list(tmp_path: Path) -> None:
    """L68: citations key is not a list → fallback to empty."""
    path = tmp_path / "citations.yaml"
    path.write_text("citations: not_a_list\n", encoding="utf-8")
    registry = CitationRegistry.from_yaml(path)
    assert registry.all == []


def test_citation_registry_for_tool() -> None:
    """L78: for_tool() filters by tool_id."""
    registry = CitationRegistry([
        {"tool": "fastp", "stage": "qc", "citation": "Chen et al. 2018"},
        {"tool": "STAR", "stage": "alignment", "citation": "Dobin et al. 2013"},
        {"tool": "fastp", "stage": "trimming", "citation": "Chen et al. 2018"},
    ])
    results = registry.for_tool("fastp")
    assert len(results) == 2
    assert all(c["tool"] == "fastp" for c in results)


def test_citation_registry_for_stage() -> None:
    """L82: for_stage() filters by stage."""
    registry = CitationRegistry([
        {"tool": "fastp", "stage": "qc", "citation": "Chen et al. 2018"},
        {"tool": "STAR", "stage": "alignment", "citation": "Dobin et al. 2013"},
        {"tool": "bowtie2", "stage": "alignment", "citation": "Langmead 2012"},
    ])
    results = registry.for_stage("alignment")
    assert len(results) == 2
    assert all(c["stage"] == "alignment" for c in results)


def test_citation_registry_to_dicts() -> None:
    """L97: to_dicts() returns all citations as canonical dict list."""
    registry = CitationRegistry([
        {"tool": "fastp", "stage": "qc", "citation": "Chen et al. 2018"},
    ])
    result = registry.to_dicts()
    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0]["citation"] == "Chen et al. 2018"


# ── load_citations ─────────────────────────────────────────────────────────


def test_load_citations_with_list_source() -> None:
    """L109: load_citations() with list source."""
    result = load_citations([
        {"tool": "fastp", "citation": "Chen et al. 2018"},
    ])
    assert len(result) == 1
    assert result[0]["tool"] == "fastp"


def test_load_citations_with_iterable_source() -> None:
    """L111: load_citations() with non-str/non-Path iterable (tuple)."""
    result = load_citations((
        {"tool": "fastp", "stage": "qc", "citation": "Chen et al. 2018"},
        {"tool": "STAR", "stage": "alignment", "citation": "Dobin et al. 2013"},
    ))
    assert len(result) == 2
    assert result[0]["tool"] == "fastp"


def test_load_citations_with_set_source() -> None:
    """load_citations() with a non-list iterable."""
    def _gen():
        yield {"tool": "fastp", "citation": "Chen et al. 2018"}
    result = load_citations(_gen())  # type: ignore[arg-type]
    assert len(result) == 1
    assert result[0]["tool"] == "fastp"


# ── format_citations_markdown ──────────────────────────────────────────────


def test_format_citations_markdown_empty() -> None:
    """L125: format_citations_markdown() with empty list → ''."""
    result = format_citations_markdown([])
    assert result == ""


def test_format_citations_markdown_tool_only() -> None:
    """L133-134: citation with tool but no stage → tool-only line."""
    result = format_citations_markdown([
        {"tool": "fastp", "citation": "Chen et al. 2018"},
    ])
    assert "**fastp**:" in result
    assert "(" not in result.split("**fastp**:")[0]


def test_format_citations_markdown_citation_only() -> None:
    """L135-136: citation with no tool and no stage → bare citation."""
    result = format_citations_markdown([
        {"citation": "Some generic reference."},
    ])
    assert "1. Some generic reference." in result
    assert "**" not in result


def test_format_citations_markdown_full() -> None:
    """Tool + stage + citation."""
    result = format_citations_markdown([
        {"tool": "STAR", "stage": "alignment", "citation": "Dobin et al. 2013"},
    ])
    assert "**STAR** (alignment): Dobin et al. 2013" in result


# ── format_citations_html ──────────────────────────────────────────────────


def test_format_citations_html_empty() -> None:
    """L151: format_citations_html() with empty list → ''."""
    result = format_citations_html([])
    assert result == ""


def test_format_citations_html_tool_only() -> None:
    """L161-162: citation with tool but no stage → <strong>tool</strong>."""
    result = format_citations_html([
        {"tool": "fastp", "citation": "Chen et al. 2018"},
    ])
    assert "<strong>fastp</strong>:" in result
    assert "(" not in result


def test_format_citations_html_citation_only() -> None:
    """L163-164: citation with no tool and no stage → bare <li>."""
    result = format_citations_html([
        {"citation": "Some reference."},
    ])
    assert "<li>Some reference.</li>" in result
    assert "<strong>" not in result


# ── Unique citations ───────────────────────────────────────────────────────


def test_citation_registry_unique_citations() -> None:
    """unique_citations() deduplicates and preserves order."""
    registry = CitationRegistry([
        {"tool": "fastp", "stage": "qc", "citation": "Chen et al. 2018"},
        {"tool": "STAR", "stage": "alignment", "citation": "Dobin et al. 2013"},
        {"tool": "fastp", "stage": "trimming", "citation": "Chen et al. 2018"},
        {"tool": "bowtie2", "stage": "alignment", "citation": "Langmead 2012"},
    ])
    result = registry.unique_citations()
    assert result == ["Chen et al. 2018", "Dobin et al. 2013", "Langmead 2012"]


def test_citation_registry_unique_empty_citation() -> None:
    """unique_citations() skips empty citation strings."""
    registry = CitationRegistry([
        {"tool": "fastp", "citation": ""},
        {"tool": "STAR", "citation": "Dobin et al. 2013"},
    ])
    result = registry.unique_citations()
    assert result == ["Dobin et al. 2013"]


# ── for_tool / for_stage with no matches ───────────────────────────────────


def test_citation_registry_for_tool_no_match() -> None:
    """for_tool() with unknown tool → empty list."""
    registry = CitationRegistry([
        {"tool": "fastp", "stage": "qc", "citation": "Chen et al. 2018"},
    ])
    assert registry.for_tool("nonexistent") == []


def test_citation_registry_for_stage_no_match() -> None:
    """for_stage() with unknown stage → empty list."""
    registry = CitationRegistry([
        {"tool": "fastp", "stage": "qc", "citation": "Chen et al. 2018"},
    ])
    assert registry.for_stage("nonexistent") == []


# ── load_citations with YAML file ──────────────────────────────────────────


def test_load_citations_from_yaml_file(tmp_path: Path) -> None:
    """L112: load_citations() with str/Path → loads from YAML file."""
    path = tmp_path / "citations.yaml"
    path.write_text(
        "citations:\n"
        "  - tool: fastp\n"
        "    stage: qc\n"
        "    citation: Chen et al. 2018\n",
        encoding="utf-8",
    )
    result = load_citations(path)
    assert len(result) == 1
    assert result[0]["tool"] == "fastp"
    assert result[0]["citation"] == "Chen et al. 2018"


def test_load_citations_from_str_path(tmp_path: Path) -> None:
    """load_citations() with string path → resolves to Path."""
    path = tmp_path / "citations.yaml"
    path.write_text(
        "citations:\n"
        "  - tool: STAR\n"
        "    citation: Dobin et al. 2013\n",
        encoding="utf-8",
    )
    result = load_citations(str(path))
    assert len(result) == 1
    assert result[0]["tool"] == "STAR"


# ── format_citations with custom titles ────────────────────────────────────


def test_format_citations_markdown_custom_title() -> None:
    """Custom title in markdown format."""
    result = format_citations_markdown(
        [{"citation": "A reference."}],
        title="Bibliography",
    )
    assert "## Bibliography" in result


def test_format_citations_html_custom_title() -> None:
    """Custom title in HTML format."""
    result = format_citations_html(
        [{"citation": "A reference."}],
        title="Bibliography",
    )
    assert "<h2>Bibliography</h2>" in result


def test_format_citations_html_full_entry() -> None:
    """Full tool + stage + citation in HTML."""
    result = format_citations_html([
        {"tool": "STAR", "stage": "alignment", "citation": "Dobin et al. 2013"},
    ])
    assert "<strong>STAR</strong> (alignment): Dobin et al. 2013" in result
