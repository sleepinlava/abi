"""Queue-backed HTTP job service for ABI agent calls.

Architecture overview / 架构概述
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
The ``ABIJobService`` is a **multi-worker, queue-backed** HTTP service that
accepts, schedules, executes, and monitors ABI agent jobs.  It is designed to
run inside the same Python 3.10 environment as the ABI agent and relies on
**only the standard library** for HTTP, threading, and subprocess management.

``ABIJobService`` 是一个 **多 worker、队列驱动** 的 HTTP 服务，用于接受、调度、
执行和监控 ABI agent 作业。它设计为在与 ABI agent 相同的 Python 3.10 环境中运行，
并仅依赖标准库进行 HTTP、线程和子进程管理。

Key components / 关键组件
~~~~~~~~~~~~~~~~~~~~~~~~~
* **JobRecord** -- 17-field dataclass tracking every job from submission to
  completion, including the worker PID and remote scheduler job ID.
* **In-process workers** -- each worker thread calls ``agent.dispatch()``
  directly (same process, same memory space).
* **Subprocess workers** (``subprocess_workers=True``) -- each worker spawns
  ``abi dispatch`` as a subprocess so cancel can send SIGTERM for true
  force-kill.
* **Persistence** -- JSON job store with atomic ``.tmp`` writes to survive
  restarts.
* **HTTP API** -- stdlib ``ThreadingHTTPServer`` serving:

  ==============  ======  ===========================================
  Endpoint        Method  Purpose
  ==============  ======  ===========================================
  /health         GET     Liveness check / 存活检查
  /jobs           GET     List all jobs (newest first) / 列出所有作业
  /jobs           POST    Submit a new job / 提交新作业
  /jobs/{id}      GET     Get job details / 获取作业详情
  /jobs/{id}/artifacts  GET  Collect output artifacts / 收集输出产物
  /jobs/{id}/cancel     POST Cancel a running job / 取消运行中的作业
  ==============  ======  ===========================================

Execution modes / 执行模式
~~~~~~~~~~~~~~~~~~~~~~~~~~
1. **In-process** (default): ``ABIAgentInterface.dispatch()`` is called
   directly inside the worker thread.  Fast, but cancel is cooperative
   (the worker checks ``cancel_requested`` between steps).

2. **Subprocess** (``subprocess_workers=True``): ``abi dispatch`` runs in
   a child process.  Cancel sends ``SIGTERM`` with a 3-second grace period
   before escalating to ``SIGKILL`` for true force-kill semantics.

Force-kill mechanism / 强制终止机制
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
When ``subprocess_workers=True`` and a cancel is requested::

    1. SIGTERM  ──→  3-second grace period
    2. SIGKILL  ──→  unconditional kill

This two-phase escalation gives the process a chance to clean up
(e.g. flush logs, remove temp files) before being forcibly killed.

Persistence & restart / 持久化与重启
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
* Jobs are written to a JSON file (``store_path``) via atomic ``.tmp``
  writes: write to ``.tmp``, then ``os.replace()`` so the store is never
  half-written.
* On restart, jobs in ``"queued"`` state are re-enqueued; jobs in
  ``"running"`` or ``"cancel_requested"`` are marked ``"failed"`` with
  ``error_type="service_restart"``.

Data flow / 数据流
~~~~~~~~~~~~~~~~~~
::

   Client ──POST /jobs──→ submit() ──→ queue.put() ──→ worker_loop ──→ _run_job
                                                                          │
                              ┌─ in-process ── agent.dispatch()           │
                              │                                           │
                              └─ subprocess ── abi dispatch (Popen)       │
                                                                          │
   Client ←──GET /jobs/{id}── get_job() ←── JobRecord ←── _persist_locked()

The service intentionally uses only the Python standard library so it can run in
the Python 3.10 ABI environment.  It is a thin transport around
``ABIAgentInterface``: queued jobs dispatch through the same tool boundary used
by CLI JSON, MCP, and function-calling integrations.

该服务有意仅使用 Python 标准库，以便在 Python 3.10 ABI 环境中运行。
它是 ``ABIAgentInterface`` 的一个薄传输层：排队作业通过与 CLI JSON、MCP
和函数调用集成相同的工具边界进行调度。
"""

from __future__ import annotations

import json
import os
import queue
import signal
import subprocess
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
    """Base exception for all job-service errors.

    Carries an HTTP status code so the HTTP handler can respond without
    maintaining a separate error-to-status mapping.

    所有作业服务错误的基础异常。携带 HTTP 状态码，使 HTTP 处理器无需维护
    单独的错误到状态码映射。
    """

    status_code = HTTPStatus.BAD_REQUEST

    def __init__(self, message: str, *, payload: Optional[Mapping[str, Any]] = None) -> None:
        super().__init__(message)
        self.payload = dict(payload or {})


class JobNotFoundError(JobServiceError):
    """Raised when a requested job ID is unknown in the job store.

    当请求的作业 ID 在作业存储中不存在时抛出。
    """

    status_code = HTTPStatus.NOT_FOUND


class UnauthorizedError(JobServiceError):
    """Raised when a request lacks valid Authorization credentials (S7 fix).

    当请求缺少有效 Authorization 凭证时抛出。
    """

    status_code = HTTPStatus.UNAUTHORIZED


class ConfirmationRequiredError(JobServiceError):
    """Raised when an execution job is submitted without ``confirm_execution=true``.

    This is a safety gate: the caller must explicitly acknowledge that they
    want to run real computation (not a dry-run or plan).  The error payload
    includes a ``status: "confirmation_required"`` marker so the client can
    re-submit with the confirmation flag.

    当执行作业提交时未带 ``confirm_execution=true`` 时抛出。这是一个安全
    关卡：调用者必须明确确认要运行真实计算（而非演习或计划）。错误载荷包含
    ``status: "confirmation_required"`` 标记，客户端可据此重新提交并带上确认标志。
    """

    status_code = HTTPStatus.CONFLICT


