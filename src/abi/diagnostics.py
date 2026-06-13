"""User-facing ABI error taxonomy and diagnostic hints.

# Why diagnostic hints matter / 为什么诊断提示很重要?

ABI is designed for **agentic autonomy**: an LLM-based agent should be able to
recover from common failures without human intervention. To make this possible,
every ABI error response carries:

    error_code           — stable, machine-readable code (e.g. ``"missing_input"``)
    diagnostic_hints     — list of ``DiagnosticHint`` objects, each containing:
        severity              — ``"error"`` (always error-level for now)
        code                  — same as parent error_code (for cheap filtering)
        artifact              — path of the problematic file (when known)
        field                 — config/schema field name (when known)
        message               — human-readable summary of what went wrong
        suggested_next_action — concrete step the agent should take next

An agent that receives an error envelope can:
1. Switch on ``error_code`` to determine the failure category.
2. Read ``suggested_next_action`` for the recommended recovery step.
3. Inspect ``artifact`` to identify the problematic file.
4. Retry with corrected inputs — all without round-tripping to a human.

# The error taxonomy / 错误分类体系

ERROR_CODES is a frozen set of 14 stable error codes covering the full
failure surface of ABI:

    unknown_analysis_type  — plugin ID not recognized
    invalid_config         — YAML/JSON config failed schema validation
    invalid_sample_sheet   — sample sheet missing or malformed
    missing_input          — a required input file does not exist
    missing_resource       — a resource is NOT_CONFIGURED or missing
    missing_database       — a bioinformatics database is unavailable
    tool_not_found         — an external tool executable is not on PATH
    permission_required    — execution requires explicit user confirmation
    runtime_not_supported  — the requested engine is not local/nextflow
    nonzero_exit           — an external command returned non-zero
    parse_failed           — tool output could not be parsed into tables
    empty_result           — the pipeline produced no output
    artifact_missing       — a required result artifact is absent
    internal_error         — unexpected/unclassified error at the ABI boundary

# classify_exception data flow / classify_exception 数据流

    1. Python exception is caught by ``ABIAgentInterface._call()``.
    2. Exception class name and message are passed to ``classify_exception``.
    3. ``classify_exception`` matches keyword patterns in the message against
       the error taxonomy (ordered from most specific to least specific).
       The ``artifact_missing`` branch uses precise phrase matching via
       ``_match_artifact_missing()`` rather than a bare ``"artifact"`` keyword
       to avoid misclassifying unrelated tool errors. / artifact_missing 分支
       使用精确短语匹配以避免误判。
    4. A single ``DiagnosticHint`` is returned with the best-matching code.
    5. The caller wraps the hint in an ``error_envelope`` and returns JSON.

This whole pipeline ensures that *every* exception at the agent boundary is
converted to a structured, self-describing error response.

# 设计目标

- 每个 ABI 错误响应都携带稳定的 error_code 和可操作的 diagnostic_hints。
- Agent 可以自主恢复常见故障, 无需人工介入。
- 错误分类使用关键词匹配, 从具体到通用排序, 确保最佳匹配。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

__all__ = [
    "ERROR_CODES",
    "DiagnosticHint",
    "classify_exception",
]


# Frozen set of all recognized ABI error codes.
# Callers can safely test membership (e.g. ``if code in ERROR_CODES``).
# 所有识别的 ABI 错误码的冻结集合。
# 调用者可安全测试成员资格 (如 if code in ERROR_CODES)。
ERROR_CODES = {
    "unknown_analysis_type",
    "invalid_config",
    "invalid_sample_sheet",
    "missing_input",
    "missing_resource",
    "missing_database",
    "tool_not_found",
    "permission_required",
    "runtime_not_supported",
    "nonzero_exit",
    "parse_failed",
    "empty_result",
    "artifact_missing",
    "internal_error",
}


@dataclass(frozen=True)
class DiagnosticHint:
    """A single actionable recovery hint produced by error classification.

    Immutable (frozen=True) so hints can be cached and reused safely.

    Fields / 字段说明:
        severity:              always ``"error"`` — reserved for future warning/info levels.
        code:                  stable error code from ``ERROR_CODES``.
        message:               human-readable one-line description of the failure.
        suggested_next_action: concrete step the agent should take to recover.
        artifact:              path to the problematic file (when extractable from
                               the exception message).
        field:                 config/schema field name (reserved for future use).

    # 单个可操作的恢复提示, 由错误分类生成。
    # 不可变 (frozen=True), 可安全缓存和复用。
    """

    severity: str
    code: str
    message: str
    suggested_next_action: str
    artifact: Optional[str] = None
    field: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dict, omitting None-valued optional fields.

        This keeps the JSON output compact — empty optional fields are
        simply absent rather than ``null``.
        # 序列化为字典, 省略值为 None 的可选字段。
        # 保持 JSON 输出紧凑 — 空可选字段直接不出现。
        """
        return {key: value for key, value in asdict(self).items() if value is not None}


