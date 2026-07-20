#!/usr/bin/env python3
"""Score plasmid predictions against a frozen SCAPP-style truth set.

The expected headerless BLAST columns are::

    qseqid qlen sseqid slen pident length qstart qend sstart send bitscore

Queries are plasmid predictions and subjects are truth references. A pair is a
match only when identity is strictly greater than 80% and the union of matching
regions covers strictly more than 90% of both sequences. For real samples, one
prediction per identical matched-reference set is counted as a true positive;
additional predictions with that same reference set are duplicate false
positives, following the SCAPP supplementary method's split-plasmid penalty.
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
    prediction_length: int
    reference_length: int
    prediction_intervals: list[tuple[int, int]] = field(default_factory=list)
    reference_intervals: list[tuple[int, int]] = field(default_factory=list)
    hsp_count: int = 0


def merged_length(intervals: list[tuple[int, int]]) -> int:
    if not intervals:
        return 0
    ordered = sorted(intervals)
    start, end = ordered[0]
    total = 0
    for current_start, current_end in ordered[1:]:
        if current_start > end + 1:
            total += end - start + 1
            start, end = current_start, current_end
        else:
            end = max(end, current_end)
    return total + end - start + 1


def fasta_lengths(path: Path) -> dict[str, int]:
    lengths: dict[str, int] = {}
    identifier: str | None = None
    length = 0
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.startswith(">"):
                if identifier is not None:
                    lengths[identifier] = length
                identifier = line[1:].split(maxsplit=1)[0]
                if not identifier or identifier in lengths:
                    raise ValueError(
                        f"Invalid or duplicate FASTA identifier in {path}: {identifier}"
                    )
                length = 0
            elif identifier is not None:
                length += len(line.strip())
    if identifier is not None:
        lengths[identifier] = length
    if not lengths:
        raise ValueError(f"No FASTA records found in {path}")
    return lengths


def score_predictions(
    blast_tsv: Path,
    prediction_lengths: dict[str, int],
    reference_lengths: dict[str, int],
    *,
    min_identity: float,
    min_coverage: float,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
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
                prediction_id,
                prediction_length_raw,
                reference_id,
                reference_length_raw,
                identity_raw,
                _alignment_length,
                prediction_start_raw,
                prediction_end_raw,
                reference_start_raw,
                reference_end_raw,
                _bitscore,
            ) = row
            if prediction_id not in prediction_lengths:
                raise ValueError(f"BLAST query is absent from prediction FASTA: {prediction_id}")
            if reference_id not in reference_lengths:
                raise ValueError(f"BLAST subject is absent from truth FASTA: {reference_id}")
            prediction_length = int(prediction_length_raw)
            reference_length = int(reference_length_raw)
            if prediction_length != prediction_lengths[prediction_id]:
                raise ValueError(f"BLAST/FASTA prediction length mismatch: {prediction_id}")
            if reference_length != reference_lengths[reference_id]:
                raise ValueError(f"BLAST/FASTA reference length mismatch: {reference_id}")
            if float(identity_raw) <= min_identity:
                continue
            key = (prediction_id, reference_id)
            evidence = pairs.setdefault(key, PairEvidence(prediction_length, reference_length))
            prediction_interval = _bounded_interval(
                prediction_start_raw, prediction_end_raw, prediction_length
            )
            reference_interval = _bounded_interval(
                reference_start_raw, reference_end_raw, reference_length
            )
            if prediction_interval and reference_interval:
                evidence.prediction_intervals.append(prediction_interval)
                evidence.reference_intervals.append(reference_interval)
                evidence.hsp_count += 1

    matched_references: dict[str, set[str]] = defaultdict(set)
    pair_rows: list[dict[str, Any]] = []
    pair_strength: dict[tuple[str, str], float] = {}
    all_pair_strength: dict[tuple[str, str], float] = {}
    for (prediction_id, reference_id), evidence in sorted(pairs.items()):
        prediction_covered = merged_length(evidence.prediction_intervals)
        reference_covered = merged_length(evidence.reference_intervals)
        prediction_fraction = min(1.0, prediction_covered / evidence.prediction_length)
        reference_fraction = min(1.0, reference_covered / evidence.reference_length)
        is_match = prediction_fraction > min_coverage and reference_fraction > min_coverage
        all_pair_strength[(prediction_id, reference_id)] = min(
            prediction_fraction, reference_fraction
        )
        if is_match:
            matched_references[prediction_id].add(reference_id)
            pair_strength[(prediction_id, reference_id)] = min(
                prediction_fraction, reference_fraction
            )
        pair_rows.append(
            {
                "prediction_id": prediction_id,
                "prediction_length": evidence.prediction_length,
                "reference_id": reference_id,
                "reference_length": evidence.reference_length,
                "identity_filtered_hsp_count": evidence.hsp_count,
                "prediction_covered_bases": prediction_covered,
                "prediction_coverage_fraction": f"{prediction_fraction:.8f}",
                "reference_covered_bases": reference_covered,
                "reference_coverage_fraction": f"{reference_fraction:.8f}",
                "matched": str(is_match).lower(),
            }
        )

    signature_groups: dict[tuple[str, ...], list[str]] = defaultdict(list)
    for prediction_id, matched_set in matched_references.items():
        signature_groups[tuple(sorted(matched_set))].append(prediction_id)
    selected_true_positives: set[str] = set()
    for signature, prediction_ids in signature_groups.items():
        selected_true_positives.add(
            sorted(
                prediction_ids,
                key=lambda prediction_id: (
                    -max(pair_strength[(prediction_id, reference)] for reference in signature),
                    prediction_id,
                ),
            )[0]
        )

    prediction_rows: list[dict[str, Any]] = []
    for prediction_id in sorted(prediction_lengths):
        reference_signature = tuple(sorted(matched_references.get(prediction_id, set())))
        best_coverage = max(
            (
                strength
                for (candidate, _reference), strength in all_pair_strength.items()
                if candidate == prediction_id
            ),
            default=0.0,
        )
        if not reference_signature:
            status = "false_positive_no_match"
        elif prediction_id in selected_true_positives:
            status = "true_positive"
        else:
            status = "false_positive_duplicate_match_signature"
        prediction_rows.append(
            {
                "prediction_id": prediction_id,
                "prediction_length": prediction_lengths[prediction_id],
                "matched_reference_count": len(reference_signature),
                "matched_reference_ids": ",".join(reference_signature),
                "best_bidirectional_coverage_fraction": f"{best_coverage:.8f}",
                "match_signature_sha256": (
                    _signature_sha256(reference_signature) if reference_signature else ""
                ),
                "status": status,
            }
        )

    recalled_by: dict[str, list[str]] = defaultdict(list)
    for prediction_id, matched_set in matched_references.items():
        for reference_id in matched_set:
            recalled_by[reference_id].append(prediction_id)
    reference_rows = [
        {
            "reference_id": reference_id,
            "reference_length": reference_lengths[reference_id],
            "recalled": str(reference_id in recalled_by).lower(),
            "matching_prediction_count": len(recalled_by[reference_id]),
            "matching_prediction_ids": ",".join(sorted(recalled_by[reference_id])),
        }
        for reference_id in sorted(reference_lengths)
    ]

    true_positives = len(selected_true_positives)
    total_predictions = len(prediction_lengths)
    recalled_references = len(recalled_by)
    total_references = len(reference_lengths)
    precision = true_positives / total_predictions
    recall = recalled_references / total_references
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    summary = {
        "thresholds": {
            "identity_strictly_greater_than_percent": min_identity,
            "bidirectional_coverage_strictly_greater_than_fraction": min_coverage,
        },
        "duplicate_policy": (
            "One true-positive prediction per identical non-empty set of matched truth "
            "references; additional predictions with that signature are false positives."
        ),
        "counts": {
            "total_predictions": total_predictions,
            "raw_predictions_with_match": len(matched_references),
            "true_positive_predictions_after_duplicate_penalty": true_positives,
            "duplicate_false_positive_predictions": len(matched_references) - true_positives,
            "no_match_false_positive_predictions": total_predictions - len(matched_references),
            "total_truth_references": total_references,
            "recalled_truth_references": recalled_references,
            "false_negative_truth_references": total_references - recalled_references,
        },
        "metrics": {
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "precision_percent": 100 * precision,
            "recall_percent": 100 * recall,
            "f1_percent": 100 * f1,
        },
    }
    return pair_rows, prediction_rows, reference_rows, summary


def derived_tables(
    prediction_rows: list[dict[str, Any]], summary: dict[str, Any]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    counts = summary["counts"]
    metrics = summary["metrics"]
    metric_rows = [
        {
            "metric": (
                "Precision "
                f"({counts['true_positive_predictions_after_duplicate_penalty']}/"
                f"{counts['total_predictions']})"
            ),
            "percent": metrics["precision_percent"],
            "numerator": counts["true_positive_predictions_after_duplicate_penalty"],
            "denominator": counts["total_predictions"],
            "definition": "True-positive ABI predictions after duplicate-signature penalty",
        },
        {
            "metric": (
                f"Recall ({counts['recalled_truth_references']}/{counts['total_truth_references']})"
            ),
            "percent": metrics["recall_percent"],
            "numerator": counts["recalled_truth_references"],
            "denominator": counts["total_truth_references"],
            "definition": "Truth references recalled by at least one ABI prediction",
        },
        {
            "metric": "F1",
            "percent": metrics["f1_percent"],
            "numerator": "",
            "denominator": "",
            "definition": "Harmonic mean of paper-method precision and recall",
        },
    ]
    directional_rows = [
        {
            "direction": f"Truth references (n={counts['total_truth_references']})",
            "Matched": counts["recalled_truth_references"],
            "Unmatched": counts["false_negative_truth_references"],
        },
        {
            "direction": f"ABI predictions (n={counts['total_predictions']})",
            "Matched": counts["true_positive_predictions_after_duplicate_penalty"],
            "Unmatched": (
                counts["duplicate_false_positive_predictions"]
                + counts["no_match_false_positive_predictions"]
            ),
        },
    ]
    evidence_rows = [
        {
            "reference_id": row["prediction_id"],
            "reference_length": row["prediction_length"],
            "coverage_fraction": row["best_bidirectional_coverage_fraction"],
            "hit_count": row["matched_reference_count"],
            "selected": str(row["status"] == "true_positive").lower(),
            "prediction_status": row["status"],
        }
        for row in prediction_rows
    ]
    return metric_rows, directional_rows, evidence_rows


def _bounded_interval(start_raw: str, end_raw: str, length: int) -> tuple[int, int] | None:
    start, end = sorted((int(start_raw), int(end_raw)))
    start = max(1, start)
    end = min(length, end)
    return (start, end) if start <= end else None


def _signature_sha256(references: tuple[str, ...]) -> str:
    return hashlib.sha256("\n".join(references).encode()).hexdigest()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_tsv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--blast-tsv", type=Path, required=True)
    parser.add_argument("--predictions-fasta", type=Path, required=True)
    parser.add_argument("--truth-fasta", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--min-identity", type=float, default=80.0)
    parser.add_argument("--min-coverage", type=float, default=0.90)
    args = parser.parse_args()
    prediction_lengths = fasta_lengths(args.predictions_fasta)
    reference_lengths = fasta_lengths(args.truth_fasta)
    pair_rows, prediction_rows, reference_rows, summary = score_predictions(
        args.blast_tsv,
        prediction_lengths,
        reference_lengths,
        min_identity=args.min_identity,
        min_coverage=args.min_coverage,
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    _write_tsv(
        args.output_dir / "prediction_reference_pairs.tsv",
        pair_rows,
        list(pair_rows[0]) if pair_rows else ["prediction_id"],
    )
    _write_tsv(args.output_dir / "prediction_status.tsv", prediction_rows, list(prediction_rows[0]))
    _write_tsv(args.output_dir / "truth_status.tsv", reference_rows, list(reference_rows[0]))
    metric_rows, directional_rows, evidence_rows = derived_tables(prediction_rows, summary)
    _write_tsv(args.output_dir / "figure_metrics.tsv", metric_rows, list(metric_rows[0]))
    _write_tsv(
        args.output_dir / "figure_directional_recovery.tsv",
        directional_rows,
        list(directional_rows[0]),
    )
    _write_tsv(args.output_dir / "evidence_match_table.tsv", evidence_rows, list(evidence_rows[0]))
    summary["inputs"] = {
        "blast_tsv": _portable_path(args.blast_tsv, args.output_dir),
        "blast_tsv_sha256": _sha256(args.blast_tsv),
        "predictions_fasta": _portable_path(args.predictions_fasta, args.output_dir),
        "predictions_fasta_sha256": _sha256(args.predictions_fasta),
        "truth_fasta": _portable_path(args.truth_fasta, args.output_dir),
        "truth_fasta_sha256": _sha256(args.truth_fasta),
    }
    (args.output_dir / "score_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))


def _portable_path(path: Path, output_dir: Path) -> str:
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(output_dir.resolve()))
    except ValueError:
        return str(resolved)


if __name__ == "__main__":
    main()
