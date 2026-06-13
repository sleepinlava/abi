"""Queue-backed HTTP job service for ABI agent calls.

The service intentionally uses only the Python standard library so it can run in
the Python 3.9 ABI environment. It is a thin transport around
``ABIAgentInterface``: queued jobs dispatch through the same tool boundary used
by CLI JSON, MCP, and function-calling integrations.
"""

from __future__ import annotations

import json
import queue
import threading
import time
import uuid
from dataclasses import dataclass, field
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional, Tuple
from urllib.parse import urlparse

from abi.agent import ABIAgentInterface
from abi.json_utils import loads_json

TERMINAL_STATUSES = {"succeeded", "failed", "cancelled"}


class JobServiceError(Exception):
    """Base class for job service errors."""

    status_code = HTTPStatus.BAD_REQUEST

    def __init__(self, message: str, *, payload: Optional[Mapping[str, Any]] = None) -> None:
        super().__init__(message)
        self.payload = dict(payload or {})


class JobNotFoundError(JobServiceError):
    """Raised when a requested job id is unknown."""

    status_code = HTTPStatus.NOT_FOUND


class ConfirmationRequiredError(JobServiceError):
    """Raised when an execution job is submitted without explicit approval."""

    status_code = HTTPStatus.CONFLICT


@dataclass
class JobRecord:
    job_id: str
    command: str
    arguments: Dict[str, Any]
    backend: str
    status: str = "queued"
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    error_type: Optional[str] = None
    cancel_requested: bool = False
    job_provenance_path: Optional[str] = None
    job_provenance_error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "command": self.command,
            "arguments": dict(self.arguments),
            "backend": self.backend,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "result": self.result,
            "error": self.error,
            "error_type": self.error_type,
            "cancel_requested": self.cancel_requested,
            "job_provenance_path": self.job_provenance_path,
            "job_provenance_error": self.job_provenance_error,
        }


