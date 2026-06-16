"""Provenance logging and progress recording for ABI pipeline execution.

# Data flow / 数据流
Each pipeline run produces a provenance/ directory that serves as the single
source of truth for what happened, why, and with what inputs.  The artifacts are
organized by concern:

    provenance/
        commands.tsv       ← every step attempted: id, tool, status, return code, etc.
        resolved_inputs.tsv ← resolved paths & existence check per input per step
        tool_versions.tsv   ← tool binary versions (for reproducing analyses)
        resources.json       ← resolved resource files (databases, models, etc.)
        environment.yml      ← conda/mamba environment lock for the run
        run_summary.json     ← top-level summary (dry_run, parallel, status, counts)
        progress.json        ← live snapshot for dashboards (instrumented mode only)
        progress.jsonl       ← append-only event stream for audit trail
        step_logs/           ← per-step stderr/stdout captures

这些 artifacts 服务于三类消费者:
  1) Dashboards that poll progress.json for current status. / 轮询进度仪表盘
  2) Audit tools that replay progress.jsonl for a full event timeline. / 审计重放
  3) Human readers who inspect commands.tsv and logs to debug failures. / 人工调试

# Two recording modes / 两种记录模式
- **Live / 实时模式**: PipelineProgressRecorder emits every step start/complete
  event as it happens; suitable when the pipeline is run interactively.
- **Minimal / 最小模式**: write_minimal_progress_artifacts writes a single
  start+complete pair after all steps finish; used in batch / dry-run contexts
  where per-step granularity is unnecessary overhead.

# Thread safety / 线程安全
PipelineProgressRecorder uses a threading.Lock to serialize writes to both the
JSONL event stream and the JSON snapshot, so multiple worker threads can record
events concurrently without corruption.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping

from abi._shared import _display_command
from abi.filesystem import ensure_directory

__all__ = [
    "PipelineProgressRecorder",
    "RunLogger",
    "write_commands_tsv",
    "write_methods_md",
    "write_minimal_progress_artifacts",
    "write_resolved_inputs_tsv",
    "write_tool_versions",
]

# ── RunLogger ──────────────────────────────────────────────────────────
# Structured JSON-line log for human post-mortem debugging.
# Each log_event() appends one line; log_step() is a convenience that extracts
# fields from a pipeline Step object and delegates to log_event().
#
# 结构化 JSON 行日志，用于事后调试。每次调用 log_event() 追加一行 JSON；
# log_step() 从 pipeline Step 对象中提取字段并委托给 log_event()。


class RunLogger:
    """Structured JSON-line event logger for a single pipeline run.

    # Why JSON-line? / 为什么用 JSON-line？
    - Append-only means no file corruption on crash. / 追加模式，崩溃不损坏文件
    - Each line is self-contained for grep/tail/jq.
      / 每行自包含，方便用 grep/tail/jq 查看
    - `sort_keys=True` ensures deterministic field ordering across runs. / 排序键确保跨运行的可比性
    """

    def __init__(self, log_dir: str | Path) -> None:
        # ensure_directory creates the directory if it doesn't exist / 确保目录存在
        self.log_dir = ensure_directory(log_dir, label="Log directory")
        # Name includes timestamp so multiple runs never collide / 文件名包含时间戳避免多次运行冲突
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_file = self.log_dir / f"log_abi_{timestamp}.log"

    def log_event(self, event: str, payload: Mapping[str, Any]) -> None:
        """Append a single structured event record to the log file.

        # Thread-safe by construction / 线程安全设计
        The file handle is opened, written, and closed per call, so concurrent
        writers interleave whole lines (not partial bytes). For high-frequency
        event streams prefer PipelineProgressRecorder which uses a shared Lock.
        """
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
        """Log a pipeline step with its command, inputs, outputs, and status.

        # Parameters / 参数
        - step: Pipeline Step object (duck-typed via getattr) / 管道步骤对象
        - command: The shell command invoked (str or token list) / 执行的命令
        - status: "success", "failed", "running", etc. / 状态
        - error_message: Optional error detail for failed steps / 可选的错误详情
        """
        # Normalize command to a string for readability / 将命令规范化为字符串以便阅读
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
# These write tab-separated tables that follow the ABI provenance spec.
# They are called at the END of a run (live or minimal mode) to produce the
# final static artifacts. Each function takes pre-built row dicts so callers
# control the schema; the function only handles I/O and header ordering.
#
# 这些函数生成遵循 ABI provenance 规范的 TSV 表格。
# 它们在运行结束后（实时或最小模式）被调用，生成最终的静态 artifacts。
# 每个函数接收预构建的行字典，调用者控制 schema，函数只处理 I/O 和表头顺序。


def write_commands_tsv(rows: Iterable[Mapping[str, Any]], path: str | Path) -> Path:
    """Write commands.tsv: one row per pipeline step executed.

    # Design / 设计
    - Header order is fixed to match the ABI spec, ensuring stable column positions
      across runs — important for downstream parsers. / 表头顺序与 ABI 规范一致
    - `_tsv_value` converts None to "" so tab delimiters stay aligned. / None 转为空串保持制表符对齐
    - The function creates parent directories (mkdir -p semantics). / 自动创建父目录
    """
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
    """Write tool_versions.tsv: tool executable paths and version strings.

    # Purpose / 目的
    Reproducibility: if a run produces surprising results, tool_versions.tsv
    records exactly which version of each tool was invoked so the analysis can
    be re-created with the same software stack. / 记录工具版本用于重现分析
    """
    versions_path = Path(path)
    versions_path.parent.mkdir(parents=True, exist_ok=True)
    fields = ["tool_id", "executable", "env_name", "version", "status"]
    with versions_path.open("w", encoding="utf-8") as handle:
        handle.write("\t".join(fields) + "\n")
        for row in rows:
            handle.write("\t".join(_tsv_value(row.get(field, "")) for field in fields) + "\n")
    return versions_path


def write_resolved_inputs_tsv(rows: Iterable[Mapping[str, Any]], path: str | Path) -> Path:
    """Write resolved_inputs.tsv: input file paths and existence checks.

    # Why this exists / 为什么需要这个表
    Pipeline steps often reference inputs symbolically (e.g. "assembly.fasta").
    resolved_inputs.tsv captures the concrete filesystem path that was actually
    used and whether it existed at run time, so post-mortem debugging can
    distinguish "tool bug" from "missing input file". / 区分工具 bug 与输入文件缺失
    """
    inputs_path = Path(path)
    inputs_path.parent.mkdir(parents=True, exist_ok=True)
    fields = ["step_id", "tool_id", "sample_id", "input_name", "path", "exists", "source"]
    with inputs_path.open("w", encoding="utf-8") as handle:
        handle.write("\t".join(fields) + "\n")
        for row in rows:
            handle.write("\t".join(_tsv_value(row.get(field, "")) for field in fields) + "\n")
    return inputs_path


def write_methods_md(
    command_rows: list[dict],
    tool_versions: list[dict],
    resources: list[dict] | None = None,
    *,
    path: str | Path | None = None,
    title: str = "Methods",
) -> str:
    """Generate a methods.md section with actual execution parameters (B23 fix).

    Unlike the generic report which uses planned parameters, this function
    uses the ``resolved_params`` recorded in ``RunResult`` and the actual
    tool versions from execution, ensuring the methods section reflects
    what was actually run, not what was planned.

    Returns the markdown string.  If ``path`` is given, also writes it.
    """
    lines = [
        f"# {title}",
        "",
        "## Software Versions",
        "",
        "| Tool | Executable | Version | Status |",
        "|------|-----------|---------|--------|",
    ]
    for tv in tool_versions:
        version = tv.get("version", "")
        # B21: Semantic version field labeling
        if not version or version == "":
            version = "not_captured"
        elif version.startswith("version_command_"):
            version = f"capture_failed ({version})"
        lines.append(
            f"| {tv.get('tool_id', '')} "
            f"| {tv.get('executable', '')} "
            f"| {version} "
            f"| {tv.get('status', '')} |"
        )

    if resources:
        lines.extend(
            [
                "",
                "## Reference Databases",
                "",
                "| Resource | Version | Source | Path |",
                "|----------|---------|--------|------|",
            ]
        )
        for res in resources:
            lines.append(
                f"| {res.get('name', '')} "
                f"| {res.get('version', 'not_captured')} "
                f"| {res.get('source_url', '')} "
                f"| {res.get('path', '')} |"
            )

    lines.extend(
        [
            "",
            "## Commands Executed",
            "",
            "| Step ID | Tool | Command | Status |",
            "|---------|------|---------|--------|",
        ]
    )
    for row in command_rows:
        # B10: Escape pipe characters in commands for markdown table safety
        cmd = str(row.get("command", "")).replace("|", "\\|")
        lines.append(
            f"| {row.get('step_id', '')} "
            f"| {row.get('tool_id', '')} "
            f"| `{cmd}` "
            f"| {row.get('status', '')} |"
        )

    lines.extend(
        [
            "",
            "## Interpretation Notes",
            "",
            "- All tools were executed with the parameters recorded above.",
            "- Tool versions marked as `not_captured` did not have a `version_command` configured.",
            "- Tool versions marked as `capture_failed` had a version command "
            "but it returned a non-zero exit code.",
            "- Reference databases without version information should be treated as unversioned.",
            "",
            f"*Generated by ABI {title.lower()} provenance system.*",
        ]
    )

    markdown = "\n".join(lines) + "\n"
    if path:
        output_path = Path(path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(markdown, encoding="utf-8")
    return markdown


# ── PipelineProgressRecorder ───────────────────────────────────────────
# This is the LIVE progress recorder. It is instrumented into every pipeline
# run so that dashboards and monitoring tools can observe the run in real time.
# When `record_progress: false` is set, the pipeline uses the cheaper
# write_minimal_progress_artifacts() function instead.
#
# 这是实时进度记录器。它被植入每个管道运行中，使仪表盘和监控工具能够实时观察运行。
# 当 `record_progress: false` 时，管道使用更轻量的 write_minimal_progress_artifacts()。


class PipelineProgressRecorder:
    """Thread-safe writer for live pipeline progress.

    # Two-output design / 双输出设计
    - **progress.jsonl**: Append-only JSON-line stream. Every event (run_started,
      step_started, step_completed/step_failed, run_completed) is one line.
      Append-only means no partial-write corruption; the audit trail is always
      recoverable even after a crash. / 追加式 JSON 行流，即使崩溃审计跟踪也可恢复

    - **progress.json**: Atomic snapshot. Written via tmp+rename to avoid readers
      seeing a half-written file. Polling dashboards read this, not the JSONL.
      / 原子快照，通过 tmp+rename 避免读者看到半写文件

    # Thread safety / 线程安全
    A single `threading.Lock` serializes all access to the in-memory snapshot
    dict, the JSONL append, and the snapshot file write. This guarantees that
    concurrent step_started/step_completed calls from different worker threads
    produce correct counter increments and consistent snapshot state. / 单一锁
    串行化所有对内存快照、JSONL 和 snapshot 文件的访问。

    # Event-driven state machine / 事件驱动状态机
    `_apply_event()` mutates `self._snapshot` in response to each event, keeping
    per-step and per-sample counters in sync. This is intentionally kept as a
    sequence of imperative updates rather than a formal state machine to keep
    the code readable and easy to verify by inspection. / _apply_event() 响应每
    个事件修改 self._snapshot，保持步骤级和样本级计数同步。
    """

    def __init__(self, provenance_dir: str | Path) -> None:
        # ensure_directory returns the dir after creating if needed / 确保目录存在
        self.provenance_dir = ensure_directory(provenance_dir, label="Provenance directory")
        # Two output files: events stream + snapshot / 两个输出文件：事件流 + 快照
        self.events_path = self.provenance_dir / "progress.jsonl"
        self.snapshot_path = self.provenance_dir / "progress.json"
        # Single lock protects all mutable state / 单锁保护所有可变状态
        self._lock = threading.Lock()
        # In-memory snapshot mutated by _apply_event / 内存快照由 _apply_event 修改
        self._snapshot: Dict[str, Any] = {}

    @property
    def paths(self) -> Dict[str, Path]:
        """Return paths to both output files for external consumers."""
        return {"events": self.events_path, "snapshot": self.snapshot_path}

    def start_run(
        self,
        plan: Any,
        *,
        dry_run: bool,
        parallel: bool,
        workers: int,
    ) -> None:
        """Initialize the snapshot and emit the run_started event.

        # What happens / 做了什么
        1. Populates the snapshot with every step in "pending" status and every
           sample in "pending" status. / 将所有步骤和样本初始化为 "pending"
        2. Emits run_started to the JSONL stream.
        3. Writes the initial snapshot atomically.
        """
        # Build per-step state: every step starts as "pending" / 每步骤初始 "pending"
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
        # Build per-sample state for sample-level progress tracking / 每样本状态
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
        # The snapshot is the authoritative in-memory state / snapshot 是权威内存状态
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
        """Record that a step has begun execution.

        Called by a worker thread just before it invokes the tool. / 工作线程在执行工具前调用
        """
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
        """Record that a step has finished (success or failure).

        # Event naming / 事件命名
        - status="failed" → emitted as "step_failed" so dashboards can filter
          on event type without inspecting the payload. / 仪表盘可按事件类型过滤
        - All other statuses → emitted as "step_completed". / 其余状态用 step_completed
        """
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
        """Emit run_completed and finalize the snapshot.

        Called after all steps have been processed (or the pipeline aborted).
        / 所有步骤处理完毕后（或管道中止后）调用
        """
        self.record("run_completed", {"status": status})

    def record(self, event: str, payload: Mapping[str, Any]) -> None:
        """The single entry point for all progress events.

        # Serialization guarantee / 序列化保证
        Under the lock we:
        1. Update the in-memory snapshot via _apply_event(). / 更新内存快照
        2. Append one JSON line to progress.jsonl. / 追加一行到 JSONL
        3. Atomically overwrite progress.json via tmp+rename. / 原子覆盖进度文件

        All three steps happen before the lock is released, so a reader of
        progress.json always sees state consistent with the JSONL stream up to
        some point.
        / 锁释放前完成所有三步，读取 progress.json 时状态与 JSONL 一致。
        """
        timestamp = _timestamp()
        record = {
            "timestamp": timestamp,
            "event": event,
            "payload": dict(payload),
        }
        with self._lock:
            # Mutate snapshot counters and per-step state / 修改快照计数和步骤状态
            self._apply_event(event, payload, timestamp)
            # Append to JSONL stream for audit trail / 追加到审计流
            with self.events_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
            # Keep last_event for consumers that want the most recent event / 保留最后事件
            self._snapshot["last_event"] = record
            # Atomic snapshot write / 原子快照写入
            self._write_snapshot()

    def _apply_event(self, event: str, payload: Mapping[str, Any], timestamp: str) -> None:
        """Mutate self._snapshot to reflect the event.

        # Design rationale / 设计理由
        This is an imperative state-update function, not a generic event
        reducer. It mutates the snapshot dict in place for performance (no
        copies) and simplicity (one place to see all state transitions).
        / 这是一个命令式的状态更新函数，非通用事件归约器。直接修改 dict 提高性能和简洁性。

        # State transitions / 状态转换
        - step_started: step→running, sample→running, add to current_steps / 步骤和样本进入running
        - step_completed: step→success/failed, sample counters updated / 更新步骤和样本计数
        - step_failed: same as completed but also marks overall run as failed / 同时标记运行失败
        - run_completed: final counts, clear current_steps, mark finished_at / 最终计数清空当前步骤
        """
        # Handle run-level completion / 处理运行级别完成
        if event == "run_completed":
            self._snapshot["status"] = str(payload.get("status", "completed"))
            self._snapshot["finished_at"] = timestamp
            self._snapshot["running_step_count"] = 0
            self._snapshot["current_steps"] = []
            # Move any "running" samples to "completed" / 将 "running" 样本改为 "completed"
            for sample in self._snapshot.get("samples", {}).values():
                if sample.get("status") == "running":
                    sample["status"] = "completed"
                    sample["current_step_id"] = ""
            return
        # Only handle step-level events / 仅处理步骤级别事件
        if event not in {"step_started", "step_completed", "step_failed"}:
            return

        step_id = str(payload.get("step_id", ""))
        sample_id = str(payload.get("sample_id", ""))
        # Find the step entry in the steps list (linear scan, but step counts
        # are typically <1000 so this is fine) / 线性扫描查找步骤条目（步骤数通常<1000）
        step_state = self._step_state(step_id)
        if not step_state:
            return

        # ── step_started ── / 步骤开始
        if event == "step_started":
            step_state["status"] = "running"
            step_state["started_at"] = timestamp
            # Track which steps are concurrently running / 跟踪并发运行的步骤
            current_steps = list(self._snapshot.get("current_steps", []))
            if step_id not in current_steps:
                current_steps.append(step_id)
            self._snapshot["current_steps"] = current_steps
            self._snapshot["running_step_count"] = len(current_steps)
            # Update sample-level state / 更新样本级别状态
            if sample_id and sample_id in self._snapshot.get("samples", {}):
                sample = self._snapshot["samples"][sample_id]
                sample["status"] = "running"
                sample["current_step_id"] = step_id
            return

        # ── step_completed / step_failed ── / 步骤完成/失败
        status = str(payload.get("status", "success"))
        step_state["status"] = status
        step_state["reason"] = str(payload.get("reason", ""))
        step_state["return_code"] = payload.get("return_code", "")
        step_state["parsed_status"] = str(payload.get("parsed_status", ""))
        step_state["standard_tables"] = str(payload.get("standard_tables", ""))
        step_state["finished_at"] = timestamp

        # Remove this step from the currently-running list / 从当前运行列表中移除
        current_steps = [
            current for current in self._snapshot.get("current_steps", []) if current != step_id
        ]
        self._snapshot["current_steps"] = current_steps
        self._snapshot["running_step_count"] = len(current_steps)
        # Increment global completed counter / 递增全局完成计数
        self._snapshot["completed_step_count"] = (
            int(self._snapshot.get("completed_step_count", 0)) + 1
        )
        # If failed, increment failed counter and mark run as failed / 失败则递增失败计数
        if status == "failed":
            self._snapshot["failed_step_count"] = (
                int(self._snapshot.get("failed_step_count", 0)) + 1
            )
            self._snapshot["status"] = "failed"
        # Update sample-level counters / 更新样本级别计数
        if sample_id and sample_id in self._snapshot.get("samples", {}):
            sample = self._snapshot["samples"][sample_id]
            sample["completed_step_count"] = int(sample.get("completed_step_count", 0)) + 1
            if status == "failed":
                sample["failed_step_count"] = int(sample.get("failed_step_count", 0)) + 1
                sample["status"] = "failed"
            elif sample.get("status") == "running":
                # Sample is no longer running an active step / 样本不再有活动步骤
                sample["current_step_id"] = ""

    def _step_state(self, step_id: str) -> Dict[str, Any] | None:
        """Look up the step dict in the snapshot by step_id.

        Returns None if the step_id is not found (defensive: shouldn't happen
        in practice unless event ordering is violated).
        / 按 step_id 查找步骤字典，找不到返回 None。
        """
        for step in self._snapshot.get("steps", []):
            if isinstance(step, dict) and step.get("step_id") == step_id:
                return step
        return None

    def _write_snapshot(self) -> None:
        """Atomically write the current snapshot to progress.json.

        # Atomic write pattern / 原子写入模式
        Write to a .tmp file first, then os.replace() (atomic on POSIX). This
        guarantees external readers never see a partially-written file. / 先写
        .tmp 文件再用 replace() 原子替换，读者永不见半写文件。
        """
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
    """Write stable progress artifacts when live progress recording is disabled.

    # When is this used? / 何时使用？
    When `record_progress: false` is set in the pipeline config. Instead of
    instrumenting every step with the PipelineProgressRecorder, the pipeline
    calls this function once at the end with the complete command_rows list.
    / 当配置中设置 `record_progress: false` 时，管道结束时调用此函数一次。

    # What it produces / 生成内容
    - progress.jsonl: Exactly two events (run_started + run_completed). / 恰好两个事件
    - progress.json: A snapshot that looks structurally identical to the live
      version, but with `record_progress: false` so consumers know it is a
      post-hoc summary rather than a real-time instrumented run. / 结构与实时版相同但有标记

    # Design trade-off / 设计取舍
    No per-step start events are recorded (started_at is empty for every step).
    This is intentional: the minimal mode exists for batch/dry-run scenarios
    where per-step timing data would be meaningless overhead.
    / 不记录逐步骤启动事件（started_at 为空）。这是有意为之：最小模式用于批量/试运行场景。
    """
    provenance = ensure_directory(provenance_dir, label="Provenance directory")
    events_path = provenance / "progress.jsonl"
    snapshot_path = provenance / "progress.json"
    # Index command rows by step_id for O(1) lookup / 按 step_id 索引以 O(1) 查找
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
    # Minimal JSONL: only start and end events / 最小 JSONL：只有开始和结束事件
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

    # Build snapshot with post-hoc status / 构建事后状态快照
    snapshot = {
        "project_name": getattr(plan, "project_name", ""),
        "status": status,
        "dry_run": dry_run,
        "parallel": parallel,
        "workers": workers,
        "record_progress": False,  # signals to consumers this is not live / 标记非实时
        "started_at": started_at,
        "finished_at": finished_at,
        "total_step_count": total_step_count,
        "completed_step_count": completed_step_count,
        "failed_step_count": failed_step_count,
        "running_step_count": 0,
        "current_steps": [],
        # Derive per-sample and per-step status from command_rows / 从命令行推导样本和步骤状态
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
# These are package-private utilities used by the classes and functions above.
# They are not exported in __all__.
# 以下是包内部工具函数，不被 __all__ 导出。


def _step_payload(step: Any) -> Dict[str, Any]:
    """Extract identifying fields from a pipeline Step for event payloads.

    Uses duck-typing via attribute access (not isinstance checks) so any object
    with .step_id, .sample_id, .step_name, .tool_id, .category works. / 通过
    属性访问而非类型检查实现鸭子类型。
    """
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
    """Compute per-sample status for the minimal (post-hoc) snapshot.

    # Status derivation / 状态推导
    - If any step for this sample failed → "failed" / 任何步骤失败则 "failed"
    - If all steps completed (rows exist) → "completed" / 所有步骤有行则 "completed"
    - If no rows for this sample → "pending" / 无行则 "pending"
    """
    samples: Dict[str, Any] = {}
    for sample in getattr(plan, "samples", []):
        sample_id = str(getattr(sample, "sample_id", ""))
        if not sample_id:
            continue
        # Filter command rows that belong to this sample / 过滤属于此样本的命令行
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
    """Compute per-step status for the minimal (post-hoc) snapshot.

    # Key difference from live mode / 与实时模式的关键区别
    - `started_at` is always "" because we have no per-step start timing data.
      / started_at 始终为空，因为没有逐步骤启动时间数据。
    - `finished_at` is set to the snapshot timestamp for steps that have a
      corresponding row in the commands TSV. / 有对应命令行则有 finished_at。
    - Steps not present in command_rows are left as "pending". / 不在命令行中的步骤为 "pending"
    """
    steps = []
    for step in getattr(plan, "steps", []):
        # Look up the actual outcome from commands.tsv / 从 commands.tsv 查找实际结果
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
    """Coerce any value to a TSV-safe string. None → "" to keep columns aligned.

    Embedded tabs and newlines are replaced with spaces so they cannot corrupt
    the TSV column structure.

    # Why not just str(None)? / 为什么不直接用 str(None)？
    `str(None)` produces the literal string "None", which is ambiguous (did we
    mean the Python None or the user-specified value "None"?). We convert None
    to the empty string instead, which is unambiguous in TSV: an empty cell
    means "no value".
    """
    if value is None:
        return ""
    result = str(value)
    if any(ch in result for ch in ("\t", "\n", "\r")):
        result = result.replace("\t", "  ").replace("\n", " | ").replace("\r", "")
    return result


def _timestamp() -> str:
    """Return the current UTC-ish local time as an ISO 8601 string with second precision.

    `timespec="seconds"` truncates to second granularity, which is sufficient
    for pipeline progress events where sub-second precision adds noise. / 秒级
    精度足够管道进度事件使用。
    """
    return datetime.now().isoformat(timespec="seconds")
