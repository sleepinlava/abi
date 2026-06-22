"""Multi-sample statistics derived from AutoPlasm standard tables."""

from __future__ import annotations

import math
from itertools import combinations
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Sequence

from abi.plugins.metagenomic_plasmid._engine.schemas import ExecutionPlan
from abi.plugins.metagenomic_plasmid._engine.standard_tables import read_standard_table

Matrix = Dict[str, Dict[str, float]]


def compute_diversity_and_differential(
    plan: ExecutionPlan,
    tables_dir: str | Path,
) -> Dict[str, List[Dict[str, Any]]]:
    matrix = _abundance_matrix(tables_dir)
    rows: Dict[str, List[Dict[str, Any]]] = {
        "sample_diversity": [],
        "differential_abundance": [],
    }
    if not matrix:
        warning = "No abundance rows were available; multi-sample statistics were skipped."
        rows["sample_diversity"].append(_skipped_diversity_row(warning))
        rows["differential_abundance"].append(_skipped_differential_row(warning))
        return rows

    sample_groups = {sample.sample_id: sample.group or "" for sample in plan.samples}
    features = sorted({feature for values in matrix.values() for feature in values})
    samples = [sample.sample_id for sample in plan.samples if sample.sample_id in matrix]

    for sample_id in samples:
        values = [matrix.get(sample_id, {}).get(feature, 0.0) for feature in features]
        group = sample_groups.get(sample_id, "")
        rows["sample_diversity"].extend(_alpha_rows(sample_id, group, values))

    for left, right in combinations(samples, 2):
        left_values = [matrix.get(left, {}).get(feature, 0.0) for feature in features]
        right_values = [matrix.get(right, {}).get(feature, 0.0) for feature in features]
        rows["sample_diversity"].extend(_beta_rows(left, right, left_values, right_values))

    rows["differential_abundance"].extend(_differential_rows(matrix, features, sample_groups))
    return rows


def compute_network_fallback(
    plan: ExecutionPlan,
    tables_dir: str | Path,
) -> Dict[str, List[Dict[str, Any]]]:
    matrix = _abundance_matrix(tables_dir)
    rows: Dict[str, List[Dict[str, Any]]] = {"network_edges": [], "network_nodes": []}
    if not matrix:
        rows["network_edges"].append(
            {
                "source": "",
                "target": "",
                "correlation": "",
                "covariance": "",
                "p_value": "",
                "q_value": "",
                "method": "spearman_fallback",
                "evidence": "",
                "warnings": "No abundance rows were available; network analysis was skipped.",
                "source_file": "",
            }
        )
        return rows

    samples = [sample.sample_id for sample in plan.samples if sample.sample_id in matrix]
    features = sorted({feature for values in matrix.values() for feature in values})
    node_degrees = {feature: 0 for feature in features}
    if len(samples) < 3 or len(features) < 2:
        warning = "At least three samples and two features are required for correlation network."
        rows["network_edges"].append(
            {
                "source": "",
                "target": "",
                "correlation": "",
                "covariance": "",
                "p_value": "",
                "q_value": "",
                "method": "spearman_fallback",
                "evidence": "",
                "warnings": warning,
                "source_file": "",
            }
        )
    else:
        for left, right in combinations(features, 2):
            left_values = [matrix.get(sample, {}).get(left, 0.0) for sample in samples]
            right_values = [matrix.get(sample, {}).get(right, 0.0) for sample in samples]
            correlation = _spearman(left_values, right_values)
            covariance = _covariance(left_values, right_values)
            if correlation is None:
                continue
            if abs(correlation) > 0:
                node_degrees[left] += 1
                node_degrees[right] += 1
            rows["network_edges"].append(
                {
                    "source": left,
                    "target": right,
                    "correlation": _fmt(correlation),
                    "covariance": _fmt(covariance),
                    "p_value": "",
                    "q_value": "",
                    "method": "spearman_fallback",
                    "evidence": f"samples={len(samples)}",
                    "warnings": (
                        "Fallback Spearman correlation is not compositional-aware; "
                        "prefer FastSpar for production network inference."
                    ),
                    "source_file": "",
                }
            )

    for feature in features:
        values = [matrix.get(sample, {}).get(feature, 0.0) for sample in samples]
        rows["network_nodes"].append(
            {
                "node_id": feature,
                "node_type": "plasmid_feature",
                "sample_count": sum(1 for value in values if value > 0),
                "mean_abundance": _fmt(_mean(values)),
                "degree": node_degrees.get(feature, 0),
                "evidence": f"samples={len(samples)}",
                "source_file": "",
            }
        )
    return rows


