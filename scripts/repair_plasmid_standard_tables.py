#!/usr/bin/env python3
"""Backfill public plasmid result tables from an existing successful ABI result."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from abi.plugins.metagenomic_plasmid._engine.pipeline import (
    _read_fasta_records,
    _terminal_overlap_length,
)
from abi.plugins.metagenomic_plasmid._engine.standard_tables import (
    expand_standard_rows,
    read_standard_table,
    summarize_standard_tables,
    write_standard_table,
)

SOURCE_TABLES = (
    "qc_summary",
    "assembly_summary",
    "abundance",
    "annotations",
    "host_predictions",
    "differential_abundance",
)

MODULE_TABLES = {
    "qc": ("qc_summary", "sample_qc"),
    "assembly": ("assembly_summary", "assembly_qc"),
    "plasmid_detection": ("plasmid_predictions", "plasmid_consensus", "plasmid_structure"),
    "typing": ("plasmid_typing",),
    "annotation": ("annotations", "plasmid_annotation", "amr_genes", "mge_elements"),
    "abundance": ("abundance", "plasmid_abundance"),
    "plasmid_binning": ("plasmid_bins", "bin_to_contig"),
    "host_prediction": ("host_predictions", "host_profile", "host_plasmid_links"),
    "comparative_genomics": ("plasmid_catalog", "comparative_hits"),
    "diversity": ("sample_diversity", "differential_abundance"),
    "network": ("network_edges", "network_nodes"),
}


def repair_result(result_dir: str | Path) -> dict[str, Any]:
    root = Path(result_dir).resolve()
    plan_path = root / "execution_plan.json"
    summary_path = root / "provenance" / "run_summary.json"
    tables_dir = root / "tables"
    if not plan_path.is_file() or not summary_path.is_file() or not tables_dir.is_dir():
        raise ValueError(f"Not a complete ABI result directory: {root}")

    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    analysis_type = plan.get("analysis_type") or summary.get("analysis_type")
    if analysis_type != "metagenomic_plasmid":
        raise ValueError(f"Expected metagenomic_plasmid result, found {analysis_type!r}")
    if summary.get("status") != "success":
        raise ValueError("Refusing to repair a result whose run_summary status is not success")

    before = _table_hashes(tables_dir)
    summary_backup = summary_path.with_name("run_summary.pre_plasmid_standard_tables_v1.json")
    if not summary_backup.exists():
        shutil.copy2(summary_path, summary_backup)
    written: dict[str, int] = {}
    for source_table in SOURCE_TABLES:
        source_rows = read_standard_table(tables_dir, source_table)
        mirrors = expand_standard_rows({source_table: source_rows})
        for table_name, rows in mirrors.items():
            if table_name == source_table:
                continue
            write_standard_table(tables_dir, table_name, rows)
            written[table_name] = len(rows)

    structure_rows = _structure_rows(root)
    write_standard_table(tables_dir, "plasmid_structure", structure_rows)
    written["plasmid_structure"] = len(structure_rows)

    status_rows = _analysis_status_rows(plan, tables_dir)
    write_standard_table(tables_dir, "analysis_status", status_rows)
    written["analysis_status"] = len(status_rows)

    table_summary = summarize_standard_tables(tables_dir)
    summary["standard_tables"] = table_summary
    summary_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    repair_record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "repair": "plasmid_standard_tables_v1",
        "result_dir": str(root),
        "source_table_sha256": before,
        "run_summary_backup": str(summary_backup),
        "written_rows": written,
        "repaired_table_sha256": {
            name: _sha256(tables_dir / f"{name}.tsv") for name in sorted(written)
        },
    }
    repairs_path = root / "provenance" / "repairs.jsonl"
    with repairs_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(repair_record, ensure_ascii=False) + "\n")
    return repair_record


def _structure_rows(root: Path) -> list[dict[str, Any]]:
    rows = []
    for fasta in sorted((root / "04_plasmid_detection").glob("*/plasmid_contigs.fasta")):
        sample_id = fasta.parent.name
        for record in _read_fasta_records(fasta):
            sequence = record["sequence"].upper()
            overlap = _terminal_overlap_length(sequence)
            header_circular = any(
                marker in record["header"].lower()
                for marker in ("circular=true", "topology=circular", "_circular")
            )
            rows.append(
                {
                    "sample_id": sample_id,
                    "plasmid_id": record["id"],
                    "length_bp": len(sequence),
                    "is_circular": str(bool(header_circular or overlap >= 20)).lower(),
                    "terminal_overlap_bp": overlap,
                    "method": "header_or_exact_terminal_overlap",
                    "warnings": (
                        "Sequence-based circularity is predictive and should be confirmed from "
                        "the assembly graph or read support."
                    ),
                    "source_file": str(fasta),
                }
            )
    return rows


def _analysis_status_rows(plan: dict[str, Any], tables_dir: Path) -> list[dict[str, Any]]:
    active = {
        str(step.get("category", ""))
        for step in plan.get("steps", [])
        if isinstance(step, dict) and not step.get("skipped", False)
    }
    sample_count = len(plan.get("samples", []))
    rows = []
    for module, table_names in MODULE_TABLES.items():
        table_counts = {name: len(read_standard_table(tables_dir, name)) for name in table_names}
        total_rows = sum(table_counts.values())
        enabled = module in active
        rows.append(
            {
                "module": module,
                "status": (
                    "not_enabled"
                    if not enabled
                    else "completed_with_rows"
                    if total_rows
                    else "completed_no_hits"
                ),
                "reason": (
                    f"active execution-plan category; table_rows={table_counts}"
                    if enabled
                    else "category absent from execution plan"
                ),
                "sample_count": sample_count,
                "eligible_sample_count": sample_count if enabled else 0,
                "group_counts": "",
                "threshold": "",
            }
        )
    return rows


def _table_hashes(tables_dir: Path) -> dict[str, str]:
    return {path.name: _sha256(path) for path in sorted(tables_dir.glob("*.tsv")) if path.is_file()}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--result-dir", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(repair_result(args.result_dir), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
