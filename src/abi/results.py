"""Shared ABI result/provenance writer."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional

from abi._shared import _read_tsv
from abi.config import resolved_mamba_root, write_yaml
from abi.provenance import (
    write_commands_tsv,
    write_resolved_inputs_tsv,
    write_tool_versions,
)
from abi.report import write_generic_report
from abi.tables import StandardTableManager

__all__ = ["ABIResultWriter", "completed_abi_result_outputs", "validate_abi_result_dir"]

RESULT_OUTPUT_PATHS = {
    "plan": "execution_plan.json",
    "config": "provenance/config.resolved.yaml",
    "commands": "provenance/commands.tsv",
    "resolved_inputs": "provenance/resolved_inputs.tsv",
    "tool_versions": "provenance/tool_versions.tsv",
    "resources": "provenance/resources.json",
    "environment": "provenance/environment.yml",
    "methods": "provenance/methods.md",
    "summary": "provenance/run_summary.json",
    "progress": "provenance/progress.json",
    "progress_events": "provenance/progress.jsonl",
    "tables": "tables",
    "report": "report/report.md",
    "report_html": "report/report.html",
    "trace": "provenance/nextflow_trace.tsv",
}

REQUIRED_RESULT_OUTPUT_KEYS = (
    "plan",
    "summary",
    "commands",
    "resolved_inputs",
    "tool_versions",
    "resources",
    "progress_events",
    "report",
    "report_html",
)
REQUIRED_RESULT_ARTIFACTS = [RESULT_OUTPUT_PATHS[key] for key in REQUIRED_RESULT_OUTPUT_KEYS]

WRITER_OUTPUT_KEYS = (
    "plan",
    "config",
    "commands",
    "resolved_inputs",
    "tool_versions",
    "resources",
    "environment",
    "summary",
    "progress_events",
    "tables",
    "report",
    "report_html",
)


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
        write_yaml(config, provenance / "config.resolved.yaml")
        write_commands_tsv(command_rows, provenance / "commands.tsv")
        write_resolved_inputs_tsv(
            _resolved_input_rows(plan, smoke=smoke),
            provenance / "resolved_inputs.tsv",
        )
        write_tool_versions(
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
        write_yaml(
            _environment_snapshot(self.registry, engine, smoke, extra_environment),
            provenance / "environment.yml",
        )
        trace_path = _write_trace_tsv(trace_rows or [], provenance / "nextflow_trace.tsv")
        progress_events_path = provenance / "progress.jsonl"
        progress_events_path.write_text(
            json.dumps(
                {
                    "event": "run_completed",
                    "status": status,
                    "engine": engine,
                    "completed_step_count": _completed_step_count(command_rows),
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        table_summary = self.table_manager.summarize(tables_dir)
        write_generic_report(
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
        outputs = {key: result_dir / RESULT_OUTPUT_PATHS[key] for key in WRITER_OUTPUT_KEYS}
        if trace_path:
            outputs["trace"] = trace_path
        return outputs


def completed_abi_result_outputs(result_dir: str | Path) -> Dict[str, Path] | None:
    """Load canonical artifacts when ``result_dir`` is a valid successful ABI result."""
    root = Path(result_dir)
    if not validate_abi_result_dir(root)["valid"]:
        return None
    return {
        key: root / relative_path
        for key, relative_path in RESULT_OUTPUT_PATHS.items()
        if (root / relative_path).exists()
    }


def validate_abi_result_dir(
    result_dir: str | Path,
    *,
    allow_empty_tables: bool = True,
) -> Dict[str, Any]:
    """Validate a result directory against its ABI plugin standard table schema."""
    root = Path(result_dir)
    errors: list[str] = []
    warnings: list[str] = []

    if not root.exists():
        return {
            "result_dir": str(root),
            "analysis_type": "",
            "valid": False,
            "errors": [f"Result directory does not exist: {root}"],
            "warnings": [],
            "status": "missing",
            "failed_steps": [],
            "tables": {},
            "artifacts": {},
        }

    artifacts = _artifact_status(root, REQUIRED_RESULT_ARTIFACTS)
    for relpath, artifact in artifacts.items():
        if not artifact["exists"]:
            errors.append(f"Missing artifact: {relpath}")
        elif artifact["empty"]:
            errors.append(f"Empty artifact: {relpath}")

    plan_path = root / "execution_plan.json"
    summary_path = root / "provenance" / "run_summary.json"
    commands_path = root / "provenance" / "commands.tsv"
    plan = _read_json(plan_path, errors)
    summary = _read_json(summary_path, errors)
    commands = _read_tsv(commands_path)

    status = str(summary.get("status", "unknown")) if summary else "unknown"
    if status != "success":
        errors.append(f"run_summary status is {status!r}, not 'success'")

    failed_steps = [row for row in commands if row.get("status") == "failed"]
    if failed_steps:
        errors.append(f"commands.tsv contains {len(failed_steps)} failed step(s)")

    analysis_type = _analysis_type(plan, summary)
    schemas: Mapping[str, Iterable[str]] = {}
    plugin: Any = None
    if not analysis_type:
        errors.append("Cannot determine analysis_type from execution_plan.json or run_summary.json")
    else:
        try:
            from abi.plugins import get_plugin

            plugin = get_plugin(analysis_type)
            schemas = plugin.table_schemas()
        except Exception as exc:
            errors.append(f"Cannot load table schema for analysis_type {analysis_type!r}: {exc}")

    tables = _table_status(root / "tables", schemas)
    missing_tables = [name for name, table in tables.items() if not table["exists"]]
    if missing_tables:
        errors.append("Missing standard table(s): " + ", ".join(sorted(missing_tables)))

    missing_fields = {
        name: table["missing_fields"]
        for name, table in tables.items()
        if table["exists"] and table["missing_fields"]
    }
    if missing_fields:
        for table_name, fields in sorted(missing_fields.items()):
            errors.append(f"{table_name}.tsv missing field(s): {', '.join(fields)}")

    if not allow_empty_tables:
        specialized_validator = getattr(plugin, "validate_result_dir", None)
        specialized: Mapping[str, Any] | None = None
        if callable(specialized_validator):
            candidate = specialized_validator(root, allow_empty_tables=False)
            if isinstance(candidate, Mapping):
                specialized = candidate
        if specialized is not None and isinstance(specialized.get("errors"), list):
            errors.extend(
                error
                for error in specialized.get("errors", [])
                if str(error).startswith("Empty ") and error not in errors
            )
        else:
            empty_tables = [
                name for name, table in tables.items() if table["exists"] and table["rows"] == 0
            ]
            if empty_tables:
                errors.append("Empty standard table(s): " + ", ".join(sorted(empty_tables)))

    return {
        "result_dir": str(root),
        "analysis_type": analysis_type,
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
        "status": status,
        "failed_steps": failed_steps,
        "tables": tables,
        "artifacts": artifacts,
    }


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
                    "sample_id": "" if step.sample_id is None else str(step.sample_id),
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
        "mamba_root": str(resolved_mamba_root()),
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


def _artifact_status(root: Path, relpaths: Iterable[str]) -> Dict[str, Dict[str, Any]]:
    status: Dict[str, Dict[str, Any]] = {}
    for relpath in relpaths:
        path = root / relpath
        exists = path.exists()
        status[relpath] = {
            "exists": exists,
            "empty": bool(exists and path.is_file() and path.stat().st_size == 0),
            "path": str(path),
        }
    return status


def _read_json(path: Path, errors: list[str]) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        errors.append(f"Invalid JSON in {path}: {exc}")
        return {}


def _analysis_type(plan: Mapping[str, Any], summary: Mapping[str, Any]) -> str:
    value = plan.get("analysis_type") or summary.get("analysis_type") or ""
    return str(value) if value else ""


def _table_status(
    tables_dir: Path,
    schemas: Mapping[str, Iterable[str]],
) -> Dict[str, Dict[str, Any]]:
    status: Dict[str, Dict[str, Any]] = {}
    for table_name, fields in schemas.items():
        expected_fields = [str(field) for field in fields]
        path = tables_dir / f"{table_name}.tsv"
        if not path.exists():
            status[table_name] = {
                "exists": False,
                "rows": 0,
                "path": str(path),
                "missing_fields": expected_fields,
            }
            continue
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle, delimiter="\t")
            rows = list(reader)
            actual_fields = reader.fieldnames or []
        status[table_name] = {
            "exists": True,
            "rows": len(rows),
            "path": str(path),
            "missing_fields": [field for field in expected_fields if field not in actual_fields],
        }
    return status
