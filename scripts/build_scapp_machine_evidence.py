#!/usr/bin/env python3
"""Build a portable, machine-readable evidence record for SCAPP validation."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "abi.scapp.paper_method_evidence.v1"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return value


def _read_provenance(path: Path) -> dict[str, str]:
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.reader(handle, delimiter="\t"))
    invalid = [index for index, row in enumerate(rows, start=1) if len(row) != 2]
    if invalid:
        raise ValueError(f"Invalid two-column provenance rows in {path}: {invalid}")
    return {key: value for key, value in rows}


def build_evidence(output_dir: Path) -> dict[str, Any]:
    root = output_dir.resolve()
    required = {
        "truth_summary": root / "truth_summary.json",
        "score_summary": root / "score_summary.json",
        "run_provenance": root / "run_provenance.tsv",
        "truth_reference_coverage": root / "truth_reference_coverage.tsv",
        "truth_contig_reference_pairs": root / "truth_contig_reference_pairs.tsv",
        "prediction_reference_pairs": root / "prediction_reference_pairs.tsv",
        "prediction_status": root / "prediction_status.tsv",
        "truth_status": root / "truth_status.tsv",
        "figure_metrics": root / "figure_metrics.tsv",
        "figure_directional_recovery": root / "figure_directional_recovery.tsv",
        "evidence_match_table": root / "evidence_match_table.tsv",
    }
    missing = [str(path) for path in required.values() if not path.is_file()]
    if missing:
        raise FileNotFoundError("Missing SCAPP evidence files: " + ", ".join(missing))

    truth = _read_json(required["truth_summary"])
    score = _read_json(required["score_summary"])
    provenance = _read_provenance(required["run_provenance"])
    counts = score["counts"]
    metrics = score["metrics"]
    true_positives = int(counts["true_positive_predictions_after_duplicate_penalty"])
    false_positives = int(counts["duplicate_false_positive_predictions"]) + int(
        counts["no_match_false_positive_predictions"]
    )
    false_negatives = int(counts["false_negative_truth_references"])

    artifacts = {
        role: {"path": path.name, "sha256": _sha256(path)}
        for role, path in sorted(required.items())
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "evidence_id": "scapp_srr11038083_plsdb_2018_12_05_paper_method_v1",
        "status": "complete",
        "analysis_type": "metagenomic_plasmid",
        "sample_accession": "SRR11038083",
        "evaluation_scope": "paper-method reconstruction; not paper-exact",
        "reference_method": {
            "name": "SCAPP supplementary methods S5",
            "truth_thresholds": truth["thresholds"],
            "scoring_thresholds": score["thresholds"],
            "duplicate_policy": score["duplicate_policy"],
        },
        "confusion_counts": {
            "true_positive_predictions": true_positives,
            "false_positive_predictions": false_positives,
            "false_negative_truth_references": false_negatives,
            "truth_references": int(counts["total_truth_references"]),
            "predictions": int(counts["total_predictions"]),
        },
        "metrics": {
            "precision": float(metrics["precision"]),
            "recall": float(metrics["recall"]),
            "f1": float(metrics["f1"]),
        },
        "truth_reconstruction_counts": truth["counts"],
        "database_scope": {
            "archive_records": int(provenance["plsdb_input_records"]),
            "paper_reported_deduplicated_records": int(
                provenance["paper_reported_deduplicated_plsdb_records"]
            ),
            "note": provenance["database_scope_note"],
        },
        "limitations": [
            "The paper-specific 13,469-record PLSDB deduplication list and evaluation code "
            "were not published; the official 14,739-record archive is used.",
            "Duplicate predictions are penalized by identical non-empty matched-reference "
            "signatures, the closest reproducible implementation of the published prose.",
            "Metrics describe agreement with the reconstructed reference set, not proof of "
            "biological truth for every unmatched prediction.",
        ],
        "code_and_input_hashes": {
            key: value
            for key, value in provenance.items()
            if key.endswith("_sha256") or key in {"abi_git_commit", "abi_git_dirty"}
        },
        "artifacts": artifacts,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--output-json", type=Path)
    args = parser.parse_args()
    evidence = build_evidence(args.output_dir)
    destination = args.output_json or args.output_dir / "machine_readable_evidence.json"
    destination.write_text(
        json.dumps(evidence, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(evidence, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
