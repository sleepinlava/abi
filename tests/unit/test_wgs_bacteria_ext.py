"""Extended unit tests for wgs_bacteria plugin: edge/error paths."""

from __future__ import annotations

from pathlib import Path

import pytest

from abi.plugins.wgs_bacteria import (
    WGSBacteriaPlugin,
    _compute_gc_content,
    _compute_n50,
    _parse_prokka,
    _parse_sample_sheet,
    _parse_spades,
)

# ── build_sample_context(): missing sample_sheet → ValueError ─────────


def test_build_sample_context_missing_sample_sheet_raises_value_error() -> None:
    """build_sample_context() without input.sample_sheet raises ValueError."""
    plugin = WGSBacteriaPlugin()
    config: dict = {}
    with pytest.raises(ValueError, match="sample_sheet"):
        plugin.build_sample_context(config)


# ── _validate_config(): missing required config keys → ValueError ──────


def test_validate_config_missing_required_keys_raises_value_error() -> None:
    """_validate_config() lists all missing required keys in the error."""
    plugin = WGSBacteriaPlugin()
    with pytest.raises(ValueError, match="Missing wgs_bacteria config keys"):
        plugin._validate_config({})
    # call with only project_name → should still fail on the other 5
    with pytest.raises(ValueError, match="Missing wgs_bacteria config keys"):
        plugin._validate_config({"project_name": "test"})


# ── _parse_sample_sheet(): file doesn't exist when check_files=True ────


def test_parse_sample_sheet_nonexistent_file_check_files_true_raises() -> None:
    """_parse_sample_sheet() raises ValueError when path is missing and check_files=True."""
    path = "/nonexistent/sample_sheet_42.tsv"
    with pytest.raises(ValueError, match="does not exist"):
        _parse_sample_sheet(path, check_files=True)


# ── _parse_spades(): empty FASTA → no entries ──────────────────────────


def test_parse_spades_empty_fasta_returns_empty_list(tmp_path: Path) -> None:
    """_parse_spades() returns [] when contigs.fasta has no sequences."""
    fasta = tmp_path / "contigs.fasta"
    fasta.write_text(">contig_1\n")
    result = _parse_spades(tmp_path, "sample_1")
    assert result == []


def test_parse_spades_no_contigs_file_returns_empty_list(tmp_path: Path) -> None:
    """_parse_spades() returns [] when directory has no contigs.fasta."""
    result = _parse_spades(tmp_path, "sample_1")
    assert result == []


# ── _parse_prokka(): GFF line with <9 tab-separated columns → skipped ──


def test_parse_prokka_short_gff_line_skipped(tmp_path: Path) -> None:
    """_parse_prokka() skips GFF lines with fewer than 9 tab-separated columns."""
    gff = tmp_path / "test.gff"
    gff.write_text("chr1\tsource\tgene\t1\t100\t.\t+\t.\n")
    result = _parse_prokka(tmp_path, "sample_1")
    assert result == []


# ── _compute_n50(): empty lengths → 0 ──────────────────────────────────


def test_compute_n50_empty_lengths_returns_zero() -> None:
    """_compute_n50([]) returns 0."""
    assert _compute_n50([]) == 0


# ── _compute_gc_content(): no valid bases (only N's) → None ────────────


def test_compute_gc_content_all_n_bases_returns_none(tmp_path: Path) -> None:
    """_compute_gc_content() returns None when FASTA contains only non-ATGCU bases."""
    fasta = tmp_path / "only_n.fasta"
    fasta.write_text(">seq\nNNNNNNNNNN\nNNNNN\n")
    assert _compute_gc_content(fasta) is None