@dataclass
class JobRecord:
    """Full lifecycle record for a single ABI agent job.

    Design rationale / 设计理由
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~
    * 17 fields capture the complete lifecycle: submission, queuing,
      execution, completion/failure/cancellation, and provenance.
    * ``worker_pid`` and ``remote_scheduler_job_id`` are only populated
      during subprocess-mode execution -- they link the ABI job to the
      OS process and (optionally) a remote cluster scheduler.
    * Fields use ``float`` timestamps (``time.time()``) rather than
      ``datetime`` objects so the dataclass round-trips cleanly through
      JSON without custom serialization.

    单个 ABI agent 作业的完整生命周期记录。17 个字段覆盖完整生命周期：
    提交、排队、执行、完成/失败/取消以及溯源信息。
    """

    # ── Identity / 身份标识 ──
    job_id: str
    # ── Command / 命令 ──
    command: str
    # ── Normalized arguments for the agent call / agent 调用的规范化参数 ──
    arguments: Dict[str, Any]
    # ── Execution backend (local, nextflow, hpc, cloud) / 执行后端 ──
    backend: str
    # ── Lifecycle status: queued → running → succeeded|failed|cancelled / 生命周期状态 ──
    status: str = "queued"
    # ── Submission timestamp / 提交时间戳 ──
    created_at: float = field(default_factory=time.time)
    # ── Last mutation timestamp / 最后修改时间戳 ──
    updated_at: float = field(default_factory=time.time)
    # ── Transition to "running" timestamp / 转入 "running" 的时间戳 ──
    started_at: Optional[float] = None
    # ── Terminal status timestamp / 终止状态时间戳 ──
    finished_at: Optional[float] = None
    # ── Envelope dict from agent.dispatch() / agent.dispatch() 返回的信封字典 ──
    result: Optional[Dict[str, Any]] = None
    # ── Human-readable error message / 人类可读的错误消息 ──
    error: Optional[str] = None
    # ── Exception class name for categorisation / 异常类名，用于分类 ──
    error_type: Optional[str] = None
    # ── True when cancel() has been called before completion / cancel() 在完成前被调用时为 True ──
    cancel_requested: bool = False
    # ── Path to the on-disk provenance record / 磁盘溯源记录的路径 ──
    job_provenance_path: Optional[str] = None
    # ── Error message if provenance write failed / 溯源写入失败时的错误消息 ──
    job_provenance_error: Optional[str] = None
    # ── OS PID of the worker subprocess (subprocess mode only)
    #    worker 子进程的 OS PID（仅子进程模式） ──
    worker_pid: Optional[int] = None
    # ── Job ID from a remote scheduler (Nextflow/SLURM, etc.)
    #    远程调度器（Nextflow/SLURM 等）的作业 ID ──
    remote_scheduler_job_id: Optional[str] = None

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
            "worker_pid": self.worker_pid,
            "remote_scheduler_job_id": self.remote_scheduler_job_id,
        }