def compute_host_plasmid_coabundance(
    plan: ExecutionPlan,
    tables_dir: str | Path,
) -> List[Dict[str, Any]]:
    """Compute explicitly predictive host-plasmid links from matched abundance profiles."""
    plasmids = _abundance_matrix(tables_dir)
    hosts: Matrix = {}
    for row in read_standard_table(tables_dir, "host_predictions"):
        sample_id = row.get("sample_id", "")
        host_id = row.get("host_taxon", "")
        if not sample_id or not host_id or row.get("contig_id"):
            continue
        value = _coerce_float(row.get("confidence", ""))
        hosts.setdefault(sample_id, {})[host_id] = value

    sample_ids = [
        sample.sample_id
        for sample in plan.samples
        if sample.sample_id in plasmids and sample.sample_id in hosts
    ]
    if len(sample_ids) < 3:
        return []

    plasmid_ids = sorted({key for sample in sample_ids for key in plasmids[sample]})
    host_ids = sorted({key for sample in sample_ids for key in hosts[sample]})
    rows = []
    for plasmid_id in plasmid_ids:
        plasmid_values = [plasmids[sample].get(plasmid_id, 0.0) for sample in sample_ids]
        for host_id in host_ids:
            host_values = [hosts[sample].get(host_id, 0.0) for sample in sample_ids]
            score = _spearman(plasmid_values, host_values)
            if score is None:
                continue
            rows.append(
                {
                    "sample_id": "ALL",
                    "plasmid_id": plasmid_id,
                    "host_id": host_id,
                    "evidence_type": "co_abundance",
                    "evidence_level": f"samples={len(sample_ids)}",
                    "score": _fmt(score),
                    "is_prediction": "true",
                    "source_file": "tables/abundance.tsv;tables/host_predictions.tsv",
                }
            )
    return rows


def _abundance_matrix(tables_dir: str | Path) -> Matrix:
    matrix: Matrix = {}
    for row in read_standard_table(tables_dir, "abundance"):
        sample_id = row.get("sample_id", "")
        feature_id = row.get("feature_id") or row.get("contig_id", "")
        if not sample_id or not feature_id:
            continue
        value = _first_float(row, ("tpm", "rpkm", "coverage", "mapped_reads"))
        matrix.setdefault(sample_id, {})[feature_id] = (
            matrix.setdefault(sample_id, {}).get(feature_id, 0.0) + value
        )
    return matrix


def _alpha_rows(sample_id: str, group: str, values: Sequence[float]) -> List[Dict[str, Any]]:
    total = sum(value for value in values if value > 0)
    proportions = [value / total for value in values if total > 0 and value > 0]
    shannon = -sum(p * math.log(p) for p in proportions) if proportions else 0.0
    simpson = 1.0 - sum(p * p for p in proportions) if proportions else 0.0
    observed = sum(1 for value in values if value > 0)
    return [
        _diversity_row(sample_id, "", "shannon", shannon, "internal", group),
        _diversity_row(sample_id, "", "simpson", simpson, "internal", group),
        _diversity_row(sample_id, "", "observed_features", observed, "internal", group),
    ]


def _beta_rows(
    sample_id: str,
    comparison_sample_id: str,
    left: Sequence[float],
    right: Sequence[float],
) -> List[Dict[str, Any]]:
    bray_denominator = sum(a + b for a, b in zip(left, right))
    bray = (
        sum(abs(a - b) for a, b in zip(left, right)) / bray_denominator if bray_denominator else 0.0
    )
    left_present = {index for index, value in enumerate(left) if value > 0}
    right_present = {index for index, value in enumerate(right) if value > 0}
    union = left_present | right_present
    jaccard = 1.0 - (len(left_present & right_present) / len(union)) if union else 0.0
    return [
        _diversity_row(sample_id, comparison_sample_id, "bray_curtis", bray, "internal", ""),
        _diversity_row(sample_id, comparison_sample_id, "jaccard", jaccard, "internal", ""),
    ]


