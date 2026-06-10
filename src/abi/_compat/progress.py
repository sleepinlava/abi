"""Progress event recording for pipeline execution.

Copied from autoplasm.progress with import path adjustments.
Uses Any for plan/step types to avoid circular dependencies.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Mapping

from abi._compat.filesystem import ensure_directory


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
            if step.get("step_id") == step_id:
                return step
        return None

    def _write_snapshot(self) -> None:
        tmp_path = self.snapshot_path.with_suffix(".json.tmp")
        tmp_path.write_text(
            json.dumps(self._snapshot, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        tmp_path.replace(self.snapshot_path)


def _step_payload(step: Any) -> Dict[str, Any]:
    return {
        "step_id": step.step_id,
        "sample_id": step.sample_id or "",
        "step_name": step.step_name,
        "tool_id": step.tool_id,
        "category": step.category,
    }


def _timestamp() -> str:
    return datetime.now().isoformat(timespec="seconds")
