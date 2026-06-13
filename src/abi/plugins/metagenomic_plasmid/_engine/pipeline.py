"""Plan execution and dry-run provenance."""

from __future__ import annotations

import json
import shlex
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Mapping

from abi.plugins.metagenomic_plasmid._engine.config import write_resolved_config
from abi.plugins.metagenomic_plasmid._engine.filesystem import ensure_directory
from abi.plugins.metagenomic_plasmid._engine.logger import (
    RunLogger,
    write_commands_tsv,
    write_resolved_inputs_tsv,
    write_tool_versions,
)
from abi.plugins.metagenomic_plasmid._engine.parsers import parse_standard_outputs, supports_standard_parsing
from abi.plugins.metagenomic_plasmid._engine.progress import (
    PipelineProgressRecorder,
    write_minimal_progress_artifacts,
)
from abi.plugins.metagenomic_plasmid._engine.report.html import write_html_report
from abi.plugins.metagenomic_plasmid._engine.report.markdown import write_markdown_report
from abi.plugins.metagenomic_plasmid._engine.resources import (
    write_environment_snapshot,
    write_resources_provenance,
)
from abi.plugins.metagenomic_plasmid._engine.schemas import ExecutionPlan, PlanStep, ToolError
from abi.plugins.metagenomic_plasmid._engine.standard_tables import (
    append_standard_rows,
    ensure_standard_tables,
    read_standard_table,
    summarize_standard_tables,
    write_consensus_table,
)
from abi.plugins.metagenomic_plasmid._engine.statistics import (
    compute_diversity_and_differential,
    compute_network_fallback,
)
from abi.plugins.metagenomic_plasmid._engine.timeouts import mapping_block
from abi.errors import ToolError as ABIToolError

PLASMID_DETECTION_DIR = "04_plasmid_detection"


