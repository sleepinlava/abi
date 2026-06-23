"""Normalize stable files from ``08_ViWrap_summary_outdir``."""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Any, Iterable

from .errors import ViWrapParseError

SUMMARY_FILES = {
    "virus_summary": "Virus_summary_info.txt",
    "taxonomy": "Tax_classification_result.txt",
    "host_prediction_genome": "Host_prediction_to_genome_m90.csv",
    "host_prediction_genus": "Host_prediction_to_genus_m90.csv",
    "normalized_abundance": "Virus_normalized_abundance.txt",
    "raw_abundance": "Virus_raw_abundance.txt",
    "annotation": "Virus_annotation_results.txt",
    "genus_cluster": "Genus_cluster_info.txt",
    "species_cluster": "Species_cluster_info.txt",
    "sample_read_info": "Sample2read_info.txt",
}
REQUIRED_SUMMARIES = frozenset({"virus_summary"})
ABI_TABLE_ALIASES = {
    "viral_taxonomy": "taxonomy",
    "viral_hosts": "host_prediction_genome",
    "viral_abundance_normalized": "normalized_abundance",
}
ABI_COLUMN_ALIASES = {
    "virus_summary": {
        "virus_id": ("virus_id", "virus", "contig_id", "sequence_id"),
        "length": ("length", "virus_length", "sequence_length", "contig_length"),
        "circularity": ("circularity", "circular", "topology"),
        "checkv_quality": ("checkv_quality", "quality", "quality_tier"),
        "completeness": ("completeness", "checkv_completeness"),
        "contamination": ("contamination", "checkv_contamination"),
        "taxonomy": ("taxonomy", "tax_classification", "lineage"),
        "lifestyle": ("lifestyle", "virus_lifestyle"),
        "gene_count": ("gene_count", "number_of_genes", "genes"),
    },
    "viral_taxonomy": {
        "virus_id": ("virus_id", "virus", "contig_id", "sequence_id"),
        "taxonomy": ("taxonomy", "tax_classification", "lineage"),
        "realm": ("realm",),
        "kingdom": ("kingdom",),
        "phylum": ("phylum",),
        "class": ("class",),
        "order": ("order",),
        "family": ("family",),
        "genus": ("genus",),
        "species": ("species",),
        "confidence": ("confidence", "score", "taxonomy_score"),
    },
    "viral_hosts": {
        "virus_id": ("virus_id", "virus", "contig_id", "sequence_id"),
        "host_id": ("host_id", "host_genome", "genome", "host"),
        "host_taxonomy": ("host_taxonomy", "host_lineage", "taxonomy"),
        "host_genus": ("host_genus", "genus"),
        "method": ("method", "prediction_method", "evidence"),
        "score": ("score", "confidence", "similarity"),
    },
    "viral_abundance_normalized": {
        "virus_id": ("virus_id", "virus", "contig_id", "sequence_id"),
        "abundance": (
            "abundance",
            "normalized_abundance",
            "relative_abundance",
            "value",
        ),
        "unit": ("unit", "abundance_unit"),
    },
}


def _read_table(path: Path) -> list[dict[str, str]]:
    """Read comma- or tab-delimited output while preserving upstream columns."""
    with path.open("r", encoding="utf-8", errors="replace", newline="") as handle:
        first = handle.readline()
        handle.seek(0)
        delimiter = "," if path.suffix.lower() == ".csv" else "\t"
        if delimiter not in first and "," in first:
            delimiter = ","
        reader = csv.DictReader(handle, delimiter=delimiter)
        if not reader.fieldnames:
            return []
        return [
            {str(key).strip(): str(value or "").strip() for key, value in row.items()}
            for row in reader
        ]


def parse_viwrap_outputs(out_dir: str | Path, *, require_core: bool = True) -> dict[str, Any]:
    """Parse available summaries; optional missing files become warnings."""
    root = Path(out_dir)
    summary_dir = root / "08_ViWrap_summary_outdir"
    if not summary_dir.is_dir():
        raise ViWrapParseError(f"ViWrap summary directory not found: {summary_dir}")

    table_rows: dict[str, list[dict[str, str]]] = {}
    files: dict[str, str] = {}
    warnings: list[str] = []
    for table_name, filename in SUMMARY_FILES.items():
        path = summary_dir / filename
        if not path.is_file() or path.stat().st_size == 0:
            message = f"Missing or empty optional summary: {filename}"
            if require_core and table_name in REQUIRED_SUMMARIES:
                raise ViWrapParseError(message.replace("optional ", "required "))
            warnings.append(message)
            table_rows[table_name] = []
            continue
        table_rows[table_name] = _read_table(path)
        files[table_name] = str(path)
    amg_dir = summary_dir / "AMG_statistics"
    amg_outputs = [str(path) for path in sorted(amg_dir.glob("*")) if path.is_file()]
    return {
        "plugin": "viral_viwrap",
        "status": "warn" if warnings else "success",
        "out_dir": str(root),
        "summary_dir": str(summary_dir),
        "tables": files,
        "table_rows": table_rows,
        "artifacts": {"viral_genomes": [], "figures": [], "amg_outputs": amg_outputs},
        "logs": {},
        "warnings": warnings,
    }


def parse_table_for_abi(
    out_dir: str | Path, table_name: str, sample_id: str
) -> Iterable[dict[str, str]]:
    parsed = parse_viwrap_outputs(out_dir, require_core=False)
    source_name = ABI_TABLE_ALIASES.get(table_name, table_name)
    rows = parsed["table_rows"].get(source_name, [])
    source_file = parsed["tables"].get(source_name, "")
    aliases = ABI_COLUMN_ALIASES.get(table_name, {})
    normalized_rows = []
    for row in rows:
        normalized = {_normalize_column(key): value for key, value in row.items()}
        output = {
            "sample_id": sample_id,
            "source_file": source_file,
            "raw_record_json": json.dumps(row, ensure_ascii=False, sort_keys=True),
        }
        for target, source_aliases in aliases.items():
            output[target] = next(
                (normalized[alias] for alias in source_aliases if normalized.get(alias)),
                "",
            )
        normalized_rows.append(output)
    return normalized_rows


def _normalize_column(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value).strip().lower()).strip("_")
