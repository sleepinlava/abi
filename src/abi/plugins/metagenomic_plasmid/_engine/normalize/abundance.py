"""Normalize abundance values."""

from __future__ import annotations

from typing import Dict, Mapping


def rpkm(raw_count: float, feature_length_bp: float, mapped_reads_millions: float) -> float:
    if feature_length_bp <= 0 or mapped_reads_millions <= 0:
        return 0.0
    return raw_count / (feature_length_bp / 1000.0) / mapped_reads_millions


def tpm(raw_counts: Mapping[str, float], lengths_bp: Mapping[str, float]) -> Dict[str, float]:
    rates = {
        feature: (
            (count / (lengths_bp.get(feature, 0.0) / 1000.0))
            if lengths_bp.get(feature, 0.0) > 0
            else 0.0
        )
        for feature, count in raw_counts.items()
    }
    total = sum(rates.values())
    if total <= 0:
        return {feature: 0.0 for feature in raw_counts}
    return {feature: rate / total * 1_000_000 for feature, rate in rates.items()}
