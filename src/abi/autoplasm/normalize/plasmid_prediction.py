"""Normalize plasmid prediction outputs."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping

VALID_STRATEGIES = {"single_tool", "union", "intersection", "majority_vote", "weighted_vote"}


def integrate_calls(
    calls_by_tool: Mapping[str, Mapping[str, bool]],
    *,
    strategy: str,
    weights: Mapping[str, float] | None = None,
) -> Dict[str, bool]:
    if strategy not in VALID_STRATEGIES:
        raise ValueError(f"Unsupported plasmid decision strategy: {strategy}")
    contigs = sorted({contig for calls in calls_by_tool.values() for contig in calls})
    if not contigs:
        return {}
    if strategy == "single_tool":
        if len(calls_by_tool) != 1:
            raise ValueError("single_tool strategy requires exactly one tool")
        return dict(next(iter(calls_by_tool.values())))

    integrated: Dict[str, bool] = {}
    for contig in contigs:
        calls = [bool(tool_calls.get(contig, False)) for tool_calls in calls_by_tool.values()]
        if strategy == "union":
            integrated[contig] = any(calls)
        elif strategy == "intersection":
            integrated[contig] = all(calls)
        elif strategy == "majority_vote":
            integrated[contig] = sum(calls) > len(calls) / 2
        else:
            tool_weights = weights or {tool: 1.0 for tool in calls_by_tool}
            score = sum(
                tool_weights.get(tool, 1.0)
                for tool, tool_calls in calls_by_tool.items()
                if tool_calls.get(contig, False)
            )
            integrated[contig] = score >= (sum(tool_weights.values()) / 2)
    return integrated


def normalize_prediction_rows(
    *,
    sample_id: str,
    contig_lengths: Mapping[str, int],
    calls_by_tool: Mapping[str, Mapping[str, bool]],
    strategy: str,
) -> List[Dict[str, Any]]:
    final_calls = integrate_calls(calls_by_tool, strategy=strategy)
    rows: List[Dict[str, Any]] = []
    for contig_id in sorted(final_calls):
        row: Dict[str, Any] = {
            "sample_id": sample_id,
            "contig_id": contig_id,
            "contig_length": contig_lengths.get(contig_id, 0),
            "circularity": "",
            "coverage": "",
            "gc_content": "",
            "final_plasmid_call": final_calls[contig_id],
            "confidence_score": 1.0 if final_calls[contig_id] else 0.0,
            "decision_strategy": strategy,
        }
        for tool_id, calls in calls_by_tool.items():
            row[f"{tool_id}_call"] = bool(calls.get(contig_id, False))
        rows.append(row)
    return rows


def rows_to_tsv(rows: Iterable[Mapping[str, Any]]) -> str:
    rows = list(rows)
    if not rows:
        return ""
    fields = list(rows[0].keys())
    lines = ["\t".join(fields)]
    for row in rows:
        lines.append("\t".join(str(row.get(field, "")) for field in fields))
    return "\n".join(lines) + "\n"
