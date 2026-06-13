"""Normalize annotation tables."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping


def normalize_annotation_rows(
    rows: Iterable[Mapping[str, Any]],
    *,
    category: str,
    sample_id: str,
) -> List[Dict[str, Any]]:
    normalized = []
    for row in rows:
        normalized.append(
            {
                "sample_id": sample_id,
                "category": category,
                "contig_id": row.get("contig_id") or row.get("sequence") or "",
                "start": row.get("start", ""),
                "end": row.get("end", ""),
                "strand": row.get("strand", ""),
                "gene": row.get("gene") or row.get("product") or "",
                "tool": row.get("tool", ""),
                "evidence": row.get("evidence", ""),
            }
        )
    return normalized