class ABIJobService:
    """ABI job queue with optional JSON persistence."""

    def __init__(
        self,
        *,
        agent: Optional[ABIAgentInterface] = None,
        max_workers: int = 1,
        store_path: Optional[str | Path] = None,
    ) -> None:
        if max_workers < 1:
            raise ValueError("max_workers must be at least 1")
        self.agent = agent or ABIAgentInterface()
        self._jobs: Dict[str, JobRecord] = {}
        self._lock = threading.RLock()
        self._queue: "queue.Queue[str]" = queue.Queue()
        self._stop = threading.Event()
        self._store_path = Path(store_path) if store_path else None
        queued_jobs = self._load_store()
        self._workers = [
            threading.Thread(target=self._worker_loop, name=f"abi-job-worker-{index}", daemon=True)
            for index in range(max_workers)
        ]
        for worker in self._workers:
            worker.start()
        for job_id in queued_jobs:
            self._queue.put(job_id)

    def submit(self, payload: Mapping[str, Any]) -> Dict[str, Any]:
        """Validate and queue a job request."""
        command, arguments = _request_to_command(payload)
        backend = _backend_for(command, arguments)
        if _is_execution_command(command) and not bool(arguments.get("confirm_execution")):
            raise ConfirmationRequiredError(
                "Execution jobs require confirm_execution=true after user approval.",
                payload={
                    "status": "confirmation_required",
                    "command": _canonical_command(command),
                    "result": {
                        "analysis_type": arguments.get("analysis_type", "metagenomic_plasmid"),
                        "engine": _engine_for_backend(backend, arguments),
                        "backend": backend,
                        "message": "Re-submit with confirm_execution=true after user approval.",
                    },
                },
            )
        arguments = _normalize_backend_arguments(command, arguments, backend)
        job_id = uuid.uuid4().hex
        record = JobRecord(
            job_id=job_id,
            command=_canonical_command(command),
            arguments=arguments,
            backend=backend,
        )
        with self._lock:
            self._jobs[job_id] = record
            self._persist_locked()
        self._queue.put(job_id)
        return record.to_dict()

    def list_jobs(self) -> Dict[str, Any]:
        with self._lock:
            jobs = [record.to_dict() for record in self._jobs.values()]
        jobs.sort(key=lambda item: item["created_at"], reverse=True)
        return {"jobs": jobs, "count": len(jobs)}

    def get_job(self, job_id: str) -> Dict[str, Any]:
        return self._record(job_id).to_dict()

    def artifacts(self, job_id: str) -> Dict[str, Any]:
        record = self._record(job_id)
        artifacts: Dict[str, Any] = {
            "job_id": job_id,
            "status": record.status,
            "artifacts": {},
        }
        result = record.result or {}
        if isinstance(result.get("result"), Mapping):
            _collect_artifacts(result["result"], artifacts["artifacts"])
        if record.job_provenance_path:
            artifacts["artifacts"]["job_provenance"] = record.job_provenance_path
        return artifacts

    def cancel(self, job_id: str) -> Dict[str, Any]:
        with self._lock:
            record = self._jobs.get(job_id)
            if record is None:
                raise JobNotFoundError(f"Unknown ABI job: {job_id}")
            if record.status == "queued":
                record.status = "cancelled"
                record.finished_at = time.time()
            elif record.status not in TERMINAL_STATUSES:
                record.status = "cancel_requested"
                record.cancel_requested = True
            record.updated_at = time.time()
            self._write_job_provenance_locked(record)
            self._persist_locked()
            return record.to_dict()

    def shutdown(self, *, wait: bool = True) -> None:
        self._stop.set()
        if wait:
            for worker in self._workers:
                worker.join(timeout=2)

    def _record(self, job_id: str) -> JobRecord:
        with self._lock:
            record = self._jobs.get(job_id)
            if record is None:
                raise JobNotFoundError(f"Unknown ABI job: {job_id}")
            return record

    def _worker_loop(self) -> None:
        while not self._stop.is_set():
            try:
                job_id = self._queue.get(timeout=0.2)
            except queue.Empty:
                continue
            try:
                self._run_job(job_id)
            finally:
                self._queue.task_done()

    def _run_job(self, job_id: str) -> None:
        record = self._record(job_id)
        with self._lock:
            if record.status == "cancelled":
                return
            record.status = "running"
            record.started_at = time.time()
            record.updated_at = record.started_at
            self._persist_locked()
        try:
            envelope = loads_json(
                self.agent.dispatch(record.command, record.arguments),
                label=f"agent response for {record.command}",
            )
            with self._lock:
                record.result = envelope
                if envelope.get("status") == "success":
                    record.status = "succeeded"
                else:
                    record.status = "failed"
                    record.error = str(envelope.get("error") or envelope.get("status"))
                    record.error_type = str(envelope.get("error_type") or envelope.get("status"))
                self._persist_locked()
        except MemoryError:
            raise
        except Exception as exc:  # pragma: no cover - defensive around user plugins
            with self._lock:
                record.status = "failed"
                record.error = str(exc)
                record.error_type = exc.__class__.__name__
                record.result = {
                    "status": "error",
                    "command": record.command,
                    "error": str(exc),
                    "error_type": exc.__class__.__name__,
                }
                self._persist_locked()
        finally:
            with self._lock:
                record.finished_at = time.time()
                record.updated_at = record.finished_at
                self._write_job_provenance_locked(record)
                self._persist_locked()

    def _load_store(self) -> list[str]:
        if self._store_path is None or not self._store_path.exists():
            return []
        try:
            data = loads_json(
                self._store_path.read_text(encoding="utf-8"),
                label=f"ABI job store {self._store_path}",
            )
        except Exception as exc:
            raise JobServiceError(
                f"Could not load ABI job store {self._store_path}: {exc}"
            ) from exc
        if not isinstance(data, Mapping):
            raise JobServiceError(f"ABI job store must contain a JSON object: {self._store_path}")
        queued_jobs: list[str] = []
        for item in data.get("jobs", []):
            if not isinstance(item, Mapping):
                continue
            record = _record_from_mapping(item)
            if record.status == "queued":
                queued_jobs.append(record.job_id)
            elif record.status in {"running", "cancel_requested"}:
                record.status = "failed"
                record.error = "Job did not complete before the Job Service restarted."
                record.error_type = "service_restart"
                record.finished_at = time.time()
                record.updated_at = record.finished_at
            self._jobs[record.job_id] = record
        self._persist_locked()
        return queued_jobs

    def _persist_locked(self) -> None:
        if self._store_path is None:
            return
        self._store_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "updated_at": time.time(),
            "jobs": [record.to_dict() for record in self._jobs.values()],
        }
        tmp_path = self._store_path.with_name(f"{self._store_path.name}.tmp")
        tmp_path.write_text(json.dumps(_jsonable(payload), indent=2) + "\n", encoding="utf-8")
        tmp_path.replace(self._store_path)

    def _write_job_provenance_locked(self, record: JobRecord) -> None:
        root = _record_result_root(record)
        if root is None:
            return
        provenance = root / "provenance"
        path = provenance / "job.json"
        try:
            provenance.mkdir(parents=True, exist_ok=True)
            payload = {
                "schema_version": "abi.job.provenance.v1",
                "written_at": time.time(),
                "job": record.to_dict(),
            }
            tmp_path = path.with_name(f"{path.name}.tmp")
            tmp_path.write_text(json.dumps(_jsonable(payload), indent=2) + "\n", encoding="utf-8")
            tmp_path.replace(path)
            record.job_provenance_path = str(path)
            record.job_provenance_error = None
        except OSError as exc:
            record.job_provenance_error = str(exc)


