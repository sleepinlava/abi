"""Permission model for ABI agent-facing operations."""

from __future__ import annotations

from enum import Enum
from typing import Dict

__all__ = [
    "PermissionLevel",
    "TOOL_PERMISSIONS",
    "permission_for_tool",
    "requires_confirmation",
]


class PermissionLevel(str, Enum):
    READ_ONLY = "read_only"
    PLANNING_WRITE = "planning_write"
    EXECUTION = "execution"


TOOL_PERMISSIONS: Dict[str, PermissionLevel] = {
    "abi_list_types": PermissionLevel.READ_ONLY,
    "abi_inspect": PermissionLevel.READ_ONLY,
    "abi_validate_result": PermissionLevel.READ_ONLY,
    "autoplasm_validate_result": PermissionLevel.READ_ONLY,
    "abi_plan": PermissionLevel.PLANNING_WRITE,
    "abi_dry_run": PermissionLevel.PLANNING_WRITE,
    "abi_report": PermissionLevel.PLANNING_WRITE,
    "abi_export_nextflow": PermissionLevel.PLANNING_WRITE,
    "abi_export_agent_context": PermissionLevel.READ_ONLY,
    "abi_doctor_agent": PermissionLevel.READ_ONLY,
    "abi_run": PermissionLevel.EXECUTION,
}


def permission_for_tool(tool_name: str) -> PermissionLevel:
    """Return the agent permission level for an ABI tool name."""
    return TOOL_PERMISSIONS.get(tool_name, PermissionLevel.PLANNING_WRITE)


def requires_confirmation(tool_name: str) -> bool:
    """Return whether an ABI tool is execution-gated."""
    return permission_for_tool(tool_name) == PermissionLevel.EXECUTION
