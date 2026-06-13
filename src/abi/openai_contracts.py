"""OpenAI-compatible tool descriptor export for ABI plugins."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping, TypedDict

__all__ = [
    "ABI_AGENT_TOOLS",
    "READ_ONLY_TOOLS",
    "ToolMetadata",
    "export_openai_tools",
]


def _string(description: str) -> Dict[str, str]:
    return {"type": "string", "description": description}


def _integer(description: str, *, minimum: int | None = None) -> Dict[str, Any]:
    schema: Dict[str, Any] = {"type": "integer", "description": description}
    if minimum is not None:
        schema["minimum"] = minimum
    return schema


def _boolean(description: str) -> Dict[str, str]:
    return {"type": "boolean", "description": description}


COMMON_PLAN_PROPERTIES: Dict[str, Mapping[str, Any]] = {
    "analysis_type": _string("ABI analysis type."),
    "config_path": _string("Optional plugin config YAML path."),
    "sample_sheet": _string("Optional sample sheet TSV path."),
    "profile": _string("Optional plugin configuration profile."),
    "mode": _string("Optional execution or planning mode override."),
    "threads": _integer("Optional thread count override.", minimum=1),
    "outdir": _string("Output directory for generated ABI artifacts."),
    "log_dir": _string("Optional log directory override."),
    "check_files": _boolean("Check input paths when planning."),
}


class ToolMetadata(TypedDict, total=False):
    description: str
    properties: Dict[str, Mapping[str, Any]]
    required: List[str]
    read_only: bool
    permission: str
    requires_confirmation: bool


ABI_AGENT_TOOLS: Dict[str, ToolMetadata] = {
    "abi_list_types": {
        "description": "List installed ABI analysis plugin types.",
        "properties": {},
        "required": [],
        "read_only": True,
        "permission": "read_only",
    },
    "abi_plan": {
        "description": "Build and persist an ABI execution plan without running external tools.",
        "properties": dict(COMMON_PLAN_PROPERTIES),
        "required": ["analysis_type", "outdir"],
        "read_only": False,
        "permission": "planning_write",
    },
    "abi_dry_run": {
        "description": "Render commands and provenance without executing external tools.",
        "properties": {
            **COMMON_PLAN_PROPERTIES,
            "progress": _boolean("Write live progress artifacts when supported."),
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
            "profile": _string("Optional plugin configuration profile."),
            "mode": _string("Optional planning mode override."),
            "threads": _integer("Optional thread count override.", minimum=1),
            "log_dir": _string("Optional log directory override."),
            "output": _string("Output .nf workflow path."),
            "smoke": _boolean("Export a runnable smoke workflow."),
            "mamba_root": _string("Optional local mamba root for generated workflows."),
            "check_files": _boolean("Check input paths when planning."),
        },
        "required": ["analysis_type", "output"],
        "read_only": False,
        "permission": "planning_write",
    },
    "abi_export_agent_context": {
        "description": "Export compact machine-readable guidance for ABI agent callers.",
        "properties": {"analysis_type": _string("ABI analysis type.")},
        "required": ["analysis_type"],
        "read_only": True,
        "permission": "read_only",
    },
    "abi_doctor_agent": {
        "description": "Return the shortest safe operating guide for ABI agent callers.",
        "properties": {"analysis_type": _string("ABI analysis type.")},
        "required": ["analysis_type"],
        "read_only": True,
        "permission": "read_only",
    },
    "abi_run": {
        "description": "Execute an ABI analysis through a runtime backend after explicit approval.",
        "properties": {
            "analysis_type": _string("ABI analysis type."),
            "config_path": _string("Optional plugin config YAML path."),
            "sample_sheet": _string("Optional sample sheet TSV path."),
            "outdir": _string("Output directory for run artifacts."),
            "profile": _string("Optional plugin configuration profile."),
            "mode": _string("Optional execution mode override."),
            "threads": _integer("Optional thread count override.", minimum=1),
            "log_dir": _string("Optional log directory override."),
            "engine": {
                "type": "string",
                "enum": ["local", "nextflow"],
                "description": "Runtime backend.",
            },
            "workflow": _string("Optional workflow path to write or run."),
            "work_dir": _string("Optional Nextflow work directory."),
            "nxf_home": _string("Optional Nextflow home directory."),
            "nextflow_bin": _string("Optional Nextflow executable path."),
            "nextflow_profile": _string("Optional Nextflow profile."),
            "executor": _string("Optional Nextflow process executor override."),
            "resume": _boolean("Resume a previous Nextflow run when supported."),
            "mamba_root": _string("Optional local mamba root for generated workflows."),
            "smoke": _boolean("Use mocked/smoke tools."),
            "check_files": _boolean("Check input paths before execution."),
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
    "abi_validate_result": {
        "description": "Validate an ABI result directory without modifying it.",
        "properties": {
            "result_dir": _string("ABI result directory."),
            "allow_empty_tables": {
                "type": "boolean",
                "description": "Allow standard tables with headers and zero data rows.",
            },
        },
        "required": ["result_dir"],
        "read_only": True,
        "permission": "read_only",
    },
}


READ_ONLY_TOOLS: Dict[str, ToolMetadata] = {
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
                    "name": name,
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
