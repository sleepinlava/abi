#!/usr/bin/env python3
"""Reconstruct SCAPP's two-stage PLSDB truth set from BLAST HSPs.

The expected headerless BLAST columns are::

    qseqid qlen sseqid slen pident length qstart qend sstart send bitscore

Here the query is a metaSPAdes contig and the subject is a PLSDB reference.
This orientation is required because the paper first filters contig/reference
pairs by contig coverage, then measures reference coverage using only those
matching contigs.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class PairEvidence:
    """Identity-filtered HSP evidence for one contig/reference pair."""

    contig_length: int
    reference_length: int
    contig_intervals: list[tuple[int, int]] = field(default_factory=list)
    reference_intervals: list[tuple[int, int]] = field(default_factory=list)
    hsp_count: int = 0


def merged_length(intervals: list[tuple[int, int]]) -> int:
    """Return the inclusive length of the union of one-based intervals."""
    if not intervals:
        return 0
    ordered = sorted(intervals)
    total = 0
    start, end = ordered[0]
    for current_start, current_end in ordered[1:]:
        if current_start > end + 1:
            total += end - start + 1
            start, end = current_start, current_end
        else:
            end = max(end, current_end)
    return total + end - start + 1


def extract_fasta(source: Path, selected: set[str], destination: Path) -> int:
    """Write records whose first FASTA header token is in ``selected``."""
    written = 0
    keep = False
    with (
        source.open(encoding="utf-8") as input_handle,
        destination.open("w", encoding="utf-8") as output_handle,
    ):
        for line in input_handle:
            if line.startswith(">"):
                identifier = line[1:].split(maxsplit=1)[0]
                keep = identifier in selected
                written += int(keep)
            if keep:
                output_handle.write(line)
    return written


def reconstruct_truth(
    blast_tsv: Path,
    *,
    min_identity: float,
    min_contig_coverage: float,
    min_reference_coverage: float,
) -> tuple[list[dict[str, object]], list[dict[str, object]], set[str]]:
    """Apply the paper's contig gate followed by its reference coverage gate."""
    pairs: dict[tuple[str, str], PairEvidence] = {}
    with blast_tsv.open(encoding="utf-8", newline="") as handle:
        for line_number, row in enumerate(csv.reader(handle, delimiter="\t"), start=1):
            if not row:
                continue
            if len(row) != 11:
                raise ValueError(
                    f"{blast_tsv}:{line_number}: expected 11 BLAST columns, got {len(row)}"
                )
            (
                contig_id,
                contig_length_raw,
                reference_id,
                reference_length_raw,
                identity_raw,
                _alignment_length,
                contig_start_raw,
                contig_end_raw,
                reference_start_raw,
                reference_end_raw,
                _bitscore,
            ) = row
            identity = float(identity_raw)
            # The supplementary method uses strict greater-than thresholds.
            if identity <= min_identity:
                continue
            contig_length = int(contig_length_raw)
            reference_length = int(reference_length_raw)
            key = (contig_id, reference_id)
            evidence = pairs.setdefault(key, PairEvidence(contig_length, reference_length))
            if (evidence.contig_length, evidence.reference_length) != (
                contig_length,
                reference_length,
            ):
                raise ValueError(f"Inconsistent sequence lengths for BLAST pair {key}")
            contig_interval = _bounded_interval(contig_start_raw, contig_end_raw, contig_length)
            reference_interval = _bounded_interval(
                reference_start_raw, reference_end_raw, reference_length
            )
            if contig_interval and reference_interval:
                evidence.contig_intervals.append(contig_interval)
                evidence.reference_intervals.append(reference_interval)
                evidence.hsp_count += 1

    reference_lengths: dict[str, int] = {}
    reference_intervals: dict[str, list[tuple[int, int]]] = defaultdict(list)
    reference_contigs: dict[str, set[str]] = defaultdict(set)
    reference_hsp_counts: dict[str, int] = defaultdict(int)
    pair_rows: list[dict[str, object]] = []
    for (contig_id, reference_id), evidence in sorted(pairs.items()):
        reference_lengths[reference_id] = evidence.reference_length
        contig_covered = merged_length(evidence.contig_intervals)
        contig_fraction = min(1.0, contig_covered / evidence.contig_length)
        is_matching_pair = contig_fraction > min_contig_coverage
        pair_rows.append(
            {
                "contig_id": contig_id,
                "contig_length": evidence.contig_length,
                "reference_id": reference_id,
                "reference_length": evidence.reference_length,
                "identity_filtered_hsp_count": evidence.hsp_count,
                "contig_covered_bases": contig_covered,
                "contig_coverage_fraction": f"{contig_fraction:.8f}",
                "matching_contig_reference_pair": str(is_matching_pair).lower(),
            }
        )
        if is_matching_pair:
            reference_intervals[reference_id].extend(evidence.reference_intervals)
            reference_contigs[reference_id].add(contig_id)
            reference_hsp_counts[reference_id] += evidence.hsp_count

    selected: set[str] = set()
    reference_rows: list[dict[str, object]] = []
    for reference_id in sorted(reference_lengths):
        reference_length = reference_lengths[reference_id]
        covered = merged_length(reference_intervals[reference_id])
        fraction = min(1.0, covered / reference_length)
        is_selected = fraction > min_reference_coverage
        if is_selected:
            selected.add(reference_id)
        contigs = sorted(reference_contigs[reference_id])
        reference_rows.append(
            {
                "reference_id": reference_id,
                "reference_length": reference_length,
                "covered_bases": covered,
                "coverage_fraction": f"{fraction:.8f}",
                "hit_count": reference_hsp_counts[reference_id],
                "matching_contig_count": len(contigs),
                "matching_contig_ids": ",".join(contigs),
                "selected": str(is_selected).lower(),
            }
        )
    return reference_rows, pair_rows, selected


