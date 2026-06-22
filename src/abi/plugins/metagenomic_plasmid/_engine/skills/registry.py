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
    _env_assignments = None  # class-level cache for tool→env assignments

    def __init__(
        self,
        tools: Iterable[Mapping[str, Any]],
        *,
        environments_path: str | Path | None = None,
        plugin_name: str = "_default",
    ) -> None:
        self._plugin = plugin_name
        # Load tool→env assignments from environments.yaml (once, cached)
        if ToolRegistry._env_assignments is None and environments_path is not None:
            ToolRegistry._load_environment_assignments(environments_path)

        self._tools: Dict[str, Dict[str, Any]] = {}
        for tool in tools:
            tool_id = str(tool.get("id", "")).strip()
            if not tool_id:
                raise ConfigError("tool_registry.yaml contains a tool without id")
            if tool_id in self._tools:
                raise ConfigError(f"Duplicate tool id in registry: {tool_id}")
            tool_dict = dict(tool)
            # Auto-fill env_name from environments.yaml if missing
            if not tool_dict.get("env_name") and ToolRegistry._env_assignments:
                resolved = ToolRegistry._resolve_env(tool_id, plugin=plugin_name)
                if resolved and resolved != "abi-base":
                    tool_dict["env_name"] = resolved
            self._tools[tool_id] = tool_dict

    @classmethod
    def _load_environment_assignments(cls, path: str | Path) -> None:
        if cls._env_assignments is not None:
            return
        env_file = Path(path)
        if not env_file.exists():
            return
        data = yaml.safe_load(env_file.read_text(encoding="utf-8")) or {}
        raw = data.get("tool_assignments", {})
        if raw and isinstance(next(iter(raw.values())), dict):
            cls._env_assignments = {
                str(pn): {str(k): str(v) for k, v in tools.items()} for pn, tools in raw.items()
            }
        else:
            cls._env_assignments = {"_default": {str(k): str(v) for k, v in raw.items()}}

    @classmethod
    def _resolve_env(cls, tool_id: str, plugin: str = "_default") -> str:
        if cls._env_assignments is None:
            return ""
        # Direct lookup in the specified plugin
        plugin_map = cls._env_assignments.get(plugin, {})
        if plugin_map and tool_id in plugin_map:
            return plugin_map[tool_id]
        # Fallback: search all plugins for the tool
        for pn, pmap in cls._env_assignments.items():
            if pn == plugin:
                continue
            if tool_id in pmap:
                return pmap[tool_id]
        # Last resort: try _default
        default_map = cls._env_assignments.get("_default", {})
        return default_map.get(tool_id, "")

    @classmethod
    def from_path(cls, path: str | Path | None = None) -> "ToolRegistry":
        registry_path = (
            Path(path)
            if path
            else PROJECT_ROOT / "plugins" / "metagenomic_plasmid" / "tool_registry.yaml"
        )
        if not registry_path.exists():
            raise ConfigError(f"Tool registry does not exist: {registry_path}")
        with registry_path.open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
        tools = data.get("tools")
        if not isinstance(tools, list):
            raise ConfigError("tool_registry.yaml must contain a tools list")

        # Auto-detect plugin name from path
        plugin = registry_path.parent.name if "plugins" in str(registry_path) else "_default"
        if plugin == "config":
            plugin = "_default"

        # Auto-detect environments.yaml
        env_path = registry_path.parent.parent / "environments.yaml"
        if not env_path.exists():
            env_path = PROJECT_ROOT / "environments.yaml"

        return cls(
            tools,
            environments_path=env_path if env_path.exists() else None,
            plugin_name=plugin,
        )

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
