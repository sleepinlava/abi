"""Standard AutoPlasm result tables."""

from __future__ import annotations

import csv
import logging
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Sequence

logger = logging.getLogger(__name__)

TABLE_SCHEMAS: Dict[str, List[str]] = {
    # Canonical result contract from the metagenomic-plasmid workflow plan.
    # These files are always created, even when a tool finds no records.
    "sample_qc": [
        "sample_id",
        "tool",
        "raw_reads",
        "clean_reads",
        "q30",
        "gc_content",
        "filter_rate",
        "source_file",
        "warnings",
    ],
    "assembly_qc": [
        "sample_id",
        "assembler",
        "contig_count",
        "n50",
        "total_length",
        "max_contig",
        "gc_content",
        "source_file",
        "warnings",
    ],
    "plasmid_predictions": [
        "sample_id",
        "contig_id",
        "tool",
        "evidence_level",
        "score",
        "confidence",
        "contig_length",
        "circularity",
        "evidence",
        "warnings",
        "source_file",
    ],
    "plasmid_consensus": [
        "sample_id",
        "contig_id",
        "final_plasmid_call",
        "decision_strategy",
        "support_tools",
        "support_count",
        "total_tools",
        "confidence_score",
        "weighted_score",
        "weight_threshold",
        "tool_weights",
        "contig_length",
        "evidence",
        "warnings",
    ],
    "plasmid_catalog": [
        "cluster_id",
        "representative_id",
        "member_id",
        "sample_id",
        "length_bp",
        "circularity",
        "identity",
        "coverage",
        "method",
        "source_file",
    ],
    "plasmid_structure": [
        "sample_id",
        "plasmid_id",
        "length_bp",
        "is_circular",
        "terminal_overlap_bp",
        "method",
        "warnings",
        "source_file",
    ],
    "plasmid_abundance": [
        "sample_id",
        "plasmid_id",
        "coverage",
        "rpkm",
        "tpm",
        "raw_count",
        "mapper",
        "source_file",
    ],
    "plasmid_annotation": [
        "sample_id",
        "contig_id",
        "gene_id",
        "start",
        "end",
        "strand",
        "gene",
        "product",
        "functional_label",
        "tool",
        "source_file",
    ],
    "amr_genes": [
        "sample_id",
        "contig_id",
        "gene",
        "drug_class",
        "identity",
        "coverage",
        "tool",
        "source_file",
    ],
    "mge_elements": [
        "sample_id",
        "contig_id",
        "element_id",
        "element_type",
        "start",
        "end",
        "tool",
        "source_file",
    ],
    "host_profile": [
        "sample_id",
        "taxon_name",
        "taxon_id",
        "rank",
        "relative_abundance",
        "tool",
        "source_file",
    ],
    "host_plasmid_links": [
        "sample_id",
        "plasmid_id",
        "host_id",
        "evidence_type",
        "evidence_level",
        "score",
        "is_prediction",
        "source_file",
    ],
    "differential_plasmids": [
        "plasmid_id",
        "group_a",
        "group_b",
        "log2_fold_change",
        "p_value",
        "q_value",
        "method",
        "warnings",
    ],
    "analysis_status": [
        "module",
        "status",
        "reason",
        "sample_count",
        "eligible_sample_count",
        "group_counts",
        "threshold",
    ],
    "annotations": [
        "sample_id",
        "contig_id",
        "start",
        "end",
        "strand",
        "gene",
        "product",
        "category",
        "tool",
        "evidence",
        "identity",
        "coverage",
        "source_file",
    ],
    "host_predictions": [
        "sample_id",
        "contig_id",
        "host_taxon",
        "method",
        "confidence",
        "evidence",
        "tool",
        "source_file",
    ],
    "abundance": [
        "sample_id",
        "feature_id",
        "contig_id",
        "coverage",
        "tpm",
        "rpkm",
        "mapped_reads",
        "length_bp",
        "tool",
        "source_file",
    ],
    "qc_summary": ["sample_id", "tool", "metric", "value", "unit", "source_file"],
    "assembly_summary": ["sample_id", "tool", "metric", "value", "unit", "source_file"],
    "plasmid_typing": [
        "sample_id",
        "contig_id",
        "typing_scheme",
        "type_id",
        "mobility",
        "confidence",
        "tool",
        "evidence",
        "source_file",
    ],
    "plasmid_bins": [
        "sample_id",
        "bin_id",
        "method",
        "contig_count",
        "total_length_bp",
        "confidence",
        "evidence",
        "source_file",
    ],
    "bin_to_contig": [
        "sample_id",
        "bin_id",
        "contig_id",
        "membership_score",
        "tool",
        "source_file",
    ],
    "comparative_hits": [
        "sample_id",
        "query_id",
        "subject_id",
        "identity",
        "coverage",
        "e_value",
        "bit_score",
        "alignment_length",
        "tool",
        "evidence",
        "source_file",
    ],
    "visualization_outputs": [
        "sample_id",
        "output_type",
        "path",
        "tool",
        "description",
    ],
    "sample_diversity": [
        "sample_id",
        "comparison_sample_id",
        "metric",
        "value",
        "method",
        "group",
        "source_file",
        "warnings",
    ],
    "differential_abundance": [
        "feature_id",
        "contig_id",
        "group_a",
        "group_b",
        "mean_a",
        "mean_b",
        "log2_fold_change",
        "statistic",
        "p_value",
        "q_value",
        "method",
        "warnings",
    ],
    "network_edges": [
        "source",
        "target",
        "correlation",
        "covariance",
        "p_value",
        "q_value",
        "method",
        "evidence",
        "warnings",
        "source_file",
    ],
    "network_nodes": [
        "node_id",
        "node_type",
        "sample_count",
        "mean_abundance",
        "degree",
        "evidence",
        "source_file",
    ],
}


