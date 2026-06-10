"""OpenAI-compatible tool descriptor export for ABI plugins."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping


def _string(description: str) -> Dict[str, str]:
    return {"type": "string", "description": description}


ABI_AGENT_TOOLS = {
    "abi_list_types": {
        "description": "List installed ABI analysis plugin types.",
        "properties": {},
        "required": [],
        "read_only": True,
        "permission": "read_only",
    },
    "abi_plan": {
        "description": "Build and persist an ABI execution plan without running external tools.",
        "properties": {
            "analysis_type": _string("ABI analysis type."),
            "config_path": _string("Optional plugin config YAML path."),
            "sample_sheet": _string("Optional sample sheet TSV path."),
            "outdir": _string("Output directory for the generated plan."),
            "check_files": {"type": "boolean", "description": "Check input paths when planning."},
        },
        "required": ["analysis_type", "outdir"],
        "read_only": False,
        "permission": "planning_write",
    },
    "abi_dry_run": {
        "description": "Render commands and provenance without executing external tools.",
        "properties": {
            "analysis_type": _string("ABI analysis type."),
            "config_path": _string("Optional plugin config YAML path."),
            "sample_sheet": _string("Optional sample sheet TSV path."),
            "outdir": _string("Output directory for dry-run artifacts."),
        },
        "required": ["analysis_type", "outdir"],
        "read_only": False,
        "permission": "planning_write",
    },
    "abi_inspect": {
        "description": "Inspect ABI provenance and summarize run health.",
        "properties": {"result_dir": _string("ABI result directory.")},
        "required": ["result_dir"],
        "read_only": True,
        "permission": "read_only",
    },
    "abi_report": {
        "description": "Regenerate report files from existing ABI results.",
        "properties": {
            "result_dir": _string("ABI result directory."),
            "analysis_type": _string("Optional ABI analysis type override."),
        },
        "required": ["result_dir"],
        "read_only": False,
        "permission": "planning_write",
    },
    "abi_export_nextflow": {
        "description": (
            "Export an ABI execution plan as a Nextflow DSL2 workflow without running it."
        ),
        "properties": {
            "analysis_type": _string("ABI analysis type."),
            "config_path": _string("Optional plugin config YAML path."),
            "sample_sheet": _string("Optional sample sheet TSV path."),
            "outdir": _string("Output directory used while building the plan."),
            "output": _string("Output .nf workflow path."),
            "smoke": {"type": "boolean", "description": "Export a runnable smoke workflow."},
            "check_files": {"type": "boolean", "description": "Check input paths when planning."},
        },
        "required": ["analysis_type", "output"],
        "read_only": False,
        "permission": "planning_write",
    },
    "abi_run": {
        "description": "Execute an ABI analysis through a runtime backend after explicit approval.",
        "properties": {
            "analysis_type": _string("ABI analysis type."),
            "config_path": _string("Optional plugin config YAML path."),
            "sample_sheet": _string("Optional sample sheet TSV path."),
            "outdir": _string("Output directory for run artifacts."),
            "engine": {
                "type": "string",
                "enum": ["local", "nextflow"],
                "description": "Runtime backend.",
            },
            "smoke": {"type": "boolean", "description": "Use mocked/smoke tools."},
            "confirm_execution": {
                "type": "boolean",
                "description": "Must be true after user approval before execution.",
            },
        },
        "required": ["analysis_type", "confirm_execution"],
        "read_only": False,
        "permission": "execution",
        "requires_confirmation": True,
    },
}


READ_ONLY_TOOLS = {
    name: metadata
    for name, metadata in ABI_AGENT_TOOLS.items()
    if metadata["permission"] == "read_only"
}


def export_openai_tools(
    plugin: Any,
    *,
    descriptor_format: str,
    include_execution: bool = False,
) -> List[Dict[str, Any]]:
    tools = []
    for name, metadata in ABI_AGENT_TOOLS.items():
        if metadata["permission"] == "execution" and not include_execution:
            continue
        schema = _strict_schema(metadata["properties"], metadata["required"])
        description = f"{metadata['description']} Plugin scope: {plugin.plugin_id}."
        if descriptor_format == "responses":
            tools.append(
                {
                    "type": "function",
                    "name": name,
                    "description": description,
                    "parameters": schema,
                    "strict": True,
                }
            )
        elif descriptor_format == "apps-sdk":
            tools.append(
                {
                    "title": name,
                    "description": description,
                    "inputSchema": schema,
                    "annotations": {"readOnlyHint": bool(metadata["read_only"])},
                    "_meta": {"securitySchemes": [{"type": "noauth"}]},
                }
            )
        elif descriptor_format == "json":
            tools.append(
                {
                    "name": name,
                    "description": description,
                    "input_schema": schema,
                    "read_only": bool(metadata["read_only"]),
                    "permission": metadata["permission"],
                    "requires_confirmation": bool(metadata.get("requires_confirmation", False)),
                    "plugin_id": plugin.plugin_id,
                }
            )
        else:
            raise ValueError(f"Unknown OpenAI tool export format: {descriptor_format}")
    return tools


def _strict_schema(
    properties: Mapping[str, Mapping[str, Any]],
    required: Iterable[str],
) -> Dict[str, Any]:
    return {
        "type": "object",
        "properties": dict(properties),
        "required": list(required),
        "additionalProperties": False,
    }