class PipelineExecutor:
    def __init__(
        self,
        registry: Any,
        logger: RunLogger,
        *,
        mock_tools: bool = False,
        progress_callback: Callable[[Mapping[str, Any]], None] | None = None,
    ) -> None:
        self.registry = registry
        self.logger = logger
        self.mock_tools = mock_tools
        self.progress_callback = progress_callback
        self._tables_lock = threading.Lock()
        self._log_lock = threading.Lock()

    def dry_run(self, plan: ExecutionPlan, config: Mapping[str, Any]) -> Dict[str, Path]:
        return self._run_plan(plan, config, dry_run=True)

    def run(
        self,
        plan: ExecutionPlan,
        config: Mapping[str, Any],
        *,
        dry_run: bool = False,
    ) -> Dict[str, Path]:
        return self._run_plan(plan, config, dry_run=dry_run)

    def _run_plan(
        self, plan: ExecutionPlan, config: Mapping[str, Any], *, dry_run: bool
    ) -> Dict[str, Path]:
        outdir = ensure_directory(plan.outdir, label="Output directory")
        provenance = ensure_directory(outdir / "provenance", label="Provenance directory")
        tables_dir = ensure_directory(outdir / "tables", label="Standard tables directory")
        ensure_standard_tables(tables_dir)
        for step in plan.steps:
            for output_path in step.outputs.values():
                path = Path(str(output_path))
                if path.suffix:
                    ensure_directory(
                        path.parent,
                        label=f"Output parent directory for {step.step_id}",
                    )
                else:
                    ensure_directory(path, label=f"Output directory for {step.step_id}")

        plan_path = outdir / "execution_plan.json"
        ensure_directory(plan_path.parent, label="Execution plan directory")
        plan_payload = _plan_payload(plan)
        with plan_path.open("w", encoding="utf-8") as handle:
            json.dump(plan_payload, handle, indent=2, ensure_ascii=False)

        config_path = write_resolved_config(config)
        resolved_inputs_path = write_resolved_inputs_tsv(
            self._resolved_input_rows(plan, dry_run=dry_run),
            provenance / "resolved_inputs.tsv",
        )

        execution = _execution_options(config)
        parallel = bool(execution["parallel"])
        workers = int(execution["workers"])
        progress_recorder = (
            PipelineProgressRecorder(provenance) if bool(execution["record_progress"]) else None
        )
        if progress_recorder:
            progress_recorder.start_run(plan, dry_run=dry_run, parallel=parallel, workers=workers)
        self._emit_progress(
            "run_started",
            {
                "project_name": plan.project_name,
                "dry_run": dry_run,
                "parallel": parallel,
                "workers": workers,
                "total_step_count": len(plan.steps),
            },
        )

        command_rows_by_step: Dict[str, Dict[str, Any]] = {}
        command_lock = threading.Lock()
        stop_event = threading.Event()

        def record_row(row: Mapping[str, Any]) -> None:
            with command_lock:
                command_rows_by_step[str(row["step_id"])] = dict(row)

        failed_error = self._execute_plan_steps(
            plan,
            config,
            dry_run=dry_run,
            provenance=provenance,
            tables_dir=tables_dir,
            parallel=parallel,
            workers=workers,
            progress_recorder=progress_recorder,
            stop_event=stop_event,
            record_row=record_row,
        )

        command_rows = [
            command_rows_by_step[step.step_id]
            for step in plan.steps
            if step.step_id in command_rows_by_step
        ]

        fasta_outputs = self._refresh_consensus_and_fastas(
            plan,
            tables_dir,
            config,
            candidate_mode=False,
            write_fastas=not dry_run,
        )
        table_summary = summarize_standard_tables(tables_dir)
        commands_path = write_commands_tsv(command_rows, provenance / "commands.tsv")
        versions_path = self._write_tool_versions(provenance / "tool_versions.tsv")
        resources_path = write_resources_provenance(config, outdir)
        environment_path = write_environment_snapshot(
            config,
            self.registry,
            provenance / "environment.yml",
        )
        report_path = write_markdown_report(
            plan,
            outdir / "report",
            tables_dir=tables_dir,
            provenance_dir=provenance,
            dry_run=dry_run,
        )
        report_html_path = write_html_report(
            plan,
            outdir / "report",
            tables_dir=tables_dir,
            provenance_dir=provenance,
            dry_run=dry_run,
        )
        run_status = "failed" if failed_error else "success"
        if progress_recorder:
            progress_recorder.finish_run(status=run_status)
            progress_paths = progress_recorder.paths
        else:
            progress_paths = write_minimal_progress_artifacts(
                provenance,
                plan,
                dry_run=dry_run,
                parallel=parallel,
                workers=workers,
                status=run_status,
                command_rows=command_rows,
            )
        summary_path = provenance / "run_summary.json"
        with summary_path.open("w", encoding="utf-8") as handle:
            json.dump(
                {
                    "project_name": plan.project_name,
                    "analysis_type": plan_payload["analysis_type"],
                    "dry_run": dry_run,
                    "sample_count": len(plan.samples),
                    "step_count": len(plan.steps),
                    "completed_step_count": len(command_rows),
                    "status": run_status,
                    "parallel": parallel,
                    "workers": workers,
                    "selected_tools": plan.selected_tools,
                    "standard_tables": table_summary,
                    "fasta_outputs": fasta_outputs,
                    "progress_file": str(progress_paths["snapshot"]),
                    "progress_events": str(progress_paths["events"]),
                    "log_file": str(self.logger.log_file),
                },
                handle,
                indent=2,
                ensure_ascii=False,
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
            "report": report_path,
            "report_html": report_html_path,
            "log": self.logger.log_file,
            "progress": progress_paths["snapshot"],
            "progress_events": progress_paths["events"],
        }
        self._emit_progress("run_completed", {"status": run_status})
        if failed_error:
            raise failed_error
        return outputs

    def _execute_plan_steps(
        self,
        plan: ExecutionPlan,
        config: Mapping[str, Any],
        *,
        dry_run: bool,
        provenance: Path,
        tables_dir: Path,
        parallel: bool,
        workers: int,
        progress_recorder: PipelineProgressRecorder | None,
        stop_event: threading.Event,
        record_row: Callable[[Mapping[str, Any]], None],
    ) -> ToolError | None:
        if not parallel or workers <= 1:
            return self._run_steps_sequential(
                plan.steps,
                plan,
                config,
                dry_run=dry_run,
                provenance=provenance,
                tables_dir=tables_dir,
                progress_recorder=progress_recorder,
                stop_event=stop_event,
                record_row=record_row,
            )

        sample_steps = _steps_by_sample(plan.steps)
        global_steps = [step for step in plan.steps if not step.sample_id]
        failed_error: ToolError | None = None
        if sample_steps:
            max_workers = min(workers, len(sample_steps))
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = [
                    executor.submit(
                        self._run_steps_sequential,
                        steps,
                        plan,
                        config,
                        dry_run=dry_run,
                        provenance=provenance,
                        tables_dir=tables_dir,
                        progress_recorder=progress_recorder,
                        stop_event=stop_event,
                        record_row=record_row,
                    )
                    for steps in sample_steps.values()
                ]
                for future in as_completed(futures):
                    error = future.result()
                    if error and not failed_error:
                        failed_error = error
                        stop_event.set()
        if failed_error:
            return failed_error
        return self._run_steps_sequential(
            global_steps,
            plan,
            config,
            dry_run=dry_run,
            provenance=provenance,
            tables_dir=tables_dir,
            progress_recorder=progress_recorder,
            stop_event=stop_event,
            record_row=record_row,
        )

    def _run_steps_sequential(
        self,
        steps: Iterable[PlanStep],
        plan: ExecutionPlan,
        config: Mapping[str, Any],
        *,
        dry_run: bool,
        provenance: Path,
        tables_dir: Path,
        progress_recorder: PipelineProgressRecorder | None,
        stop_event: threading.Event,
        record_row: Callable[[Mapping[str, Any]], None],
    ) -> ToolError | None:
        for step in steps:
            if stop_event.is_set():
                break
            row, error = self._execute_step(
                step,
                plan,
                config,
                dry_run=dry_run,
                provenance=provenance,
                tables_dir=tables_dir,
                progress_recorder=progress_recorder,
            )
            record_row(row)
            if error:
                stop_event.set()
                return error
        return None

    def _execute_step(
        self,
        step: PlanStep,
        plan: ExecutionPlan,
        config: Mapping[str, Any],
        *,
        dry_run: bool,
        provenance: Path,
        tables_dir: Path,
        progress_recorder: PipelineProgressRecorder | None,
    ) -> tuple[Dict[str, Any], ToolError | None]:
        if not dry_run and _needs_plasmid_candidate_fasta(step):
            plasmid_contigs = Path(str(step.params.get("plasmid_contigs", "")))
            if plasmid_contigs and not plasmid_contigs.exists():
                with self._tables_lock:
                    self._refresh_consensus_and_fastas(
                        plan,
                        tables_dir,
                        config,
                        candidate_mode=True,
                    )
        command = self._command_for_step(step, dry_run=dry_run)
        status = "dry_run" if dry_run else "success"
        reason = step.reason or ""
        return_code: int | str = ""
        parsed_status = ""
        standard_tables = ""
        failed_error: ToolError | None = None

        if progress_recorder:
            progress_recorder.step_started(step)
        self._emit_progress("step_started", _progress_step_payload(step))

        if step.skipped:
            status = "skipped"
        elif dry_run or step.tool_id == "report_markdown":
            pass
        elif step.tool_id == "internal":
            result = self._run_internal_step(step, plan, tables_dir)
            parsed_status = str(result.get("parsed_status", ""))
            standard_tables = str(result.get("standard_tables", ""))
        elif not self.registry.has(step.tool_id):
            status = "failed"
            reason = f"Tool {step.tool_id!r} is not registered"
            failed_error = ToolError(reason)
        elif step.tool_id == "fastspar" and (
            not self.registry.create(step.tool_id, mock_tools=self.mock_tools).check_installation()
            or _network_fallback_needed(step, tables_dir)
        ):
            result = self._run_network_fallback_step(plan, tables_dir)
            parsed_status = str(result.get("parsed_status", ""))
            standard_tables = str(result.get("standard_tables", ""))
            reason = str(result.get("reason", ""))
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
            "reason": reason,
            "return_code": return_code,
            "parsed_status": parsed_status,
            "standard_tables": standard_tables,
        }
        with self._log_lock:
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
        self._emit_progress(
            "step_failed" if status == "failed" else "step_completed",
            {
                **_progress_step_payload(step),
                "status": status,
                "reason": reason,
                "return_code": return_code,
                "parsed_status": parsed_status,
                "standard_tables": standard_tables,
            },
        )
        return row, failed_error

    def _run_internal_step(
        self,
        step: PlanStep,
        plan: ExecutionPlan,
        tables_dir: Path,
    ) -> Dict[str, Any]:
        rows_by_table: Dict[str, Iterable[Mapping[str, Any]]] = {}
        if step.step_name == "diversity":
            computed = compute_diversity_and_differential(plan, tables_dir)
            rows_by_table = {"sample_diversity": computed.get("sample_diversity", [])}
        elif step.step_name == "differential_abundance":
            computed = compute_diversity_and_differential(plan, tables_dir)
            rows_by_table = {"differential_abundance": computed.get("differential_abundance", [])}

        with self._tables_lock:
            written = append_standard_rows(tables_dir, rows_by_table)
        return {
            "parsed_status": "parsed" if written else "no_standard_rows",
            "standard_tables": ",".join(sorted(written)),
        }

    def _run_network_fallback_step(
        self,
        plan: ExecutionPlan,
        tables_dir: Path,
    ) -> Dict[str, Any]:
        rows_by_table = compute_network_fallback(plan, tables_dir)
        with self._tables_lock:
            written = append_standard_rows(tables_dir, rows_by_table)
        return {
            "parsed_status": "parsed" if written else "no_standard_rows",
            "standard_tables": ",".join(sorted(written)),
            "reason": "FastSpar executable unavailable; wrote internal Spearman fallback network.",
        }

    def _refresh_consensus_and_fastas(
        self,
        plan: ExecutionPlan,
        tables_dir: Path,
        config: Mapping[str, Any],
        *,
        candidate_mode: bool,
        write_fastas: bool = True,
    ) -> List[Dict[str, Any]]:
        plasmid_detection = mapping_block(config, "plasmid_detection")
        write_consensus_table(
            tables_dir,
            strategy=str(plasmid_detection.get("strategy", "single_tool")),
            detection_tools=(
                plasmid_detection.get("consensus_tools") or plasmid_detection.get("tools", [])
            ),
        )
        if not write_fastas:
            return []
        return self._write_plasmid_candidate_fastas(
            plan,
            tables_dir,
            candidate_mode=candidate_mode,
        )

    def _write_plasmid_candidate_fastas(
        self, plan: ExecutionPlan, tables_dir: Path, *, candidate_mode: bool = False
    ) -> List[Dict[str, Any]]:
        consensus = read_standard_table(tables_dir, "plasmid_consensus")
        by_sample: Dict[str, Dict[str, str]] = {}
        for row in consensus:
            sample_id = row.get("sample_id", "")
            contig_id = row.get("contig_id", "")
            if sample_id and contig_id:
                by_sample.setdefault(sample_id, {})[contig_id] = row.get("final_plasmid_call", "")

        outputs: List[Dict[str, Any]] = []
        assembly_paths = _assembly_paths_by_sample(plan)
        for sample in plan.samples:
            assembly_value = sample.assembly or assembly_paths.get(sample.sample_id)
            if not assembly_value:
                continue
            assembly = Path(assembly_value)
            sample_outdir = Path(plan.outdir) / PLASMID_DETECTION_DIR / sample.sample_id
            if not assembly.exists():
                outputs.append(
                    {
                        "sample_id": sample.sample_id,
                        "assembly": str(assembly),
                        "status": "missing_assembly",
                        "message": "Assembly FASTA was not found; FASTA export skipped.",
                    }
                )
                continue
            records = _read_fasta_records(assembly)
            sample_calls = by_sample.get(sample.sample_id, {})
            plasmid_records = []
            uncertain_records = []
            non_plasmid_records = []
            for record in records:
                call = sample_calls.get(record["id"], "")
                if candidate_mode and record["id"] in sample_calls:
                    plasmid_records.append(record)
                elif _truthy(call):
                    plasmid_records.append(record)
                elif record["id"] in sample_calls:
                    uncertain_records.append(record)
                else:
                    non_plasmid_records.append(record)

            plasmid_path = sample_outdir / "plasmid_contigs.fasta"
            uncertain_path = sample_outdir / "uncertain_contigs.fasta"
            non_plasmid_path = sample_outdir / "non_plasmid_contigs.fasta"
            _write_fasta_records(plasmid_path, plasmid_records)
            _write_fasta_records(uncertain_path, uncertain_records)
            _write_fasta_records(non_plasmid_path, non_plasmid_records)
            outputs.append(
                {
                    "sample_id": sample.sample_id,
                    "assembly": str(assembly),
                    "status": "candidate_written" if candidate_mode else "written",
                    "plasmid_contigs": str(plasmid_path),
                    "plasmid_count": len(plasmid_records),
                    "uncertain_contigs": str(uncertain_path),
                    "uncertain_count": len(uncertain_records),
                    "non_plasmid_contigs": str(non_plasmid_path),
                    "non_plasmid_count": len(non_plasmid_records),
                }
            )
        return outputs

    def _params_for_step(self, step: PlanStep, *, dry_run: bool) -> Dict[str, Any]:
        params = dict(step.inputs)
        params.update(step.params)
        params.update(step.outputs)
        if "output_dir" not in params and "outdir" in params:
            params["output_dir"] = params["outdir"]
        params["dry_run"] = dry_run
        return params

    def _resolved_input_rows(self, plan: ExecutionPlan, *, dry_run: bool) -> List[Dict[str, Any]]:
        rows = []
        path_fields = {
            "read1",
            "read2",
            "long_reads",
            "assembly",
            "plasmid_contigs",
            "database",
            "model",
            "annotations",
            "gene_calls",
            "plasmid_index",
            "bam",
            "alignment",
            "reference",
            "refgraph",
            "reflist",
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
                        "source": (
                            "sample"
                            if name in step.inputs and str(step.inputs.get(name)) == str(value)
                            else "config_or_plan"
                        ),
                    }
                )
        return rows

    def _run_external_step(
        self, step: PlanStep, provenance: Path, tables_dir: Path
    ) -> Dict[str, Any]:
        skill = self.registry.create(step.tool_id, mock_tools=self.mock_tools)
        step_log_dir = provenance / "step_logs"
        params = self._params_for_step(step, dry_run=False)
        params["stdout_path"] = str(step_log_dir / f"{step.step_id}.stdout.log")
        params["stderr_path"] = str(step_log_dir / f"{step.step_id}.stderr.log")
        try:
            result = skill.run(params, dry_run=False)
        except (ToolError, ABIToolError) as exc:
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
            return {
                "status": "failed",
                "return_code": result.return_code,
                "reason": reason,
            }
        parsed_status = "not_supported"
        standard_tables = ""
        if supports_standard_parsing(step.tool_id):
            rows_by_table = parse_standard_outputs(
                step.tool_id,
                step.outputs.get("output_dir", params.get("output_dir", "")),
                str(step.sample_id or ""),
            )
            with self._tables_lock:
                written = append_standard_rows(tables_dir, rows_by_table)
            parsed_status = "parsed" if written else "no_standard_rows"
            standard_tables = ",".join(sorted(written))
        return {
            "status": result.status,
            "return_code": result.return_code,
            "reason": "",
            "parsed_status": parsed_status,
            "standard_tables": standard_tables,
        }

    def _command_for_step(self, step: PlanStep, *, dry_run: bool) -> List[str]:
        if step.tool_id == "internal":
            return ["autoplasm", "internal", step.step_name, "--step-id", step.step_id]
        if not self.registry.has(step.tool_id):
            return [
                "autoplasm",
                "missing-wrapper",
                step.tool_id,
                "--step-id",
                step.step_id,
            ]
        skill = self.registry.create(step.tool_id, mock_tools=self.mock_tools or dry_run)
        params = self._params_for_step(step, dry_run=dry_run)
        return skill.build_command(params)

    def _write_tool_versions(self, path: Path) -> Path:
        rows = []
        for tool in self.registry.list_tools():
            skill = self.registry.create(str(tool.get("id")), mock_tools=self.mock_tools)
            installed = skill.check_installation()
            rows.append(
                {
                    "tool_id": tool.get("id"),
                    "executable": tool.get("executable"),
                    "env_name": tool.get("env_name"),
                    "version": "not_checked",
                    "status": (
                        "mock" if self.mock_tools else ("installed" if installed else "missing")
                    ),
                }
            )
        return write_tool_versions(rows, path)

    def _emit_progress(self, event: str, payload: Mapping[str, Any]) -> None:
        if self.progress_callback:
            self.progress_callback({"event": event, "payload": dict(payload)})


