"""Provenance logging and progress recording for ABI pipeline execution.

Writes the stable provenance artefacts defined by the ABI spec:
  provenance/
    commands.tsv
    resolved_inputs.tsv
    tool_versions.tsv
    resources.json
    environment.yml
    run_summary.json
    progress.json
    progress.jsonl
    step_logs/
"""

from __future__ import annotations

import json
import shlex
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping

from abi.filesystem import ensure_directory

__all__ = [
    "PipelineProgressRecorder",
    "RunLogger",
    "write_commands_tsv",
    "write_minimal_progress_artifacts",
    "write_resolved_inputs_tsv",
    "write_tool_versions",
]

# ── RunLogger ──────────────────────────────────────────────────────────


class RunLogger:
    """Structured JSON-line event logger for a single pipeline run."""

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


# ── TSV provenance writers ─────────────────────────────────────────────


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


# ── PipelineProgressRecorder ───────────────────────────────────────────


class PipelineProgressRecorder:
    """Thread-safe writer for live pipeline progress.

    The JSONL stream is append-only for auditability. The JSON snapshot is for
    dashboards and other polling clients that need the current state quickly.
    """

    def __init__(self, provenance_dir: str | Path) -> None:
        self.provenance_dir = ensure_directory(provenance_dir, label="Provenance directory")
        self.events_path = self.provenance_dir / "progress.jsonl"
        self.snapshot_path = self.provenance_dir / "progress.json"
        self._lock = threading.Lock()
        self._snapshot: Dict[str, Any] = {}

    @property
    def paths(self) -> Dict[str, Path]:
        return {"events": self.events_path, "snapshot": self.snapshot_path}

    def start_run(
        self,
        plan: Any,
        *,
        dry_run: bool,
        parallel: bool,
        workers: int,
    ) -> None:
        steps = [
            {
                "step_id": step.step_id,
                "sample_id": step.sample_id or "",
                "step_name": step.step_name,
                "tool_id": step.tool_id,
                "category": step.category,
                "status": "pending",
                "reason": step.reason or "",
                "return_code": "",
                "parsed_status": "",
                "standard_tables": "",
                "started_at": "",
                "finished_at": "",
            }
            for step in plan.steps
        ]
        sample_status = {
            sample.sample_id: {
                "sample_id": sample.sample_id,
                "platform": sample.platform,
                "status": "pending",
                "current_step_id": "",
                "completed_step_count": 0,
                "failed_step_count": 0,
            }
            for sample in plan.samples
        }
        self._snapshot = {
            "project_name": plan.project_name,
            "status": "running",
            "dry_run": dry_run,
            "parallel": parallel,
            "workers": workers,
            "started_at": _timestamp(),
            "finished_at": "",
            "total_step_count": len(plan.steps),
            "completed_step_count": 0,
            "failed_step_count": 0,
            "running_step_count": 0,
            "current_steps": [],
            "samples": sample_status,
            "steps": steps,
            "last_event": {},
        }
        self.record("run_started", {"dry_run": dry_run, "parallel": parallel, "workers": workers})

    def step_started(self, step: Any) -> None:
        self.record("step_started", _step_payload(step))

    def step_completed(
        self,
        step: Any,
        *,
        status: str,
        reason: str = "",
        return_code: int | str = "",
        parsed_status: str = "",
        standard_tables: str = "",
    ) -> None:
        self.record(
            "step_completed" if status != "failed" else "step_failed",
            {
                **_step_payload(step),
                "status": status,
                "reason": reason,
                "return_code": return_code,
                "parsed_status": parsed_status,
                "standard_tables": standard_tables,
            },
        )

    def finish_run(self, *, status: str) -> None:
        self.record("run_completed", {"status": status})

    def record(self, event: str, payload: Mapping[str, Any]) -> None:
        timestamp = _timestamp()
        record = {
            "timestamp": timestamp,
            "event": event,
            "payload": dict(payload),
        }
        with self._lock:
            self._apply_event(event, payload, timestamp)
            with self.events_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
            self._snapshot["last_event"] = record
            self._write_snapshot()

    def _apply_event(self, event: str, payload: Mapping[str, Any], timestamp: str) -> None:
        if event == "run_completed":
            self._snapshot["status"] = str(payload.get("status", "completed"))
            self._snapshot["finished_at"] = timestamp
            self._snapshot["running_step_count"] = 0
            self._snapshot["current_steps"] = []
            for sample in self._snapshot.get("samples", {}).values():
                if sample.get("status") == "running":
                    sample["status"] = "completed"
                    sample["current_step_id"] = ""
            return
        if event not in {"step_started", "step_completed", "step_failed"}:
            return

        step_id = str(payload.get("step_id", ""))
        sample_id = str(payload.get("sample_id", ""))
        step_state = self._step_state(step_id)
        if not step_state:
            return

        if event == "step_started":
            step_state["status"] = "running"
            step_state["started_at"] = timestamp
            current_steps = list(self._snapshot.get("current_steps", []))
            if step_id not in current_steps:
                current_steps.append(step_id)
            self._snapshot["current_steps"] = current_steps
            self._snapshot["running_step_count"] = len(current_steps)
            if sample_id and sample_id in self._snapshot.get("samples", {}):
                sample = self._snapshot["samples"][sample_id]
                sample["status"] = "running"
                sample["current_step_id"] = step_id
            return

        status = str(payload.get("status", "success"))
        step_state["status"] = status
        step_state["reason"] = str(payload.get("reason", ""))
        step_state["return_code"] = payload.get("return_code", "")
        step_state["parsed_status"] = str(payload.get("parsed_status", ""))
        step_state["standard_tables"] = str(payload.get("standard_tables", ""))
        step_state["finished_at"] = timestamp

        current_steps = [
            current for current in self._snapshot.get("current_steps", []) if current != step_id
        ]
        self._snapshot["current_steps"] = current_steps
        self._snapshot["running_step_count"] = len(current_steps)
        self._snapshot["completed_step_count"] = (
            int(self._snapshot.get("completed_step_count", 0)) + 1
        )
        if status == "failed":
            self._snapshot["failed_step_count"] = (
                int(self._snapshot.get("failed_step_count", 0)) + 1
            )
            self._snapshot["status"] = "failed"
        if sample_id and sample_id in self._snapshot.get("samples", {}):
            sample = self._snapshot["samples"][sample_id]
            sample["completed_step_count"] = int(sample.get("completed_step_count", 0)) + 1
            if status == "failed":
                sample["failed_step_count"] = int(sample.get("failed_step_count", 0)) + 1
                sample["status"] = "failed"
            elif sample.get("status") == "running":
                sample["current_step_id"] = ""

    def _step_state(self, step_id: str) -> Dict[str, Any] | None:
        for step in self._snapshot.get("steps", []):
            if isinstance(step, dict) and step.get("step_id") == step_id:
                return step
        return None

    def _write_snapshot(self) -> None:
        tmp_path = self.snapshot_path.with_suffix(".json.tmp")
        tmp_path.write_text(
            json.dumps(self._snapshot, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        tmp_path.replace(self.snapshot_path)


def write_minimal_progress_artifacts(
    provenance_dir: str | Path,
    plan: Any,
    *,
    dry_run: bool,
    parallel: bool,
    workers: int,
    status: str,
    command_rows: Iterable[Mapping[str, Any]],
) -> Dict[str, Path]:
    """Write stable progress artifacts when live progress recording is disabled."""
    provenance = ensure_directory(provenance_dir, label="Provenance directory")
    events_path = provenance / "progress.jsonl"
    snapshot_path = provenance / "progress.json"
    rows_by_step = {
        str(row.get("step_id", "")): dict(row)
        for row in command_rows
        if str(row.get("step_id", ""))
    }
    started_at = _timestamp()
    finished_at = _timestamp()
    total_step_count = len(getattr(plan, "steps", []))
    completed_step_count = len(rows_by_step)
    failed_step_count = sum(
        1 for row in rows_by_step.values() if str(row.get("status", "")) == "failed"
    )
    started_event = {
        "timestamp": started_at,
        "event": "run_started",
        "payload": {
            "dry_run": dry_run,
            "parallel": parallel,
            "workers": workers,
            "record_progress": False,
        },
    }
    completed_event = {
        "timestamp": finished_at,
        "event": "run_completed",
        "payload": {
            "status": status,
            "record_progress": False,
            "completed_step_count": completed_step_count,
            "failed_step_count": failed_step_count,
            "total_step_count": total_step_count,
        },
    }
    events_path.write_text(
        "\n".join(
            json.dumps(event, ensure_ascii=False, sort_keys=True)
            for event in (started_event, completed_event)
        )
        + "\n",
        encoding="utf-8",
    )

    snapshot = {
        "project_name": getattr(plan, "project_name", ""),
        "status": status,
        "dry_run": dry_run,
        "parallel": parallel,
        "workers": workers,
        "record_progress": False,
        "started_at": started_at,
        "finished_at": finished_at,
        "total_step_count": total_step_count,
        "completed_step_count": completed_step_count,
        "failed_step_count": failed_step_count,
        "running_step_count": 0,
        "current_steps": [],
        "samples": _minimal_sample_status(plan, rows_by_step),
        "steps": _minimal_step_status(plan, rows_by_step, finished_at),
        "last_event": completed_event,
    }
    snapshot_path.write_text(
        json.dumps(snapshot, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return {"events": events_path, "snapshot": snapshot_path}


# ── Internal helpers ───────────────────────────────────────────────────


def _step_payload(step: Any) -> Dict[str, Any]:
    return {
        "step_id": step.step_id,
        "sample_id": step.sample_id or "",
        "step_name": step.step_name,
        "tool_id": step.tool_id,
        "category": step.category,
    }


def _minimal_sample_status(
    plan: Any, rows_by_step: Mapping[str, Mapping[str, Any]]
) -> Dict[str, Any]:
    samples: Dict[str, Any] = {}
    for sample in getattr(plan, "samples", []):
        sample_id = str(getattr(sample, "sample_id", ""))
        if not sample_id:
            continue
        sample_rows = [
            row for row in rows_by_step.values() if str(row.get("sample_id", "")) == sample_id
        ]
        failed_count = sum(1 for row in sample_rows if str(row.get("status", "")) == "failed")
        samples[sample_id] = {
            "sample_id": sample_id,
            "platform": getattr(sample, "platform", ""),
            "status": ("failed" if failed_count else ("completed" if sample_rows else "pending")),
            "current_step_id": "",
            "completed_step_count": len(sample_rows),
            "failed_step_count": failed_count,
        }
    return samples


def _minimal_step_status(
    plan: Any,
    rows_by_step: Mapping[str, Mapping[str, Any]],
    finished_at: str,
) -> list[Dict[str, Any]]:
    steps = []
    for step in getattr(plan, "steps", []):
        row = rows_by_step.get(str(getattr(step, "step_id", "")), {})
        row_status = str(row.get("status", "pending"))
        steps.append(
            {
                "step_id": getattr(step, "step_id", ""),
                "sample_id": getattr(step, "sample_id", "") or "",
                "step_name": getattr(step, "step_name", ""),
                "tool_id": getattr(step, "tool_id", ""),
                "category": getattr(step, "category", ""),
                "status": row_status,
                "reason": str(row.get("reason", getattr(step, "reason", "") or "")),
                "return_code": row.get("return_code", ""),
                "parsed_status": str(row.get("parsed_status", "")),
                "standard_tables": str(row.get("standard_tables", "")),
                "started_at": "",
                "finished_at": finished_at if row else "",
            }
        )
    return steps


def _tsv_value(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def _display_command(command: Iterable[str]) -> str:
    return " ".join(">" if token == ">" else shlex.quote(str(token)) for token in command)


def _timestamp() -> str:
    return datetime.now().isoformat(timespec="seconds")
