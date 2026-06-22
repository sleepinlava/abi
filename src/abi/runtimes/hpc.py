"""Native Slurm-first HPC runtime with real dependencies and resumable steps."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from hashlib import sha256
from pathlib import Path
from typing import Any, Mapping

from abi.config import PROJECT_ROOT
from abi.contracts.step_contract import compute_file_checksum, load_checksums
from abi.dag import ABIDAG, infer_dag
from abi.internal import internal_handler_spec, run_plugin_preflight
from abi.results import ABIResultWriter
from abi.runtimes.base import RuntimeOptions, RuntimeResult
from abi.schemas import ABIError
from abi.step_runner import StepExecutionResult, execute_step, write_step_payload
from abi.tables import StandardTableManager
from abi.tools import ResourceSpec, resolve_container_image, resolve_resources

SLURM_SUCCESS_STATES = frozenset({"COMPLETED"})
SLURM_FAILURE_STATES = frozenset(
    {
        "BOOT_FAIL",
        "CANCELLED",
        "DEADLINE",
        "FAILED",
        "NODE_FAIL",
        "OUT_OF_MEMORY",
        "PREEMPTED",
        "REVOKED",
        "TIMEOUT",
    }
)
SLURM_TERMINAL_STATES = SLURM_SUCCESS_STATES | SLURM_FAILURE_STATES


class HpcRuntime:
    """Generate, submit, monitor, and collect one scheduler job per DAG step."""

    def __init__(self, plugin: Any, *, options: RuntimeOptions | None = None) -> None:
        self.plugin = plugin
        self.options = options or RuntimeOptions(engine="hpc")
        self._script_steps: dict[str, Any] = {}
        self._script_by_step: dict[str, Path] = {}
        self._result_by_step: dict[str, Path] = {}
        self._driver_results: dict[str, StepExecutionResult] = {}
        self._resumed_steps: set[str] = set()
        self._dag: ABIDAG | None = None

    def check(self) -> None:
        scheduler = self.options.scheduler or "slurm"
        required = (
            ("sbatch", "squeue", "sacct", "scancel")
            if scheduler == "slurm"
            else ("qsub", "qstat", "qdel")
        )
        missing = [command for command in required if not shutil.which(command)]
        if missing:
            raise ABIError(f"HPC scheduler {scheduler!r} commands not found: {', '.join(missing)}")

    def dry_run(self, plan: object, config: Mapping[str, Any]) -> RuntimeResult:
        self._generate_all_scripts(plan, config)
        manifest = self._write_hpc_manifest({}, {}, config, dry_run=True)
        return RuntimeResult(
            status="dry_run",
            return_code=0,
            outputs={
                "scripts_dir": self._scripts_dir(config),
                "hpc_manifest": manifest,
                "submit_command": Path("/dev/null"),
            },
        )

    def run(self, plan: object, config: Mapping[str, Any]) -> RuntimeResult:
        self.check()
        report = run_plugin_preflight(self.plugin, config, engine="hpc")
        if str(report.get("status", "pass")) == "fail":
            raise ABIError(
                f"{self.plugin.plugin_id} preflight failed: "
                + "; ".join(str(item) for item in report.get("recommendations", []))
            )
        self._prepare_dirs(config)
        self._dag = infer_dag(getattr(plan, "steps", []), sequential_fallback=False)
        self._run_driver_steps(plan, config)
        scripts = self._generate_all_scripts(plan, config)
        try:
            job_ids = self._submit_jobs(scripts)
        except Exception:
            self._cancel_jobs(list(getattr(self, "_submitted_job_ids", {}).values()))
            raise
        timeout = self.options.timeout_seconds or 3600 * 24 * 7
        statuses = self._poll_until_complete(job_ids, timeout)
        return self._collect_results(plan, config, job_ids, statuses)

    def _prepare_dirs(self, config: Mapping[str, Any]) -> None:
        for path in (
            self._scripts_dir(config),
            self._payloads_dir(config),
            self._step_results_dir(config),
            Path(_log_dir(config)),
            Path(str(config["outdir"])) / "tables",
        ):
            path.mkdir(parents=True, exist_ok=True)

    def _scripts_dir(self, config: Mapping[str, Any]) -> Path:
        return Path(str(config.get("outdir", "."))) / "provenance" / "hpc_scripts"

    def _payloads_dir(self, config: Mapping[str, Any]) -> Path:
        return Path(str(config.get("outdir", "."))) / "provenance" / "step_payloads"

    def _step_results_dir(self, config: Mapping[str, Any]) -> Path:
        return Path(str(config.get("outdir", "."))) / "provenance" / "step_results"

    def _provenance_dir(self, config: Mapping[str, Any]) -> Path:
        return Path(str(config.get("outdir", "."))) / "provenance"

    def _run_driver_steps(self, plan: object, config: Mapping[str, Any]) -> None:
        self._driver_results = {}
        for step in getattr(plan, "steps", []):
            handler_id, scope = internal_handler_spec(step)
            if getattr(step, "tool_id", "") != "internal" or scope != "driver":
                continue
            result = execute_step(
                self.plugin,
                step,
                config,
                provenance_dir=self._provenance_dir(config),
            )
            self._driver_results[step.step_id] = result
            self._write_step_result(step.step_id, result, config)
            if result.status != "success":
                raise ABIError(
                    f"Driver handler {handler_id!r} failed before submission: {result.reason}"
                )

    def _generate_all_scripts(self, plan: object, config: Mapping[str, Any]) -> list[Path]:
        self._prepare_dirs(config)
        dag = self._dag or infer_dag(getattr(plan, "steps", []), sequential_fallback=False)
        self._dag = dag
        registry = self.plugin.registry()
        self._script_steps = {}
        self._script_by_step = {}
        self._result_by_step = {}
        self._resumed_steps = set()
        scripts: list[Path] = []
        for step_id in dag.topological_order:
            binding = dag.binding_for(step_id)
            step = binding.step
            _, scope = internal_handler_spec(step)
            if step.tool_id == "internal" and scope == "driver":
                continue
            if self.options.resume and self._step_is_resumable(step, config):
                self._resumed_steps.add(step.step_id)
                continue
            tool_meta = registry.get(step.tool_id) if registry.has(step.tool_id) else {}
            resources = self._resolve_step_resources(step.tool_id, tool_meta, config)
            container = resolve_container_image(
                step.tool_id,
                tool_meta,
                config=config,
                cli_image=self.options.container_image,
            )
            safe_id = _safe_name(step.step_id)
            script_path = self._scripts_dir(config) / f"{safe_id}.sh"
            payload_path = self._payloads_dir(config) / f"{safe_id}.json"
            result_path = self._step_results_dir(config) / f"{safe_id}.json"
            write_step_payload(
                payload_path,
                plugin_id=str(getattr(self.plugin, "plugin_id", "test_plugin")),
                step=step,
                config=config,
                provenance_dir=self._provenance_dir(config),
                result_path=result_path,
            )
            self._write_single_script(
                script_path,
                step,
                binding,
                resources,
                container,
                config,
                dag,
                payload_path=payload_path,
            )
            scripts.append(script_path)
            self._script_steps[script_path.name] = step
            self._script_by_step[step.step_id] = script_path
            self._result_by_step[step.step_id] = result_path
        return scripts

    def _resolve_step_resources(
        self,
        tool_id: str,
        tool_meta: Mapping[str, Any],
        config: Mapping[str, Any],
    ) -> ResourceSpec:
        cli = None
        if any(
            getattr(self.options, field, None)
            for field in ("cpu_override", "memory_override", "walltime_override")
        ):
            cli = ResourceSpec(
                cpu=self.options.cpu_override or 1,
                memory=self.options.memory_override or "4GB",
                walltime=self.options.walltime_override or "01:00:00",
            )
        return resolve_resources(
            tool_id,
            tool_meta,
            config=config,
            cli_overrides=cli,
            resource_profile=self.options.resource_profile,
        )

    def _write_single_script(
        self,
        path: Path,
        step: Any,
        binding: Any,
        resources: ResourceSpec,
        container: str | None,
        config: Mapping[str, Any],
        dag: ABIDAG,
        *,
        payload_path: Path | None = None,
    ) -> None:
        del binding, dag
        scheduler = self.options.scheduler or "slurm"
        if scheduler == "pbs":
            directives = resources.to_pbs_directives()
            log_dir = _scheduler_value(_log_dir(config), "log_dir")
            extra = [f"#PBS -N {_safe_name(step.step_id)}", f"#PBS -o {log_dir}"]
            extra.append(f"#PBS -e {log_dir}")
            if self.options.partition:
                extra.append(f"#PBS -q {_scheduler_value(self.options.partition, 'partition')}")
            if self.options.account:
                extra.append(f"#PBS -A {_scheduler_value(self.options.account, 'account')}")
        else:
            directives = resources.to_slurm_directives()
            log_dir = _scheduler_value(_log_dir(config), "log_dir")
            extra = [
                f"#SBATCH --job-name={_safe_name(step.step_id)}",
                f"#SBATCH --output={log_dir}/%x_%j.out",
                f"#SBATCH --error={log_dir}/%x_%j.err",
            ]
            for flag, value in (
                ("partition", self.options.partition),
                ("account", self.options.account),
                ("qos", self.options.qos),
                ("mail-type", self.options.mail_type),
                ("mail-user", self.options.mail_user),
            ):
                if value:
                    extra.append(f"#SBATCH --{flag}={_scheduler_value(value, flag)}")
        payload = payload_path or path.with_suffix(".payload.json")
        env_lines = self._render_env(config, container)
        lines = [
            "#!/bin/bash",
            "set -euo pipefail",
            "# Generated by ABI HpcRuntime",
            f"# Step: {step.step_id}",
            "",
            *directives,
            *extra,
            "",
            "# --- Environment ---",
            *env_lines,
            "",
            "# --- Execution ---",
            "# Batch replacement for legacy `abi dispatch` step execution",
            f"abi run-step --payload-file {shlex_quote(str(payload))}",
        ]
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        path.chmod(0o700)

    def _dependency_job_ids(self, binding: Any, dag: ABIDAG) -> list[str]:
        del dag
        if not binding.dependencies:
            return []
        return [f"${{JOB_{_safe_name(dependency)}}}" for dependency in binding.dependencies]

    def _render_env(self, config: Mapping[str, Any], container: str | None) -> list[str]:
        mamba_root = str(
            self.options.mamba_root
            or config.get("mamba_root")
            or os.environ.get("ABI_MAMBA_ROOT")
            or PROJECT_ROOT / ".mamba"
        )
        lines = [f"export ABI_MAMBA_ROOT={shlex_quote(mamba_root)}"]
        abi_bin = Path(mamba_root) / "envs" / "abi-base" / "bin"
        configured_env = str(config.get("env_name", "abi-base"))
        configured_bin = Path(mamba_root) / "envs" / configured_env / "bin"
        lines.append(f'export PATH="{abi_bin}:{configured_bin}:$PATH"')
        if container:
            runtime = self.options.container_runtime or "apptainer"
            lines.append(f"# Container: {container} (runtime: {runtime})")
        return lines

    def _submit_jobs(self, scripts: list[Path]) -> dict[str, str]:
        scheduler = self.options.scheduler or "slurm"
        if self._dag is None:
            # Compatibility path used by focused unit tests.
            result: dict[str, str] = {}
            command = "sbatch" if scheduler == "slurm" else "qsub"
            for script in scripts:
                proc = subprocess.run(
                    [command, str(script)], capture_output=True, text=True, check=False
                )
                job_id = self._parse_job_id(proc.stdout, scheduler)
                if job_id:
                    result[script.name] = job_id
            return result
        job_ids: dict[str, str] = {}
        self._submitted_job_ids = job_ids
        for step_id in self._dag.topological_order:
            script_path = self._script_by_step.get(step_id)
            if script_path is None:
                continue
            binding = self._dag.binding_for(step_id)
            dependencies = [
                job_ids[dependency] for dependency in binding.dependencies if dependency in job_ids
            ]
            if scheduler == "slurm":
                submit_command: list[str] = ["sbatch", "--parsable"]
                if dependencies:
                    submit_command.append(f"--dependency=afterok:{':'.join(dependencies)}")
                submit_command.append(str(script_path))
            else:
                submit_command = ["qsub"]
                if dependencies:
                    submit_command.extend(["-W", f"depend=afterok:{':'.join(dependencies)}"])
                submit_command.append(str(script_path))
            proc = subprocess.run(submit_command, capture_output=True, text=True, check=False)
            if proc.returncode != 0:
                raise ABIError(
                    f"Failed to submit {step_id}: {proc.stderr.strip() or proc.stdout.strip()}"
                )
            job_id = self._parse_job_id(proc.stdout, scheduler)
            if not job_id:
                raise ABIError(f"Scheduler did not return a job ID for {step_id}")
            job_ids[step_id] = job_id
        return job_ids

    def _parse_job_id(self, stdout: str, scheduler: str) -> str:
        text = stdout.strip()
        if scheduler == "slurm":
            first = text.split(";", 1)[0]
            if first.isdigit():
                return first
            for word in text.split():
                if word.isdigit():
                    return word
            return ""
        return text.split(".", 1)[0]

    def _poll_until_complete(
        self, job_ids: dict[str, str], timeout_seconds: float
    ) -> dict[str, str]:
        scheduler = self.options.scheduler or "slurm"
        deadline = time.time() + timeout_seconds
        pending = set(job_ids.values())
        statuses: dict[str, str] = {}
        unknown_counts: dict[str, int] = {job_id: 0 for job_id in pending}
        poll_interval = max(0.1, float(getattr(self.options, "poll_interval_seconds", 30.0)))
        while pending and time.time() < deadline:
            current = (
                self._poll_slurm(sorted(pending))
                if scheduler == "slurm"
                else self._poll_pbs(sorted(pending))
            )
            for job_id in list(pending):
                state = _normalize_slurm_state(current.get(job_id, ""))
                if state:
                    statuses[job_id] = state
                    unknown_counts[job_id] = 0
                else:
                    unknown_counts[job_id] += 1
                    if unknown_counts[job_id] >= 3:
                        statuses[job_id] = "UNKNOWN"
                        pending.remove(job_id)
                        continue
                if state in SLURM_TERMINAL_STATES or state in {"C", "F", "X", "E"}:
                    pending.remove(job_id)
            if pending:
                time.sleep(poll_interval)
        if pending:
            self._cancel_jobs(sorted(pending))
            for job_id in pending:
                statuses[job_id] = "TIMEOUT"
        return statuses

    def _poll_slurm(self, job_ids: list[str]) -> dict[str, str]:
        result: dict[str, str] = {}
        try:
            active = subprocess.run(
                ["squeue", "--job", ",".join(job_ids), "-o", "%i|%T", "--noheader"],
                capture_output=True,
                text=True,
                check=False,
                timeout=15,
            )
            for line in active.stdout.splitlines():
                parts = line.strip().split("|", 1)
                if len(parts) == 2:
                    result[parts[0]] = parts[1]
        except (subprocess.TimeoutExpired, OSError):
            pass
        missing = [job_id for job_id in job_ids if job_id not in result]
        if not missing:
            return result
        try:
            accounting = subprocess.run(
                [
                    "sacct",
                    "-X",
                    "-n",
                    "-P",
                    "-j",
                    ",".join(missing),
                    "-o",
                    "JobIDRaw,State,ExitCode",
                ],
                capture_output=True,
                text=True,
                check=False,
                timeout=15,
            )
            for line in accounting.stdout.splitlines():
                parts = line.strip().split("|")
                if len(parts) >= 2 and parts[0] in missing and "." not in parts[0]:
                    result[parts[0]] = parts[1]
        except (subprocess.TimeoutExpired, OSError):
            pass
        return result

    def _poll_pbs(self, job_ids: list[str]) -> dict[str, str]:
        result: dict[str, str] = {}
        for job_id in job_ids:
            try:
                proc = subprocess.run(
                    ["qstat", "-f", job_id],
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=10,
                )
                for line in proc.stdout.splitlines():
                    if "job_state" in line.lower():
                        result[job_id] = line.split("=")[-1].strip()
                        break
            except (subprocess.TimeoutExpired, OSError):
                pass
        return result

    def _cancel_jobs(self, job_ids: list[str]) -> None:
        command = "scancel" if (self.options.scheduler or "slurm") == "slurm" else "qdel"
        for job_id in job_ids:
            subprocess.run([command, job_id], capture_output=True, check=False)

    def _collect_results(
        self,
        plan: object,
        config: Mapping[str, Any],
        job_ids: dict[str, str],
        statuses: dict[str, str],
    ) -> RuntimeResult:
        table_manager = StandardTableManager(self.plugin.table_schemas())
        tables_dir = Path(str(config["outdir"])) / "tables"
        table_manager.ensure_tables(tables_dir)
        command_rows: list[dict[str, Any]] = []
        checksums: dict[str, str] = {}
        results = dict(self._driver_results)
        for step_id, path in self._result_by_step.items():
            if path.is_file():
                data = json.loads(path.read_text(encoding="utf-8"))
                results[step_id] = StepExecutionResult(**data)
        for step in getattr(plan, "steps", []):
            if step.step_id in self._resumed_steps:
                command_rows.append(_command_row(step, "resumed", 0, "validated outputs reused"))
                continue
            result = results.get(step.step_id)
            job_id = job_ids.get(step.step_id, "")
            scheduler_state = _normalize_slurm_state(statuses.get(job_id, "")) if job_id else ""
            if result is None:
                status = "failed" if scheduler_state in SLURM_FAILURE_STATES else "unknown"
                command_rows.append(
                    _command_row(step, status, 1, f"missing step result; Slurm={scheduler_state}")
                )
                continue
            command_rows.append(
                _command_row(
                    step,
                    result.status,
                    result.return_code,
                    result.reason,
                    command=result.command,
                )
            )
            if result.standard_tables:
                table_manager.append_rows(tables_dir, result.standard_tables)
            checksums.update(result.checksums)
        if checksums:
            checksum_path = self._provenance_dir(config) / "checksums.json"
            checksum_path.write_text(
                json.dumps(checksums, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
        failed = [row for row in command_rows if row["status"] not in {"success", "resumed"}]
        manifest = self._write_hpc_manifest(job_ids, statuses, config)
        writer = ABIResultWriter(
            self.plugin,
            self.plugin.registry(),
            table_manager=table_manager,
        )
        outputs = writer.write(
            plan=plan,
            config=config,
            command_rows=command_rows,
            status="success" if not failed else "partial_failure",
            return_code=0 if not failed else 1,
            engine="hpc",
            extra_summary={
                "job_ids": job_ids,
                "statuses": statuses,
                "scheduler": self.options.scheduler or "slurm",
                "resumed_steps": sorted(self._resumed_steps),
            },
        )
        outputs["hpc_manifest"] = manifest
        return RuntimeResult(
            status="success" if not failed else "partial_failure",
            return_code=0 if not failed else 1,
            outputs=outputs,
        )

    def _write_hpc_manifest(
        self,
        job_ids: Mapping[str, str],
        statuses: Mapping[str, str],
        config: Mapping[str, Any],
        *,
        dry_run: bool = False,
    ) -> Path:
        path = self._provenance_dir(config) / "hpc_jobs.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        jobs = []
        for step_id, script in self._script_by_step.items():
            job_id = str(job_ids.get(step_id, ""))
            dependencies = []
            if self._dag and step_id in self._dag.topological_order:
                dependencies = list(self._dag.binding_for(step_id).dependencies)
            jobs.append(
                {
                    "step_id": step_id,
                    "script": str(script),
                    "job_id": job_id,
                    "dependencies": dependencies,
                    "status": "dry_run" if dry_run else statuses.get(job_id, "unknown"),
                }
            )
        path.write_text(
            json.dumps(
                {
                    "scheduler": self.options.scheduler or "slurm",
                    "dry_run": dry_run,
                    "resumed_steps": sorted(self._resumed_steps),
                    "jobs": jobs,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return path

    def _write_step_result(
        self,
        step_id: str,
        result: StepExecutionResult,
        config: Mapping[str, Any],
    ) -> Path:
        path = self._step_results_dir(config) / f"{_safe_name(step_id)}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(result.to_dict(), indent=2) + "\n", encoding="utf-8")
        return path

    def _step_is_resumable(self, step: Any, config: Mapping[str, Any]) -> bool:
        checksums = load_checksums(self._provenance_dir(config), strict=False)
        file_outputs: list[Path] = []
        for key, value in getattr(step, "outputs", {}).items():
            if key == "output_dir" or not value:
                continue
            path = Path(str(value))
            if not path.is_file() or path.stat().st_size == 0:
                return False
            file_outputs.append(path)
        if not file_outputs:
            return False
        return all(checksums.get(str(path)) == compute_file_checksum(path) for path in file_outputs)

    def _build_submit_command(self, scripts: list[Path]) -> str:
        command = "sbatch" if (self.options.scheduler or "slurm") == "slurm" else "qsub"
        return f"for f in {' '.join(str(script) for script in scripts)}; do {command} $f; done"


def _command_row(
    step: Any,
    status: str,
    return_code: int | str,
    reason: str,
    *,
    command: str = "",
) -> dict[str, Any]:
    return {
        "step_id": step.step_id,
        "sample_id": step.sample_id,
        "step_name": step.step_name,
        "tool_id": step.tool_id,
        "category": step.category,
        "command": command,
        "status": status,
        "return_code": return_code,
        "reason": reason,
        "parsed_status": "parsed" if status == "success" else "",
        "standard_tables": "",
    }


def _normalize_slurm_state(state: str) -> str:
    return state.strip().upper().split("+", 1)[0].split(" ", 1)[0]


def _safe_name(name: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", name).strip("._-") or "step"
    if len(safe) <= 50:
        return safe
    digest = sha256(name.encode("utf-8")).hexdigest()[:8]
    return f"{safe[:41]}_{digest}"


def _scheduler_value(value: Any, label: str) -> str:
    text = str(value)
    if "\n" in text or "\r" in text:
        raise ABIError(f"Invalid newline in HPC scheduler {label}")
    return text


def _log_dir(config: Mapping[str, Any]) -> str:
    return str(config.get("log_dir", str(Path(str(config.get("outdir", "/tmp"))) / "logs")))


def shlex_quote(value: str) -> str:
    import shlex

    return shlex.quote(value)
