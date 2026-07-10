"""Nextflow ABI runtime backend."""

from __future__ import annotations

import csv
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping

from abi.config import resolved_mamba_root
from abi.dag import ABIDAG, infer_dag, process_name
from abi.execution_policy import ExecutionPolicy, ResourceOverride
from abi.exporters import NextflowExporter
from abi.results import ABIResultWriter
from abi.runtimes.base import RuntimeOptions, RuntimeResult
from abi.schemas import ABIError
from abi.timeouts import (
    DEFAULT_TOOL_TIMEOUT_SECONDS,
    mapping_block,
    timeout_from_env_or_value,
)


class NextflowRuntime:
    """Run ABI plans through generated Nextflow DSL2 workflows."""

    def __init__(self, plugin: Any, *, options: RuntimeOptions | None = None) -> None:
        self.plugin = plugin
        self.options = options or RuntimeOptions(engine="nextflow", smoke=True)
        self.exporter = NextflowExporter()

    def _execution_policy(self) -> ExecutionPolicy:
        return ExecutionPolicy(
            mamba_root=self.options.mamba_root,
            container_image=self.options.container_image,
            container_runtime=self.options.container_runtime,
            resource_profile=self.options.resource_profile,
            invocation_overrides=ResourceOverride(
                cpu=self.options.cpu_override,
                memory=self.options.memory_override,
                walltime=self.options.walltime_override,
                accelerator=self.options.accelerator_override,
            ),
        )

    def check(self) -> None:
        resolve_nextflow_bin(self.options.nextflow_bin, self.options.mamba_root)

    def dry_run(self, plan: object, config: Mapping[str, Any]) -> RuntimeResult:
        result_dir = Path(str(config["outdir"]))
        nextflow_dir = result_dir / "nextflow"
        workflow_path = self.options.workflow or nextflow_dir / "workflow.nf"
        dag = infer_dag(getattr(plan, "steps", []), sequential_fallback=True)
        self.exporter.write(
            plan,
            config,
            self.plugin.registry(),
            workflow_path,
            smoke=self.options.smoke,
            mamba_root=self.options.mamba_root,
            dag=dag,
            execution_policy=self._execution_policy(),
            plugin_id=str(getattr(self.plugin, "plugin_id", getattr(plan, "analysis_type", ""))),
        )
        writer = ABIResultWriter(self.plugin, self.plugin.registry())
        outputs = writer.write(
            plan=plan,
            config=config,
            command_rows=_command_rows(
                plan,
                self.plugin.registry(),
                self.exporter,
                dag=dag,
                return_code=0,
                smoke=self.options.smoke,
                trace_rows=[],
                dry_run=True,
            ),
            status="dry_run",
            return_code=0,
            engine="nextflow",
            smoke=self.options.smoke,
            extra_summary={"workflow": str(workflow_path), "dag": _dag_summary(dag)},
            extra_environment=_nextflow_environment(
                workflow_path=workflow_path,
                work_dir=self.options.work_dir or nextflow_dir / "work",
                nxf_home=self.options.nxf_home or nextflow_dir / "nxf_home",
                trace_path=nextflow_dir / "trace.txt",
                timeline_path=nextflow_dir / "timeline.html",
                options=self.options,
            ),
        )
        outputs["workflow"] = workflow_path
        return RuntimeResult(status="dry_run", return_code=0, outputs=outputs)

    def run(self, plan: object, config: Mapping[str, Any]) -> RuntimeResult:
        registry = self.plugin.registry()
        result_dir = Path(str(config["outdir"]))
        nextflow_dir = result_dir / "nextflow"
        workflow_path = self.options.workflow or nextflow_dir / "workflow.nf"
        work_dir = self.options.work_dir or nextflow_dir / "work"
        nxf_home = self.options.nxf_home or nextflow_dir / "nxf_home"
        stdout_path = nextflow_dir / "nextflow.stdout.log"
        stderr_path = nextflow_dir / "nextflow.stderr.log"
        trace_path = nextflow_dir / "trace.txt"
        timeline_path = nextflow_dir / "timeline.html"
        nextflow_bin = resolve_nextflow_bin(self.options.nextflow_bin, self.options.mamba_root)
        dag = infer_dag(getattr(plan, "steps", []), sequential_fallback=True)

        workflow_path = self.exporter.write(
            plan,
            config,
            registry,
            workflow_path,
            smoke=self.options.smoke,
            mamba_root=self.options.mamba_root,
            dag=dag,
            execution_policy=self._execution_policy(),
            plugin_id=str(getattr(self.plugin, "plugin_id", getattr(plan, "analysis_type", ""))),
        )
        nextflow_dir.mkdir(parents=True, exist_ok=True)
        work_dir.mkdir(parents=True, exist_ok=True)
        nxf_home.mkdir(parents=True, exist_ok=True)
        command = [
            str(nextflow_bin),
            "run",
            str(workflow_path),
            "-work-dir",
            str(work_dir),
            "-with-trace",
            str(trace_path),
            "-with-timeline",
            str(timeline_path),
        ]
        if self.options.profile:
            command.extend(["-profile", self.options.profile])
        if self.options.executor:
            command.extend(["-process.executor", self.options.executor])
        if self.options.resume:
            command.append("-resume")

        env = os.environ.copy()
        env.setdefault("NXF_ANSI_LOG", "false")
        env["NXF_HOME"] = str(nxf_home)
        with (
            stdout_path.open("w", encoding="utf-8") as stdout_handle,
            stderr_path.open("w", encoding="utf-8") as stderr_handle,
        ):
            timeout_seconds = _nextflow_timeout_seconds(config, self.options)
            try:
                result = subprocess.run(
                    command,
                    cwd=nextflow_dir,
                    env=env,
                    stdout=stdout_handle,
                    stderr=stderr_handle,
                    text=True,
                    check=False,
                    timeout=timeout_seconds,
                )
            except subprocess.TimeoutExpired as exc:
                raise ABIError(
                    "Nextflow run timed out after "
                    f"{timeout_seconds:g}s; stdout: {stdout_path}; stderr: {stderr_path}"
                ) from exc

        trace_rows = parse_nextflow_trace(trace_path)
        remote_scheduler_jobs = _remote_scheduler_jobs(trace_rows)
        status = "success" if result.returncode == 0 else "failed"
        writer = ABIResultWriter(self.plugin, registry)
        outputs = writer.write(
            plan=plan,
            config=config,
            command_rows=_command_rows(
                plan,
                registry,
                self.exporter,
                dag=dag,
                return_code=result.returncode,
                smoke=self.options.smoke,
                trace_rows=trace_rows,
                dry_run=False,
            ),
            status=status,
            return_code=result.returncode,
            engine="nextflow",
            smoke=self.options.smoke,
            trace_rows=trace_rows,
            extra_summary={
                "workflow": str(workflow_path),
                "work_dir": str(work_dir),
                "nxf_home": str(nxf_home),
                "trace": str(trace_path),
                "timeline": str(timeline_path),
                "stdout": str(stdout_path),
                "stderr": str(stderr_path),
                "command": " ".join(command),
                "executor_profile": self.options.profile or "",
                "executor": self.options.executor or "",
                "resume": self.options.resume,
                "remote_scheduler_jobs": remote_scheduler_jobs,
                "dag": _dag_summary(dag),
            },
            extra_environment=_nextflow_environment(
                workflow_path=workflow_path,
                work_dir=work_dir,
                nxf_home=nxf_home,
                trace_path=trace_path,
                timeline_path=timeline_path,
                options=self.options,
            ),
        )
        outputs.update(
            {
                "workflow": workflow_path,
                "work_dir": work_dir,
                "nextflow_stdout": stdout_path,
                "nextflow_stderr": stderr_path,
                "nextflow_trace": trace_path,
                "nextflow_timeline": timeline_path,
            }
        )
        if result.returncode != 0:
            raise ABIError(
                f"Nextflow run failed with exit code {result.returncode}; stderr: {stderr_path}"
            )
        return RuntimeResult(status=status, return_code=result.returncode, outputs=outputs)


