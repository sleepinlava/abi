"""Declarative workflow preset catalog shared by plugins and transports."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from abi.config import PLUGIN_ROOT, load_yaml
from abi.errors import ConfigError


class WorkflowCatalogError(ConfigError, ValueError):
    """A workflow catalog is missing required structure or contains invalid rows."""


class WorkflowPresetError(ConfigError, ValueError):
    """A caller requested a workflow preset that the catalog does not declare."""


@dataclass(frozen=True)
class WorkflowPreset:
    """Resolved, transport-neutral workflow selection."""

    preset_id: str
    name: str
    description: str
    required_resources: tuple[str, ...]
    include_nodes: tuple[str, ...]
    capabilities: frozenset[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.preset_id,
            "name": self.name,
            "description": self.description,
            "required_resources": list(self.required_resources),
            "include_nodes": list(self.include_nodes),
            "capabilities": sorted(self.capabilities),
        }


class WorkflowCatalog:
    """Load and resolve one plugin's declarative workflow presets."""

    def __init__(self, plugin_id: str, presets: tuple[WorkflowPreset, ...]) -> None:
        self.plugin_id = plugin_id
        self._presets = presets
        self._by_id = {preset.preset_id: preset for preset in presets}

    @classmethod
    def for_plugin(
        cls,
        plugin_id: str,
        *,
        plugin_root: str | Path | None = None,
    ) -> "WorkflowCatalog":
        root = Path(plugin_root) if plugin_root is not None else PLUGIN_ROOT / plugin_id
        path = root / "workflows/catalog.yaml"
        if not path.is_file():
            return cls(plugin_id, ())
        payload = load_yaml(path)
        rows = payload.get("workflows", [])
        if not isinstance(rows, list):
            raise WorkflowCatalogError(f"{plugin_id} workflow catalog requires a workflows list")
        presets = tuple(_parse_preset(plugin_id, row) for row in rows)
        ids = [preset.preset_id for preset in presets]
        duplicates = sorted({preset_id for preset_id in ids if ids.count(preset_id) > 1})
        if duplicates:
            raise WorkflowCatalogError(
                f"{plugin_id} workflow catalog has duplicate preset ids: {', '.join(duplicates)}"
            )
        return cls(plugin_id, presets)

    @property
    def preset_ids(self) -> tuple[str, ...]:
        return tuple(preset.preset_id for preset in self._presets)

    def resolve(self, preset_id: str) -> WorkflowPreset:
        try:
            return self._by_id[preset_id]
        except KeyError as exc:
            raise WorkflowPresetError(
                f"Unknown {self.plugin_id} workflow preset {preset_id!r}; "
                f"choose one of {list(self.preset_ids)}"
            ) from exc

    def rows(self) -> list[dict[str, Any]]:
        return [preset.to_dict() for preset in self._presets]


def _parse_preset(plugin_id: str, value: Any) -> WorkflowPreset:
    if not isinstance(value, Mapping) or not value.get("id"):
        raise WorkflowCatalogError(f"{plugin_id} workflow catalog contains a preset without an id")
    preset_id = str(value["id"])
    return WorkflowPreset(
        preset_id=preset_id,
        name=str(value.get("name", preset_id)),
        description=str(value.get("description", "")),
        required_resources=_string_tuple(plugin_id, preset_id, value, "required_resources"),
        include_nodes=_string_tuple(plugin_id, preset_id, value, "include_nodes"),
        capabilities=frozenset(_string_tuple(plugin_id, preset_id, value, "capabilities")),
    )


def _string_tuple(
    plugin_id: str,
    preset_id: str,
    value: Mapping[str, Any],
    field: str,
) -> tuple[str, ...]:
    items = value.get(field, [])
    if not isinstance(items, list) or not all(isinstance(item, str) and item for item in items):
        raise WorkflowCatalogError(
            f"{plugin_id} workflow preset {preset_id!r} field {field!r} must be a string list"
        )
    return tuple(items)