class ABIJobService:
    """ABI job queue with optional JSON persistence and optional force-kill.

    Lifecycle / 生命周期
    ~~~~~~~~~~~~~~~~~~~~
    1. **Construction**: starts ``max_workers`` daemon threads, loads any
       persisted jobs from ``store_path``, re-enqueues uncompleted jobs.
    2. **Serving**: clients submit jobs via HTTP; workers pull from the
       internal queue and call either ``agent.dispatch()`` (in-process) or
       ``abi dispatch`` (subprocess).
    3. **Shutdown**: ``shutdown()`` signals workers to stop and joins them.

    Thread safety / 线程安全
    ~~~~~~~~~~~~~~~~~~~~~~~~
    All shared state (``_jobs`` dict, ``_processes`` dict) is guarded by a
    single ``threading.RLock`` so mutation and persistence are atomic.

    Set ``subprocess_workers=True`` to run each job in a separate ``abi dispatch``
    subprocess so that :meth:`cancel` can send SIGTERM for true force-kill.

    设置 ``subprocess_workers=True`` 可使每个作业在独立的 ``abi dispatch``
    子进程中运行，从而让 :meth:`cancel` 可以发送 SIGTERM 实现真正的强制终止。
    """

    def __init__(
        self,
        *,
        agent: Optional[ABIAgentInterface] = None,
        max_workers: int = 1,
        store_path: Optional[str | Path] = None,
        subprocess_workers: bool = False,
    ) -> None:
        """Initialize the job service and start worker threads.

        On construction the service loads any persisted jobs, marks
        in-flight jobs as failed (they did not survive the restart),
        and re-enqueues jobs that were still ``"queued"``.

        初始化作业服务并启动 worker 线程。构造时会加载持久化的作业，
        将进行中的作业标记为失败（未能在重启后存活），并重新排队仍处于
        ``"queued"`` 状态的作业。
        """
        if max_workers < 1:
            raise ValueError("max_workers must be at least 1")
        # Agent used for in-process dispatch / 用于进程内调度的 agent
        self.agent = agent or ABIAgentInterface()
        # Job store keyed by job_id / 以 job_id 为键的作业存储
        self._jobs: Dict[str, JobRecord] = {}
        # Guards all shared mutable state / 保护所有共享可变状态
        self._lock = threading.RLock()
        # FIFO queue of job_ids waiting to be processed / 待处理的 job_id 的 FIFO 队列
        self._queue: "queue.Queue[str]" = queue.Queue()
        # Signals worker threads to exit / 通知 worker 线程退出
        self._stop = threading.Event()
        # Optional on-disk persistence path / 可选的磁盘持久化路径
        self._store_path = Path(store_path) if store_path else None
        # Whether to run jobs in subprocesses / 是否在子进程中运行作业
        self._subprocess_workers = bool(subprocess_workers)
        # Maps job_id → Popen for active subprocess workers
        # job_id → Popen 的映射（活跃的子进程 worker）
        self._processes: Dict[str, "subprocess.Popen[str]"] = {}
        # Recover persisted jobs; returns job_ids that were "queued"
        # 恢复持久化作业；返回处于 "queued" 状态的 job_id
        queued_jobs = self._load_store()
        # Spawn daemon worker threads / 启动守护 worker 线程
        self._workers = [
            threading.Thread(target=self._worker_loop, name=f"abi-job-worker-{index}", daemon=True)
            for index in range(max_workers)
        ]
        for worker in self._workers:
            worker.start()
        # Re-enqueue jobs that were waiting when the service last stopped
        # 重新排队上次服务停止时等待的作业
        for job_id in queued_jobs:
            self._queue.put(job_id)

    def submit(self, payload: Mapping[str, Any]) -> Dict[str, Any]:
        """Validate and queue a job request.

        Data flow / 数据流
        ~~~~~~~~~~~~~~~~~~
        1. Extract ``command`` and ``arguments`` from the payload.
        2. Require ``confirm_execution=true`` for execution commands
           (safety gate against accidental runs / 防止意外运行的安全关卡).
        3. Normalize backend-specific arguments (HPC → executor=slurm, etc.).
        4. Create a ``JobRecord``, persist it, and push the job_id onto
           the queue for a worker to pick up.

        验证并排队作业请求。
        """
        command, arguments = _request_to_command(payload)
        backend = _backend_for(command, arguments)
        # Safety gate: execution commands must be explicitly confirmed
        # 安全关卡：执行命令必须明确确认
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
        # Generate a unique job ID / 生成唯一作业 ID
        job_id = uuid.uuid4().hex
        record = JobRecord(
            job_id=job_id,
            command=_canonical_command(command),
            arguments=arguments,
            backend=backend,
        )
        with self._lock:
            self._jobs[job_id] = record
            # Persist immediately so the job survives a crash / 立即持久化以便作业在崩溃后存活
            self._persist_locked()
        self._queue.put(job_id)
        return record.to_dict()

    def list_jobs(self) -> Dict[str, Any]:
        """Return all known jobs, newest first.

        返回所有已知作业，最新的在前。
        """
        with self._lock:
            jobs = [record.to_dict() for record in self._jobs.values()]
        jobs.sort(key=lambda item: item["created_at"], reverse=True)
        return {"jobs": jobs, "count": len(jobs)}

    def get_job(self, job_id: str) -> Dict[str, Any]:
        """Return a single job's full record.

        返回单个作业的完整记录。
        """
        return self._record(job_id).to_dict()

    def artifacts(self, job_id: str) -> Dict[str, Any]:
        """Collect output artifacts (files, dirs, reports) for a completed job.

        Walks the result envelope to discover written files, standard output
        directories, and report paths.  Includes the provenance record if one
        was written during execution.

        收集已完成作业的输出产物（文件、目录、报告）。遍历结果信使以发现
        已写入的文件、标准输出目录和报告路径。包含执行期间写入的溯源记录。
        """
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
        """Request cancellation of a job.

        Behaviour by current status / 按当前状态的行为：
        * ``"queued"`` → immediately marked ``"cancelled"`` (never started).
        * ``"running"`` → ``cancel_requested=True``; if a subprocess worker
          is active, sends SIGTERM (→ 3s grace → SIGKILL).
        * Terminal status → no-op (job already finished).

        请求取消作业。排队中的作业立即标记为已取消；运行中的作业设置取消标志
        并对子进程发送 SIGTERM（→ 3 秒宽限期 → SIGKILL）；已终止的作业无操作。
        """
        with self._lock:
            record = self._jobs.get(job_id)
            if record is None:
                raise JobNotFoundError(f"Unknown ABI job: {job_id}")
            if record.status == "queued":
                # Never started -- cancel immediately / 从未开始——立即取消
                record.status = "cancelled"
                record.finished_at = time.time()
            elif record.status not in TERMINAL_STATUSES:
                # Running -- request cancellation; may be honoured cooperatively or via force-kill /
                # 运行中——请求取消；可能通过协作方式或强制终止来响应
                record.status = "cancel_requested"
                record.cancel_requested = True
                # Force-kill subprocess worker when available / 如果有子进程 worker，强制终止
                proc = self._processes.get(job_id)
                if proc is not None and proc.poll() is None:
                    _kill_process(proc, record.worker_pid)
            record.updated_at = time.time()
            self._write_job_provenance_locked(record)
            self._persist_locked()
            return record.to_dict()

    def shutdown(self, *, wait: bool = True) -> None:
        """Signal all worker threads to stop and optionally wait for them.

        通知所有 worker 线程停止，并可选等待它们结束。
        """
        self._stop.set()
        if wait:
            for worker in self._workers:
                worker.join(timeout=2)

    def _record(self, job_id: str) -> JobRecord:
        """Look up a job by ID, raising ``JobNotFoundError`` if missing.

        按 ID 查找作业，若不存在则抛出 ``JobNotFoundError``。
        """
        with self._lock:
            record = self._jobs.get(job_id)
            if record is None:
                raise JobNotFoundError(f"Unknown ABI job: {job_id}")
            return record

    def _worker_loop(self) -> None:
        """Block on the queue and execute jobs until the stop event is set.

        Uses a 0.2-second timeout on ``queue.get()`` so the loop checks
        ``_stop`` frequently and can exit promptly on shutdown.

        在队列上阻塞并执行作业，直到停止事件被设置。使用 0.2 秒超时的
        ``queue.get()``，使循环频繁检查 ``_stop`` 并在关闭时及时退出。
        """
        while not self._stop.is_set():
            try:
                job_id = self._queue.get(timeout=0.2)
            except queue.Empty:
                continue
            try:
                self._run_job(job_id)
            finally:
                # Mark the queue task done regardless of outcome / 无论结果如何，标记队列任务完成
                self._queue.task_done()

    def _run_job(self, job_id: str) -> None:
        """Execute a single job: dispatch, capture results, update status.

        Execution paths / 执行路径
        ~~~~~~~~~~~~~~~~~~~~~~~~~~
        1. **In-process** (``subprocess_workers=False``): calls
           ``self.agent.dispatch()`` inside the worker thread.  Cancel is
           cooperative -- the worker must check ``cancel_requested``.

        2. **Subprocess** (``subprocess_workers=True``): spawns
           ``abi dispatch`` as a child process via ``_dispatch_subprocess``.
           Cancel can send SIGTERM/SIGKILL to the child.

        After dispatch, the result envelope is parsed to determine the
        terminal status (succeeded / failed / cancelled) and the remote
        scheduler job ID is extracted when available.

        执行单个作业：调度、捕获结果、更新状态。
        """
        record = self._record(job_id)
        with self._lock:
            # Already cancelled before a worker picked it up / 在 worker 取走前已被取消
            if record.status == "cancelled":
                return
            record.status = "running"
            record.started_at = time.time()
            record.updated_at = record.started_at
            self._persist_locked()
        try:
            if self._subprocess_workers:
                # Subprocess path: true force-kill support / 子进程路径：支持真正的强制终止
                envelope = self._dispatch_subprocess(job_id, record)
            else:
                # In-process path: cooperative cancel only / 进程内路径：仅支持协作取消
                envelope = loads_json(
                    self.agent.dispatch(record.command, record.arguments),
                    label=f"agent response for {record.command}",
                )
            with self._lock:
                record.result = envelope
                # Extract remote scheduler job ID from the result envelope
                # 从结果信使中提取远程调度器作业 ID
                self._capture_remote_scheduler_id(record, envelope)
                # Determine terminal status from envelope + cancel state
                # 从信使和取消状态确定终止状态
                if self._cancel_requested_or_cancelled(record):
                    record.status = "cancelled"
                elif envelope.get("status") == "success":
                    record.status = "succeeded"
                else:
                    record.status = "failed"
                    record.error = str(envelope.get("error") or envelope.get("status"))
                    record.error_type = str(envelope.get("error_type") or envelope.get("status"))
                self._persist_locked()
        except MemoryError:
            # Never swallow MemoryError -- let the process crash / 绝不吞掉 MemoryError——让进程崩溃
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
                # Write provenance record to disk (best-effort)
                # 将溯源记录写入磁盘（尽力而为）
                self._write_job_provenance_locked(record)
                # Clean up subprocess reference / 清理子进程引用
                self._processes.pop(job_id, None)
                self._persist_locked()

    # ── helpers / 辅助方法 ──────────────────────────────────────────────

    def _dispatch_subprocess(self, job_id: str, record: JobRecord) -> Dict[str, Any]:
        """Run ``abi dispatch`` in a subprocess, capturing its JSON output.

        The subprocess is registered in ``self._processes`` so that
        ``cancel()`` can locate and kill it.  After ``proc.communicate()``
        returns, the stdout is parsed as JSON.  If the job was cancelled
        during execution, a synthetic cancelled envelope is returned instead.

        在子进程中运行 ``abi dispatch``，捕获其 JSON 输出。子进程注册到
        ``self._processes`` 中，以便 ``cancel()`` 可以定位并终止它。
        """
        args_json = json.dumps(record.arguments, ensure_ascii=False)
        # Hold the lock across Popen creation and registration so that
        # cancel() cannot miss a process that is about to start.
        # 在 Popen 创建和注册期间持有锁，防止 cancel() 遗漏即将启动的进程。
        with self._lock:
            proc = subprocess.Popen(
                ["abi", "dispatch", "--command", record.command, "--arguments", args_json],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            self._processes[job_id] = proc
            # Record the OS PID for force-kill and diagnostics
            # 记录 OS PID 用于强制终止和诊断
            record.worker_pid = proc.pid
        # Block until the subprocess exits / 阻塞直到子进程退出
        stdout, stderr = proc.communicate()
        # If cancel was requested while the subprocess ran, override the result
        # 如果子进程运行期间请求取消，覆盖结果
        if self._cancel_requested_or_cancelled(record):
            return {
                "status": "cancelled",
                "command": record.command,
                "result": {},
                "error": "Job was cancelled.",
            }
        if proc.returncode != 0:
            raise JobServiceError(
                f"abi dispatch failed with code {proc.returncode}: {stderr.strip()}"
            )
        return loads_json(stdout, label=f"subprocess dispatch stdout for {job_id}")

    @staticmethod
    def _capture_remote_scheduler_id(record: JobRecord, envelope: Mapping[str, Any]) -> None:
        """Extract a remote scheduler job ID from the result envelope.

        Search order / 搜索顺序:
        1. Top-level ``result.remote_scheduler_job_id``, ``result.nextflow_job_id``,
           ``result.job_id``.
        2. Nested ``result.outputs.remote_scheduler_job_id``,
           ``result.outputs.nextflow_job_id``.

        This allows the job service to cross-reference ABI jobs with
        Nextflow/SLURM/cloud scheduler jobs for observability.

        从结果信使中提取远程调度器作业 ID，使作业服务可以将 ABI 作业与
        Nextflow/SLURM/云调度器作业进行交叉引用，便于可观测性。
        """
        result = envelope.get("result")
        if not isinstance(result, Mapping):
            return
        # Check top-level result fields first / 首先检查顶层 result 字段
        for key in ("remote_scheduler_job_id", "nextflow_job_id", "job_id"):
            value = result.get(key)
            if value:
                record.remote_scheduler_job_id = str(value)
                return
        # Fall back to nested outputs / 回退到嵌套的 outputs
        outputs = result.get("outputs")
        if isinstance(outputs, Mapping):
            for key in ("remote_scheduler_job_id", "nextflow_job_id"):
                value = outputs.get(key)
                if value:
                    record.remote_scheduler_job_id = str(value)
                    return

    @staticmethod
    def _cancel_requested_or_cancelled(record: JobRecord) -> bool:
        """Return True if this job has been cancelled or a cancel is pending.

        如果此作业已被取消或有待处理的取消请求，返回 True。
        """
        return record.cancel_requested or record.status in {"cancelled", "cancel_requested"}

    def _load_store(self) -> list[str]:
        """Load persisted jobs and return job_ids that should be re-enqueued.

        Restart semantics / 重启语义
        ~~~~~~~~~~~~~~~~~~~~~~~~~~~~
        * ``"queued"`` jobs → re-enqueued (they never started).
        * ``"running"`` / ``"cancel_requested"`` jobs → marked ``"failed"``
          with ``error_type="service_restart"`` because the in-flight work
          was lost when the service process died.
        * Terminal jobs → left as-is.

        加载持久化的作业，返回应重新排队的 job_id 列表。
        """
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
                # Never started -- safe to re-enqueue / 从未开始——可安全重新排队
                queued_jobs.append(record.job_id)
            elif record.status in {"running", "cancel_requested"}:
                # Was in-flight when the service died -- mark as failed
                # 服务挂掉时正在执行——标记为失败
                record.status = "failed"
                record.error = "Job did not complete before the Job Service restarted."
                record.error_type = "service_restart"
                record.finished_at = time.time()
                record.updated_at = record.finished_at
            self._jobs[record.job_id] = record
        # Persist the corrected state immediately / 立即持久化修正后的状态
        self._persist_locked()
        return queued_jobs

    def _persist_locked(self) -> None:
        """Write the full job store to disk atomically.

        Atomic write pattern / 原子写入模式
        ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
        1. Write the payload to ``<store_path>.tmp``.
        2. ``os.replace()`` (via ``Path.replace``) the tmp file over the
           real path.

        This guarantees the store is never observed half-written -- the
        consumer always sees either the old complete file or the new one.

        将完整作业存储原子性地写入磁盘。先写入 ``.tmp`` 文件，再用
        ``Path.replace`` 替换真实文件，保证存储永远不会处于半写入状态。
        """
        if self._store_path is None:
            return
        self._store_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "updated_at": time.time(),
            "jobs": [record.to_dict() for record in self._jobs.values()],
        }
        # Write to .tmp first, then atomically replace to avoid corruption
        # 先写入 .tmp，然后原子替换以避免损坏
        tmp_path = self._store_path.with_name(f"{self._store_path.name}.tmp")
        tmp_path.write_text(json.dumps(_jsonable(payload), indent=2) + "\n", encoding="utf-8")
        tmp_path.replace(self._store_path)

    def _write_job_provenance_locked(self, record: JobRecord) -> None:
        """Write a per-job provenance record into the output directory.

        The provenance file (``job.json``) is placed under
        ``<result_dir>/provenance/`` so it travels with the pipeline outputs.
        Write failures are recorded on the record's
        ``job_provenance_error`` field but do **not** fail the job.

        将每个作业的溯源记录（``job.json``）写入输出目录下的
        ``<result_dir>/provenance/``，使其随管道输出一起保留。
        写入失败会记录到 ``job_provenance_error`` 字段，但**不会**导致作业失败。
        """
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
            # Atomic write with .tmp to prevent partial JSON / 使用 .tmp 原子写入防止不完整的 JSON
            tmp_path = path.with_name(f"{path.name}.tmp")
            tmp_path.write_text(json.dumps(_jsonable(payload), indent=2) + "\n", encoding="utf-8")
            tmp_path.replace(path)
            record.job_provenance_path = str(path)
            record.job_provenance_error = None
        except OSError as exc:
            # Best-effort: provenance write failure must not crash the job
            # 尽力而为：溯源写入失败不能导致作业崩溃
            record.job_provenance_error = str(exc)


