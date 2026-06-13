"""Uniform JSON envelope helpers for ABI agent transports."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence

__all__ = [
    "confirmation_required_envelope",
    "error_envelope",
    "json_dumps",
    "success_envelope",
    "to_jsonable",
]


def success_envelope(command: str, result: Mapping[str, Any]) -> Dict[str, Any]:
    return {"status": "success", "command": command, "result": to_jsonable(result)}


def confirmation_required_envelope(command: str, result: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "status": "confirmation_required",
        "command": command,
        "result": to_jsonable(result),
    }


def error_envelope(
    command: str,
    *,
    error: str,
    error_type: str,
    error_code: str,
    diagnostic_hints: Sequence[Mapping[str, Any]],
    extra: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "status": "error",
        "command": command,
        "error_code": error_code,
        "error": error,
        "error_type": error_type,
        "diagnostic_hints": to_jsonable(diagnostic_hints),
    }
    if extra:
        payload.update(to_jsonable(extra))
    return payload


def json_dumps(payload: Mapping[str, Any]) -> str:
    return json.dumps(to_jsonable(payload), indent=2, ensure_ascii=False)


def to_jsonable(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): to_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_jsonable(item) for item in value]
    return value
