"""Unit tests for rnaseq_expression parsers against fixture data."""

from __future__ import annotations

from pathlib import Path

from abi.plugins import get_plugin

_FIXTURES = Path("tests/fixtures/tool_outputs")


# ── fastp parser ──────────────────────────────────────────────────────────


def test_fastp_parser_emits_correct_metrics():
    plugin = get_plugin("rnaseq_expression")
    result = plugin.parse_outputs("fastp", _FIXTURES / "fastp", "S1")
    rows = result["qc_summary"]
    # 6 metrics: 3 before_filtering + 3 after_filtering
    assert len(rows) == 6
    assert all(r["sample_id"] == "S1" for r in rows)
    assert all(r["tool"] == "fastp" for r in rows)
    # Verify specific metric values
    before_total = [r for r in rows if r["metric"] == "before_filtering.total_reads"]
    assert len(before_total) == 1
    assert before_total[0]["value"] == 20
    after_total = [r for r in rows if r["metric"] == "after_filtering.total_reads"]
    assert len(after_total) == 1
    assert after_total[0]["value"] == 18


def test_fastp_parser_empty_dir_returns_empty():
    plugin = get_plugin("rnaseq_expression")
    result = plugin.parse_outputs("fastp", Path("/nonexistent/dir"), "S1")
    # qc_summary key exists but rows list is empty
    assert result["qc_summary"] == []


# ── STAR parser ───────────────────────────────────────────────────────────


def test_star_parser_extracts_all_metrics():
    plugin = get_plugin("rnaseq_expression")
    result = plugin.parse_outputs("star", _FIXTURES / "star", "S1")
    rows = result["alignment_summary"]
    # The fixture has ~28 pipe-delimited lines
    assert len(rows) >= 20
    assert all(r["sample_id"] == "S1" for r in rows)
    assert all(r["tool"] == "star" for r in rows)
    # Verify key metrics
    by_metric = {r["metric"]: r["value"] for r in rows}
    assert by_metric["Number of input reads"] == "1000000"
    assert by_metric["Uniquely mapped reads %"] == "85.00"
    assert by_metric["Uniquely mapped reads number"] == "850000"


def test_star_parser_hisat2_alias():
    """hisat2 is an alias for the same parser path."""
    plugin = get_plugin("rnaseq_expression")
    result = plugin.parse_outputs("hisat2", _FIXTURES / "star", "S1")
    rows = result["alignment_summary"]
    assert len(rows) >= 20
    assert all(r["tool"] == "star" for r in rows)