# ── HTTP server factory / HTTP 服务器工厂 ───────────────────────────────


def _is_localhost(host: str) -> bool:
    """Return True if *host* is a loopback address (S7 fix)."""
    return host in ("127.0.0.1", "localhost", "::1")


def create_http_server(
    service: ABIJobService,
    *,
    host: str = "127.0.0.1",
    port: int = 18791,
    required_secret: str | None = None,
) -> ThreadingHTTPServer:
    """Create a stdlib ``ThreadingHTTPServer`` bound to an ``ABIJobService``.

    Design decisions / 设计决策
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~
    * ``ThreadingHTTPServer`` is used so each request is handled in its own
      thread -- this keeps the job-service responsive even while a long
      request body is being read.
    * ``log_message`` is overridden to suppress the default stdlib access
      log (ABI has its own structured logging).
    * All exceptions are caught at the HTTP boundary and serialized to
      JSON error responses so the client always gets a valid JSON payload.
    * **S7 fix**: When binding to a non-localhost address, ``required_secret``
      is enforced via ``Authorization: Bearer <secret>`` header validation.

    创建绑定到 ``ABIJobService`` 的标准库 ``ThreadingHTTPServer``。
    """

    class Handler(BaseHTTPRequestHandler):
        server_version = "ABIJobService/0.1"

        def _check_auth(self) -> None:  # noqa: N802 - auth check helper
            """Validate the Authorization header if auth is required (S7 fix)."""
            if required_secret is None:
                return  # localhost binding — no auth needed
            auth = self.headers.get("Authorization", "")
            if auth != f"Bearer {required_secret}":
                raise UnauthorizedError("Unauthorized: missing or invalid Authorization header")

        def do_GET(self) -> None:  # noqa: N802 - stdlib hook name
            """Route GET requests to the job service."""
            try:
                self._check_auth()
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
            """Route POST requests to the job service."""
            try:
                self._check_auth()
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
            """Suppress default stdlib access logging / 抑制默认的标准库访问日志."""
            return

        def _read_json(self) -> Dict[str, Any]:
            """Read and parse the JSON request body.

            读取并解析 JSON 请求体。
            """
            length = int(self.headers.get("Content-Length", "0"))
            if length == 0:
                return {}
            raw = self.rfile.read(length).decode("utf-8")
            data = json.loads(raw)
            if not isinstance(data, dict):
                raise JobServiceError("Request body must be a JSON object.")
            return data

        def _send_json(self, status: int, payload: Mapping[str, Any]) -> None:
            """Serialize a dict to JSON and send it as the HTTP response.

            将字典序列化为 JSON 并作为 HTTP 响应发送。
            """
            data = json.dumps(_jsonable(payload), indent=2, ensure_ascii=False).encode("utf-8")
            self.send_response(int(status))
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    return ThreadingHTTPServer((host, port), Handler)