def _differential_rows(
    matrix: Matrix,
    features: Sequence[str],
    sample_groups: Mapping[str, str],
) -> List[Dict[str, Any]]:
    groups: Dict[str, List[str]] = {}
    for sample_id in matrix:
        group = sample_groups.get(sample_id, "")
        if group:
            groups.setdefault(group, []).append(sample_id)
    if len(groups) < 2:
        return [
            _skipped_differential_row(
                "At least two non-empty sample groups are required for differential abundance."
            )
        ]

    rows: List[Dict[str, Any]] = []
    for group_a, group_b in combinations(sorted(groups), 2):
        samples_a = groups[group_a]
        samples_b = groups[group_b]
        for feature in features:
            values_a = [matrix.get(sample, {}).get(feature, 0.0) for sample in samples_a]
            values_b = [matrix.get(sample, {}).get(feature, 0.0) for sample in samples_b]
            mean_a = _mean(values_a)
            mean_b = _mean(values_b)
            pseudo = 1e-9
            rows.append(
                {
                    "feature_id": feature,
                    "contig_id": feature,
                    "group_a": group_a,
                    "group_b": group_b,
                    "mean_a": _fmt(mean_a),
                    "mean_b": _fmt(mean_b),
                    "log2_fold_change": _fmt(math.log2((mean_a + pseudo) / (mean_b + pseudo))),
                    "statistic": _fmt(mean_a - mean_b),
                    "p_value": "",
                    "q_value": "",
                    "method": "internal_effect_size",
                    "warnings": (
                        "Exploratory effect-size table; p/q values require a configured "
                        "statistical backend and adequate replication."
                    ),
                }
            )
    return rows


def _diversity_row(
    sample_id: str,
    comparison_sample_id: str,
    metric: str,
    value: float,
    method: str,
    group: str,
) -> Dict[str, Any]:
    return {
        "sample_id": sample_id,
        "comparison_sample_id": comparison_sample_id,
        "metric": metric,
        "value": _fmt(value),
        "method": method,
        "group": group,
        "source_file": "tables/abundance.tsv",
        "warnings": "",
    }


def _skipped_diversity_row(warning: str) -> Dict[str, Any]:
    return {
        "sample_id": "",
        "comparison_sample_id": "",
        "metric": "skipped",
        "value": "",
        "method": "internal",
        "group": "",
        "source_file": "tables/abundance.tsv",
        "warnings": warning,
    }


def _skipped_differential_row(warning: str) -> Dict[str, Any]:
    return {
        "feature_id": "",
        "contig_id": "",
        "group_a": "",
        "group_b": "",
        "mean_a": "",
        "mean_b": "",
        "log2_fold_change": "",
        "statistic": "",
        "p_value": "",
        "q_value": "",
        "method": "internal_effect_size",
        "warnings": warning,
    }


def _first_float(row: Mapping[str, str], fields: Iterable[str]) -> float:
    for field in fields:
        value = row.get(field, "")
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return 0.0


def _coerce_float(value: Any) -> float:
    try:
        return float(str(value).rstrip("%"))
    except (TypeError, ValueError):
        return 0.0


def _mean(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _covariance(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) < 2 or len(left) != len(right):
        return 0.0
    mean_left = _mean(left)
    mean_right = _mean(right)
    return sum((a - mean_left) * (b - mean_right) for a, b in zip(left, right)) / (len(left) - 1)


def _spearman(left: Sequence[float], right: Sequence[float]) -> float | None:
    if len(left) != len(right) or len(left) < 2:
        return None
    return _pearson(_ranks(left), _ranks(right))


def _pearson(left: Sequence[float], right: Sequence[float]) -> float | None:
    mean_left = _mean(left)
    mean_right = _mean(right)
    numerator = sum((a - mean_left) * (b - mean_right) for a, b in zip(left, right))
    left_denominator = math.sqrt(sum((a - mean_left) ** 2 for a in left))
    right_denominator = math.sqrt(sum((b - mean_right) ** 2 for b in right))
    denominator = left_denominator * right_denominator
    if denominator == 0:
        return None
    return numerator / denominator


def _ranks(values: Sequence[float]) -> List[float]:
    indexed = sorted(enumerate(values), key=lambda item: item[1])
    ranks = [0.0] * len(values)
    index = 0
    while index < len(indexed):
        end = index + 1
        while end < len(indexed) and indexed[end][1] == indexed[index][1]:
            end += 1
        rank = (index + 1 + end) / 2.0
        for original_index, _ in indexed[index:end]:
            ranks[original_index] = rank
        index = end
    return ranks


def _fmt(value: Any) -> str:
    if isinstance(value, int):
        return str(value)
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return "" if value is None else str(value)
    if math.isnan(numeric) or math.isinf(numeric):
        return ""
    return f"{numeric:.6g}"
