"""Canonical automatic tool selections for the plasmid workflow."""

from __future__ import annotations


def default_tools_for_category(category: str, data_profile: str) -> list[str]:
    """Return the default tools for a workflow category and data profile."""
    if category == "plasmid_detection":
        return ["genomad"]
    if category == "plasmid_binning":
        return ["gplas2"]
    if category == "typing" and (
        data_profile in {"isolate", "isolate_plasmid"} or data_profile.endswith("_isolate")
    ):
        return ["mob_typer", "plasmidfinder"]
    if category == "host_prediction":
        if data_profile in {"illumina_short", "ont_long", "pacbio_hifi", "hybrid_short_long"}:
            return ["metaphlan"]
        return ["plasmidhostfinder"]
    return []