# ── Convenience entry point / 便捷入口点 ─────────────────────────────────


def serve(
    *,
    host: str = "127.0.0.1",
    port: int = 18791,
    max_workers: int = 1,
    store_path: Optional[str | Path] = None,
    subprocess_workers: bool = False,
) -> None:
    """Run the ABI Job Service until interrupted (e.g. Ctrl+C).

    This is the primary CLI entry point.  It creates a service, wraps it
    in an HTTP server, and blocks on ``serve_forever()``.  On shutdown
    the server socket is closed and the workers are signalled to stop.

    运行 ABI 作业服务直到被中断（如 Ctrl+C）。这是主要的 CLI 入口点。
    """

    # S7: enforce auth for non-localhost bindings
    secret = os.environ.get("ABI_JOB_SECRET") if not _is_localhost(host) else None
    if not _is_localhost(host) and not secret:
        raise JobServiceError(
            f"Binding to non-localhost address {host!r} requires "
            f"ABI_JOB_SECRET environment variable to be set."
        )

    service = ABIJobService(
        max_workers=max_workers,
        store_path=store_path,
        subprocess_workers=subprocess_workers,
    )
    server = create_http_server(service, host=host, port=port, required_secret=secret)
    try:
        server.serve_forever()
    finally:
        server.server_close()
        service.shutdown(wait=False)


