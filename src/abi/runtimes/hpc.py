"""Native HPC runtime — generates SLURM/PBS job scripts and submits them directly.

This runtime is an alternative to ``NextflowRuntime``.  Instead of generating a
Nextflow DSL2 pipeline and delegating to ``nextflow run``, it generates
self-contained bash scripts with ``#SBATCH`` / ``#PBS`` directives and submits
them via ``sbatch`` / ``qsub``.

Three execution backends, all parallel and selectable: / 三条技术路线并行可选

    --engine local     → LocalRuntime    → subprocess
    --engine nextflow  → NextflowRuntime → DSL2 .nf → nextflow run
    --engine hpc       → HpcRuntime      → bash script → sbatch/qsub
"""

from __future__ import annotations

import json as _json
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Mapping

from abi.config import PROJECT_ROOT
from abi.dag import ABIDAG, infer_dag
from abi.results import ABIResultWriter
from abi.runtimes.base import RuntimeOptions, RuntimeResult
from abi.schemas import ABIError
from abi.tools import (
    ResourceSpec,
    resolve_container_image,
    resolve_resources,
)


class HpcRuntime:
    """Native HPC runtime — generates and submits SLURM/PBS job scripts.

    Implements the ``ABIRuntime`` protocol (``check``, ``dry_run``, ``run``).
    """

    def __init__(self, plugin: Any, *, options: RuntimeOptions | None = None) -> None:
        self.plugin = plugin
        self.options = options or RuntimeOptions(engine="hpc")

    # ── ABIRuntime interface ────────────────────────────────────────────

    def check(self) -> None:
        """Verify the scheduler command (sbatch/qsub) is available."""
        scheduler = self.options.scheduler or "slurm"
        cmd = "sbatch" if scheduler == "slurm" else "qsub"
        if not shutil.which(cmd):
            raise ABIError(
                f"HPC scheduler '{scheduler}' not found: {cmd!r} is not on PATH. "
                f"Install SLURM or PBS/Torque, or use --engine nextflow."
            )

    def dry_run(self, plan: object, config: Mapping[str, Any]) -> RuntimeResult:
        """Generate job scripts but do NOT submit.

        Writes scripts to ``<outdir>/provenance/hpc_scripts/`` and returns
        their paths along with the submit command for manual submission.
        """
        scripts_dir = self._scripts_dir(config)
        scripts_dir.mkdir(parents=True, exist_ok=True)
        self._generate_all_scripts(plan, config)
        return RuntimeResult(
            status="dry_run",
            return_code=0,
            outputs={
                "scripts_dir": scripts_dir,
                "submit_command": Path("/dev/null"),  # informational, not a real file
                "hpc_script_count": Path("/dev/null"),
            },
        )

    def run(self, plan: object, config: Mapping[str, Any]) -> RuntimeResult:
        """Generate scripts, submit, poll, collect results."""
        scripts = self._generate_all_scripts(plan, config)
        job_ids = self._submit_jobs(scripts)
        timeout = self.options.timeout_seconds or 3600 * 24 * 7  # 7 days default
        statuses = self._poll_until_complete(job_ids, timeout)
        return self._collect_results(plan, config, job_ids, statuses)

    # ── Script generation ───────────────────────────────────────────────

    def _scripts_dir(self, config: Mapping[str, Any]) -> Path:
        return Path(str(config.get("outdir", "."))) / "provenance" / "hpc_scripts"

    def _generate_all_scripts(self, plan: object, config: Mapping[str, Any]) -> list[Path]:
        """Generate one batch script per DAG step with RBAC/SBATCH directives."""
        dag = infer_dag(getattr(plan, "steps", []), sequential_fallback=True)
        registry = self.plugin.registry()
        scripts_dir = self._scripts_dir(config)
        scripts_dir.mkdir(parents=True, exist_ok=True)
        result: list[Path] = []
        for step_id in dag.topological_order:
            binding = dag.binding_for(step_id)
            step = binding.step
            tool_id = getattr(step, "tool_id", "")
            if tool_id == "internal":
                continue
            tool_meta = registry.get(tool_id) if tool_id and registry.has(tool_id) else {}
            resources = self._resolve_step_resources(tool_id, tool_meta, config)
            container = resolve_container_image(
                tool_id,
                tool_meta,
                config=config,
                cli_image=self.options.container_image,
            )
            script_path = scripts_dir / f"{_safe_name(step.step_id)}.sh"
            self._write_single_script(
                script_path,
                step,
                binding,
                resources,
                container,
                config,
                dag,
            )
            result.append(script_path)
        return result

    def _resolve_step_resources(
        self,
        tool_id: str,
        tool_meta: Mapping[str, Any],
        config: Mapping[str, Any],
    ) -> ResourceSpec:
        cli = None
        if any(
            getattr(self.options, f, None)
            for f in ("cpu_override", "memory_override", "walltime_override")
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
    ) -> None:
        """Render one step's batch script."""
        scheduler = self.options.scheduler or "slurm"
        if scheduler == "pbs":
            directives = resources.to_pbs_directives()
            job_name_dir = f"#PBS -N {_safe_name(step.step_id)}"
        else:
            directives = resources.to_slurm_directives()
            job_name_dir = f"#SBATCH --job-name={_safe_name(step.step_id)}"

        # Scheduler-specific options
        extra = [job_name_dir]
        if scheduler == "slurm":
            extra.append(f"#SBATCH --output={_log_dir(config)}/%x_%j.out")
            extra.append(f"#SBATCH --error={_log_dir(config)}/%x_%j.err")
            if self.options.partition:
                extra.append(f"#SBATCH --partition={self.options.partition}")
            if self.options.account:
                extra.append(f"#SBATCH --account={self.options.account}")
            if self.options.qos:
                extra.append(f"#SBATCH --qos={self.options.qos}")
            if self.options.mail_type:
                extra.append(f"#SBATCH --mail-type={self.options.mail_type}")
            if self.options.mail_user:
                extra.append(f"#SBATCH --mail-user={self.options.mail_user}")
            # Dependency chain: wait for upstream steps
            deps = self._dependency_job_ids(binding, dag)
            if deps:
                extra.append(f"#SBATCH --dependency=afterok:{':'.join(deps)}")
        elif scheduler == "pbs":
            extra.append(f"#PBS -o {_log_dir(config)}")
            extra.append(f"#PBS -e {_log_dir(config)}")
            if self.options.partition:
                extra.append(f"#PBS -q {self.options.partition}")
            if self.options.account:
                extra.append(f"#PBS -A {self.options.account}")
            if self.options.mail_user:
                extra.append(f"#PBS -M {self.options.mail_user}")

        # Environment setup
        env_lines = self._render_env(config, container)

        # Dispatch command
        step_json = _json.dumps(
            {
                "step_id": step.step_id,
                "sample_id": step.sample_id,
                "tool_id": getattr(step, "tool_id", ""),
                "step_name": step.step_name,
                "params": getattr(step, "params", {}),
                "inputs": getattr(step, "inputs", {}),
                "outputs": getattr(step, "outputs", {}),
            }
        )
        dispatch_cmd = f"abi dispatch --command run-step --arguments '{step_json}'"

        lines = [
            "#!/bin/bash",
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
            dispatch_cmd,
        ]
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def _dependency_job_ids(self, binding: Any, dag: ABIDAG) -> list[str]:
        """Placeholder job IDs for dependency chain.

        In production, these are resolved after all scripts are submitted.
        For dry-run, returns placeholder names.
        """
        if not binding.dependencies:
            return []
        return [f"${{JOB_{_safe_name(dep)}" for dep in binding.dependencies]

    def _render_env(self, config: Mapping[str, Any], container: str | None) -> list[str]:
        """Render environment setup lines."""
        lines: list[str] = []
        if container:
            container_runtime = self.options.container_runtime or "docker"
            lines.append(f"# Container: {container} (runtime: {container_runtime})")
        else:
            mamba_root = str(
                self.options.mamba_root or config.get("mamba_root", str(PROJECT_ROOT / ".mamba"))
            )
            env_name = config.get("env_name", "abi-base")
            env_bin = f"{mamba_root}/envs/{env_name}/bin"
            lines.append(f'export PATH="{env_bin}:$PATH"')
        return lines

    # ── Job submission ────────────────────────────────────────────────

    def _submit_jobs(self, scripts: list[Path]) -> dict[str, str]:
        """Submit all scripts to the scheduler. Returns {script_name: job_id}."""
        scheduler = self.options.scheduler or "slurm"
        submit_cmd = "sbatch" if scheduler == "slurm" else "qsub"
        result: dict[str, str] = {}
        for script in scripts:
            proc = subprocess.run(
                [submit_cmd, str(script)],
                capture_output=True,
                text=True,
                check=False,
            )
            job_id = self._parse_job_id(proc.stdout, scheduler)
            if job_id:
                result[script.name] = job_id
        return result

    def _parse_job_id(self, stdout: str, scheduler: str) -> str:
        """Extract job ID from submit command output."""
        if scheduler == "slurm":
            # "Submitted batch job 12345"
            for word in stdout.strip().split():
                if word.isdigit():
                    return word
        else:
            # PBS: "12345.scheduler.host"
            return stdout.strip().split(".")[0]
        return ""

    def _poll_until_complete(
        self, job_ids: dict[str, str], timeout_seconds: float
    ) -> dict[str, str]:
        """Poll squeue/qstat until all jobs complete or timeout."""
        scheduler = self.options.scheduler or "slurm"
        deadline = time.time() + timeout_seconds
        statuses: dict[str, str] = {}
        all_ids = list(job_ids.values())
        while all_ids and time.time() < deadline:
            if scheduler == "slurm":
                statuses = self._poll_slurm(all_ids)
            else:
                statuses = self._poll_pbs(all_ids)
            # Remove completed jobs
            done = {k for k, v in statuses.items() if v in ("COMPLETED", "FAILED", "CANCELLED")}
            all_ids = [j for j in all_ids if j not in done]
            if not all_ids:
                break
            time.sleep(30)
        return statuses

    def _poll_slurm(self, job_ids: list[str]) -> dict[str, str]:
        try:
            proc = subprocess.run(
                ["squeue", "--job", ",".join(job_ids), "-o", "%i %T", "--noheader"],
                capture_output=True,
                text=True,
                check=False,
                timeout=15,
            )
            result: dict[str, str] = {}
            for line in proc.stdout.strip().splitlines():
                parts = line.strip().split(None, 1)
                if len(parts) == 2:
                    result[parts[0]] = parts[1]
            return result
        except (subprocess.TimeoutExpired, OSError):
            return {}

    def _poll_pbs(self, job_ids: list[str]) -> dict[str, str]:
        result: dict[str, str] = {}
        for jid in job_ids:
            try:
                proc = subprocess.run(
                    ["qstat", "-f", jid],
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=10,
                )
                for line in proc.stdout.splitlines():
                    if "job_state" in line.lower():
                        result[jid] = line.split("=")[-1].strip()
                        break
            except (subprocess.TimeoutExpired, OSError):
                pass
        return result

    def _cancel_jobs(self, job_ids: list[str]) -> None:
        scheduler = self.options.scheduler or "slurm"
        cmd = "scancel" if scheduler == "slurm" else "qdel"
        for jid in job_ids:
            subprocess.run([cmd, jid], capture_output=True, check=False)

    # ── Result collection ──────────────────────────────────────────────

    def _collect_results(
        self,
        plan: object,
        config: Mapping[str, Any],
        job_ids: dict[str, str],
        statuses: dict[str, str],
    ) -> RuntimeResult:
        failed = sum(1 for s in statuses.values() if s not in ("COMPLETED", "C"))
        writer = ABIResultWriter(self.plugin, self.plugin.registry())
        outputs = writer.write(
            plan=plan,
            config=config,
            command_rows=[],
            status="success" if not failed else "partial_failure",
            return_code=0 if not failed else 1,
            engine="hpc",
            extra_summary={
                "job_ids": job_ids,
                "statuses": statuses,
                "scheduler": self.options.scheduler or "slurm",
            },
        )
        return RuntimeResult(
            status="success" if not failed else "partial_failure",
            return_code=0 if not failed else 1,
            outputs=outputs,
        )

    def _build_submit_command(self, scripts: list[Path]) -> str:
        """Build a convenience submit-all command for the user."""
        scheduler = self.options.scheduler or "slurm"
        cmd = "sbatch" if scheduler == "slurm" else "qsub"
        return f"for f in {' '.join(str(s) for s in scripts)}; do {cmd} $f; done"


def _safe_name(name: str) -> str:
    """Sanitize a string for use in a SLURM/PBS job name."""
    return name.replace(" ", "_").replace("/", "_")[:50]


def _log_dir(config: Mapping[str, Any]) -> str:
    return str(config.get("log_dir", str(Path(str(config.get("outdir", "/tmp"))) / "logs")))