def classify_exception(exc: Exception, *, command: str) -> tuple[str, List[Dict[str, Any]]]:
    """Map a Python exception to ABI's stable error taxonomy and recovery hints.

    This is the central error-classification function called by
    ``ABIAgentInterface._call()``. It inspects the exception message (and to a
    lesser extent the exception type) to determine the best-matching error code.

    Matching strategy / 匹配策略:
        1. The exception message is lowercased for case-insensitive matching.
        2. Rules are tested in order from **most specific to least specific**.
        3. The first matching rule wins — ordering matters.
        4. If no rule matches, the fallback is ``internal_error``.

    Args:
        exc:     the caught Python exception.
        command: the ABI method name that was being called (for context in
                 diagnostic messages).

    Returns:
        A tuple of ``(error_code, [diagnostic_hint_dict, ...])`` where
        ``error_code`` is one of the ``ERROR_CODES`` strings and each hint
        dict is the serialized form of a ``DiagnosticHint``.

    # 将 Python 异常映射到 ABI 稳定错误分类和恢复提示。
    # 这是 ABIAgentInterface._call() 调用的核心错误分类函数。
    # 匹配策略: 从最具体到最通用的顺序测试关键词, 第一条匹配获胜, 兜底为 internal_error。
    """
    message = str(exc)
    lowered = message.lower()
    error_type = exc.__class__.__name__

    # Match against the error taxonomy — ordered from most specific patterns
    # to least specific, so the first hit is the best classification.
    # 按从最具体到最通用的顺序匹配错误分类, 第一条命中即为最佳分类。

    if "unknown abi analysis type" in lowered:
        # Plugin ID not found in the registry — tell the agent which IDs exist.
        # 插件 ID 在注册表中未找到 — 告诉 agent 哪些 ID 可用。
        return _diagnosis(
            "unknown_analysis_type",
            f"Unsupported analysis type for {command}.",
            "Call abi_list_types and retry with one of the returned analysis_type values.",
        )
    if "requires confirm_execution" in lowered or "confirmation" in lowered:
        # The run() safety gate was triggered — agent must get user approval.
        # run() 安全闸门被触发 — agent 必须获得用户批准。
        return _diagnosis(
            "permission_required",
            "Execution requires explicit confirmation.",
            "Ask the user for approval, then retry with confirm_execution=true.",
        )
    if "unsupported runtime engine" in lowered:
        # The engine parameter was not "local" or "nextflow".
        # engine 参数不是 local 或 nextflow。
        return _diagnosis(
            "runtime_not_supported",
            "The requested runtime backend is not supported.",
            "Use engine=local or engine=nextflow, or add a runtime backend before retrying.",
        )
    if error_type == "ABIJSONError" or "invalid json" in lowered:
        # JSON deserialization failed — artifact is likely corrupted or malformed.
        # JSON 反序列化失败 — 产物可能损坏或格式错误。
        return _diagnosis(
            "parse_failed",
            "ABI could not parse a JSON config or result artifact.",
            "Check the referenced JSON file, regenerate the artifact if needed, then retry.",
            artifact=_extract_path(message),
        )
    if "missing execution plan" in lowered or _match_artifact_missing(lowered):
        # A required result file (usually execution_plan.json) is absent.
        # 必需的结果文件 (通常是 execution_plan.json) 不存在。
        return _diagnosis(
            "artifact_missing",
            "A required ABI result artifact is missing.",
            "Run plan or dry-run first, or pass the correct result_dir.",
            artifact=_extract_path(message),
        )
    if error_type in {"FileNotFoundError"} or _looks_like_missing_input(lowered):
        # The OS can't find a file or path — check config and sample sheet paths.
        # 操作系统找不到文件或路径 — 检查配置和 sample sheet 中的路径。
        return _diagnosis(
            "missing_input",
            "A required input or artifact path does not exist.",
            (
                "Inspect the referenced path, fix the config or sample sheet, "
                "then rerun plan or dry-run."
            ),
            artifact=_extract_path(message),
        )
    if "sample sheet" in lowered:
        # The sample sheet TSV is missing, has wrong columns, or invalid rows.
        # sample sheet TSV 文件缺失、列名错误或行数据无效。
        return _diagnosis(
            "invalid_sample_sheet",
            "The sample sheet is missing, malformed, or contains invalid rows.",
            "Fix the sample sheet columns and paths, then rerun plan or dry-run.",
            artifact=_extract_path(message),
        )
    if "config" in lowered or error_type in {"ConfigError"}:
        # Config loading/validation failed — probably a YAML schema mismatch.
        # 配置加载/验证失败 — 可能是 YAML schema 不匹配。
        return _diagnosis(
            "invalid_config",
            "The ABI configuration could not be loaded or validated.",
            "Check the YAML file and plugin config schema, then retry.",
            artifact=_extract_path(message),
        )
    if "database" in lowered:
        # A bioinformatics reference database (BLAST, Kraken2, etc.) is missing.
        # 生物信息学参考数据库 (BLAST, Kraken2 等) 缺失。
        return _diagnosis(
            "missing_database",
            "A required bioinformatics database is not configured or unavailable.",
            "Run the resource checker or configure a valid local database path.",
            artifact=_extract_path(message),
        )
    if "resource" in lowered or "not_configured" in lowered:
        # A resource path is still the placeholder (NOT_CONFIGURED) or doesn't
        # exist on disk — needs real configuration before execution.
        # 资源路径仍为占位符 (NOT_CONFIGURED) 或磁盘上不存在 — 执行前需配置真实路径。
        return _diagnosis(
            "missing_resource",
            "A required resource is missing or still set to a placeholder.",
            "Configure the resource path or run a dry-run with --no-check-files if only planning.",
            artifact=_extract_path(message),
        )
    if "tool not found" in lowered or "executable" in lowered:
        # A registered external tool (bwa, samtools, etc.) is not on PATH.
        # 注册的外部工具 (bwa, samtools 等) 不在 PATH 中。
        return _diagnosis(
            "tool_not_found",
            "A registered external tool executable could not be found.",
            "Install the tool in the configured environment or update the tool registry.",
        )
    if "nonzero" in lowered or "return code" in lowered:
        # An external subprocess exited with a non-zero status — check stderr.
        # 外部子进程以非零状态退出 — 检查 stderr。
        return _diagnosis(
            "nonzero_exit",
            "An external command failed with a non-zero exit status.",
            (
                "Read provenance/step_logs for stderr and retry after fixing the "
                "tool input or environment."
            ),
        )
    if "parse" in lowered:
        # Tool ran but its output couldn't be parsed into ABI standard tables.
        # 工具运行了但输出无法解析为 ABI 标准表。
        return _diagnosis(
            "parse_failed",
            "ABI could not parse a tool output into standard tables.",
            "Check the raw output file and parser contract for the failing tool.",
            artifact=_extract_path(message),
        )
    # Fallback: nothing matched — this is an unclassified/internal error.
    # 兜底: 没有匹配任何模式 — 这是未分类的内部错误。
    return _diagnosis(
        "internal_error",
        "ABI hit an unexpected error at the agent boundary.",
        "Inspect the error_type and message, then retry with a narrower command or report a bug.",
    )