def table_path(tables_dir: str | Path, table_name: str) -> Path:
    if table_name not in TABLE_SCHEMAS:
        raise ValueError(f"Unknown AutoPlasm table: {table_name}")
    return Path(tables_dir) / f"{table_name}.tsv"


def ensure_standard_tables(tables_dir: str | Path) -> Dict[str, Path]:
    paths = {}
    for table_name, fields in TABLE_SCHEMAS.items():
        path = table_path(tables_dir, table_name)
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            _write_header(path, fields)
        paths[table_name] = path
    return paths


def write_standard_table(
    tables_dir: str | Path,
    table_name: str,
    rows: Iterable[Mapping[str, Any]],
    *,
    append: bool = False,
) -> Path:
    fields = TABLE_SCHEMAS[table_name]
    path = table_path(tables_dir, table_name)
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = list(rows)
    mode = "a" if append and path.exists() else "w"
    with path.open(mode, encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fields,
            delimiter="\t",
            extrasaction="ignore",
            lineterminator="\n",
        )
        if mode == "w" or path.stat().st_size == 0:
            writer.writeheader()
        for row in rows:
            writer.writerow({field: _tsv_value(row.get(field, "")) for field in fields})
    return path


def append_standard_rows(
    tables_dir: str | Path,
    rows_by_table: Mapping[str, Iterable[Mapping[str, Any]]],
) -> Dict[str, Path]:
    written = {}
    ensure_standard_tables(tables_dir)
    expanded: Dict[str, List[Mapping[str, Any]]] = {}
    for table_name, source_rows in rows_by_table.items():
        rows = list(source_rows)
        expanded.setdefault(table_name, []).extend(rows)
        for canonical_name, canonical_rows in _canonical_result_rows(table_name, rows).items():
            expanded.setdefault(canonical_name, []).extend(canonical_rows)
    for table_name, rows in expanded.items():
        if not rows:
            continue
        written[table_name] = write_standard_table(tables_dir, table_name, rows, append=True)
    return written


