"""Unified tool descriptor export for all major LLM providers.

This module is the **single source of truth** for ABI tool metadata, dispatch
aliases, and provider-specific export formats. It replaces the old
``openai_contracts.py`` pattern where tool definitions and their exporters were
coupled to a single LLM provider.

All LLM providers fall into exactly three format families:

1. **OpenAI-compatible** — OpenAI, DeepSeek, 智谱 GLM, Kimi, Qwen, MiniMax
2. **Anthropic Claude**   — ``input_schema`` key, no ``strict`` field
3. **Google Gemini**      — ``function_declarations`` wrapper

Provider-specific quirks (e.g., ``strict`` mode support, naming rules) are
controlled via ``PROVIDER_PROFILES`` rather than duplicated exporters.

使用方式
~~~~~~~~

.. code-block:: python

    from abi.tool_descriptors import (
        export_openai_compatible,
        export_anthropic,
        export_gemini,
        export_json,
    )

    plugin = get_plugin("metatranscriptomics")

    # OpenAI-compatible providers
    tools = export_openai_compatible(plugin, provider="deepseek")
    tools = export_openai_compatible(plugin, provider="zhipu")

    # Anthropic Claude
    tools = export_anthropic(plugin)

    # Google Gemini
    tools = export_gemini(plugin)
"""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Mapping, TypedDict

__all__ = [
    "ABI_AGENT_TOOLS",
    "COMMON_PLAN_PROPERTIES",
    "PROVIDER_PROFILES",
    "READ_ONLY_TOOLS",
    "TOOL_ALIASES",
    "ToolMetadata",
    "_strict_schema",
    "export_anthropic",
    "export_gemini",
    "export_json",
    "export_openai_compatible",
    "export_openai_tools",
]

# ═══════════════════════════════════════════════════════════════════════════
# Schema helpers
# ═══════════════════════════════════════════════════════════════════════════


def _string(description: str) -> Dict[str, str]:
    return {"type": "string", "description": description}


def _integer(description: str, *, minimum: int | None = None) -> Dict[str, Any]:
    schema: Dict[str, Any] = {"type": "integer", "description": description}
    if minimum is not None:
        schema["minimum"] = minimum
    return schema


def _boolean(description: str) -> Dict[str, str]:
    return {"type": "boolean", "description": description}


# ═══════════════════════════════════════════════════════════════════════════
# Shared schema fragments
# ═══════════════════════════════════════════════════════════════════════════

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
    "db_profile": _string("Optional database profile name (e.g. light, full, shared)."),
    "resource_root": _string("Optional resource root directory override."),
    "resource_overrides_list": {
        "type": "array",
        "items": {"type": "string"},
        "description": "Optional resource path overrides (id=path).",
    },
}

RESOURCE_RUNTIME_PROPERTIES: Dict[str, Mapping[str, Any]] = {
    "resource_profile": _string("Optional resource profile preset."),
    "cpu_override": _integer("Optional CPU override for every step.", minimum=1),
    "memory_override": _string("Optional memory override, for example 16GB."),
    "walltime_override": _string("Optional walltime override, for example 04:00:00."),
    "accelerator_override": _string("Optional accelerator override."),
    "container_image": _string("Optional default container image."),
    "container_runtime": _string("Optional container runtime."),
}


# ═══════════════════════════════════════════════════════════════════════════
# Data types
# ═══════════════════════════════════════════════════════════════════════════


class ToolMetadata(TypedDict, total=False):
    description: str
    properties: Dict[str, Mapping[str, Any]]
    required: List[str]
    read_only: bool
    permission: str
    requires_confirmation: bool


