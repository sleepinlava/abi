"""Timeout parsing helpers for ABI external process boundaries."""

from __future__ import annotations

import os
from typing import Any

from abi.config import mapping_block

__all__ = [
    "DEFAULT_RESOURCE_TIMEOUT_SECONDS",
    "DEFAULT_TOOL_TIMEOUT_SECONDS",
    "mapping_block",
    "parse_timeout_seconds",
    "timeout_from_env_or_value",
]

DEFAULT_TOOL_TIMEOUT_SECONDS = 7 * 24 * 60 * 60
DEFAULT_RESOURCE_TIMEOUT_SECONDS = 24 * 60 * 60

_DISABLED_VALUES = {"0", "false", "no", "none", "off", "disabled"}


def parse_timeout_seconds(value: Any, *, default: float | None) -> float | None:
    """Return a positive timeout in seconds, or None when explicitly disabled."""
    if value is None or value == "":
        return default
    if isinstance(value, str) and value.strip().lower() in _DISABLED_VALUES:
        return None
    try:
        seconds = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"timeout_seconds must be a positive number, got {value!r}") from exc
    if seconds <= 0:
        return None
    return seconds


def timeout_from_env_or_value(
    env_var: str,
    value: Any,
    *,
    default: float | None,
) -> float | None:
    """Resolve timeout with an environment variable taking precedence."""
    env_value = os.environ.get(env_var)
    return parse_timeout_seconds(env_value if env_value is not None else value, default=default)