# ── HTTP routing / HTTP 路由 ────────────────────────────────────────────


def _handle_get(service: ABIJobService, path: str) -> Tuple[int, Mapping[str, Any]]:
    """Route a GET request to the appropriate service method.

    将 GET 请求路由到相应的 service 方法。
    """
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
    """Route a POST request to the appropriate service method.

    将 POST 请求路由到相应的 service 方法。
    """
    parts = _path_parts(path)
    if parts == ["jobs"]:
        record = service.submit(body)
        return HTTPStatus.ACCEPTED, {"status": "accepted", "job": record}
    if len(parts) == 3 and parts[0] == "jobs" and parts[2] == "cancel":
        return HTTPStatus.OK, {"status": "success", "job": service.cancel(parts[1])}
    raise JobServiceError(f"Unknown endpoint: POST /{'/'.join(parts)}", payload={"status": "error"})


# ── Request parsing & validation / 请求解析与验证 ──────────────────────


def _request_to_command(payload: Mapping[str, Any]) -> Tuple[str, Dict[str, Any]]:
    """Extract the canonical command and arguments from a request payload.

    Supports two payload shapes / 支持两种载荷形式：
    1. ``{"command": "run", "arguments": {...}}`` -- explicit separation.
    2. Flat payload where every key not reserved (``command``, ``tool``,
       ``arguments``, ``backend``) becomes part of ``arguments``.

    从请求载荷中提取规范化命令和参数。
    """
    command = str(payload.get("command") or payload.get("tool") or "abi_run")
    raw_arguments = payload.get("arguments")
    if raw_arguments is None:
        # Flat payload: promote non-reserved keys into arguments / 扁平载荷：将非保留键提升为参数
        arguments = {
            key: value
            for key, value in payload.items()
            if key not in {"command", "tool", "arguments", "backend"}
        }
    elif isinstance(raw_arguments, Mapping):
        arguments = dict(raw_arguments)
    else:
        raise JobServiceError("arguments must be a JSON object.")
    # Carry backend through if specified at the top level / 如果在顶层指定了 backend，则传递下去
    if "backend" in payload and "backend" not in arguments:
        arguments["backend"] = payload["backend"]
    return command, arguments