def create_http_server(
    service: ABIJobService,
    *,
    host: str = "127.0.0.1",
    port: int = 18791,
) -> ThreadingHTTPServer:
    """Create a stdlib HTTP server bound to an ``ABIJobService`` instance."""

    class Handler(BaseHTTPRequestHandler):
        server_version = "ABIJobService/0.1"

        def do_GET(self) -> None:  # noqa: N802 - stdlib hook name
            try:
                status, payload = _handle_get(service, self.path)
                self._send_json(status, payload)
            except JobServiceError as exc:
                self._send_json(exc.status_code, _error_payload(exc))
            except MemoryError:
                raise
            except Exception as exc:  # pragma: no cover - defensive HTTP boundary
                self._send_json(
                    HTTPStatus.INTERNAL_SERVER_ERROR,
                    {
                        "status": "error",
                        "error": str(exc),
                        "error_type": exc.__class__.__name__,
                    },
                )

        def do_POST(self) -> None:  # noqa: N802 - stdlib hook name
            try:
                body = self._read_json()
                status, payload = _handle_post(service, self.path, body)
                self._send_json(status, payload)
            except JobServiceError as exc:
                self._send_json(exc.status_code, _error_payload(exc))
            except json.JSONDecodeError as exc:
                self._send_json(
                    HTTPStatus.BAD_REQUEST,
                    {"status": "error", "error": f"Invalid JSON: {exc}"},
                )
            except MemoryError:
                raise
            except Exception as exc:  # pragma: no cover - defensive HTTP boundary
                self._send_json(
                    HTTPStatus.INTERNAL_SERVER_ERROR,
                    {
                        "status": "error",
                        "error": str(exc),
                        "error_type": exc.__class__.__name__,
                    },
                )

        def log_message(self, format: str, *args: Any) -> None:
            return

        def _read_json(self) -> Dict[str, Any]:
            length = int(self.headers.get("Content-Length", "0"))
            if length == 0:
                return {}
            raw = self.rfile.read(length).decode("utf-8")
            data = json.loads(raw)
            if not isinstance(data, dict):
                raise JobServiceError("Request body must be a JSON object.")
            return data

        def _send_json(self, status: int, payload: Mapping[str, Any]) -> None:
            data = json.dumps(_jsonable(payload), indent=2, ensure_ascii=False).encode("utf-8")
            self.send_response(int(status))
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    return ThreadingHTTPServer((host, port), Handler)


def serve(
    *,
    host: str = "127.0.0.1",
    port: int = 18791,
    max_workers: int = 1,
    store_path: Optional[str | Path] = None,
) -> None:
    """Run the ABI Job Service until interrupted."""

    service = ABIJobService(max_workers=max_workers, store_path=store_path)
    server = create_http_server(service, host=host, port=port)
    try:
        server.serve_forever()
    finally:
        server.server_close()
        service.shutdown(wait=False)


def _handle_get(service: ABIJobService, path: str) -> Tuple[int, Mapping[str, Any]]:
    parts = _path_parts(path)
    if parts == ["health"]:
        return HTTPStatus.OK, {"status": "ok", "service": "abi-job-service"}
    if parts == ["jobs"]:
        return HTTPStatus.OK, service.list_jobs()
    if len(parts) == 2 and parts[0] == "jobs":
        return HTTPStatus.OK, service.get_job(parts[1])
    if len(parts) == 3 and parts[0] == "jobs" and parts[2] == "artifacts":
        return HTTPStatus.OK, service.artifacts(parts[1])
    raise JobServiceError(f"Unknown endpoint: GET /{'/'.join(parts)}", payload={"status": "error"})


