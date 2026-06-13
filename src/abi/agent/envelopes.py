"""Uniform JSON envelope helpers for ABI agent transports.

# Why a unified envelope format? / 为什么需要统一的信封格式?

ABI is called by diverse agent platforms — CLI subprocesses, MCP servers, HTTP
endpoints, and OpenAI function-calling schemas. If each transport returned a
different error shape, every caller would need custom parsing logic. By
enforcing the same three-status JSON envelope everywhere, any ABI caller can:

1. Inspect ``status`` to decide the control-flow branch (success / confirm / error).
2. Read ``command`` to correlate the response with the originating call.
3. On success: consume ``result`` as the payload.
4. On confirmation_required: present the approval prompt, then retry.
5. On error: read ``error_code`` and ``diagnostic_hints`` to attempt
   automated recovery without human intervention.

# The three envelope types / 三种信封类型

    success_envelope              — ``status: "success"``
        The operation completed. ``result`` holds the structured payload.

    confirmation_required_envelope— ``status: "confirmation_required"``
        The operation is gated on user approval. The caller should present the
        result to the user and re-invoke with ``confirm_execution=true``.

    error_envelope                — ``status: "error"``
        The operation failed. ``error_code`` is a stable machine-readable code,
        ``diagnostic_hints`` are actionable recovery hints, and ``extra`` can
        carry additional context (e.g. the list of valid analysis types).

# Design decisions / 设计决策

- ``to_jsonable()`` recursively converts ``Path`` objects to strings and
  ensures all keys are plain ``str`` so the output is always safe for
  ``json.dumps``, even when intermediate data structures use ``Path`` keys
  or nested ``Path`` values.
- ``json_dumps()`` uses ``ensure_ascii=False`` so Unicode characters
  (file paths, sample names) are human-readable in the JSON output.
- All ``status`` values are stable enum-like strings — callers can safely
  ``==`` compare them without worrying about casing or spelling variants.
"""

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
    """Build a success envelope around a result mapping.

    Args:
        command: the ABI method name that produced this result (e.g. ``"plan"``).
        result:  the structured return value from the handler.

    Returns:
        ``{"status": "success", "command": <command>, "result": <json-safe dict>}``

    # 构建成功信封, 包装 handler 返回的结构化结果。
    """
    return {"status": "success", "command": command, "result": to_jsonable(result)}


def confirmation_required_envelope(command: str, result: Mapping[str, Any]) -> Dict[str, Any]:
    """Build a confirmation_required envelope around a pending result.

    Used exclusively by ``_run()`` when ``confirm_execution=False``. The
    orchestrator should present the ``result`` to the user and re-invoke
    with ``confirm_execution=true`` after approval.

    Args:
        command: the ABI method name (always ``"run"`` in practice).
        result:  contextual info about what will be executed (analysis_type,
                 engine, message).

    Returns:
        ``{"status": "confirmation_required", "command": <command>, "result": <dict>}``

    # 构建确认请求信封, 用于 run() 的 confirm_execution=False 安全闸门。
    # 编排器应向用户展示 result 内容, 获得批准后以 confirm_execution=true 重新调用。
    """
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
    """Build an error envelope with structured diagnostics.

    Args:
        command:          the ABI method name that failed.
        error:            human-readable error message.
        error_type:       Python exception class name (e.g. ``"ValueError"``).
        error_code:       stable machine-readable code from ``ERROR_CODES``
                          (e.g. ``"missing_input"``, ``"tool_not_found"``).
        diagnostic_hints: list of ``DiagnosticHint`` dicts with severity, code,
                          message, and ``suggested_next_action``.
        extra:            optional additional context (e.g. available plugin
                          IDs when ``unknown_analysis_type`` is raised).

    Returns:
        ``{"status": "error", "command": <command>, "error_code": <code>, ...}``

    # 构建错误信封, 包含结构化诊断信息。
    # error_code 来自 ERROR_CODES 稳定分类; diagnostic_hints 提供可操作的恢复建议。
    # extra 可携带附加上下文 (如 unknown_analysis_type 时提供可用插件列表)。
    """
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
    """Serialize a payload dict to a pretty-printed JSON string.

    Uses ``indent=2`` for readability in logs and ``ensure_ascii=False`` so
    that non-ASCII characters (e.g. CJK sample names, Unicode paths) are
    rendered as-is rather than escaped.

    # 将载荷字典序列化为美观的 JSON 字符串。
    # indent=2 便于日志阅读, ensure_ascii=False 保留非 ASCII 字符原样输出。
    """
    return json.dumps(to_jsonable(payload), indent=2, ensure_ascii=False)


def to_jsonable(value: Any) -> Any:
    """Recursively convert a value to a JSON-serializable equivalent.

    - ``Path`` objects are converted to strings.
    - ``Mapping`` keys are coerced to ``str``.
    - ``list`` and ``tuple`` elements are recursively processed.
    - All other types pass through unchanged (assumed JSON-safe).

    This function is the single choke-point that guarantees every envelope
    payload is safe for ``json.dumps`` regardless of what Python types the
    handler returns internally.

    # 递归将值转换为 JSON 可序列化的等价物。
    # 这是唯一保证所有信封载荷对 json.dumps 安全的关卡点。
    # Path -> str, Mapping 键强制转为 str, 列表/元组递归处理。
    """
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): to_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_jsonable(item) for item in value]
    return value