def _canonical_result_rows(
    table_name: str, rows: Sequence[Mapping[str, Any]]
) -> Dict[str, List[Mapping[str, Any]]]:
    """Mirror legacy normalized rows into the public workflow result contract."""
    if table_name == "qc_summary":
        grouped: Dict[tuple[str, str], Dict[str, Any]] = {}
        for row in rows:
            key = (str(row.get("sample_id", "")), str(row.get("tool", "")))
            target = grouped.setdefault(
                key,
                {
                    "sample_id": key[0],
                    "tool": key[1],
                    "source_file": row.get("source_file", ""),
                },
            )
            metric = str(row.get("metric", "")).lower().replace(" ", "_")
            value = row.get("value", "")
            if "before_filtering.total_reads" in metric or metric in {
                "input_reads",
                "total_sequences",
                "number_of_reads",
            }:
                target["raw_reads"] = value
            elif "after_filtering.total_reads" in metric or metric in {
                "output_reads",
                "clean_reads",
            }:
                target["clean_reads"] = value
            elif "q30" in metric:
                target["q30"] = value
            elif "gc" in metric:
                target["gc_content"] = value
            elif "filter" in metric and ("rate" in metric or "percent" in metric):
                target["filter_rate"] = value
        return {"sample_qc": list(grouped.values())}

    if table_name == "assembly_summary":
        grouped = {}
        for row in rows:
            key = (str(row.get("sample_id", "")), str(row.get("tool", "")))
            target = grouped.setdefault(
                key,
                {
                    "sample_id": key[0],
                    "assembler": key[1],
                    "source_file": row.get("source_file", ""),
                },
            )
            metric = str(row.get("metric", "")).lower().replace(" ", "_")
            value = row.get("value", "")
            metric_map = {
                "n50": "n50",
                "total_contigs": "contig_count",
                "contigs": "contig_count",
                "total_length": "total_length",
                "max_contig": "max_contig",
                "largest_contig": "max_contig",
                "gc": "gc_content",
                "gc_content": "gc_content",
            }
            if metric in metric_map:
                target[metric_map[metric]] = value
        return {"assembly_qc": list(grouped.values())}

    if table_name == "abundance":
        return {
            "plasmid_abundance": [
                {
                    "sample_id": row.get("sample_id", ""),
                    "plasmid_id": row.get("feature_id") or row.get("contig_id", ""),
                    "coverage": row.get("coverage", ""),
                    "rpkm": row.get("rpkm", ""),
                    "tpm": row.get("tpm", ""),
                    "raw_count": row.get("mapped_reads", ""),
                    "mapper": row.get("tool", ""),
                    "source_file": row.get("source_file", ""),
                }
                for row in rows
            ]
        }

    if table_name == "annotations":
        annotation_rows: List[Mapping[str, Any]] = [
            {
                "sample_id": row.get("sample_id", ""),
                "contig_id": row.get("contig_id", ""),
                "gene_id": row.get("gene", ""),
                "start": row.get("start", ""),
                "end": row.get("end", ""),
                "strand": row.get("strand", ""),
                "gene": row.get("gene", ""),
                "product": row.get("product", ""),
                "functional_label": row.get("category", ""),
                "tool": row.get("tool", ""),
                "source_file": row.get("source_file", ""),
            }
            for row in rows
        ]
        amr_rows: List[Mapping[str, Any]] = [
            {
                "sample_id": row.get("sample_id", ""),
                "contig_id": row.get("contig_id", ""),
                "gene": row.get("gene", ""),
                "drug_class": row.get("product", ""),
                "identity": row.get("identity", ""),
                "coverage": row.get("coverage", ""),
                "tool": row.get("tool", ""),
                "source_file": row.get("source_file", ""),
            }
            for row in rows
            if str(row.get("category", "")).upper() in {"AMR", "ARG"}
        ]
        mge_rows: List[Mapping[str, Any]] = [
            {
                "sample_id": row.get("sample_id", ""),
                "contig_id": row.get("contig_id", ""),
                "element_id": row.get("gene", ""),
                "element_type": row.get("category", ""),
                "start": row.get("start", ""),
                "end": row.get("end", ""),
                "tool": row.get("tool", ""),
                "source_file": row.get("source_file", ""),
            }
            for row in rows
            if str(row.get("category", "")).lower()
            in {"is", "integron", "mge", "mobile_element", "transposase"}
        ]
        return {
            "plasmid_annotation": annotation_rows,
            "amr_genes": amr_rows,
            "mge_elements": mge_rows,
        }

    if table_name == "host_predictions":
        profiles: List[Mapping[str, Any]] = []
        links: List[Mapping[str, Any]] = []
        for row in rows:
            if not row.get("contig_id"):
                profiles.append(
                    {
                        "sample_id": row.get("sample_id", ""),
                        "taxon_name": row.get("host_taxon", ""),
                        "relative_abundance": row.get("confidence", ""),
                        "tool": row.get("tool", ""),
                        "source_file": row.get("source_file", ""),
                    }
                )
            else:
                links.append(
                    {
                        "sample_id": row.get("sample_id", ""),
                        "plasmid_id": row.get("contig_id", ""),
                        "host_id": row.get("host_taxon", ""),
                        "evidence_type": row.get("method", ""),
                        "evidence_level": row.get("evidence", ""),
                        "score": row.get("confidence", ""),
                        "is_prediction": "true",
                        "source_file": row.get("source_file", ""),
                    }
                )
        return {"host_profile": profiles, "host_plasmid_links": links}

    if table_name == "differential_abundance":
        return {
            "differential_plasmids": [
                {
                    "plasmid_id": row.get("feature_id") or row.get("contig_id", ""),
                    "group_a": row.get("group_a", ""),
                    "group_b": row.get("group_b", ""),
                    "log2_fold_change": row.get("log2_fold_change", ""),
                    "p_value": row.get("p_value", ""),
                    "q_value": row.get("q_value", ""),
                    "method": row.get("method", ""),
                    "warnings": row.get("warnings", ""),
                }
                for row in rows
            ]
        }

    return {}


