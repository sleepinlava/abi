"""Executable internal DAG handlers for the managed ViWrap workflow."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from abi.internal import FunctionInternalHandler, InternalHandlerContext, InternalHandlerResult

from .artifact_mapper import collect_artifacts
from .checker import check_environment, check_inputs
from .command_builder import build_viwrap_command, render_command
from .errors import ViWrapInputError
from .parser import parse_viwrap_outputs


def _write_json(path: str | Path, value: Mapping[str, Any]) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    return destination


def validate_inputs_handler(
    step: Any,
    config: Mapping[str, Any],
    context: InternalHandlerContext,
) -> InternalHandlerResult:
    del context
    checks = check_inputs(config)
    failures = [result.message for result in checks if result.status == "fail"]
    report = {
        "plugin": "viral_viwrap",
        "status": "fail" if failures else "pass",
        "checks": [result.__dict__ for result in checks],
    }
    _write_json(step.outputs["validation_report"], report)
    if failures:
        raise ViWrapInputError("; ".join(failures))
    return InternalHandlerResult(message="ViWrap inputs validated")


def environment_handler(
    step: Any,
    config: Mapping[str, Any],
    context: InternalHandlerContext,
) -> InternalHandlerResult:
    del context
    report = check_environment(config, check_runtime=False)
    _write_json(step.outputs["env_report"], report)
    return InternalHandlerResult(
        status="failed" if report["status"] == "fail" else "success",
        message="; ".join(report.get("recommendations", [])),
    )


def command_plan_handler(
    step: Any,
    config: Mapping[str, Any],
    context: InternalHandlerContext,
) -> InternalHandlerResult:
    del context
    command = build_viwrap_command(config)
    payload = {"argv": command, "command": render_command(command)}
    _write_json(step.outputs["command_plan"], payload)
    return InternalHandlerResult(message="ViWrap command planned")


def parse_summary_handler(
    step: Any,
    config: Mapping[str, Any],
    context: InternalHandlerContext,
) -> InternalHandlerResult:
    del config, context
    parsed = parse_viwrap_outputs(step.inputs["output_dir"])
    _write_json(step.outputs["parsed_summary"], parsed)
    return InternalHandlerResult(message="ViWrap summary parsed")


def collect_artifacts_handler(
    step: Any,
    config: Mapping[str, Any],
    context: InternalHandlerContext,
) -> InternalHandlerResult:
    del context
    manifest = collect_artifacts(config["out_dir"], step.outputs["artifact_manifest"])
    return InternalHandlerResult(message=f"Collected {manifest['artifact_count']} ViWrap artifacts")


def report_handler(
    step: Any,
    config: Mapping[str, Any],
    context: InternalHandlerContext,
) -> InternalHandlerResult:
    del context
    report_path = Path(step.outputs["report_markdown"])
    report_path.parent.mkdir(parents=True, exist_ok=True)
    parsed = parse_viwrap_outputs(config["out_dir"], require_core=False)
    rows = [
        "# ViWrap Viral Metagenomics Report",
        "",
        f"Status: {parsed['status']}",
        f"Output directory: `{config['out_dir']}`",
        "",
        "## Parsed tables",
        "",
    ]
    rows.extend(f"- {name}: `{path}`" for name, path in sorted(parsed["tables"].items()))
    if parsed["warnings"]:
        rows.extend(["", "## Warnings", ""])
        rows.extend(f"- {warning}" for warning in parsed["warnings"])
    report_path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    return InternalHandlerResult(
        message="ViWrap report generated", artifacts={"report": report_path}
    )


def handlers() -> dict[str, FunctionInternalHandler]:
    return {
        "viral_viwrap.validate_inputs": FunctionInternalHandler(
            "viral_viwrap.validate_inputs", validate_inputs_handler, "driver"
        ),
        "viral_viwrap.check_environment": FunctionInternalHandler(
            "viral_viwrap.check_environment", environment_handler, "driver"
        ),
        "viral_viwrap.plan_command": FunctionInternalHandler(
            "viral_viwrap.plan_command", command_plan_handler, "driver"
        ),
        "viral_viwrap.parse_summary": FunctionInternalHandler(
            "viral_viwrap.parse_summary", parse_summary_handler
        ),
        "viral_viwrap.collect_artifacts": FunctionInternalHandler(
            "viral_viwrap.collect_artifacts", collect_artifacts_handler
        ),
        "viral_viwrap.report": FunctionInternalHandler("viral_viwrap.report", report_handler),
    }
