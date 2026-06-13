"""JSON helpers that raise user-facing ABI errors."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from abi.schemas import ABIError


class ABIJSONError(ABIError):
    """Raised when a JSON file or payload cannot be decoded as expected."""


def load_json_file(path: str | Path) -> Any:
    json_path = Path(path)
    try:
        return json.loads(json_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ABIJSONError(f"Could not read JSON file {json_path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ABIJSONError(_json_decode_message(f"Invalid JSON in {json_path}", exc)) from exc


def load_json_object(path: str | Path) -> Dict[str, Any]:
    data = load_json_file(path)
    if not isinstance(data, dict):
        raise ABIJSONError(f"Expected a JSON object in {Path(path)}")
    return data


def loads_json(payload: str | bytes, *, label: str = "JSON payload") -> Any:
    try:
        if isinstance(payload, bytes):
            payload = payload.decode("utf-8")
        return json.loads(payload)
    except UnicodeDecodeError as exc:
        raise ABIJSONError(f"{label} is not valid UTF-8: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ABIJSONError(_json_decode_message(f"Invalid JSON in {label}", exc)) from exc


def _json_decode_message(prefix: str, exc: json.JSONDecodeError) -> str:
    return f"{prefix}: line {exc.lineno}, column {exc.colno}: {exc.msg}"
