"""Backward-compatible ViWrap entry point backed by ABI workflow execution."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any, Mapping

from abi.errors import ToolError
from abi.json_utils import load_json_object
from abi.results import validate_abi_result_dir
from abi.runtimes import RuntimeOptions
from abi.workflow import PreparedWorkflow, WorkflowCoordinator

from .checker import check_environment
from .command_builder import build_viwrap_command, render_command
from .errors import ViWrapEnvironmentError, ViWrapExecutionError, ViWrapParseError
from .parser import parse_viwrap_outputs
from .plan_outputs import find_plan_output


def run_viwrap(config: Mapping[str, Any]) -> dict[str, Any]:
    """Run the canonical ABI workflow while preserving the legacy result envelope."""
    command = build_viwrap_command(config)
    overrides = dict(config)
    out_dir = Path(str(overrides["out_dir"]))
    default_result_dir = out_dir.parent / f"{out_dir.name}.abi_logs"
    legacy_log_dir = Path(str(overrides.get("log_dir") or default_result_dir))
    abi_result_dir = Path(str(overrides.get("outdir") or legacy_log_dir))
    overrides["outdir"] = str(abi_result_dir)
    overrides["log_dir"] = str(legacy_log_dir)
    check_runtime = _legacy_runtime_check_enabled(overrides)

    coordinator = WorkflowCoordinator()
    prepared = coordinator.prepare(
        "viral_viwrap",
        overrides=overrides,
        check_files=not bool(overrides.get("dry_run")),
        options=RuntimeOptions(engine="local", check_runtime=check_runtime),
    )
    report = check_environment(
        prepared.config,
        check_runtime=check_runtime,
    )
    result: dict[str, Any] = {
        "plugin": "viral_viwrap",
        "command": command,
        "command_text": render_command(command),
        "env_report": report,
    }

    if prepared.config.get("dry_run"):
        runtime_result = coordinator.dry_run(prepared)
        result.update(
            {
                "mode": "dry_run",
                "status": "blocked" if report["status"] == "fail" else "ready",
                "abi_result_dir": str(abi_result_dir),
                "abi_outputs": _stringify_outputs(runtime_result.outputs),
            }
        )
        return result
    if report["status"] == "fail":
        raise ViWrapEnvironmentError("ViWrap preflight failed; inspect env_report")

    _write_legacy_command_logs(legacy_log_dir, result["command_text"], report)
    try:
        runtime_result = coordinator.run(prepared)
    except ToolError as exc:
        _copy_legacy_step_logs(prepared, legacy_log_dir)
        _raise_compatibility_error(prepared, out_dir, exc)

    parsed = load_json_object(_plan_output(prepared, "parsed_summary"))
    artifacts = load_json_object(_plan_output(prepared, "artifact_manifest"))
    logs = _copy_legacy_step_logs(prepared, legacy_log_dir)
    canonical_artifact_manifest = runtime_result.outputs["artifact_manifest"]
    artifact_manifest = legacy_log_dir / "artifact_manifest.json"
    shutil.copyfile(canonical_artifact_manifest, artifact_manifest)
    abi_outputs = _stringify_outputs(runtime_result.outputs)
    result.update(
        {
            "mode": "run",
            "status": "success",
            "returncode": runtime_result.return_code,
            "out_dir": str(out_dir),
            "tables": parsed["tables"],
            "artifacts": {
                "viral_genomes": artifacts["groups"]["primary_sequences"],
                "figures": artifacts["groups"]["primary_figures"],
                "amg_outputs": parsed["artifacts"]["amg_outputs"],
            },
            "logs": {
                **logs,
                "command": str(legacy_log_dir / "viwrap.command.txt"),
                "env_report": str(legacy_log_dir / "viwrap.env_report.json"),
                "artifact_manifest": str(artifact_manifest),
            },
            "warnings": parsed["warnings"],
            "abi_result_dir": str(abi_result_dir),
            "abi_outputs": abi_outputs,
        }
    )
    return result


def _plan_output(prepared: PreparedWorkflow, name: str) -> Path:
    output = find_plan_output(prepared.plan, name)
    if output is not None:
        return output
    raise ViWrapParseError(f"Canonical ViWrap plan does not declare output {name!r}")


def _external_step_logs(prepared: PreparedWorkflow) -> tuple[Path, Path]:
    step = next(step for step in prepared.plan.steps if step.tool_id == "viwrap")
    root = Path(str(prepared.plan.provenance_dir)) / "step_logs"
    return root / f"{step.step_id}.stdout.log", root / f"{step.step_id}.stderr.log"


def _stringify_outputs(outputs: Mapping[str, Path]) -> dict[str, str]:
    return {name: str(path) for name, path in outputs.items()}


def _legacy_runtime_check_enabled(config: Mapping[str, Any]) -> bool:
    value = config.get("skip_runtime_check", False)
    if isinstance(value, str):
        skip = value.strip().lower() in {"1", "true", "yes", "on"}
    else:
        skip = bool(value)
    return not skip


def _write_legacy_command_logs(
    root: Path,
    command_text: str,
    report: Mapping[str, Any],
) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "viwrap.command.txt").write_text(command_text + "\n", encoding="utf-8")
    (root / "viwrap.env_report.json").write_text(
        json.dumps(report, indent=2) + "\n",
        encoding="utf-8",
    )


def _copy_legacy_step_logs(prepared: PreparedWorkflow, root: Path) -> dict[str, str]:
    stdout_path, stderr_path = _external_step_logs(prepared)
    aliases = {
        "stdout": root / "viwrap.stdout.log",
        "stderr": root / "viwrap.stderr.log",
    }
    for name, source in (("stdout", stdout_path), ("stderr", stderr_path)):
        if source.is_file():
            shutil.copyfile(source, aliases[name])
    return {name: str(path) for name, path in aliases.items()}


def _raise_compatibility_error(
    prepared: PreparedWorkflow,
    out_dir: Path,
    exc: ToolError,
) -> None:
    commands_path = Path(str(prepared.plan.provenance_dir)) / "commands.tsv"
    inspection = validate_abi_result_dir(prepared.plan.outdir)
    failed_steps = inspection.get("failed_steps", [])
    failed = failed_steps[-1] if failed_steps else {}
    if failed.get("step_name") == "parse":
        raise ViWrapParseError(f"ViWrap output parsing failed; inspect {commands_path}") from exc
    if failed.get("tool_id") == "viwrap":
        if not failed.get("return_code") and out_dir.is_dir():
            parse_viwrap_outputs(out_dir)
        _, stderr_path = _external_step_logs(prepared)
        return_code = failed.get("return_code") or "unknown"
        raise ViWrapExecutionError(f"ViWrap exited with {return_code}; see {stderr_path}") from exc
    raise ViWrapExecutionError(f"ViWrap ABI workflow failed; inspect {commands_path}") from exc
