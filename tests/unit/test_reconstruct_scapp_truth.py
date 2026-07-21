from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


def _module():
    path = Path(__file__).parents[2] / "scripts" / "reconstruct_scapp_truth.py"
    spec = importlib.util.spec_from_file_location("reconstruct_scapp_truth", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_merged_length_unions_overlaps_and_adjoining_intervals() -> None:
    module = _module()

    assert module.merged_length([]) == 0
    assert module.merged_length([(8, 10), (1, 3), (3, 6)]) == 9
    assert module.merged_length([(1, 1), (3, 3)]) == 2


def test_two_stage_gates_only_use_matching_contigs_for_reference_coverage(tmp_path: Path) -> None:
    module = _module()
    blast = tmp_path / "hits.tsv"
    blast.write_text(
        # Two matching contigs jointly cover ref1 completely.
        "contig1\t100\tref1\t100\t90\t90\t1\t90\t1\t60\t100\n"
        "contig2\t50\tref1\t100\t95\t50\t1\t50\t61\t100\t100\n"
        # This pair is exactly 85% covered and must fail the strict >85% gate.
        "contig3\t100\tref2\t100\t95\t85\t1\t85\t1\t100\t100\n"
        # This HSP is exactly 85% identity and must be excluded.
        "contig4\t100\tref3\t100\t85\t100\t1\t100\t1\t100\t100\n",
        encoding="utf-8",
    )

    references, pairs, selected = module.reconstruct_truth(
        blast,
        min_identity=85,
        min_contig_coverage=0.85,
        min_reference_coverage=0.90,
    )

    by_reference = {row["reference_id"]: row for row in references}
    assert selected == {"ref1"}
    assert by_reference["ref1"]["coverage_fraction"] == "1.00000000"
    assert by_reference["ref1"]["matching_contig_count"] == 2
    assert by_reference["ref2"]["covered_bases"] == 0
    assert "ref3" not in by_reference
    assert sum(row["matching_contig_reference_pair"] == "true" for row in pairs) == 2


def test_main_writes_pair_audit_and_selected_fasta(tmp_path: Path, monkeypatch) -> None:
    module = _module()
    blast = tmp_path / "hits.tsv"
    blast.write_text(
        "contig1\t100\tref1\t100\t95\t100\t1\t100\t1\t100\t200\n",
        encoding="utf-8",
    )
    fasta = tmp_path / "references.fasta"
    fasta.write_text(">ref1\nACGT\n>ref2\nTGCA\n", encoding="utf-8")
    coverage = tmp_path / "coverage.tsv"
    pair_coverage = tmp_path / "pairs.tsv"
    summary_json = tmp_path / "truth_summary.json"
    selected = tmp_path / "selected.fasta"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "reconstruct_scapp_truth.py",
            "--blast-tsv",
            str(blast),
            "--fasta",
            str(fasta),
            "--coverage-tsv",
            str(coverage),
            "--pair-coverage-tsv",
            str(pair_coverage),
            "--summary-json",
            str(summary_json),
            "--selected-fasta",
            str(selected),
        ],
    )

    module.main()

    assert coverage.read_text(encoding="utf-8").splitlines()[1].endswith("\ttrue")
    assert pair_coverage.read_text(encoding="utf-8").splitlines()[1].endswith("\ttrue")
    assert selected.read_text(encoding="utf-8") == ">ref1\nACGT\n"
    summary = json.loads(summary_json.read_text(encoding="utf-8"))
    assert summary["counts"] == {
        "identity_filtered_contig_reference_pairs": 1,
        "matching_contig_reference_pairs": 1,
        "references_with_identity_filtered_hits": 1,
        "selected_truth_references": 1,
    }
    assert summary["inputs"]["blast_tsv_sha256"]
    assert summary["inputs"]["reference_fasta_sha256"]


def test_rejects_legacy_blast_columns_without_contig_and_reference_coordinates(
    tmp_path: Path,
) -> None:
    module = _module()
    blast = tmp_path / "legacy.tsv"
    blast.write_text("ref1\t100\tcontig1\t95\t50\t1\t50\t100\n", encoding="utf-8")

    with pytest.raises(ValueError, match="expected 11 BLAST columns"):
        module.reconstruct_truth(
            blast,
            min_identity=85,
            min_contig_coverage=0.85,
            min_reference_coverage=0.90,
        )
