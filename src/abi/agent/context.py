"""Agent context and doctor text for ABI plugins."""

from __future__ import annotations

from typing import Any, Dict, List

from abi.diagnostics import ERROR_CODES
from abi.openai_contracts import ABI_AGENT_TOOLS, export_openai_tools
from abi.permissions import TOOL_PERMISSIONS, PermissionLevel

__all__ = ["build_agent_context", "render_doctor_agent"]


SAFE_SEQUENCE = ["list_types", "plan", "dry_run", "inspect", "report", "run"]
IMPORTANT_ARTIFACTS = [
    "execution_plan.json",
    "provenance/commands.tsv",
    "provenance/resolved_inputs.tsv",
    "provenance/tool_versions.tsv",
    "provenance/resources.json",
    "provenance/progress.jsonl",
    "tables/*.tsv",
    "report/report.md",
    "report/report.html",
]


def build_agent_context(plugin: Any) -> Dict[str, Any]:
    """Return the compact machine-readable context an agent needs for ABI."""
    table_schemas = plugin.table_schemas()
    standard_tables = sorted(str(name) for name in table_schemas)
    tools = export_openai_tools(plugin, descriptor_format="json", include_execution=False)
    execution_tools = [
        name
        for name, permission in TOOL_PERMISSIONS.items()
        if permission == PermissionLevel.EXECUTION
    ]
    return {
        "analysis_type": plugin.plugin_id,
        "display_name": plugin.display_name,
        "description": plugin.description,
        "safe_sequence": list(SAFE_SEQUENCE),
        "execution_requires_confirmation": True,
        "unsafe_tools": sorted(execution_tools),
        "default_exported_tools": [tool["name"] for tool in tools],
        "tool_permissions": {
            name: metadata["permission"] for name, metadata in ABI_AGENT_TOOLS.items()
        },
        "standard_tables": standard_tables,
        "important_artifacts": list(IMPORTANT_ARTIFACTS),
        "error_codes": sorted(ERROR_CODES),
        "recovery_rules": [
            "Call dry_run before run.",
            "Do not call abi_run unless the user has approved execution.",
            "On errors, inspect error_code and diagnostic_hints before changing inputs.",
            "Read standard tables under tables/ instead of parsing raw tool outputs.",
        ],
    }


def render_doctor_agent(plugin: Any) -> str:
    """Render a short human-readable operating guide for agent users."""
    context = build_agent_context(plugin)
    lines: List[str] = [
        f"ABI agent guide for {context['analysis_type']}",
        "",
        "Safe call order:",
        "  " + " -> ".join(context["safe_sequence"]),
        "",
        "Rules:",
        "  - Use CLI JSON, MCP, HTTP jobs, or OpenAI descriptors as transports.",
        "  - Treat ABIAgentInterface as the business boundary.",
        "  - Never execute abi_run without explicit user approval.",
        "  - Read tables/*.tsv for results instead of raw tool outputs.",
        "  - Use error_code and diagnostic_hints for recovery.",
        "",
        "Standard tables:",
    ]
    lines.extend(f"  - {name}" for name in context["standard_tables"])
    lines.extend(
        [
            "",
            "Important artifacts:",
        ]
    )
    lines.extend(f"  - {path}" for path in context["important_artifacts"])
    return "\n".join(lines) + "\n"
