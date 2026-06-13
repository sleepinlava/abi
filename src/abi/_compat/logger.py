"""Structured logging and provenance helpers."""

from __future__ import annotations

import json
import shlex
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping

from abi.filesystem import ensure_directory


class RunLogger:
    def __init__(self, log_dir: str | Path) -> None:
        self.log_dir = ensure_directory(log_dir, label="Log directory")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_file = self.log_dir / f"log_abi_{timestamp}.log"

    def log_event(self, event: str, payload: Mapping[str, Any]) -> None:
        record = {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "event": event,
            "payload": dict(payload),
        }
        with self.log_file.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")

    def log_step(
        self,
        step: Any,
        *,
        command: Iterable[str] | str,
        status: str,
        error_message: str | None = None,
    ) -> None:
        command_text = command if isinstance(command, str) else _display_command(command)
        payload: Dict[str, Any] = {
            "sample_id": getattr(step, "sample_id", None),
            "step_name": getattr(step, "step_name", None),
            "tool_name": getattr(step, "tool_id", None),
            "command": command_text,
            "input_files": getattr(step, "inputs", {}),
            "output_files": getattr(step, "outputs", {}),
            "parameters": getattr(step, "params", {}),
            "status": status,
            "duration": 0,
            "error_message": error_message,
        }
        self.log_event("pipeline_step", payload)


def write_commands_tsv(rows: Iterable[Mapping[str, Any]], path: str | Path) -> Path:
    commands_path = Path(path)
    commands_path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "step_id",
        "sample_id",
        "step_name",
        "tool_id",
        "category",
        "command",
        "status",
        "return_code",
        "remote_scheduler_job_id",
        "reason",
        "parsed_status",
        "standard_tables",
    ]
    with commands_path.open("w", encoding="utf-8") as handle:
        handle.write("\t".join(fields) + "\n")
        for row in rows:
            handle.write("\t".join(_tsv_value(row.get(field, "")) for field in fields) + "\n")
    return commands_path


def write_tool_versions(rows: Iterable[Mapping[str, Any]], path: str | Path) -> Path:
    versions_path = Path(path)
    versions_path.parent.mkdir(parents=True, exist_ok=True)
    fields = ["tool_id", "executable", "env_name", "version", "status"]
    with versions_path.open("w", encoding="utf-8") as handle:
        handle.write("\t".join(fields) + "\n")
        for row in rows:
            handle.write("\t".join(_tsv_value(row.get(field, "")) for field in fields) + "\n")
    return versions_path


def write_resolved_inputs_tsv(rows: Iterable[Mapping[str, Any]], path: str | Path) -> Path:
    inputs_path = Path(path)
    inputs_path.parent.mkdir(parents=True, exist_ok=True)
    fields = ["step_id", "tool_id", "sample_id", "input_name", "path", "exists", "source"]
    with inputs_path.open("w", encoding="utf-8") as handle:
        handle.write("\t".join(fields) + "\n")
        for row in rows:
            handle.write("\t".join(_tsv_value(row.get(field, "")) for field in fields) + "\n")
    return inputs_path


def _tsv_value(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def _display_command(command: Iterable[str]) -> str:
    return " ".join(">" if token == ">" else shlex.quote(token) for token in command)
