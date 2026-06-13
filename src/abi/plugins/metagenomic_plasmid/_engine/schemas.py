"""Backward-compatibility shim — re-exports canonical ABI schemas."""

from __future__ import annotations

from abi.schemas import (
    ConfigError,
    ExecutionPlan,
    PlanStep,
    SampleContext,
    SampleInput,
    SampleSheetError,
    ToolError,
    VALID_MODES,
    VALID_PLATFORMS,
    VALID_PLASMID_STRATEGIES,
    ensure_parent,
)

AutoPlasmError = __import__("abi.errors", fromlist=["ABIError"]).ABIError

__all__ = [
    "AutoPlasmError",
    "ConfigError",
    "ExecutionPlan",
    "PlanStep",
    "SampleContext",
    "SampleInput",
    "SampleSheetError",
    "ToolError",
    "VALID_MODES",
    "VALID_PLATFORMS",
    "VALID_PLASMID_STRATEGIES",
    "ensure_parent",
]