def _bounded_interval(start_raw: str, end_raw: str, length: int) -> tuple[int, int] | None:
    start, end = sorted((int(start_raw), int(end_raw)))
    start = max(1, start)
    end = min(length, end)
    return (start, end) if start <= end else None


def _write_tsv(path: Path, rows: list[dict[str, object]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _portable_path(path: Path, base_dir: Path) -> str:
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(base_dir.resolve()))
    except ValueError:
        return str(resolved)


def build_summary(
    *,
    blast_tsv: Path,
    fasta: Path,
    summary_dir: Path,
    reference_rows: list[dict[str, object]],
    pair_rows: list[dict[str, object]],
    selected: set[str],
    min_identity: float,
    min_contig_coverage: float,
    min_reference_coverage: float,
) -> dict[str, Any]:
    return {
        "method": (
            "SCAPP supplementary methods S5 two-stage truth reconstruction: identity-filtered "
            "contig coverage gate followed by reference coverage gate."
        ),
        "thresholds": {
            "identity_strictly_greater_than_percent": min_identity,
            "contig_coverage_strictly_greater_than_fraction": min_contig_coverage,
            "reference_coverage_strictly_greater_than_fraction": min_reference_coverage,
        },
        "inputs": {
            "blast_tsv": _portable_path(blast_tsv, summary_dir),
            "blast_tsv_sha256": _sha256(blast_tsv),
            "reference_fasta": _portable_path(fasta, summary_dir),
            "reference_fasta_sha256": _sha256(fasta),
        },
        "counts": {
            "identity_filtered_contig_reference_pairs": len(pair_rows),
            "matching_contig_reference_pairs": sum(
                row["matching_contig_reference_pair"] == "true" for row in pair_rows
            ),
            "references_with_identity_filtered_hits": len(reference_rows),
            "selected_truth_references": len(selected),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--blast-tsv", type=Path, required=True)
    parser.add_argument("--fasta", type=Path, required=True)
    parser.add_argument("--coverage-tsv", type=Path, required=True)
    parser.add_argument("--pair-coverage-tsv", type=Path)
    parser.add_argument("--summary-json", type=Path)
    parser.add_argument("--selected-fasta", type=Path, required=True)
    parser.add_argument("--min-identity", type=float, default=85.0)
    parser.add_argument("--min-contig-coverage", type=float, default=0.85)
    parser.add_argument(
        "--min-reference-coverage",
        "--min-coverage",
        dest="min_reference_coverage",
        type=float,
        default=0.90,
    )
    args = parser.parse_args()
    for name in ("min_contig_coverage", "min_reference_coverage"):
        value = getattr(args, name)
        if not 0 <= value <= 1:
            parser.error(f"--{name.replace('_', '-')} must be between 0 and 1")

    reference_rows, pair_rows, selected = reconstruct_truth(
        args.blast_tsv,
        min_identity=args.min_identity,
        min_contig_coverage=args.min_contig_coverage,
        min_reference_coverage=args.min_reference_coverage,
    )
    _write_tsv(
        args.coverage_tsv,
        reference_rows,
        [
            "reference_id",
            "reference_length",
            "covered_bases",
            "coverage_fraction",
            "hit_count",
            "matching_contig_count",
            "matching_contig_ids",
            "selected",
        ],
    )
    if args.pair_coverage_tsv:
        _write_tsv(
            args.pair_coverage_tsv,
            pair_rows,
            [
                "contig_id",
                "contig_length",
                "reference_id",
                "reference_length",
                "identity_filtered_hsp_count",
                "contig_covered_bases",
                "contig_coverage_fraction",
                "matching_contig_reference_pair",
            ],
        )
    if args.summary_json:
        args.summary_json.parent.mkdir(parents=True, exist_ok=True)
        summary = build_summary(
            blast_tsv=args.blast_tsv,
            fasta=args.fasta,
            summary_dir=args.summary_json.parent,
            reference_rows=reference_rows,
            pair_rows=pair_rows,
            selected=selected,
            min_identity=args.min_identity,
            min_contig_coverage=args.min_contig_coverage,
            min_reference_coverage=args.min_reference_coverage,
        )
        args.summary_json.write_text(
            json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
    written = extract_fasta(args.fasta, selected, args.selected_fasta)
    if written != len(selected):
        raise SystemExit(
            f"Extracted {written} FASTA records for {len(selected)} selected references"
        )
    matching_pairs = sum(row["matching_contig_reference_pair"] == "true" for row in pair_rows)
    print(f"matching_contig_reference_pairs={matching_pairs}")
    print(f"selected_references={len(selected)}")


if __name__ == "__main__":
    main()