def _handle_post(
    service: ABIJobService,
    path: str,
    body: Mapping[str, Any],
) -> Tuple[int, Mapping[str, Any]]:
    parts = _path_parts(path)
    if parts == ["jobs"]:
        record = service.submit(body)
        return HTTPStatus.ACCEPTED, {"status": "accepted", "job": record}
    if len(parts) == 3 and parts[0] == "jobs" and parts[2] == "cancel":
        return HTTPStatus.OK, {"status": "success", "job": service.cancel(parts[1])}
    raise JobServiceError(f"Unknown endpoint: POST /{'/'.join(parts)}", payload={"status": "error"})


def _request_to_command(payload: Mapping[str, Any]) -> Tuple[str, Dict[str, Any]]:
    command = str(payload.get("command") or payload.get("tool") or "abi_run")
    raw_arguments = payload.get("arguments")
    if raw_arguments is None:
        arguments = {
            key: value
            for key, value in payload.items()
            if key not in {"command", "tool", "arguments", "backend"}
        }
    elif isinstance(raw_arguments, Mapping):
        arguments = dict(raw_arguments)
    else:
        raise JobServiceError("arguments must be a JSON object.")
    if "backend" in payload and "backend" not in arguments:
        arguments["backend"] = payload["backend"]
    return command, arguments


def _backend_for(command: str, arguments: Mapping[str, Any]) -> str:
    if not _is_execution_command(command):
        return "service"
    backend = str(arguments.get("backend") or arguments.get("engine") or "local").lower().strip()
    if backend not in {"local", "nextflow", "hpc", "cloud"}:
        raise JobServiceError(
            f"Unsupported ABI job backend: {backend}. Expected local, nextflow, hpc, or cloud."
        )
    return backend


def _normalize_backend_arguments(
    command: str,
    arguments: Mapping[str, Any],
    backend: str,
) -> Dict[str, Any]:
    normalized = dict(arguments)
    normalized.pop("backend", None)
    if not _is_execution_command(command):
        return normalized
    normalized["engine"] = _engine_for_backend(backend, normalized)
    if backend == "hpc":
        hpc_executor = normalized.pop("hpc_executor", None)
        hpc_profile = normalized.pop("hpc_profile", None)
        if "executor" not in normalized:
            normalized["executor"] = hpc_executor or "slurm"
        if hpc_profile and "nextflow_profile" not in normalized:
            normalized["nextflow_profile"] = hpc_profile
    elif backend == "cloud":
        cloud_executor = normalized.pop("cloud_executor", None)
        cloud_profile = normalized.pop("cloud_profile", None)
        if cloud_executor and "executor" not in normalized:
            normalized["executor"] = cloud_executor
        if cloud_profile and "nextflow_profile" not in normalized:
            normalized["nextflow_profile"] = cloud_profile
    return normalized


def _engine_for_backend(backend: str, arguments: Mapping[str, Any]) -> str:
    if backend in {"hpc", "cloud"}:
        return "nextflow"
    return str(arguments.get("engine") or backend or "local")


def _is_execution_command(command: str) -> bool:
    return _canonical_command(command) == "abi_run"


def _canonical_command(command: str) -> str:
    aliases = {
        "run": "abi_run",
        "abi_run": "abi_run",
        "plan": "abi_plan",
        "abi_plan": "abi_plan",
        "dry_run": "abi_dry_run",
        "dry-run": "abi_dry_run",
        "abi_dry_run": "abi_dry_run",
        "inspect": "abi_inspect",
        "abi_inspect": "abi_inspect",
        "report": "abi_report",
        "abi_report": "abi_report",
        "list": "abi_list_types",
        "list-types": "abi_list_types",
        "list_types": "abi_list_types",
        "abi_list": "abi_list_types",
        "abi_list_types": "abi_list_types",
        "export_nextflow": "abi_export_nextflow",
        "export-nextflow": "abi_export_nextflow",
        "abi_export_nextflow": "abi_export_nextflow",
        "export_agent_context": "abi_export_agent_context",
        "export-agent-context": "abi_export_agent_context",
        "abi_export_agent_context": "abi_export_agent_context",
        "doctor_agent": "abi_doctor_agent",
        "doctor-agent": "abi_doctor_agent",
        "abi_doctor_agent": "abi_doctor_agent",
        "validate_result": "abi_validate_result",
        "validate-result": "abi_validate_result",
        "abi_validate_result": "abi_validate_result",
        "autoplasm_validate_result": "autoplasm_validate_result",
    }
    key = str(command).strip()
    if key not in aliases:
        raise JobServiceError(f"Unknown ABI job command: {command}")
    return aliases[key]