def _nextflow_timeout_seconds(
    config: Mapping[str, Any],
    options: RuntimeOptions,
) -> float | None:
    execution = mapping_block(config, "execution")
    value = options.timeout_seconds
    if value is None:
        value = execution.get("nextflow_timeout_seconds")
    if value is None:
        value = execution.get("tool_timeout_seconds")
    return timeout_from_env_or_value(
        "ABI_NEXTFLOW_TIMEOUT_SECONDS",
        value,
        default=DEFAULT_TOOL_TIMEOUT_SECONDS,
    )


def resolve_nextflow_bin(
    nextflow_bin: Path | None,
    mamba_root: Path | None,
) -> Path:
    candidates = []
    if nextflow_bin:
        candidates.append(nextflow_bin)
    env_value = os.environ.get("ABI_NEXTFLOW_BIN")
    if env_value:
        candidates.append(Path(env_value))
    root = Path(mamba_root or resolved_mamba_root())
    candidates.append(root / "envs" / "autoplasm-nextflow" / "bin" / "nextflow")
    path_value = shutil.which("nextflow")
    if path_value:
        candidates.append(Path(path_value))
    for candidate in candidates:
        if candidate.exists() and os.access(candidate, os.X_OK):
            return candidate.resolve()
    raise ABIError(
        "Nextflow executable was not found. Create the repository-local environment with "
        "`bash scripts/cloud/01_envs.sh --env autoplasm-nextflow` or "
        "`.mamba/bin/micromamba create -y -p .mamba/envs/autoplasm-nextflow "
        "-f envs/autoplasm-nextflow.yml`, or pass --nextflow-bin."
    )