def _backend_for(command: str, arguments: Mapping[str, Any]) -> str:
    """Determine the execution backend from the command and arguments.

    Non-execution commands (plan, inspect, report, etc.) always run on the
    ``"service"`` backend.  Execution commands look for an explicit
    ``backend`` or ``engine`` field, defaulting to ``"local"``.

    从命令和参数中确定执行后端。非执行命令始终在 ``"service"`` 后端运行。
    执行命令查找显式的 ``backend`` 或 ``engine`` 字段，默认为 ``"local"``。
    """
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
    """Normalize backend-specific arguments into the canonical form.

    Why normalization matters / 为什么需要规范化
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    The job service accepts a user-friendly ``backend`` field (``hpc``,
    ``cloud``) but the ABI agent expects ``engine`` (``local``, ``nextflow``).
    This function translates between the two vocabularies:

    * ``backend="hpc"`` → ``engine="nextflow"``, ``executor="slurm"``
      (unless overridden via ``hpc_executor``).
    * ``backend="cloud"`` → ``engine="nextflow"``, with optional
      ``cloud_executor`` / ``cloud_profile`` promoted.

    将后端特定的参数规范化为标准形式。作业服务接受用户友好的 ``backend`` 字段，
    但 ABI agent 期望 ``engine`` 字段。此函数在两者之间进行转换。
    """
    normalized = dict(arguments)
    # Remove raw backend key -- engine replaces it / 删除原始 backend 键——engine 替代它
    normalized.pop("backend", None)
    if not _is_execution_command(command):
        return normalized
    normalized["engine"] = _engine_for_backend(backend, normalized)
    if backend == "hpc":
        # Promote HPC-specific flags to their canonical names / 将 HPC 特定标志提升为其规范名称
        hpc_executor = normalized.pop("hpc_executor", None)
        hpc_profile = normalized.pop("hpc_profile", None)
        if "executor" not in normalized:
            normalized["executor"] = hpc_executor or "slurm"
        if hpc_profile and "nextflow_profile" not in normalized:
            normalized["nextflow_profile"] = hpc_profile
    elif backend == "cloud":
        # Promote cloud-specific flags to their canonical names / 将云特定标志提升为其规范名称
        cloud_executor = normalized.pop("cloud_executor", None)
        cloud_profile = normalized.pop("cloud_profile", None)
        if cloud_executor and "executor" not in normalized:
            normalized["executor"] = cloud_executor
        if cloud_profile and "nextflow_profile" not in normalized:
            normalized["nextflow_profile"] = cloud_profile
    return normalized


def _engine_for_backend(backend: str, arguments: Mapping[str, Any]) -> str:
    """Map a user-facing backend name to the internal engine name.

    ``hpc`` and ``cloud`` both use Nextflow under the hood.  ``local``
    maps to itself.

    将面向用户的后端名称映射为内部引擎名称。``hpc`` 和 ``cloud`` 底层均使用
    Nextflow，``local`` 映射为自身。
    """
    if backend in {"hpc", "cloud"}:
        return "nextflow"
    return str(arguments.get("engine") or backend or "local")


def _is_execution_command(command: str) -> bool:
    """Return True if this command triggers real pipeline execution.

    Only ``abi_run`` requires the confirmation gate and backend selection.
    All other commands (plan, inspect, report, etc.) are read-only metadata
    operations.

    如果此命令触发真实管道执行，返回 True。仅 ``abi_run`` 需要确认关卡和
    后端选择。所有其他命令都是只读元数据操作。
    """
    return _canonical_command(command) == "abi_run"


def _canonical_command(command: str) -> str:
    """Normalize a command string to its canonical ``abi_*`` form.

    Design rationale / 设计理由
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~
    Users (and LLM agents) may type ``"run"``, ``"dry-run"``, or
    ``"abi_run"``.  This function maps all known aliases to the canonical
    name so the rest of the code only deals with one form per command.

    将命令字符串规范化为其标准 ``abi_*`` 形式。用户（和 LLM agent）可能输入
    ``"run"``、``"dry-run"`` 或 ``"abi_run"``。此函数将所有已知别名映射到
    规范名称，使其余代码只需处理每个命令的一种形式。
    """
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


# ── Persistence helpers / 持久化辅助函数 ────────────────────────────────


def _record_from_mapping(data: Mapping[str, Any]) -> JobRecord:
    """Reconstruct a ``JobRecord`` from a deserialized JSON dict.

    Maps each field with defensive type coercion so the record is always
    constructed even when the persisted JSON was hand-edited or produced
    by an older version of the service.

    从反序列化的 JSON 字典重建 ``JobRecord``。每个字段都进行防御性类型强制
    转换，确保即使持久化的 JSON 被手动编辑或由旧版本服务生成，也能成功构建记录。
    """
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
        worker_pid=(
            int(data["worker_pid"]) if isinstance(data.get("worker_pid"), (int, float)) else None
        ),
        remote_scheduler_job_id=(
            str(data["remote_scheduler_job_id"])
            if data.get("remote_scheduler_job_id") is not None
            else None
        ),
    )


def _optional_float(value: Any) -> Optional[float]:
    """Convert a value to float or return None.

    将值转换为 float 或返回 None。
    """
    if value is None:
        return None
    return float(value)


# ── Artifact collection / 产物收集 ──────────────────────────────────────


