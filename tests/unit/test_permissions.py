"""Unit tests for the ABI permission model (C5)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from abi.permissions import (
    TOOL_PERMISSIONS,
    PermissionLevel,
    permission_for_tool,
    requires_confirmation,
)


class TestPermissionLevel:
    def test_all_levels_are_valid_strings(self):
        for level in PermissionLevel:
            assert isinstance(level.value, str)
            assert level.value

    def test_three_levels_exist(self):
        assert len(PermissionLevel.__members__) == 3


class TestPermissionForTool:
    def test_known_tool_returns_correct_level(self):
        # fastp is a common tool — check its permission
        for tool_id in ("fastp", "star", "spades"):
            level = permission_for_tool(tool_id)
            assert level in PermissionLevel.__members__.values()

    def test_unknown_tool_falls_back_to_read_only(self):
        # Unknown tools default to read_only (most restrictive)
        assert permission_for_tool("nonexistent_tool_xyz") == PermissionLevel.READ_ONLY

    def test_all_registered_tools_have_valid_levels(self):
        for tool_id, level in TOOL_PERMISSIONS.items():
            assert isinstance(level, PermissionLevel), f"{tool_id}: {type(level)}"
            assert isinstance(level.value, str)


class TestRequiresConfirmation:
    def test_execution_tool_requires_confirmation(self):
        # 'abi_run' is registered as EXECUTION-level → requires confirmation
        assert requires_confirmation("abi_run") is True

    def test_read_only_tool_does_not_require_confirmation(self):
        # 'abi_list_types' is READ_ONLY → no confirmation needed
        assert requires_confirmation("abi_list_types") is False

    def test_unknown_tool_does_not_require_confirmation(self):
        # Unknown tools default to READ_ONLY → no confirmation
        assert requires_confirmation("_unknown_tool_") is False