def read_standard_table(tables_dir: str | Path, table_name: str) -> List[Dict[str, str]]:
    path = table_path(tables_dir, table_name)
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def summarize_standard_tables(tables_dir: str | Path) -> Dict[str, Dict[str, Any]]:
    ensure_standard_tables(tables_dir)
    summary = {}
    for table_name in TABLE_SCHEMAS:
        rows = read_standard_table(tables_dir, table_name)
        summary[table_name] = {
            "rows": len(rows),
            "path": str(table_path(tables_dir, table_name)),
        }
    return summary


def write_consensus_table(
    tables_dir: str | Path,
    *,
    strategy: str,
    detection_tools: Sequence[str] | None = None,
    tool_weights: Mapping[str, float] | None = None,
) -> Path:
    """Merge per-tool plasmid predictions into a single consensus table.

    Parameters
    ----------
    strategy:
        One of ``"single_tool"``, ``"union"``, ``"intersection"``,
        ``"majority_vote"``, or ``"weighted_vote"``.
    detection_tools:
        If provided, restrict consensus to these tool IDs.
    tool_weights:
        Per-tool weight map for ``"weighted_vote"`` strategy (e.g.
        ``{"genomad": 0.6, "plasme": 0.25, "plasx": 0.15}``).
        Tools not listed receive a default weight of 1.0.
        When *None* and strategy is ``"weighted_vote"``, all tools
        receive equal weight (equivalent to ``"majority_vote"``).
    """
    predictions = read_standard_table(tables_dir, "plasmid_predictions")
    configured_tools = [tool for tool in detection_tools or [] if tool]
    if configured_tools:
        consensus_source = [row for row in predictions if row.get("tool") in configured_tools]
    else:
        consensus_source = predictions
    logger.info(
        "write_consensus_table: %d predictions, %d configured_tools=%s, %d consensus_source",
        len(predictions),
        len(configured_tools),
        configured_tools,
        len(consensus_source),
    )

    # Normalise weights: fill defaults for unlisted tools
    resolved_weights: Dict[str, float] = {}
    if strategy == "weighted_vote" and tool_weights:
        for tool_id in configured_tools or sorted(
            {row.get("tool", "") for row in consensus_source if row.get("tool")}
        ):
            resolved_weights[tool_id] = float(tool_weights.get(tool_id, 1.0))

    by_sample_contig: Dict[tuple[str, str], List[Mapping[str, str]]] = {}
    for row in consensus_source:
        sample_id = row.get("sample_id", "")
        contig_id = row.get("contig_id", "")
        if not sample_id or not contig_id:
            continue
        by_sample_contig.setdefault((sample_id, contig_id), []).append(row)

    consensus_rows: List[Dict[str, Any]] = []
    for (sample_id, contig_id), rows in sorted(by_sample_contig.items()):
        support_tools = sorted({row.get("tool", "") for row in rows if row.get("tool")})
        tools_for_denominator = configured_tools or sorted(
            {row.get("tool", "") for row in consensus_source if row.get("tool")}
        )
        total_tools = max(len(tools_for_denominator), len(support_tools), 1)
        support_count = len(support_tools)

        # ── Weighted-vote: compute weighted score ──
        weighted_score: float | None = None
        if strategy == "weighted_vote":
            weighted_score = sum(resolved_weights.get(tool, 1.0) for tool in support_tools)
            total_weight = (
                sum(resolved_weights.values()) if resolved_weights else float(total_tools)
            )
            final_call = weighted_score >= (total_weight / 2.0)
        elif strategy == "single_tool" and configured_tools:
            # The first configured detector is authoritative. Additional tools
            # enrich the evidence columns but cannot create a positive call on
            # their own; metagenomic_plasmid config places geNomad first.
            final_call = configured_tools[0] in support_tools
        else:
            final_call = _consensus_call(strategy, support_count, total_tools)

        confidence = _consensus_confidence(rows, support_count, total_tools)
        if weighted_score is not None and resolved_weights:
            total_weight = sum(resolved_weights.values())
            confidence = max(confidence, round(weighted_score / total_weight, 3))
        length = next(
            (row.get("contig_length", "") for row in rows if row.get("contig_length")),
            "",
        )
        evidence = ";".join(
            f"{row.get('tool')}:{row.get('score') or row.get('confidence') or 'evidence'}"
            for row in rows
            if row.get("tool")
        )
        warnings = _consensus_warnings(rows, final_call, support_count, total_tools)
        row_data: Dict[str, Any] = {
            "sample_id": sample_id,
            "contig_id": contig_id,
            "final_plasmid_call": final_call,
            "decision_strategy": strategy,
            "support_tools": ",".join(support_tools),
            "support_count": support_count,
            "total_tools": total_tools,
            "confidence_score": confidence,
            "contig_length": length,
            "evidence": evidence,
            "warnings": warnings,
        }
        if weighted_score is not None:
            total_weight = (
                sum(resolved_weights.values()) if resolved_weights else float(total_tools)
            )
            row_data["weighted_score"] = round(weighted_score, 3)
            row_data["weight_threshold"] = round(total_weight / 2.0, 3)
            row_data["tool_weights"] = ",".join(
                f"{tool}:{resolved_weights.get(tool, 1.0):.2f}" for tool in support_tools
            )
        consensus_rows.append(row_data)

    logger.info(
        "write_consensus_table: %d groups → %d consensus_rows, strategy=%s, append=False → %s",
        len(by_sample_contig),
        len(consensus_rows),
        strategy,
        table_path(tables_dir, "plasmid_consensus"),
    )
    return write_standard_table(tables_dir, "plasmid_consensus", consensus_rows, append=False)