def parse_nextflow_trace(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def _command_rows(
    plan: Any,
    registry: Any,
    exporter: NextflowExporter,
    *,
    dag: ABIDAG,
    return_code: int,
    smoke: bool,
    trace_rows: Iterable[Mapping[str, str]],
    dry_run: bool,
) -> list[dict[str, Any]]:
    trace_by_name = _trace_by_process_name(trace_rows)
    rows = []
    fallback_status = "dry_run" if dry_run else ("success" if return_code == 0 else "failed")
    for binding in dag.bindings:
        step = binding.step
        trace = trace_by_name.get(binding.process_name, {})
        status = _status_from_trace(trace, fallback=fallback_status)
        step_return_code = trace.get("exit") or ("" if dry_run else return_code)
        rows.append(
            {
                "step_id": step.step_id,
                "sample_id": step.sample_id,
                "step_name": step.step_name,
                "tool_id": step.tool_id,
                "category": step.category,
                "command": exporter.command_for_step(step, registry, smoke=smoke),
                "status": status,
                "return_code": step_return_code,
                "remote_scheduler_job_id": _remote_scheduler_job_id(trace),
                "reason": "" if status in {"success", "dry_run"} else "Nextflow process failed",
                "parsed_status": "smoke" if smoke and status == "success" else "",
                "standard_tables": "",
            }
        )
    return rows


def _trace_by_process_name(rows: Iterable[Mapping[str, str]]) -> Dict[str, Mapping[str, str]]:
    result: Dict[str, Mapping[str, str]] = {}
    for row in rows:
        raw_name = str(row.get("process") or row.get("name") or row.get("task_id") or "")
        process = raw_name.split(" ", 1)[0].split(":")[-1].strip()
        if process:
            result[process] = row
        tag_match = re.search(r"\(([^)]+)\)", raw_name)
        if tag_match:
            result[process_name(tag_match.group(1))] = row
    return result


def _status_from_trace(row: Mapping[str, str], *, fallback: str) -> str:
    if not row:
        return fallback
    status = str(row.get("status", "")).upper()
    exit_code = str(row.get("exit", ""))
    if status in {"COMPLETED", "CACHED"} or exit_code == "0":
        return "success"
    if status:
        return "failed"
    return fallback


def _remote_scheduler_jobs(rows: Iterable[Mapping[str, str]]) -> list[Dict[str, str]]:
    jobs: list[Dict[str, str]] = []
    for row in rows:
        scheduler_job_id = _remote_scheduler_job_id(row)
        if not scheduler_job_id:
            continue
        jobs.append(
            {
                "scheduler_job_id": scheduler_job_id,
                "process": str(row.get("process") or row.get("name") or ""),
                "task_id": str(row.get("task_id", "")),
                "status": str(row.get("status", "")),
                "executor": str(row.get("executor", "")),
            }
        )
    return jobs


def _remote_scheduler_job_id(row: Mapping[str, str]) -> str:
    normalized = {_normalize_trace_key(key): value for key, value in row.items()}
    for key in (
        "nativeid",
        "jobid",
        "schedulerjobid",
        "clusterjobid",
        "remotejobid",
        "externalid",
    ):
        value = str(normalized.get(key, "")).strip()
        if value:
            return value
    return ""


def _normalize_trace_key(key: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(key).lower())


def _nextflow_environment(
    *,
    workflow_path: Path,
    work_dir: Path,
    nxf_home: Path,
    trace_path: Path,
    timeline_path: Path,
    options: RuntimeOptions,
) -> Dict[str, Any]:
    return {
        "workflow": str(workflow_path),
        "work_dir": str(work_dir),
        "nxf_home": str(nxf_home),
        "trace": str(trace_path),
        "timeline": str(timeline_path),
        "mamba_root": str(options.mamba_root or resolved_mamba_root()),
        "executor_profile": options.profile or "",
        "executor": options.executor or "",
        "resume": options.resume,
    }


def _dag_summary(dag: ABIDAG) -> Dict[str, Any]:
    return {
        "roots": dag.roots,
        "edges": dag.edges,
        "topological_order": dag.topological_order,
    }
