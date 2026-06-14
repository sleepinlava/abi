"""Configuration helpers for the ABI prototype."""

from __future__ import annotations

import os
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

import yaml


def _resolve_project_root() -> Path:
    current = Path(__file__).resolve()
    for candidate in (current.parents[2], current.parents[1], Path.cwd()):
        if (candidate / "plugins").exists():
            return candidate
    return current.parents[2]


PROJECT_ROOT = _resolve_project_root()
PLUGIN_ROOT = PROJECT_ROOT / "plugins"


class ABIConfigError(RuntimeError):
    """Raised when ABI configuration is invalid."""


def load_yaml(path: str | Path) -> Dict[str, Any]:
    yaml_path = Path(path)
    if not yaml_path.exists():
        raise ABIConfigError(f"YAML file does not exist: {yaml_path}")
    with yaml_path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ABIConfigError(f"YAML file must contain a mapping at top level: {yaml_path}")
    return data


def write_yaml(data: Mapping[str, Any], path: str | Path) -> Path:
    yaml_path = Path(path)
    yaml_path.parent.mkdir(parents=True, exist_ok=True)
    with yaml_path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(dict(data), handle, sort_keys=False, allow_unicode=True)
    return yaml_path


def resolved_mamba_root() -> Path:
    """Return the local mamba root used by ABI-managed tool environments."""
    return Path(
        os.environ.get("ABI_MAMBA_ROOT")
        or os.environ.get("AUTOPLASM_MAMBA_ROOT")
        or PROJECT_ROOT / ".mamba"
    )


def deep_merge(base: Dict[str, Any], override: Mapping[str, Any]) -> Dict[str, Any]:
    result = deepcopy(base)
    for key, value in override.items():
        if value is None:
            continue
        if isinstance(value, Mapping) and isinstance(result.get(key), Mapping):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result


def compact_overrides(overrides: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    if not overrides:
        return {}
    compacted: Dict[str, Any] = {}
    for key, value in overrides.items():
        if value is None:
            continue
        if isinstance(value, Mapping):
            nested = compact_overrides(value)
            if nested:
                compacted[key] = nested
        else:
            compacted[key] = value
    return compacted