# ═══════════════════════════════════════════════════════════════════════════
# Tool definitions (single source of truth)
# ═══════════════════════════════════════════════════════════════════════════

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
    "abi_check": {
        "description": "Run plugin input, resource, and runtime preflight checks.",
        "properties": {
            "analysis_type": _string("ABI analysis type."),
            "config_path": _string("Optional plugin config YAML path."),
            "sample_sheet": _string("Optional sample sheet TSV path."),
            "profile": _string("Optional plugin configuration profile."),
            "engine": {
                "type": "string",
                "enum": ["local", "nextflow", "hpc"],
                "description": "Target runtime backend.",
            },
            "check_runtime": _boolean("Check installed executables and environments."),
            "db_profile": _string("Optional database profile name (e.g. light, full, shared)."),
            "resource_root": _string("Optional resource root directory override."),
            "resource_overrides_list": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional resource path overrides (id=path).",
            },
        },
        "required": ["analysis_type"],
        "read_only": True,
        "permission": "read_only",
    },
    "abi_dry_run": {
        "description": "Render commands and provenance without executing external tools.",
        "properties": {
            **COMMON_PLAN_PROPERTIES,
            **RESOURCE_RUNTIME_PROPERTIES,
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
    "abi_install_skills": {
        "description": "Install bundled ABI agent skills and their README documentation.",
        "properties": {
            "target": _string("Optional destination directory."),
            "force": _boolean("Overwrite existing skill files."),
        },
        "required": [],
        "read_only": False,
        "permission": "planning_write",
    },
    "abi_query": {
        "description": "Query lightweight plugin DAG and tool metadata without building a plan.",
        "properties": {
            "analysis_type": _string("ABI analysis type."),
            "what": {
                "type": "string",
                "enum": [
                    "stages",
                    "tools",
                    "platforms",
                    "workflows",
                    "resources",
                    "inputs",
                    "outputs",
                ],
                "description": "Metadata target to query.",
            },
            "step": _string("Tool or DAG step ID required by resource/input/output queries."),
        },
        "required": ["analysis_type", "what"],
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
                "enum": ["local", "nextflow", "hpc"],
                "description": "Runtime backend.",
            },
            **RESOURCE_RUNTIME_PROPERTIES,
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
            "scheduler": _string("HPC scheduler (slurm or pbs)."),
            "partition": _string("HPC partition or queue."),
            "account": _string("HPC allocation account."),
            "qos": _string("Slurm quality of service."),
            "hpc_timeout_seconds": {
                "type": "number",
                "description": "Maximum HPC workflow duration in seconds.",
            },
            "poll_interval_seconds": {
                "type": "number",
                "description": "Scheduler polling interval in seconds.",
            },
            "db_profile": _string("Optional database profile name (e.g. light, full, shared)."),
            "resource_root": _string("Optional resource root directory override."),
            "resource_overrides_list": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional resource path overrides (id=path).",
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
    "abi_autoplasm_validate_result": {
        "description": "Validate a metagenomic-plasmid result directory (legacy public alias).",
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


# ═══════════════════════════════════════════════════════════════════════════
# Tool name aliases (single source of truth — was inline in dispatch())
# ═══════════════════════════════════════════════════════════════════════════

TOOL_ALIASES: Dict[str, str] = {
    "list": "list_types",
    "list-types": "list_types",
    "list_types": "list_types",
    "abi_list": "list_types",
    "abi_list_types": "list_types",
    "plan": "plan",
    "abi_plan": "plan",
    "check": "check",
    "abi_check": "check",
    "dry_run": "dry_run",
    "dry-run": "dry_run",
    "abi_dry_run": "dry_run",
    "inspect": "inspect",
    "abi_inspect": "inspect",
    "report": "report",
    "abi_report": "report",
    "run": "run",
    "abi_run": "run",
    "export_nextflow": "export_nextflow",
    "export-nextflow": "export_nextflow",
    "abi_export_nextflow": "export_nextflow",
    "export_agent_context": "export_agent_context",
    "export-agent-context": "export_agent_context",
    "abi_export_agent_context": "export_agent_context",
    "doctor_agent": "doctor_agent",
    "doctor-agent": "doctor_agent",
    "abi_doctor_agent": "doctor_agent",
    "install-skills": "install_skills",
    "install_skills": "install_skills",
    "abi_install_skills": "install_skills",
    "query": "query",
    "abi_query": "query",
    "validate_result": "abi_validate_result",
    "validate-result": "abi_validate_result",
    "abi_validate_result": "abi_validate_result",
    "abi_autoplasm_validate_result": "autoplasm_validate_result",
    "autoplasm_validate_result": "autoplasm_validate_result",
    "autoplasm-validate-result": "autoplasm_validate_result",
}


# ═══════════════════════════════════════════════════════════════════════════
# Provider profiles
# ═══════════════════════════════════════════════════════════════════════════

ProviderProfile = Dict[str, Any]

PROVIDER_PROFILES: Dict[str, ProviderProfile] = {
    "openai": {
        "strict": True,
        "additional_properties": False,
        "name_rules": "standard",
    },
    "deepseek": {
        "strict": True,
        "additional_properties": False,
        "name_rules": "standard",
    },
    "zhipu": {
        "strict": False,
        "additional_properties": None,  # omit entirely
        "name_rules": "zhipu",
    },
    "glm": {
        "strict": False,
        "additional_properties": None,
        "name_rules": "zhipu",
    },
    "kimi": {
        "strict": True,
        "additional_properties": False,
        "name_rules": "standard",
    },
    "qwen": {
        "strict": False,
        "additional_properties": False,
        "name_rules": "standard",
    },
    "minimax": {
        "strict": False,
        "additional_properties": None,
        "name_rules": "standard",
    },
}

# Name validation rules for provider-specific constraints.
# 智谱 GLM: [a-zA-Z0-9_], no dashes, max 64 chars.
_NAME_RULES: Dict[str, str] = {
    "standard": r"^[a-zA-Z0-9_-]{1,64}$",
    "zhipu": r"^[a-zA-Z0-9_]{1,64}$",
}

# Aliases so users can type "zhipu" or "glm" interchangeably.
_PROVIDER_ALIASES: Dict[str, str] = {
    "z.ai": "zhipu",
    "zhipuai": "zhipu",
    "chatglm": "glm",
    "moonshot": "kimi",
    "tongyi": "qwen",
    "dashscope": "qwen",
    "minimax": "minimax",
    "mimo": "minimax",
}


def _resolve_provider(name: str) -> str:
    """Normalize provider name through aliases and validate it."""
    canonical = _PROVIDER_ALIASES.get(name.lower(), name.lower())
    if canonical not in PROVIDER_PROFILES:
        known = sorted(PROVIDER_PROFILES)
        raise ValueError(
            f"Unknown provider {name!r}. Known providers: {', '.join(known)}. "
            f"Aliases: {', '.join(f'{k}→{v}' for k, v in sorted(_PROVIDER_ALIASES.items()))}."
        )
    return canonical


# ═══════════════════════════════════════════════════════════════════════════
# Schema utilities
# ═══════════════════════════════════════════════════════════════════════════


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


def _base_schema(
    properties: Mapping[str, Mapping[str, Any]],
    required: Iterable[str],
    *,
    additional_properties: bool | None,
) -> Dict[str, Any]:
    """Build a JSON Schema dict, optionally including ``additionalProperties``."""
    schema: Dict[str, Any] = {
        "type": "object",
        "properties": dict(properties),
        "required": list(required),
    }
    if additional_properties is not None:
        schema["additionalProperties"] = additional_properties
    return schema


def _validate_tool_name(name: str, *, name_rules: str) -> str:
    """Validate (and if needed, normalise) a tool name for provider constraints."""
    pattern = _NAME_RULES.get(name_rules, _NAME_RULES["standard"])
    if not re.match(pattern, name):
        # For zhipu: replace dashes with underscores
        if name_rules == "zhipu":
            sanitized = name.replace("-", "_")
            if re.match(pattern, sanitized):
                return sanitized
        raise ValueError(
            f"Tool name {name!r} does not match naming rules for {name_rules!r} "
            f"(pattern: {pattern})."
        )
    return name


# ═══════════════════════════════════════════════════════════════════════════
# Format-specific exporters
# ═══════════════════════════════════════════════════════════════════════════


def export_openai_compatible(
    plugin: Any,
    *,
    include_execution: bool = False,
    provider: str = "openai",
) -> List[Dict[str, Any]]:
    """Export tools in OpenAI-compatible function-calling format.

    Covers **all** providers that use the OpenAI tool-calling schema:
    OpenAI, DeepSeek, 智谱 GLM, Kimi (Moonshot), 通义千问 Qwen, MiniMax.

    Provider-specific adjustments are controlled by ``PROVIDER_PROFILES``.

    Args:
        plugin: An ``ABIPlugin`` instance (provides ``plugin_id`` for descriptions).
        include_execution: If True, include ``abi_run`` (default: False for safety).
        provider: Provider key in ``PROVIDER_PROFILES`` (default: ``"openai"``).

    Returns:
        List of dicts suitable for the ``tools`` parameter of the Chat Completions API.
    """
    provider_key = _resolve_provider(provider)
    profile = PROVIDER_PROFILES[provider_key]
    strict = bool(profile["strict"])
    additional_properties = profile.get("additional_properties")
    name_rules = str(profile.get("name_rules", "standard"))

    tools: List[Dict[str, Any]] = []
    for name, metadata in ABI_AGENT_TOOLS.items():
        if metadata["permission"] == "execution" and not include_execution:
            continue
        description = f"{metadata['description']} Plugin scope: {plugin.plugin_id}."
        validated_name = _validate_tool_name(name, name_rules=name_rules)
        schema = _base_schema(
            metadata["properties"],
            metadata["required"],
            additional_properties=additional_properties,
        )
        func_def: Dict[str, Any] = {
            "name": validated_name,
            "description": description,
            "parameters": schema,
        }
        if strict:
            func_def["strict"] = True
        tools.append({"type": "function", "function": func_def})
    return tools


def export_anthropic(
    plugin: Any,
    *,
    include_execution: bool = False,
) -> List[Dict[str, Any]]:
    """Export tools in Anthropic Claude-compatible ``tool_use`` format.

    Key differences from OpenAI format:
    - Uses ``input_schema`` key (not ``parameters``).
    - No ``type: "function"`` wrapper — each tool is a flat dict.
    - No ``strict`` field.
    - No ``additionalProperties: false``.

    Args:
        plugin: An ``ABIPlugin`` instance.
        include_execution: If True, include ``abi_run``.

    Returns:
        List of dicts suitable for the Anthropic Messages API ``tools`` parameter.
    """
    tools: List[Dict[str, Any]] = []
    for name, metadata in ABI_AGENT_TOOLS.items():
        if metadata["permission"] == "execution" and not include_execution:
            continue
        description = f"{metadata['description']} Plugin scope: {plugin.plugin_id}."
        schema: Dict[str, Any] = {
            "type": "object",
            "properties": dict(metadata["properties"]),
            "required": list(metadata["required"]),
        }
        tools.append(
            {
                "name": name,
                "description": description,
                "input_schema": schema,
            }
        )
    return tools


def export_gemini(
    plugin: Any,
    *,
    include_execution: bool = False,
) -> Dict[str, Any]:
    """Export tools in Google Gemini ``function_declarations`` format.

    Key differences from OpenAI format:
    - Wrapped in ``{"function_declarations": [...]}``.
    - Uses ``parameters`` key (same as OpenAI).
    - No ``strict`` field.
    - No ``additionalProperties: false``.

    Args:
        plugin: An ``ABIPlugin`` instance.
        include_execution: If True, include ``abi_run``.

    Returns:
        Dict with ``function_declarations`` key suitable for the Gemini API
        ``tools`` parameter.
    """
    declarations: List[Dict[str, Any]] = []
    for name, metadata in ABI_AGENT_TOOLS.items():
        if metadata["permission"] == "execution" and not include_execution:
            continue
        description = f"{metadata['description']} Plugin scope: {plugin.plugin_id}."
        schema: Dict[str, Any] = {
            "type": "object",
            "properties": dict(metadata["properties"]),
            "required": list(metadata["required"]),
        }
        declarations.append(
            {
                "name": name,
                "description": description,
                "parameters": schema,
            }
        )
    return {"function_declarations": declarations}


def export_json(
    plugin: Any,
    *,
    include_execution: bool = False,
) -> List[Dict[str, Any]]:
    """Export tools in the internal ABI JSON format.

    Used by ``build_agent_context()`` for platform-agnostic agent context.

    Args:
        plugin: An ``ABIPlugin`` instance.
        include_execution: If True, include ``abi_run``.

    Returns:
        List of dicts with ``name``, ``description``, ``input_schema``,
        ``read_only``, ``permission``, ``requires_confirmation``, ``plugin_id``.
    """
    tools: List[Dict[str, Any]] = []
    for name, metadata in ABI_AGENT_TOOLS.items():
        if metadata["permission"] == "execution" and not include_execution:
            continue
        description = f"{metadata['description']} Plugin scope: {plugin.plugin_id}."
        schema = _strict_schema(metadata["properties"], metadata["required"])
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
    return tools


# ═══════════════════════════════════════════════════════════════════════════
# Backward-compatible dispatch (the old ``export_openai_tools`` signature)
# ═══════════════════════════════════════════════════════════════════════════


def export_openai_tools(
    plugin: Any,
    *,
    descriptor_format: str,
    include_execution: bool = False,
) -> List[Dict[str, Any]]:
    """Backward-compatible dispatch that delegates to the new exporters.

    .. deprecated::
        Prefer ``export_openai_compatible()``, ``export_anthropic()``,
        ``export_gemini()``, or ``export_json()`` directly.
        This function is kept for backward compatibility only.

    Args:
        plugin: An ``ABIPlugin`` instance.
        descriptor_format: One of ``"responses"``, ``"apps-sdk"``, ``"json"``.
        include_execution: If True, include ``abi_run``.

    Returns:
        List of tool descriptor dicts in the requested format.
    """
    if descriptor_format == "responses":
        return _export_openai_responses_flat(plugin, include_execution=include_execution)
    elif descriptor_format == "apps-sdk":
        return _export_apps_sdk(plugin, include_execution=include_execution)
    elif descriptor_format == "json":
        return export_json(plugin, include_execution=include_execution)
    else:
        raise ValueError(f"Unknown OpenAI tool export format: {descriptor_format}")


def _export_openai_responses_flat(
    plugin: Any,
    *,
    include_execution: bool = False,
) -> List[Dict[str, Any]]:
    """Export tools in the legacy OpenAI Responses API flat format.

    Preserved for backward compatibility. The format is:
    ``{"type": "function", "name": ..., "description": ..., "parameters": ..., "strict": true}``

    New code should use ``export_openai_compatible()`` which uses the nested
    ``{"type": "function", "function": {...}}`` structure expected by the
    Chat Completions API.
    """
    tools: List[Dict[str, Any]] = []
    for name, metadata in ABI_AGENT_TOOLS.items():
        if metadata["permission"] == "execution" and not include_execution:
            continue
        description = f"{metadata['description']} Plugin scope: {plugin.plugin_id}."
        schema = _strict_schema(metadata["properties"], metadata["required"])
        tools.append(
            {
                "type": "function",
                "name": name,
                "description": description,
                "parameters": schema,
                "strict": True,
            }
        )
    return tools


def _export_apps_sdk(
    plugin: Any,
    *,
    include_execution: bool = False,
) -> List[Dict[str, Any]]:
    """Export tools in the deprecated OpenAI Apps SDK format."""
    tools: List[Dict[str, Any]] = []
    for name, metadata in ABI_AGENT_TOOLS.items():
        if metadata["permission"] == "execution" and not include_execution:
            continue
        description = f"{metadata['description']} Plugin scope: {plugin.plugin_id}."
        schema = _strict_schema(metadata["properties"], metadata["required"])
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
    return tools
