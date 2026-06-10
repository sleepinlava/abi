"""ABI configuration loading and validation."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
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
        yaml.dump(dict(data), handle, default_flow_style=False, allow_unicode=True, sort_keys=False)
    return yaml_path


def deep_merge(base: Mapping[str, Any], override: Mapping[str, Any]) -> Dict[str, Any]:
    result = dict(base)
    for key, value in override.items():
        if value is None:
            continue
        if key in result and isinstance(result[key], Mapping) and isinstance(value, Mapping):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result


def compact_overrides(overrides: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    if not overrides:
        return {}
    result: Dict[str, Any] = {}
    for key, value in overrides.items():
        if value is None:
            continue
        if isinstance(value, Mapping):
            compacted = compact_overrides(value)
            if compacted:
                result[key] = compacted
        else:
            result[key] = value
    return result
