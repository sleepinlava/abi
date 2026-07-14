"""Transport-neutral preparation and runtime selection for ABI workflows."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

from abi.runtimes import HpcRuntime, LocalRuntime, NextflowRuntime, RuntimeOptions, RuntimeResult
from abi.schemas import ABIError


@dataclass(frozen=True)
class PreparedWorkflow:
    """A resolved plugin config and canonical plan ready for one runtime."""

    analysis_type: str
    config: Mapping[str, Any]
    plan: Any
    options: RuntimeOptions
    plugin: Any = field(repr=False)


class WorkflowCoordinator:
    """Prepare and execute ABI workflows behind one transport-neutral interface."""

    def prepare(
        self,
        analysis_type: str,
        config_path: str | Path | None = None,
        *,
        profile: str | None = None,
        db_profile: str | None = None,
        overrides: Mapping[str, Any] | None = None,
        resource_overrides: Sequence[str] = (),
        check_files: bool = True,
        options: RuntimeOptions | None = None,
    ) -> PreparedWorkflow:
        from abi.plugins import get_plugin

        plugin = get_plugin(analysis_type)
        config = plugin.load_config(
            Path(config_path) if config_path is not None else None,
            profile=profile,
            db_profile=db_profile,
            overrides=overrides,
        )
        if resource_overrides:
            from abi.resources import apply_resource_overrides

            apply_resource_overrides(config, list(resource_overrides))
        plan = plugin.build_plan(config, check_files=check_files)
        return PreparedWorkflow(
            analysis_type=analysis_type,
            config=config,
            plan=plan,
            options=options or RuntimeOptions(engine="local"),
            plugin=plugin,
        )

    def dry_run(self, prepared: PreparedWorkflow) -> RuntimeResult:
        runtime = self._runtime(prepared)
        execute_dry_run = getattr(prepared.plugin, "execute_dry_run", None)
        if prepared.options.engine.lower().strip() == "local" and callable(execute_dry_run):
            outputs = execute_dry_run(prepared.plan, prepared.config)
            return RuntimeResult(status="success", return_code=0, outputs=dict(outputs))
        return runtime.dry_run(prepared.plan, prepared.config)

    def run(self, prepared: PreparedWorkflow) -> RuntimeResult:
        return self._runtime(prepared).run(prepared.plan, prepared.config)

    @staticmethod
    def _runtime(prepared: PreparedWorkflow) -> Any:
        engine = prepared.options.engine.lower().strip()
        if engine == "local":
            return LocalRuntime(prepared.plugin, options=prepared.options)
        if engine == "nextflow":
            return NextflowRuntime(prepared.plugin, options=prepared.options)
        if engine == "hpc":
            return HpcRuntime(prepared.plugin, options=prepared.options)
        raise ABIError(
            f"Unsupported runtime engine: {prepared.options.engine}. "
            "Expected local, nextflow, or hpc."
        )
