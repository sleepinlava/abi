"""Generic ABI plan executor."""

from __future__ import annotations

import json
import os
import shlex
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Mapping

from abi.config import write_yaml
from abi.errors import ToolError

__all__ = ["GenericABIExecutor"]
from abi.filesystem import ensure_directory
from abi.provenance import (
    PipelineProgressRecorder,
    RunLogger,
    write_commands_tsv,
    write_resolved_inputs_tsv,
)
from abi.report import write_generic_report
from abi.tables import StandardTableManager
from abi.tools import ToolRegistry


class GenericABIExecutor:
    """Executor for ABI plugins that only need generic command orchestration."""

    def __init__(
        self,
        registry: ToolRegistry,
        logger: RunLogger,
        *,
        table_manager: StandardTableManager,
        parse_outputs: Callable[[str, str | Path, str], Mapping[str, Iterable[Mapping[str, Any]]]],
        report_title: str = "ABI Report",
        mock_tools: bool = False,
    ) -> None:
        self.registry = registry
        self.logger = logger
        self.table_manager = table_manager
        self.parse_outputs = parse_outputs
        self.report_title = report_title
        self.mock_tools = mock_tools

    def dry_run(self, plan: Any, config: Mapping[str, Any]) -> Dict[str, Path]:
        return self.run(plan, config, dry_run=True)

    def run(
        self,
        plan: Any,
        config: Mapping[str, Any],
        *,
        dry_run: bool = False,
    ) -> Dict[str, Path]:
        outdir = ensure_directory(plan.outdir, label="Output directory")
        provenance = ensure_directory(outdir / "provenance", label="Provenance directory")
        tables_dir = ensure_directory(outdir / "tables", label="Standard tables directory")
        self.table_manager.ensure_tables(tables_dir)
        self._ensure_step_output_dirs(plan.steps)

        plan_path = outdir / "execution_plan.json"
        plan_path.write_text(
            json.dumps(plan.to_dict(), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        config_path = write_yaml(config, provenance / "config.resolved.yaml")
        resolved_inputs_path = write_resolved_inputs_tsv(
            self._resolved_input_rows(plan, dry_run=dry_run),
            provenance / "resolved_inputs.tsv",
        )

        execution = _execution_options(config)
        progress_recorder = (
            PipelineProgressRecorder(provenance) if bool(execution["record_progress"]) else None
        )
        if progress_recorder:
            progress_recorder.start_run(
                plan,
                dry_run=dry_run,
                parallel=False,
                workers=1,
            )

        command_rows = []
        failed_error: ToolError | None = None
        for step in plan.steps:
            row, error = self._execute_step(
                step,
                dry_run=dry_run,
                provenance=provenance,
                tables_dir=tables_dir,
                progress_recorder=progress_recorder,
            )
            command_rows.append(row)
            if error:
                failed_error = error
                break

        table_summary = self.table_manager.summarize(tables_dir)
        commands_path = write_commands_tsv(command_rows, provenance / "commands.tsv")
        versions_path = self._write_tool_versions(provenance / "tool_versions.tsv")
        resources_path = self._write_resources(config, provenance / "resources.json")
        environment_path = self._write_environment(provenance / "environment.yml")
        report_paths = write_generic_report(
            plan,
            outdir,
            table_summary=table_summary,
            title=self.report_title,
        )
        summary_path = provenance / "run_summary.json"
        summary_path.write_text(
            json.dumps(
                {
                    "project_name": plan.project_name,
                    "analysis_type": getattr(plan, "analysis_type", ""),
                    "dry_run": dry_run,
                    "sample_count": len(plan.samples),
                    "step_count": len(plan.steps),
                    "completed_step_count": len(command_rows),
                    "status": "failed" if failed_error else "success",
                    "parallel": False,
                    "workers": 1,
                    "selected_tools": plan.selected_tools,
                    "standard_tables": table_summary,
                    "progress_file": str(progress_recorder.snapshot_path)
                    if progress_recorder
                    else "",
                    "progress_events": str(progress_recorder.events_path)
                    if progress_recorder
                    else "",
                    "log_file": str(self.logger.log_file),
                },
                indent=2,
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )

        outputs = {
            "plan": plan_path,
            "config": config_path,
            "commands": commands_path,
            "resolved_inputs": resolved_inputs_path,
            "tool_versions": versions_path,
            "resources": resources_path,
            "environment": environment_path,
            "summary": summary_path,
            "tables": tables_dir,
            "report": report_paths["report"],
            "report_html": report_paths["report_html"],
            "log": self.logger.log_file,
        }
        if progress_recorder:
            progress_recorder.finish_run(status="failed" if failed_error else "success")
            outputs["progress"] = progress_recorder.snapshot_path
            outputs["progress_events"] = progress_recorder.events_path
        if failed_error:
            raise failed_error
        return outputs

    def _execute_step(
        self,
        step: Any,
        *,
        dry_run: bool,
        provenance: Path,
        tables_dir: Path,
        progress_recorder: PipelineProgressRecorder | None,
    ) -> tuple[Dict[str, Any], ToolError | None]:
        command = self._command_for_step(step, dry_run=dry_run)
        status = "dry_run" if dry_run else "success"
        reason = step.reason or ""
        return_code: int | str = ""
        parsed_status = ""
        standard_tables = ""
        failed_error: ToolError | None = None

        if progress_recorder:
            progress_recorder.step_started(step)

        if step.skipped:
            status = "skipped"
        elif dry_run or step.tool_id == "internal":
            pass
        elif not self.registry.has(step.tool_id):
            status = "failed"
            reason = f"Tool {step.tool_id!r} is not registered"
            failed_error = ToolError(reason)
        else:
            result = self._run_external_step(step, provenance, tables_dir)
            status = str(result["status"])
            return_code = result["return_code"]
            reason = str(result["reason"])
            parsed_status = str(result.get("parsed_status", ""))
            standard_tables = str(result.get("standard_tables", ""))
            if status != "success":
                failed_error = ToolError(reason)

        row = {
            "step_id": step.step_id,
            "sample_id": step.sample_id,
            "step_name": step.step_name,
            "tool_id": step.tool_id,
            "category": step.category,
            "command": _display_command(command),
            "status": status,
            "return_code": return_code,
            "reason": reason,
            "parsed_status": parsed_status,
            "standard_tables": standard_tables,
        }
        self.logger.log_step(step, command=command, status=status, error_message=reason)
        if progress_recorder:
            progress_recorder.step_completed(
                step,
                status=status,
                reason=reason,
                return_code=return_code,
                parsed_status=parsed_status,
                standard_tables=standard_tables,
            )
        return row, failed_error

    def _run_external_step(self, step: Any, provenance: Path, tables_dir: Path) -> Dict[str, Any]:
        skill = self.registry.create(step.tool_id, mock_tools=self.mock_tools)
        step_log_dir = provenance / "step_logs"
        params = self._params_for_step(step, dry_run=False)
        params["stdout_path"] = str(step_log_dir / f"{step.step_id}.stdout.log")
        params["stderr_path"] = str(step_log_dir / f"{step.step_id}.stderr.log")
        try:
            result = skill.run(params, dry_run=False)
        except ToolError as exc:
            reason = _tool_failure_reason(
                step,
                return_code="",
                stderr_path=params["stderr_path"],
                message=str(exc),
            )
            return {"status": "failed", "return_code": "", "reason": reason}
        if result.return_code != 0:
            reason = _tool_failure_reason(
                step,
                return_code=result.return_code,
                stderr_path=str(result.outputs.get("stderr_path", params["stderr_path"])),
                stdout_path=str(result.outputs.get("stdout_path", params["stdout_path"])),
            )
            return {"status": "failed", "return_code": result.return_code, "reason": reason}

        rows_by_table = self.parse_outputs(
            step.tool_id,
            step.outputs.get("output_dir", params.get("output_dir", "")),
            str(step.sample_id or ""),
        )
        written = self.table_manager.append_rows(tables_dir, rows_by_table)
        return {
            "status": result.status,
            "return_code": result.return_code,
            "reason": "",
            "parsed_status": "parsed" if written else "no_standard_rows",
            "standard_tables": ",".join(sorted(written)),
        }

    def _command_for_step(self, step: Any, *, dry_run: bool) -> List[str]:
        if step.tool_id == "internal":
            return ["abi", "internal", step.step_name, "--step-id", step.step_id]
        if not self.registry.has(step.tool_id):
            return ["abi", "missing-wrapper", step.tool_id, "--step-id", step.step_id]
        skill = self.registry.create(step.tool_id, mock_tools=self.mock_tools or dry_run)
        return skill.build_command(self._params_for_step(step, dry_run=dry_run))

    def _params_for_step(self, step: Any, *, dry_run: bool) -> Dict[str, Any]:
        params = dict(step.inputs)
        params.update(step.params)
        params.update(step.outputs)
        if "output_dir" not in params and "outdir" in params:
            params["output_dir"] = params["outdir"]
        params["dry_run"] = dry_run
        return params

    def _resolved_input_rows(self, plan: Any, *, dry_run: bool) -> List[Dict[str, Any]]:
        rows = []
        path_fields = {
            "read1",
            "read2",
            "long_reads",
            "assembly",
            "database",
            "model",
            "reference",
            "genome_index",
            "annotation_gtf",
            "gtf",
            "bam",
            "alignment",
            "counts",
        }
        for step in plan.steps:
            params = self._params_for_step(step, dry_run=dry_run)
            for name in sorted(path_fields):
                value = params.get(name)
                if not value:
                    continue
                path = Path(str(value))
                rows.append(
                    {
                        "step_id": step.step_id,
                        "tool_id": step.tool_id,
                        "sample_id": step.sample_id or "",
                        "input_name": name,
                        "path": str(path),
                        "exists": path.exists(),
                        "source": "sample"
                        if name in step.inputs and str(step.inputs.get(name)) == str(value)
                        else "config_or_plan",
                    }
                )
        return rows

    def _write_tool_versions(self, path: Path) -> Path:
        rows = []
        for tool in self.registry.list_tools():
            skill = self.registry.create(str(tool.get("id")), mock_tools=self.mock_tools)
            rows.append(
                {
                    "tool_id": tool.get("id"),
                    "executable": tool.get("executable", ""),
                    "env_name": tool.get("env_name", ""),
                    "version": "",
                    "status": "ok" if skill.check_installation() else "missing",
                }
            )
        path.parent.mkdir(parents=True, exist_ok=True)
        fields = ["tool_id", "executable", "env_name", "version", "status"]
        with path.open("w", encoding="utf-8") as handle:
            handle.write("\t".join(fields) + "\n")
            for row in rows:
                handle.write("\t".join(str(row.get(field, "")) for field in fields) + "\n")
        return path

    def _write_resources(self, config: Mapping[str, Any], path: Path) -> Path:
        rows = self.registry.check_tools(mock_tools=self.mock_tools, config=config)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"resources": rows}, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        return path

    def _write_environment(self, path: Path) -> Path:
        environment = {
            "mamba_root": os.environ.get("ABI_MAMBA_ROOT", ".mamba"),
            "tools": [
                {
                    "tool_id": tool.get("id", ""),
                    "env_name": tool.get("env_name", ""),
                    "executable": tool.get("executable", ""),
                }
                for tool in self.registry.list_tools()
            ],
        }
        return write_yaml(environment, path)

    @staticmethod
    def _ensure_step_output_dirs(steps: Iterable[Any]) -> None:
        for step in steps:
            for output_path in step.outputs.values():
                path = Path(str(output_path))
                if path.suffix:
                    ensure_directory(
                        path.parent,
                        label=f"Output parent directory for {step.step_id}",
                    )
                else:
                    ensure_directory(path, label=f"Output directory for {step.step_id}")


def _execution_options(config: Mapping[str, Any]) -> Dict[str, Any]:
    execution = config.get("execution", {})
    if not isinstance(execution, Mapping):
        execution = {}
    progress = bool(execution.get("progress", True))
    dashboard = execution.get("dashboard", {})
    dashboard_enabled = isinstance(dashboard, Mapping) and bool(dashboard.get("enable", False))
    return {"record_progress": progress or dashboard_enabled}


def _display_command(command: Iterable[str]) -> str:
    return " ".join(">" if token == ">" else shlex.quote(str(token)) for token in command)


def _tool_failure_reason(
    step: Any,
    *,
    return_code: int | str,
    stderr_path: str,
    stdout_path: str = "",
    message: str = "",
) -> str:
    details = [
        f"step_id={step.step_id}",
        f"tool_id={step.tool_id}",
        f"exit_code={return_code if return_code != '' else 'not_started'}",
        f"stderr_path={stderr_path}",
    ]
    if stdout_path:
        details.append(f"stdout_path={stdout_path}")
    if message:
        details.append(f"message={message}")
    details.append(
        "suggested_checks=inspect stderr/stdout logs; verify input paths, tool "
        "environment, database/model resources, and command template parameters."
    )
    return "; ".join(details)
