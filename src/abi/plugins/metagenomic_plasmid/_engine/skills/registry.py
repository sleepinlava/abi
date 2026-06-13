"""Tool registry loader."""

from __future__ import annotations

import string
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping

import yaml

from abi.plugins.metagenomic_plasmid._engine.config import PROJECT_ROOT
from abi.plugins.metagenomic_plasmid._engine.schemas import ConfigError
from abi.plugins.metagenomic_plasmid._engine.skills.base import GenericCommandSkill

RESOURCE_FIELDS = {
    "database",
    "model",
    "refgraph",
    "ref_list",
    "plasmid_index",
    "annotations",
    "gene_calls",
    "reference",
    "genome_index",
    "annotation_gtf",
}


class ToolRegistry:
    def __init__(self, tools: Iterable[Mapping[str, Any]]) -> None:
        self._tools: Dict[str, Dict[str, Any]] = {}
        for tool in tools:
            tool_id = str(tool.get("id", "")).strip()
            if not tool_id:
                raise ConfigError("tool_registry.yaml contains a tool without id")
            if tool_id in self._tools:
                raise ConfigError(f"Duplicate tool id in registry: {tool_id}")
            self._tools[tool_id] = dict(tool)

    @classmethod
    def from_path(cls, path: str | Path | None = None) -> "ToolRegistry":
        registry_path = Path(path) if path else PROJECT_ROOT / "config" / "tool_registry.yaml"
        if not registry_path.exists():
            raise ConfigError(f"Tool registry does not exist: {registry_path}")
        with registry_path.open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
        tools = data.get("tools")
        if not isinstance(tools, list):
            raise ConfigError("tool_registry.yaml must contain a tools list")
        return cls(tools)

    def ids(self) -> List[str]:
        return sorted(self._tools)

    def list_tools(self) -> List[Dict[str, Any]]:
        return [self._tools[tool_id] for tool_id in self.ids()]

    def get(self, tool_id: str) -> Dict[str, Any]:
        if tool_id not in self._tools:
            raise ConfigError(f"Tool {tool_id!r} is not registered")
        return self._tools[tool_id]

    def has(self, tool_id: str) -> bool:
        return tool_id in self._tools

    def create(self, tool_id: str, *, mock_tools: bool = False) -> GenericCommandSkill:
        metadata = dict(self.get(tool_id))
        metadata["mock_tools"] = mock_tools
        return GenericCommandSkill(metadata)

    def check_tools(
        self, *, mock_tools: bool = False, config: Mapping[str, Any] | None = None
    ) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        for metadata in self.list_tools():
            skill = self.create(str(metadata["id"]), mock_tools=mock_tools)
            installed = skill.check_installation()
            resource_status, resource_details = _resource_status(metadata, config or {})
            rows.append(
                {
                    "tool_id": metadata["id"],
                    "name": metadata.get("name", metadata["id"]),
                    "category": metadata.get("category", ""),
                    "required": bool(metadata.get("required", False)),
                    "default_enabled": bool(metadata.get("default_enabled", False)),
                    "env_name": metadata.get("env_name", ""),
                    "executable": metadata.get("executable", ""),
                    "installed": installed,
                    "resource_status": resource_status,
                    "resources": resource_details,
                    "status": "ok" if installed else "missing",
                }
            )
        return rows


def _resource_status(
    metadata: Mapping[str, Any],
    config: Mapping[str, Any],
) -> tuple[str, Dict[str, str]]:
    fields = _resource_fields(str(metadata.get("command_template", "")))
    if not fields:
        return "not_required", {}

    tool_id = str(metadata.get("id", ""))
    resources = config.get("resources", {})
    tool_params = config.get("tool_params", {})
    configured: Dict[str, Any] = {}
    if isinstance(resources, Mapping):
        tool_resources = resources.get(tool_id, {})
        if isinstance(tool_resources, Mapping):
            configured.update(tool_resources)
        for field in fields:
            if field in resources:
                configured[field] = resources[field]
    if isinstance(tool_params, Mapping):
        tool_parameter_values = tool_params.get(tool_id, {})
        if isinstance(tool_parameter_values, Mapping):
            configured.update(tool_parameter_values)

    details: Dict[str, str] = {}
    missing = []
    not_configured = []
    for field in fields:
        value = configured.get(field)
        if not value:
            details[field] = "not_configured"
            not_configured.append(field)
            continue
        path = Path(str(value))
        if path.exists():
            details[field] = str(path)
        else:
            details[field] = f"missing:{path}"
            missing.append(field)

    if missing:
        return "missing", details
    if not_configured:
        return "not_configured", details
    return "ok", details


def _resource_fields(command_template: str) -> List[str]:
    fields: List[str] = []
    formatter = string.Formatter()
    for _, field_name, _, _ in formatter.parse(command_template):
        if not field_name:
            continue
        root = field_name.split(".", 1)[0].split("[", 1)[0]
        if root in RESOURCE_FIELDS and root not in fields:
            fields.append(root)
    return fields