def _record_from_mapping(data: Mapping[str, Any]) -> JobRecord:
    return JobRecord(
        job_id=str(data["job_id"]),
        command=str(data["command"]),
        arguments=dict(data.get("arguments", {})),
        backend=str(data.get("backend", "service")),
        status=str(data.get("status", "queued")),
        created_at=float(data.get("created_at", time.time())),
        updated_at=float(data.get("updated_at", time.time())),
        started_at=_optional_float(data.get("started_at")),
        finished_at=_optional_float(data.get("finished_at")),
        result=(dict(data["result"]) if isinstance(data.get("result"), Mapping) else None),
        error=str(data["error"]) if data.get("error") is not None else None,
        error_type=(str(data["error_type"]) if data.get("error_type") is not None else None),
        cancel_requested=bool(data.get("cancel_requested", False)),
        job_provenance_path=(
            str(data["job_provenance_path"])
            if data.get("job_provenance_path") is not None
            else None
        ),
        job_provenance_error=(
            str(data["job_provenance_error"])
            if data.get("job_provenance_error") is not None
            else None
        ),
    )


def _optional_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    return float(value)


def _collect_artifacts(result: Mapping[str, Any], artifacts: Dict[str, Any]) -> None:
    for key in ("outdir", "plan_path", "result_dir", "workflow"):
        if key in result:
            artifacts[key] = result[key]
    if "outdir" in artifacts:
        _collect_outdir_artifacts(str(artifacts["outdir"]), artifacts)
    if "written_files" in result and isinstance(result["written_files"], Iterable):
        artifacts["written_files"] = list(result["written_files"])
    outputs = result.get("outputs")
    if isinstance(outputs, Mapping):
        artifacts["outputs"] = dict(outputs)
        for key in (
            "report",
            "report_html",
            "summary",
            "commands",
            "resources",
            "workflow",
        ):
            if key in outputs:
                artifacts[key] = outputs[key]


def _collect_outdir_artifacts(outdir: str, artifacts: Dict[str, Any]) -> None:
    root = Path(outdir)
    artifacts.setdefault("outdir", str(root))
    artifacts.setdefault("execution_plan", str(root / "execution_plan.json"))
    artifacts.setdefault("provenance_dir", str(root / "provenance"))
    artifacts.setdefault("job_provenance", str(root / "provenance" / "job.json"))
    artifacts.setdefault("commands", str(root / "provenance" / "commands.tsv"))
    artifacts.setdefault("resolved_inputs", str(root / "provenance" / "resolved_inputs.tsv"))
    artifacts.setdefault("tool_versions", str(root / "provenance" / "tool_versions.tsv"))
    artifacts.setdefault("resources", str(root / "provenance" / "resources.json"))
    artifacts.setdefault("tables_dir", str(root / "tables"))
    artifacts.setdefault("report_dir", str(root / "report"))
    artifacts.setdefault("report_md", str(root / "report" / "report.md"))
    artifacts.setdefault("report_html", str(root / "report" / "report.html"))


def _record_result_root(record: JobRecord) -> Optional[Path]:
    result = record.result or {}
    payload = result.get("result")
    if isinstance(payload, Mapping):
        for key in ("outdir", "result_dir"):
            value = payload.get(key)
            if value not in (None, ""):
                return Path(str(value))
        outputs = payload.get("outputs")
        if isinstance(outputs, Mapping):
            for key in ("plan", "report", "report_html", "commands", "summary"):
                value = outputs.get(key)
                if value not in (None, ""):
                    return _infer_result_root_from_artifact(Path(str(value)))
    for key in ("outdir", "result_dir"):
        value = record.arguments.get(key)
        if value not in (None, ""):
            return Path(str(value))
    return None


def _infer_result_root_from_artifact(path: Path) -> Path:
    parts = path.parts
    if "provenance" in parts:
        return Path(*parts[: parts.index("provenance")])
    if "report" in parts:
        return Path(*parts[: parts.index("report")])
    if path.name == "execution_plan.json":
        return path.parent
    return path.parent


def _path_parts(path: str) -> list[str]:
    parsed = urlparse(path)
    return [part for part in parsed.path.split("/") if part]


def _error_payload(exc: JobServiceError) -> Dict[str, Any]:
    if exc.payload:
        payload = dict(exc.payload)
        payload.setdefault("error", str(exc))
        return payload
    return {"status": "error", "error": str(exc), "error_type": exc.__class__.__name__}


def _jsonable(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, Iterable) and not isinstance(value, (str, bytes, bytearray)):
        return [_jsonable(item) for item in value]
    return value
