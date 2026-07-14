"""Create an auditable manifest of ViWrap outputs without moving them."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

ARTIFACT_MANIFEST_SCHEMA_VERSION = "abi.artifact-manifest.v1"

CATEGORY_DIRS = {
    "input": "00_",
    "mapping": "01_Mapping_result_outdir",
    "binning": "02_vRhyme_outdir",
    "taxonomy": "03_vConTACT2_outdir",
    "quality": "05_CheckV_outdir",
    "species": "06_dRep_outdir",
    "host_prediction": "07_iPHoP_outdir",
    "summary": "08_ViWrap_summary_outdir",
    "visualization": "09_Virus_statistics_visualization",
}


def collect_artifacts(
    out_dir: str | Path,
    manifest_path: str | Path | None = None,
    *,
    tables_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Classify raw results and link them to ABI standard tables."""
    root = Path(out_dir)
    if not root.is_dir():
        raise FileNotFoundError(f"ViWrap output directory not found: {root}")
    artifacts: list[dict[str, Any]] = []
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        relative = path.relative_to(root)
        top = relative.parts[0]
        category = "other"
        for name, prefix in CATEGORY_DIRS.items():
            if top.startswith(prefix):
                category = name
                break
        artifacts.append(
            {
                "category": category,
                "path": str(path),
                "relative_path": str(relative),
                "size_bytes": path.stat().st_size,
            }
        )
    standard_tables, source_files = _standard_table_manifest(tables_dir)
    artifact_paths = {item["path"] for item in artifacts}
    unmatched_source_files = sorted(source_files - artifact_paths)
    result = {
        "schema_version": ARTIFACT_MANIFEST_SCHEMA_VERSION,
        "plugin": "viral_viwrap",
        "root": str(root),
        "artifact_count": len(artifacts),
        "artifacts": artifacts,
        "standard_tables": standard_tables,
        "consistency": {
            "standard_table_count": len(standard_tables),
            "standard_row_count": sum(table["rows"] for table in standard_tables.values()),
            "linked_source_count": len(source_files & artifact_paths),
            "unmatched_source_files": unmatched_source_files,
        },
        "groups": {
            "primary_tables": [item["path"] for item in artifacts if item["category"] == "summary"],
            "primary_sequences": [
                item["path"]
                for item in artifacts
                if Path(item["path"]).suffix.lower() in {".fa", ".faa", ".fasta", ".ffn"}
            ],
            "primary_figures": [
                item["path"]
                for item in artifacts
                if Path(item["path"]).suffix.lower() in {".pdf", ".png"}
            ],
            "logs": [item["path"] for item in artifacts if item["path"].endswith(".log")],
        },
    }
    if manifest_path is not None:
        destination = Path(manifest_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


def _standard_table_manifest(
    tables_dir: str | Path | None,
) -> tuple[dict[str, dict[str, Any]], set[str]]:
    if tables_dir is None:
        return {}, set()
    tables: dict[str, dict[str, Any]] = {}
    source_files: set[str] = set()
    for path in sorted(Path(tables_dir).glob("*.tsv")):
        with path.open("r", encoding="utf-8", newline="") as handle:
            row_count = 0
            for row in csv.DictReader(handle, delimiter="\t"):
                row_count += 1
                source_file = str(row.get("source_file", "")).strip()
                if source_file:
                    source_files.add(source_file)
        tables[path.stem] = {"path": str(path), "rows": row_count}
    return tables, source_files