def _consensus_call(strategy: str, support_count: int, total_tools: int) -> bool:
    """Simple (unweighted) consensus decision.

    For ``"weighted_vote"``, callers must compute the decision themselves
    using per-tool weights and pass the result directly to the caller site
    in :func:`write_consensus_table`.  This function treats
    ``"weighted_vote"`` as a degenerate majority-vote fallback.
    """
    if strategy == "intersection":
        return support_count == total_tools
    if strategy in {"majority_vote", "weighted_vote"}:
        return support_count > total_tools / 2
    return support_count > 0


def _consensus_confidence(
    rows: Sequence[Mapping[str, str]], support_count: int, total_tools: int
) -> float:
    raw_scores = [_as_float(row.get("score", "")) for row in rows]
    scores: List[float] = [score for score in raw_scores if score is not None]
    support_ratio = support_count / total_tools if total_tools else 0.0
    if not scores:
        return round(support_ratio, 3)
    return round(max(max(scores), support_ratio), 3)


def _consensus_warnings(
    rows: Sequence[Mapping[str, str]],
    final_call: bool,
    support_count: int,
    total_tools: int,
) -> str:
    evidence_levels = {row.get("evidence_level", "") for row in rows}
    warnings = [row.get("warnings", "") for row in rows if row.get("warnings")]
    if "primary" not in evidence_levels:
        warnings.append("No primary plasmid detector evidence was parsed.")
    if support_count < total_tools:
        warnings.append("Absence of supporting-tool hits is not evidence of non-plasmid origin.")
    if not final_call and support_count:
        warnings.append(
            "Candidate has partial support but did not satisfy the configured strategy."
        )
    return " ".join(dict.fromkeys(warnings))


def _as_float(value: str) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _write_header(path: Path, fields: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        handle.write("\t".join(fields) + "\n")


def _tsv_value(value: Any) -> str:
    if value is None:
        return ""
    return str(value).replace("\n", " ").replace("\t", " ")
