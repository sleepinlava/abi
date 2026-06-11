"""Shared ABI result/provenance writer."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional

from abi.config import PROJECT_ROOT, write_yaml
from abi.provenance import write_commands_tsv, write_resolved_inputs_tsv, write_tool_versions
from abi.report import write_generic_report
from abi.tables import StandardTableManager


class ABIResultWriter:
    """Write common ABI provenance, standard tables, and reports."""

    def __init__(
        self,
        plugin: Any,
        registry: Any,
        *,
        table_manager: StandardTableManager | None = None,
    ) -> None:
        self.plugin = plugin
        self.registry = registry
        self.table_manager = table_manager or StandardTableManager(plugin.table_schemas())

    def write(
        self,
        *,
        plan: Any,
        config: Mapping[str, Any],
        command_rows: Iterable[Mapping[str, Any]],
        status: str,
        return_code: int | str = "",
        engine: str = "local",
        smoke: bool = False,
        extra_summary: Optional[Mapping[str, Any]] = None,
        extra_environment: Optional[Mapping[str, Any]] = None,
        trace_rows: Optional[Iterable[Mapping[str, Any]]] = None,
    ) -> Dict[str, Path]:
        command_rows = list(command_rows)
        result_dir = Path(str(config["outdir"]))
        provenance = result_dir / "provenance"
        tables_dir = result_dir / "tables"
        provenance.mkdir(parents=True, exist_ok=True)
        tables_dir.mkdir(parents=True, exist_ok=True)
        self.table_manager.ensure_tables(tables_dir)

        plan_path = result_dir / "execution_plan.json"
        plan_path.parent.mkdir(parents=True, exist_ok=True)
        plan_path.write_text(
            json.dumps(plan.to_dict(), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        config_path = write_yaml(config, provenance / "config.resolved.yaml")
        commands_path = write_commands_tsv(command_rows, provenance / "commands.tsv")
        resolved_inputs_path = write_resolved_inputs_tsv(
            _resolved_input_rows(plan, smoke=smoke),
            provenance / "resolved_inputs.tsv",
        )
        versions_path = write_tool_versions(
            _tool_version_rows(self.registry, smoke=smoke),
            provenance / "tool_versions.tsv",
        )
        resources_path = provenance / "resources.json"
        resources_path.write_text(
            json.dumps(
                {"resources": self.registry.check_tools(mock_tools=smoke, config=config)},
                indent=2,
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        environment_path = write_yaml(
            _environment_snapshot(self.registry, engine, smoke, extra_environment),
            provenance / "environment.yml",
        )
        trace_path = _write_trace_tsv(trace_rows or [], provenance / "nextflow_trace.tsv")
        table_summary = self.table_manager.summarize(tables_dir)
        report_paths = write_generic_report(
            plan,
            result_dir,
            table_summary=table_summary,
            title=self.plugin.report_title,
        )
        summary = {
            "project_name": plan.project_name,
            "analysis_type": getattr(plan, "analysis_type", ""),
            "engine": engine,
            "smoke": smoke,
            "status": status,
            "return_code": return_code,
            "sample_count": len(plan.samples),
            "step_count": len(plan.steps),
            "completed_step_count": _completed_step_count(command_rows),
            "selected_tools": plan.selected_tools,
            "standard_tables": table_summary,
        }
        if extra_summary:
            summary.update(dict(extra_summary))
        summary_path = provenance / "run_summary.json"
        summary_path.write_text(
            json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
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
        }
        if trace_path:
            outputs["trace"] = trace_path
        return outputs


def _resolved_input_rows(plan: Any, *, smoke: bool) -> list[dict[str, Any]]:
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
        params = dict(step.inputs)
        params.update(step.params)
        params.update(step.outputs)
        for name in sorted(path_fields):
            value = params.get(name)
            if not value:
                continue
            if smoke and "NOT_CONFIGURED" in str(value):
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


def _completed_step_count(command_rows: Iterable[Mapping[str, Any]]) -> int:
    completed_statuses = {"success", "dry_run"}
    return sum(1 for row in command_rows if str(row.get("status", "")) in completed_statuses)


def _tool_version_rows(registry: Any, *, smoke: bool) -> list[dict[str, Any]]:
    rows = []
    for tool in registry.list_tools():
        skill = registry.create(str(tool.get("id")), mock_tools=smoke)
        rows.append(
            {
                "tool_id": tool.get("id"),
                "executable": tool.get("executable", ""),
                "env_name": tool.get("env_name", ""),
                "version": "",
                "status": "ok" if skill.check_installation() else "missing",
            }
        )
    return rows


def _environment_snapshot(
    registry: Any,
    engine: str,
    smoke: bool,
    extra_environment: Optional[Mapping[str, Any]],
) -> Dict[str, Any]:
    environment: Dict[str, Any] = {
        "engine": engine,
        "smoke": smoke,
        "mamba_root": str(PROJECT_ROOT / ".mamba"),
        "tools": [
            {
                "tool_id": tool.get("id", ""),
                "env_name": tool.get("env_name", ""),
                "executable": tool.get("executable", ""),
            }
            for tool in registry.list_tools()
        ],
    }
    if extra_environment:
        environment.update(dict(extra_environment))
    return environment


def _write_trace_tsv(rows: Iterable[Mapping[str, Any]], path: Path) -> Path | None:
    rows = list(rows)
    if not rows:
        return None
    fields = sorted({str(key) for row in rows for key in row.keys()})
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        handle.write("\t".join(fields) + "\n")
        for row in rows:
            handle.write("\t".join(str(row.get(field, "")) for field in fields) + "\n")
    return path