def _collect_artifacts(result: Mapping[str, Any], artifacts: Dict[str, Any]) -> None:
    """Walk the result envelope and collect output file paths.

    The artifact collection is intentionally optimistic: it discovers paths
    at known keys and also infers standard subdirs (tables/, report/,
    provenance/) from the output directory.  Unknown keys are ignored.

    遍历结果信使并收集输出文件路径。产物收集有意乐观：它从已知键发现路径，
    并从输出目录推断标准子目录。
    """
    # Top-level result keys that may contain output paths / 可能包含输出路径的顶层 result 键
    for key in ("outdir", "plan_path", "result_dir", "workflow"):
        if key in result:
            artifacts[key] = result[key]
    # If we found an output directory, enumerate its known sub-paths
    # 如果找到输出目录，枚举其已知子路径
    if "outdir" in artifacts:
        _collect_outdir_artifacts(str(artifacts["outdir"]), artifacts)
    # Written files explicitly listed by the agent / agent 显式列出的已写入文件
    if "written_files" in result and isinstance(result["written_files"], Iterable):
        artifacts["written_files"] = list(result["written_files"])
    # Nested outputs dictionary / 嵌套的 outputs 字典
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
    """Enumerate standard artifact paths under a known output directory.

    These paths are set with ``setdefault`` so already-discovered
    artifacts (e.g. from ``result.written_files``) are not overwritten.

    枚举已知输出目录下的标准产物路径。使用 ``setdefault`` 设置，因此
    已发现的产物不会被覆盖。
    """
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
    """Infer the output root directory from a job record.

    Search order / 搜索顺序:
    1. ``result.result.outdir`` or ``result.result.result_dir``.
    2. Infer from artifact paths in ``result.result.outputs``.
    3. ``arguments.outdir`` or ``arguments.result_dir``.

    Returns None if no directory can be inferred.

    从作业记录推断输出根目录。无目录可推断时返回 None。
    """
    result = record.result or {}
    payload = result.get("result")
    if isinstance(payload, Mapping):
        # Check direct output directory keys / 检查直接输出目录键
        for key in ("outdir", "result_dir"):
            value = payload.get(key)
            if value not in (None, ""):
                return Path(str(value))
        # Infer from nested artifact paths / 从嵌套产物路径推断
        outputs = payload.get("outputs")
        if isinstance(outputs, Mapping):
            for key in ("plan", "report", "report_html", "commands", "summary"):
                value = outputs.get(key)
                if value not in (None, ""):
                    return _infer_result_root_from_artifact(Path(str(value)))
    # Fall back to the input arguments / 回退到输入参数
    for key in ("outdir", "result_dir"):
        value = record.arguments.get(key)
        if value not in (None, ""):
            return Path(str(value))
    return None


def _infer_result_root_from_artifact(path: Path) -> Path:
    """Heuristically find the project root from a known artifact path.

    For example, ``/out/provenance/commands.tsv`` → ``/out``.
    ``/out/report/report.md`` → ``/out``.

    从已知产物路径启发式地找到项目根目录。
    """
    parts = path.parts
    if "provenance" in parts:
        return Path(*parts[: parts.index("provenance")])
    if "report" in parts:
        return Path(*parts[: parts.index("report")])
    if path.name == "execution_plan.json":
        return path.parent
    return path.parent


def _path_parts(path: str) -> list[str]:
    """Split a URL path into non-empty segments.

    将 URL 路径分割为非空段。
    """
    parsed = urlparse(path)
    return [part for part in parsed.path.split("/") if part]


# ── Process management / 进程管理 ────────────────────────────────────────


def _kill_process(proc: "subprocess.Popen[str]", pid: Optional[int]) -> None:
    """Send SIGTERM (then SIGKILL after 3s grace) to a subprocess.

    Escalation strategy / 升级策略
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    1. ``SIGTERM`` -- polite request; allows the process to flush buffers
       and remove temporary files.
    2. Wait 3 seconds.
    3. ``SIGKILL`` -- unconditional kill; the kernel terminates the
       process immediately.
    4. ``proc.communicate()`` -- drain stdout/stderr pipes to prevent
       the parent process from blocking on pipe buffers.

    This two-phase approach balances clean shutdown with guaranteed
    termination for hung or unresponsive processes.

    向子进程发送 SIGTERM（3 秒宽限期后发送 SIGKILL）。此两阶段方法兼顾
    干净关闭与对挂起或无响应进程的强制终止。
    """
    target_pid = pid or proc.pid
    if target_pid is None:
        return
    # Phase 1: polite termination / 阶段 1：礼貌终止
    try:
        os.kill(target_pid, signal.SIGTERM)
    except OSError:
        pass
    try:
        proc.wait(timeout=3)
    except subprocess.TimeoutExpired:
        # Phase 2: force kill / 阶段 2：强制终止
        try:
            os.kill(target_pid, signal.SIGKILL)
        except OSError:
            pass
    # Wait for the process to finish (stdout/stderr are already being
    # consumed by proc.communicate() in _dispatch_subprocess).  Calling
    # proc.communicate() here would race with that thread and corrupt
    # internal Popen state.
    # 等待进程结束（stdout/stderr 已由 _dispatch_subprocess 中的
    # proc.communicate() 处理）。在此调用 proc.communicate() 会与
    # 该线程竞争并损坏内部 Popen 状态。
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        pass


def _error_payload(exc: JobServiceError) -> Dict[str, Any]:
    """Build a JSON-safe error dict from a ``JobServiceError``.

    从 ``JobServiceError`` 构建 JSON 安全的错误字典。
    """
    if exc.payload:
        payload = dict(exc.payload)
        payload.setdefault("error", str(exc))
        return payload
    return {"status": "error", "error": str(exc), "error_type": exc.__class__.__name__}


def _jsonable(value: Any) -> Any:
    """Recursively convert a value into a JSON-serializable form.

    Handles ``Path`` → ``str`` and recursively walks ``Mapping`` and
    ``Iterable`` (except ``str``/``bytes``/``bytearray``) containers.

    递归地将值转换为 JSON 可序列化形式。将 ``Path`` 转为 ``str``，
    并递归遍历 ``Mapping`` 和 ``Iterable`` 容器。
    """
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, Iterable) and not isinstance(value, (str, bytes, bytearray)):
        return [_jsonable(item) for item in value]
    return value
