"""Single-step execution used by native HPC worker jobs."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any, Mapping

from abi._shared import _display_command
from abi.contracts.step_contract import (
    ContractViolationError,
    compute_output_checksums,
    evaluate_assertions,
    validate_output_contract,
)
from abi.executor import _build_assertion_context, _resolve_actual_outputs
from abi.internal import InternalHandlerContext, internal_handler_spec, plugin_internal_handlers
from abi.path_policy import resolve_within
from abi.plugins import get_plugin
from abi.schemas import PlanStep


@dataclass
class StepExecutionResult:
    step_id: str
    tool_id: str
    status: str
    return_code: int | str = 0
    reason: str = ""
    command: str = ""
    standard_tables: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    artifacts: dict[str, str] = field(default_factory=dict)
    checksums: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def plan_step_from_dict(data: Mapping[str, Any]) -> PlanStep:
    fields = {
        "step_id",
        "step_name",
        "tool_id",
        "category",
        "sample_id",
        "inputs",
        "outputs",
        "params",
        "reason",
        "skipped",
    }
    return PlanStep(**{key: value for key, value in data.items() if key in fields})


def execute_step(
    plugin: Any,
    step: PlanStep,
    config: Mapping[str, Any],
    *,
    provenance_dir: str | Path,
) -> StepExecutionResult:
    """Execute one external tool or internal handler without global finalization."""
    provenance = Path(provenance_dir)
    log_dir = provenance / "step_logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    tables: dict[str, list[dict[str, Any]]] = {}
    artifacts: dict[str, str] = {}
    command: list[str] = []
    try:
        outdir = Path(str(config["outdir"]))
        resolved_declared_outputs = {
            key: resolve_within(outdir, Path(str(value)), label=f"{key} for step {step.step_id}")
            for key, value in step.outputs.items()
            if value
        }
        effective_outputs = dict(step.outputs)
        effective_outputs.update(
            {key: str(path) for key, path in resolved_declared_outputs.items()}
        )
        step = replace(step, outputs=effective_outputs)
        if step.tool_id == "internal":
            handler_id, _ = internal_handler_spec(step)
            handler = plugin_internal_handlers(plugin).get(handler_id)
            if handler is None:
                raise RuntimeError(f"Internal handler {handler_id!r} is not registered")
            command = ["abi", "internal", handler_id, "--step-id", step.step_id]
            handler_result = handler.run(
                step,
                config,
                InternalHandlerContext(
                    outdir=outdir,
                    provenance_dir=provenance,
                    tables_dir=outdir / "tables",
                ),
            )
            if handler_result.status != "success":
                return StepExecutionResult(
                    step.step_id,
                    step.tool_id,
                    handler_result.status,
                    1,
                    handler_result.message,
                    _display_command(command),
                )
            tables = {
                name: [dict(row) for row in rows] for name, rows in handler_result.tables.items()
            }
            artifacts = {
                name: str(
                    resolve_within(
                        outdir, Path(str(path)), label=f"artifact {name} for {step.step_id}"
                    )
                )
                for name, path in handler_result.artifacts.items()
            }
            reason = handler_result.message
        else:
            registry = plugin.registry()
            skill = registry.create(step.tool_id)
            metadata = registry.get(step.tool_id)
            must_not_exist = str(metadata.get("output_dir_policy", "create")) == "must_not_exist"
            declared_output_dir = step.outputs.get("output_dir")
            resolved_outputs = resolved_declared_outputs
            effective_outputs.update({key: str(path) for key, path in resolved_outputs.items()})
            for key, value in step.outputs.items():
                if not value:
                    continue
                output_path = resolved_outputs[key]
                if key == "output_dir":
                    target = output_path.parent if must_not_exist else output_path
                elif must_not_exist and declared_output_dir:
                    target = resolved_outputs["output_dir"].parent
                else:
                    target = output_path.parent
                target.mkdir(parents=True, exist_ok=True)
            params = dict(step.inputs)
            params.update(step.params)
            params.update(effective_outputs)
            params["stdout_path"] = str(log_dir / f"{step.step_id}.stdout.log")
            params["stderr_path"] = str(log_dir / f"{step.step_id}.stderr.log")
            command = skill.build_command(params)
            run_result = skill.run(params, dry_run=False)
            if run_result.return_code != 0:
                return StepExecutionResult(
                    step.step_id,
                    step.tool_id,
                    "failed",
                    run_result.return_code,
                    f"Tool exited with {run_result.return_code}; see {params['stderr_path']}",
                    _display_command(command),
                )
            output_dir = params.get("output_dir", "")
            parsed = plugin.parse_outputs(
                step.tool_id,
                output_dir,
                "" if step.sample_id is None else str(step.sample_id),
            )
            tables = {name: [dict(row) for row in rows] for name, rows in parsed.items()}
            reason = ""

        contract = step.params.get("_contract", {})
        resolved_outputs = _resolve_actual_outputs(
            effective_outputs,
            contract.get("outputs", {}),
            step.sample_id or "",
        )
        contract_result = validate_output_contract(
            step.step_id, resolved_outputs, contract.get("outputs", {})
        )
        if not contract_result.passed:
            raise ContractViolationError(step.step_id, contract_result.violations)
        assertions = contract.get("assertions", [])
        if assertions:
            violations = evaluate_assertions(
                assertions, _build_assertion_context(step, resolved_outputs)
            )
            if violations:
                raise ContractViolationError(step.step_id, violations)
        checksums = contract_result.checksums or compute_output_checksums(resolved_outputs)
        return StepExecutionResult(
            step.step_id,
            step.tool_id,
            "success",
            0,
            reason,
            _display_command(command),
            tables,
            artifacts,
            checksums,
        )
    except Exception as exc:
        return StepExecutionResult(
            step.step_id,
            step.tool_id,
            "failed",
            1,
            f"{type(exc).__name__}: {exc}",
            _display_command(command),
        )


def write_step_payload(
    path: str | Path,
    *,
    plugin_id: str,
    step: PlanStep,
    config: Mapping[str, Any],
    provenance_dir: str | Path,
    result_path: str | Path,
) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(
            {
                "plugin_id": plugin_id,
                "step": step.to_dict(),
                "config": dict(config),
                "provenance_dir": str(provenance_dir),
                "result_path": str(result_path),
            },
            indent=2,
            default=str,
        )
        + "\n",
        encoding="utf-8",
    )
    destination.chmod(0o600)
    return destination


def execute_step_payload(path: str | Path) -> StepExecutionResult:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    plugin = get_plugin(str(payload["plugin_id"]))
    step = plan_step_from_dict(payload["step"])
    result = execute_step(
        plugin,
        step,
        payload["config"],
        provenance_dir=payload["provenance_dir"],
    )
    result_path = Path(payload["result_path"])
    result_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = result_path.with_suffix(result_path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(result.to_dict(), handle, indent=2)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, result_path)
    return result
