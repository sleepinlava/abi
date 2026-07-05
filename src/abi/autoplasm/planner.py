"""Backward-compatibility shim — proxies to abi.plugins.metagenomic_plasmid."""
# Re-exports the wrapper from the plugin's __init__.py so that
# existing code importing from abi.autoplasm.planner still works.

from __future__ import annotations

from abi.plugins.metagenomic_plasmid import build_plan_from_dag  # noqa: F401

# Preserve the legacy standalone name for callers that import build_plan
# from abi.autoplasm.planner.
build_plan = build_plan_from_dag  # noqa: F401