def _read_fasta_records(path: Path) -> List[Dict[str, str]]:
    records: List[Dict[str, str]] = []
    header = ""
    sequence_lines: List[str] = []
    with path.open("r", encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.rstrip("\n\r")
            if line.startswith(">"):
                if header:
                    records.append(_fasta_record(header, sequence_lines))
                header = line[1:].strip()
                sequence_lines = []
            elif header:
                sequence_lines.append(line.strip())
    if header:
        records.append(_fasta_record(header, sequence_lines))
    return records


def _fasta_record(header: str, sequence_lines: Iterable[str]) -> Dict[str, str]:
    sequence = "".join(sequence_lines)
    return {
        "id": header.split()[0] if header else "",
        "header": header,
        "sequence": sequence,
    }


def _write_fasta_records(path: Path, records: Iterable[Mapping[str, str]]) -> None:
    ensure_directory(path.parent, label="FASTA output directory")
    lines: List[str] = []
    for record in records:
        header = record.get("header", "")
        sequence = record.get("sequence", "")
        if not header:
            continue
        lines.append(f">{header}")
        lines.extend(sequence[index : index + 80] for index in range(0, len(sequence), 80))
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def _needs_plasmid_candidate_fasta(step: PlanStep) -> bool:
    if step.skipped or step.category in {
        "plasmid_detection",
        "assembly_qc",
        "assembly",
        "qc",
    }:
        return False
    plasmid_contigs = step.params.get("plasmid_contigs")
    assembly = step.params.get("assembly")
    return bool(plasmid_contigs and str(plasmid_contigs) != str(assembly or ""))


def _assembly_paths_by_sample(plan: ExecutionPlan) -> Dict[str, str]:
    paths: Dict[str, str] = {}
    for step in plan.steps:
        sample_id = step.sample_id
        assembly = step.params.get("assembly")
        if sample_id and assembly and sample_id not in paths:
            paths[sample_id] = str(assembly)
    return paths


def _steps_by_sample(steps: Iterable[PlanStep]) -> Dict[str, List[PlanStep]]:
    grouped: Dict[str, List[PlanStep]] = {}
    for step in steps:
        if not step.sample_id:
            continue
        grouped.setdefault(step.sample_id, []).append(step)
    return grouped


def _network_fallback_needed(step: PlanStep, tables_dir: Path) -> bool:
    abundance_table = step.params.get("abundance_table", "")
    if abundance_table and Path(str(abundance_table)).exists():
        return False
    rows = read_standard_table(tables_dir, "abundance")
    samples = {row.get("sample_id", "") for row in rows if row.get("sample_id")}
    features = {
        row.get("feature_id") or row.get("contig_id", "")
        for row in rows
        if row.get("feature_id") or row.get("contig_id")
    }
    return len(samples) < 3 or len(features) < 2


def _progress_step_payload(step: PlanStep) -> Dict[str, Any]:
    return {
        "step_id": step.step_id,
        "sample_id": step.sample_id or "",
        "step_name": step.step_name,
        "tool_id": step.tool_id,
        "category": step.category,
    }


def _plan_payload(plan: ExecutionPlan) -> Dict[str, Any]:
    payload = plan.to_dict()
    payload.setdefault("analysis_type", "metagenomic_plasmid")
    return payload


def _execution_options(config: Mapping[str, Any]) -> Dict[str, Any]:
    execution = config.get("execution", {})
    if not isinstance(execution, Mapping):
        execution = {}
    dashboard = execution.get("dashboard", {})
    if not isinstance(dashboard, Mapping):
        dashboard = {}
    workers = execution.get("workers", 1)
    try:
        worker_count = max(int(workers), 1)
    except (TypeError, ValueError):
        worker_count = 1
    parallel = bool(execution.get("parallel", False)) and worker_count > 1
    progress = bool(execution.get("progress", True))
    dashboard_enabled = bool(dashboard.get("enable", False))
    return {
        "parallel": parallel,
        "workers": worker_count if parallel else 1,
        "progress": progress,
        "dashboard_enabled": dashboard_enabled,
        "record_progress": progress or dashboard_enabled,
    }


def _display_command(command: Iterable[str]) -> str:
    return " ".join(">" if token == ">" else shlex.quote(token) for token in command)


def _truthy(value: str) -> bool:
    return str(value).lower() in {"true", "1", "yes", "y"}


def _tool_failure_reason(
    step: PlanStep,
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
        "installation, configured database/resource path, thread/memory limits, "
        "and whether a previous partial output directory should be cleaned or rerun."
    )
    return "; ".join(details)
