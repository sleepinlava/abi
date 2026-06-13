"""Parameter selection helpers."""

from __future__ import annotations

from typing import Any, Dict, Mapping

from abi.plugins.metagenomic_plasmid._engine.schemas import ConfigError


def select_value(
    *,
    name: str,
    configured: Any,
    default: Any,
    mode: str,
    choices: list[Any] | None = None,
) -> Any:
    if mode not in {"auto", "interactive"}:
        raise ConfigError(f"Invalid mode {mode!r} for selecting {name}")

    value = configured if configured is not None else default
    if choices is not None and value not in choices:
        raise ConfigError(f"{name} must be one of {choices}, got {value!r}")
    return value


def record_auto_selection(params: Mapping[str, Any], reason: str) -> Dict[str, Any]:
    selected = dict(params)
    selected.setdefault("auto_selection_reason", reason)
    return selected
