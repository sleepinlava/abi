"""User-facing ABI error taxonomy and diagnostic hints."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

__all__ = [
    "ERROR_CODES",
    "DiagnosticHint",
    "classify_exception",
]


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
    severity: str
    code: str
    message: str
    suggested_next_action: str
    artifact: Optional[str] = None
    field: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {key: value for key, value in asdict(self).items() if value is not None}


def classify_exception(exc: Exception, *, command: str) -> tuple[str, List[Dict[str, Any]]]:
    """Map an exception to ABI's stable error taxonomy and recovery hints."""
    message = str(exc)
    lowered = message.lower()
    error_type = exc.__class__.__name__

    if "unknown abi analysis type" in lowered:
        return _diagnosis(
            "unknown_analysis_type",
            f"Unsupported analysis type for {command}.",
            "Call abi_list_types and retry with one of the returned analysis_type values.",
        )
    if "requires confirm_execution" in lowered or "confirmation" in lowered:
        return _diagnosis(
            "permission_required",
            "Execution requires explicit confirmation.",
            "Ask the user for approval, then retry with confirm_execution=true.",
        )
    if "unsupported runtime engine" in lowered:
        return _diagnosis(
            "runtime_not_supported",
            "The requested runtime backend is not supported.",
            "Use engine=local or engine=nextflow, or add a runtime backend before retrying.",
        )
    if error_type == "ABIJSONError" or "invalid json" in lowered:
        return _diagnosis(
            "parse_failed",
            "ABI could not parse a JSON config or result artifact.",
            "Check the referenced JSON file, regenerate the artifact if needed, then retry.",
            artifact=_extract_path(message),
        )
    if "missing execution plan" in lowered or "artifact" in lowered:
        return _diagnosis(
            "artifact_missing",
            "A required ABI result artifact is missing.",
            "Run plan or dry-run first, or pass the correct result_dir.",
            artifact=_extract_path(message),
        )
    if error_type in {"FileNotFoundError"} or _looks_like_missing_input(lowered):
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
        return _diagnosis(
            "invalid_sample_sheet",
            "The sample sheet is missing, malformed, or contains invalid rows.",
            "Fix the sample sheet columns and paths, then rerun plan or dry-run.",
            artifact=_extract_path(message),
        )
    if "config" in lowered or error_type in {"ConfigError"}:
        return _diagnosis(
            "invalid_config",
            "The ABI configuration could not be loaded or validated.",
            "Check the YAML file and plugin config schema, then retry.",
            artifact=_extract_path(message),
        )
    if "database" in lowered:
        return _diagnosis(
            "missing_database",
            "A required bioinformatics database is not configured or unavailable.",
            "Run the resource checker or configure a valid local database path.",
            artifact=_extract_path(message),
        )
    if "resource" in lowered or "not_configured" in lowered:
        return _diagnosis(
            "missing_resource",
            "A required resource is missing or still set to a placeholder.",
            "Configure the resource path or run a dry-run with --no-check-files if only planning.",
            artifact=_extract_path(message),
        )
    if "tool not found" in lowered or "executable" in lowered:
        return _diagnosis(
            "tool_not_found",
            "A registered external tool executable could not be found.",
            "Install the tool in the configured environment or update the tool registry.",
        )
    if "nonzero" in lowered or "return code" in lowered:
        return _diagnosis(
            "nonzero_exit",
            "An external command failed with a non-zero exit status.",
            (
                "Read provenance/step_logs for stderr and retry after fixing the "
                "tool input or environment."
            ),
        )
    if "parse" in lowered:
        return _diagnosis(
            "parse_failed",
            "ABI could not parse a tool output into standard tables.",
            "Check the raw output file and parser contract for the failing tool.",
            artifact=_extract_path(message),
        )
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
    hint = DiagnosticHint(
        severity="error",
        code=code,
        artifact=artifact,
        field=field,
        message=message,
        suggested_next_action=suggested_next_action,
    )
    return code, [hint.to_dict()]


def _looks_like_missing_input(message: str) -> bool:
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
    tokens = [token.strip(" ,;:'\"()[]{}") for token in message.split()]
    for token in reversed(tokens):
        if not token:
            continue
        if "/" in token or token.endswith((".yaml", ".yml", ".tsv", ".json", ".txt", ".fa")):
            return str(Path(token))
    return None