def _diagnosis(
    code: str,
    message: str,
    suggested_next_action: str,
    *,
    artifact: Optional[str] = None,
    field: Optional[str] = None,
) -> tuple[str, List[Dict[str, Any]]]:
    """Construct a single DiagnosticHint and return it with its error code.

    This is a convenience factory so every classification branch is a one-liner.
    # 便捷工厂函数, 使每个分类分支只需一行代码。
    """
    hint = DiagnosticHint(
        severity="error",
        code=code,
        artifact=artifact,
        field=field,
        message=message,
        suggested_next_action=suggested_next_action,
    )
    return code, [hint.to_dict()]


def _match_artifact_missing(message: str) -> bool:
    """Precise match for missing-artifact error phrases.

    Only matches explicit "missing / not found / absent" language attached to
    ABI artifacts.  The bare word ``"artifact"`` is intentionally excluded
    because it appears in many unrelated error messages (e.g. ``"artifact
    processing failed"``, ``"artifact generation error"``) that are better
    classified as ``internal_error`` or ``nonzero_exit``.
    # 精确匹配缺失产物的错误短语，避免宽泛的 "artifact" 关键词误判。
    """
    return any(
        phrase in message
        for phrase in (
            "missing artifact",
            "artifact is missing",
            "artifact not found",
            "no such artifact",
            "required artifact",
            "result artifact is absent",
        )
    )


def _looks_like_missing_input(message: str) -> bool:
    """Heuristic: does the error message indicate a missing file?

    Checks for common OS/filesystem phrases like "does not exist" or
    "no such file" that indicate a path resolution failure, even when
    the exception type is not ``FileNotFoundError``.
    # 启发式判断: 错误消息是否指示文件缺失?
    # 检查常见的 OS/文件系统短语, 即使异常类型不是 FileNotFoundError。
    """
    return any(
        marker in message
        for marker in (
            "does not exist",
            "do not exist",
            "no such file",
            "missing input",
        )
    )


def _extract_path(message: str) -> Optional[str]:
    """Best-effort extraction of a file path from an error message.

    Scans tokens in reverse order (paths tend to appear near the end of error
    messages) and returns the first token that looks like a file path
    (contains ``/`` or ends with a known extension like ``.yaml``, ``.tsv``).

    Returns None when no plausible path is found.

    # 尽力从错误消息中提取文件路径。
    # 逆序扫描 token (路径通常出现在错误消息末尾),
    # 返回第一个看起来像路径的 token (含 / 或以 .yaml .tsv 等结尾)。
    """
    tokens = [token.strip(" ,;:'\"()[]{}") for token in message.split()]
    for token in reversed(tokens):
        if not token:
            continue
        if "/" in token or token.endswith((".yaml", ".yml", ".tsv", ".json", ".txt", ".fa")):
            return str(Path(token))
    return None
