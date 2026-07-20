#!/usr/bin/env python3
"""Stratify SCAPP plasmid evidence by assembly-derived reference matching."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import statistics
from collections import Counter
from pathlib import Path
from typing import Any, Iterable


def analyze_evidence(
    result_dir: str | Path,
    match_table: str | Path,
    mob_table: str | Path,
    output_dir: str | Path,
) -> dict[str, Any]:
    root = Path(result_dir).resolve()
    output = Path(output_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)
    tables = root / "tables"

    consensus = {_seq_id(row["contig_id"]) for row in _read_tsv(tables / "plasmid_consensus.tsv")}
    matches = {_seq_id(row["reference_id"]): row for row in _read_tsv(Path(match_table))}
    paper_method_classification = any(row.get("prediction_status") for row in matches.values())
    extra = sorted(set(matches) - consensus)
    if extra:
        raise ValueError(f"Reference matching contains non-consensus IDs: {extra}")

    structure = {
        _seq_id(row["plasmid_id"]): row for row in _read_tsv(tables / "plasmid_structure.tsv")
    }
    abundance = {
        _seq_id(row["plasmid_id"]): row for row in _read_tsv(tables / "plasmid_abundance.tsv")
    }
    annotations: Counter[str] = Counter(
        _seq_id(row["contig_id"]) for row in _read_tsv(tables / "annotations.tsv")
    )
    amr: Counter[str] = Counter(
        _seq_id(row["contig_id"]) for row in _read_tsv(tables / "amr_genes.tsv")
    )
    plasmidfinder = {
        _seq_id(row["contig_id"])
        for row in _read_tsv(tables / "plasmid_typing.tsv")
        if row.get("tool") == "plasmidfinder" and row.get("type_id") not in {"", "-"}
    }
    mob = {_seq_id(row["sample_id"]): row for row in _read_tsv(Path(mob_table))}
    if set(mob) != consensus:
        raise ValueError("MOB-typer rows do not match the consensus plasmid set")

    rows = []
    for plasmid_id in sorted(consensus):
        match = matches.get(
            plasmid_id,
            {
                "reference_id": plasmid_id,
                "reference_length": "",
                "coverage_fraction": "0",
                "hit_count": "0",
                "selected": "false",
            },
        )
        struct = structure.get(plasmid_id, {})
        abundance_row = abundance.get(plasmid_id, {})
        mob_row = mob[plasmid_id]
        abundance_coverage = _as_float(abundance_row.get("coverage"))
        length_bp = _as_float(struct.get("length_bp") or match.get("reference_length"))
        rows.append(
            {
                "plasmid_id": plasmid_id,
                "reference_hit_present": plasmid_id in matches,
                "reference_matched": _as_bool(match.get("selected")),
                "prediction_status": match.get("prediction_status", ""),
                "reference_coverage_fraction": _as_float(match.get("coverage_fraction")),
                "length_bp": length_bp,
                "log10_length_bp": math.log10(length_bp) if length_bp and length_bp > 0 else None,
                "abundance_coverage": abundance_coverage,
                "log10_abundance_coverage": (
                    math.log10(abundance_coverage)
                    if abundance_coverage and abundance_coverage > 0
                    else None
                ),
                "is_circular": _as_bool(struct.get("is_circular")),
                "terminal_overlap_bp": _as_float(struct.get("terminal_overlap_bp")),
                "annotation_count": annotations[plasmid_id],
                "amr_hit_count": amr[plasmid_id],
                "plasmidfinder_positive": plasmid_id in plasmidfinder,
                "mob_replicon_positive": _present(mob_row.get("rep_type(s)")),
                "mob_relaxase_positive": _present(mob_row.get("relaxase_type(s)")),
                "mob_orit_positive": _present(mob_row.get("orit_type(s)")),
                "predicted_mobility": mob_row.get("predicted_mobility", ""),
            }
        )

    _write_tsv(output / "evidence_by_plasmid.tsv", rows)
    grouped = {
        "reference_matched": _summarize(row for row in rows if row["reference_matched"]),
        "reference_unmatched": _summarize(row for row in rows if not row["reference_matched"]),
    }
    summary = {
        "result_dir": str(root),
        "match_table": str(Path(match_table).resolve()),
        "mob_table": str(Path(mob_table).resolve()),
        "total_plasmids": len(rows),
        "input_sha256": {
            "match_table": _sha256(Path(match_table)),
            "mob_table": _sha256(Path(mob_table)),
            **{
                f"tables/{name}.tsv": _sha256(tables / f"{name}.tsv")
                for name in (
                    "plasmid_consensus",
                    "plasmid_structure",
                    "plasmid_abundance",
                    "annotations",
                    "amr_genes",
                    "plasmid_typing",
                )
            },
        },
        "groups": grouped,
        "classification_mode": (
            "paper_method_prediction_status"
            if paper_method_classification
            else "legacy_reference_match_status"
        ),
        "interpretation_limit": (
            "Reference matching is an assembly-derived technical consistency check. "
            "An unmatched prediction is not necessarily a biological false positive."
        ),
    }
    (output / "evidence_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    label_stems = (
        {
            "reference_matched": "True-positive prediction",
            "reference_unmatched": "False-positive prediction",
        }
        if paper_method_classification
        else None
    )
    _write_figure_tables(output, grouped, label_stems=label_stems)
    return summary


def _summarize(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    rows = list(rows)
    numeric = [
        "reference_coverage_fraction",
        "length_bp",
        "abundance_coverage",
        "terminal_overlap_bp",
        "annotation_count",
        "amr_hit_count",
    ]
    boolean = [
        "is_circular",
        "reference_hit_present",
        "plasmidfinder_positive",
        "mob_replicon_positive",
        "mob_relaxase_positive",
        "mob_orit_positive",
    ]
    result: dict[str, Any] = {"count": len(rows)}
    for field in numeric:
        values = [float(row[field]) for row in rows if row[field] is not None]
        result[f"median_{field}"] = statistics.median(values) if values else None
    for field in boolean:
        positives = sum(bool(row[field]) for row in rows)
        result[f"{field}_count"] = positives
        result[f"{field}_rate"] = positives / len(rows) if rows else None
    result["mobility_counts"] = dict(Counter(row["predicted_mobility"] for row in rows))
    return result


def _read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def _write_tsv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise ValueError("Cannot write empty evidence table")
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=list(rows[0]), delimiter="\t", lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(rows)


def _write_figure_tables(
    output: Path,
    grouped: dict[str, dict[str, Any]],
    *,
    label_stems: dict[str, str] | None = None,
) -> None:
    label_stems = label_stems or {
        "reference_matched": "Reference matched",
        "reference_unmatched": "Reference unmatched",
    }
    evidence = [
        ("Circular / terminal overlap", "is_circular"),
        ("PlasmidFinder", "plasmidfinder_positive"),
        ("MOB replicon", "mob_replicon_positive"),
        ("Relaxase", "mob_relaxase_positive"),
        ("oriT", "mob_orit_positive"),
    ]
    rate_rows = []
    mobility_rows = []
    for group, values in grouped.items():
        denominator = int(values["count"])
        group_label = f"{label_stems[group]} (n={denominator})"
        for evidence_label, field in evidence:
            count = int(values[f"{field}_count"])
            rate_rows.append(
                {
                    "evidence": evidence_label,
                    "group": group_label,
                    "count": count,
                    "denominator": denominator,
                    "percent": 100 * count / denominator,
                }
            )
        mobility = values["mobility_counts"]
        mobility_rows.append(
            {
                "group": group_label,
                "Mobilizable": int(mobility.get("mobilizable", 0)),
                "Non-mobilizable": int(mobility.get("non-mobilizable", 0)),
            }
        )
    _write_tsv(output / "figure_evidence_rates.tsv", rate_rows)
    _write_tsv(output / "figure_mobility_composition.tsv", mobility_rows)


def _seq_id(value: str) -> str:
    return str(value).split(maxsplit=1)[0]


def _present(value: Any) -> bool:
    return str(value or "") not in {"", "-", "NA", "N/A"}


def _as_bool(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes"}


def _as_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--result-dir", required=True, type=Path)
    parser.add_argument("--match-table", required=True, type=Path)
    parser.add_argument("--mob-table", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    print(
        json.dumps(
            analyze_evidence(args.result_dir, args.match_table, args.mob_table, args.output_dir),
            indent=2,
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
