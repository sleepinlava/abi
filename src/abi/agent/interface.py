"""Transport-neutral ABI interface for agent platforms."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Callable, Dict, Mapping, Optional, Tuple, Union, cast

from abi.config import compact_overrides
from abi.executor import GenericABIExecutor
from abi.exporters import NextflowExporter
from abi.interfaces import ABIDryRunPlugin, ABIPlugin
from abi.plugins import get_plugin, list_plugins
from abi.provenance import RunLogger
from abi.runtimes import LocalRuntime, NextflowRuntime, RuntimeOptions
from abi.schemas import ABIError
from abi.tables import StandardTableManager


class ABIAgentInterface:
    """ABI's stable tool boundary for CLI JSON, MCP, HTTP, and function calling.

    Every public method returns a JSON string with the same envelope:
    ``status``, ``command``, and either ``result`` or ``error``.
    """

    def list_types(self) -> str:
        """List installed ABI analysis plugin types."""
        return self._call("list_types", self._list_types)

    def plan(
        self,
        *,
        analysis_type: str,
        config_path: Optional[Union[str, Path]] = None,
        sample_sheet: Optional[Union[str, Path]] = None,
        profile: str = "dry_run",
        mode: Optional[str] = None,
        threads: Optional[int] = None,
        outdir: Optional[str] = None,
        log_dir: Optional[str] = None,
        check_files: bool = True,
    ) -> str:
        """Build and persist an ABI execution plan without running external tools."""
        return self._call(
            "plan",
            self._plan,
            analysis_type=analysis_type,
            config_path=config_path,
            sample_sheet=sample_sheet,
            profile=profile,
            mode=mode,
            threads=threads,
            outdir=outdir,
            log_dir=log_dir,
            check_files=check_files,
        )

    def dry_run(
        self,
        *,
        analysis_type: str,
        config_path: Optional[Union[str, Path]] = None,
        sample_sheet: Optional[Union[str, Path]] = None,
        profile: str = "dry_run",
        mode: Optional[str] = None,
        threads: Optional[int] = None,
        outdir: Optional[str] = None,
        log_dir: Optional[str] = None,
        progress: Optional[bool] = None,
        check_files: bool = True,
    ) -> str:
        """Render commands and provenance artifacts without executing real tools."""
        return self._call(
            "dry_run",
            self._dry_run,
            analysis_type=analysis_type,
            config_path=config_path,
            sample_sheet=sample_sheet,
            profile=profile,
            mode=mode,
            threads=threads,
            outdir=outdir,
            log_dir=log_dir,
            progress=progress,
            check_files=check_files,
        )

    def inspect(self, *, result_dir: Union[str, Path]) -> str:
        """Inspect an ABI result directory and summarize run health."""
        return self._call("inspect", self._inspect, result_dir=result_dir)

    def report(
        self,
        *,
        result_dir: Union[str, Path],
        analysis_type: Optional[str] = None,
    ) -> str:
        """Regenerate ABI reports from an existing result directory."""
        return self._call(
            "report",
            self._report,
            result_dir=result_dir,
            analysis_type=analysis_type,
        )

    def run(
        self,
        *,
        analysis_type: str,
        engine: str = "local",
        config_path: Optional[Union[str, Path]] = None,
        sample_sheet: Optional[Union[str, Path]] = None,
        profile: str = "dry_run",
        mode: Optional[str] = None,
        threads: Optional[int] = None,
        outdir: Optional[str] = None,
        log_dir: Optional[str] = None,
        workflow: Optional[Union[str, Path]] = None,
        work_dir: Optional[Union[str, Path]] = None,
        nxf_home: Optional[Union[str, Path]] = None,
        nextflow_bin: Optional[Union[str, Path]] = None,
        nextflow_profile: Optional[str] = None,
        executor: Optional[str] = None,
        resume: bool = False,
        mamba_root: Optional[Union[str, Path]] = None,
        smoke: bool = False,
        check_files: bool = True,
        confirm_execution: bool = False,
    ) -> str:
        """Run an ABI plan through a runtime backend after explicit confirmation."""
        return self._call(
            "run",
            self._run,
            analysis_type=analysis_type,
            engine=engine,
            config_path=config_path,
            sample_sheet=sample_sheet,
            profile=profile,
            mode=mode,
            threads=threads,
            outdir=outdir,
            log_dir=log_dir,
            workflow=workflow,
            work_dir=work_dir,
            nxf_home=nxf_home,
            nextflow_bin=nextflow_bin,
            nextflow_profile=nextflow_profile,
            executor=executor,
            resume=resume,
            mamba_root=mamba_root,
            smoke=smoke,
            check_files=check_files,
            confirm_execution=confirm_execution,
        )

    def export_nextflow(
        self,
        *,
        analysis_type: str,
        output: Union[str, Path],
        config_path: Optional[Union[str, Path]] = None,
        sample_sheet: Optional[Union[str, Path]] = None,
        profile: str = "dry_run",
        mode: Optional[str] = None,
        threads: Optional[int] = None,
        outdir: Optional[str] = None,
        log_dir: Optional[str] = None,
        smoke: bool = False,
        mamba_root: Optional[Union[str, Path]] = None,
        check_files: bool = True,
    ) -> str:
        """Export an ABI execution plan to Nextflow DSL2 without running it."""
        return self._call(
            "export_nextflow",
            self._export_nextflow,
            analysis_type=analysis_type,
            output=output,
            config_path=config_path,
            sample_sheet=sample_sheet,
            profile=profile,
            mode=mode,
            threads=threads,
            outdir=outdir,
            log_dir=log_dir,
            smoke=smoke,
            mamba_root=mamba_root,
            check_files=check_files,
        )

    def dispatch(self, tool_name: str, arguments: Optional[Mapping[str, Any]] = None) -> str:
        """Dispatch a function-calling style tool invocation."""
        args = dict(arguments or {})
        aliases = {
            "abi_list": "list_types",
            "abi_list_types": "list_types",
            "abi_plan": "plan",
            "abi_dry_run": "dry_run",
            "abi_inspect": "inspect",
            "abi_report": "report",
            "abi_run": "run",
            "abi_export_nextflow": "export_nextflow",
        }
        method_name = aliases.get(tool_name, tool_name)
        method = getattr(self, method_name, None)
        if method is None:
            return _json_dump(
                {
                    "status": "error",
                    "command": tool_name,
                    "error": f"Unknown ABI agent tool: {tool_name}",
                    "available": sorted(aliases),
                }
            )
        try:
            return cast(str, method(**args))
        except TypeError as exc:
            return _json_dump(
                {
                    "status": "error",
                    "command": method_name,
                    "error": str(exc),
                    "error_type": exc.__class__.__name__,
                }
            )

    def _call(self, command: str, handler: Callable[..., Any], *args: Any, **kwargs: Any) -> str:
        try:
            result = handler(*args, **kwargs)
        except Exception as exc:
            payload: Dict[str, Any] = {
                "status": "error",
                "command": command,
                "error": str(exc),
                "error_type": exc.__class__.__name__,
            }
            if "Unknown ABI analysis type" in str(exc):
                payload["available"] = [plugin.plugin_id for plugin in list_plugins()]
            return _json_dump(payload)
        if isinstance(result, Mapping) and result.get("status") == "confirmation_required":
            return _json_dump({"command": command, **dict(result)})
        return _json_dump({"status": "success", "command": command, "result": result})

    def _list_types(self) -> Dict[str, Any]:
        plugins = [
            {
                "analysis_type": plugin.plugin_id,
                "name": plugin.display_name,
                "description": plugin.description,
            }
            for plugin in list_plugins()
        ]
        return {"analysis_types": plugins, "count": len(plugins)}

    def _plan(
        self,
        *,
        analysis_type: str,
        config_path: Optional[Union[str, Path]],
        sample_sheet: Optional[Union[str, Path]],
        profile: str,
        mode: Optional[str],
        threads: Optional[int],
        outdir: Optional[str],
        log_dir: Optional[str],
        check_files: bool,
    ) -> Dict[str, Any]:
        plugin, cfg, plan = self._build_plan(
            analysis_type=analysis_type,
            config_path=config_path,
            sample_sheet=sample_sheet,
            profile=profile,
            mode=mode,
            threads=threads,
            outdir=outdir,
            log_dir=log_dir,
            check_files=check_files,
        )
        del plugin
        outdir_path = Path(str(cfg["outdir"]))
        outdir_path.mkdir(parents=True, exist_ok=True)
        plan_path = outdir_path / "execution_plan.json"
        plan_data = _plan_dict(plan, analysis_type)
        plan_path.write_text(
            json.dumps(plan_data, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        return {
            "analysis_type": analysis_type,
            "plan_path": plan_path,
            "steps": len(getattr(plan, "steps", [])),
            "plan": plan_data,
        }

    def _dry_run(
        self,
        *,
        analysis_type: str,
        config_path: Optional[Union[str, Path]],
        sample_sheet: Optional[Union[str, Path]],
        profile: str,
        mode: Optional[str],
        threads: Optional[int],
        outdir: Optional[str],
        log_dir: Optional[str],
        progress: Optional[bool],
        check_files: bool,
    ) -> Dict[str, Any]:
        plugin = get_plugin(analysis_type)
        cfg = plugin.load_config(
            _optional_path(config_path),
            profile=profile,
            overrides=_common_overrides(
                mode=mode,
                threads=threads,
                outdir=outdir,
                log_dir=log_dir,
                sample_sheet=sample_sheet,
                dry_run=True,
                progress=progress,
            )
            | {"mock_tools": True},
        )
        plan = plugin.build_plan(cfg, check_files=check_files)
        if hasattr(plugin, "execute_dry_run"):
            outputs = cast(ABIDryRunPlugin, plugin).execute_dry_run(plan, cfg)
        else:
            table_manager = StandardTableManager(plugin.table_schemas())
            executor = GenericABIExecutor(
                plugin.registry(),
                RunLogger(str(cfg["log_dir"])),
                table_manager=table_manager,
                parse_outputs=plugin.parse_outputs,
                report_title=plugin.report_title,
                mock_tools=True,
            )
            outputs = executor.dry_run(plan, cfg)
        return {
            "analysis_type": analysis_type,
            "outdir": cfg.get("outdir"),
            "outputs": dict(outputs),
        }

    def _inspect(self, *, result_dir: Union[str, Path]) -> Dict[str, Any]:
        root = Path(result_dir)
        provenance = root / "provenance"
        commands = _read_tsv(provenance / "commands.tsv")
        resolved_inputs = _read_tsv(provenance / "resolved_inputs.tsv")
        failed = [row for row in commands if row.get("status") == "failed"]
        skipped = [row for row in commands if row.get("status") == "skipped"]
        missing_inputs = [
            row
            for row in resolved_inputs
            if str(row.get("exists", "")).lower() == "false"
            or "NOT_CONFIGURED" in row.get("path", "")
        ]
        summary_path = provenance / "run_summary.json"
        summary = (
            json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.exists() else {}
        )
        return {
            "result_dir": root,
            "status": summary.get("status", "unknown"),
            "step_count": len(commands),
            "failed_steps": failed,
            "skipped_steps": skipped,
            "missing_or_placeholder_inputs": missing_inputs,
        }

    def _report(
        self,
        *,
        result_dir: Union[str, Path],
        analysis_type: Optional[str],
    ) -> Dict[str, Any]:
        root = Path(result_dir)
        plan_path = root / "execution_plan.json"
        if not plan_path.exists():
            raise ABIError(f"Missing execution plan: {plan_path}")
        plan_data = json.loads(plan_path.read_text(encoding="utf-8"))
        plugin_id = analysis_type or str(plan_data.get("analysis_type") or "")
        if not plugin_id:
            raise ABIError("Missing analysis_type in execution plan; pass analysis_type.")
        plugin = get_plugin(plugin_id)
        outputs = plugin.write_report(plan_data, root)
        return {"analysis_type": plugin_id, "outputs": dict(outputs)}

    def _run(
        self,
        *,
        analysis_type: str,
        engine: str,
        config_path: Optional[Union[str, Path]],
        sample_sheet: Optional[Union[str, Path]],
        profile: str,
        mode: Optional[str],
        threads: Optional[int],
        outdir: Optional[str],
        log_dir: Optional[str],
        workflow: Optional[Union[str, Path]],
        work_dir: Optional[Union[str, Path]],
        nxf_home: Optional[Union[str, Path]],
        nextflow_bin: Optional[Union[str, Path]],
        nextflow_profile: Optional[str],
        executor: Optional[str],
        resume: bool,
        mamba_root: Optional[Union[str, Path]],
        smoke: bool,
        check_files: bool,
        confirm_execution: bool,
    ) -> Dict[str, Any]:
        runtime_engine = engine.lower().strip()
        if runtime_engine not in {"local", "nextflow"}:
            raise ABIError(f"Unsupported runtime engine: {engine}. Expected local or nextflow.")
        if not confirm_execution:
            return {
                "status": "confirmation_required",
                "result": {
                    "analysis_type": analysis_type,
                    "engine": runtime_engine,
                    "message": "Re-run with confirm_execution=true after user approval.",
                },
            }

        overrides = _common_overrides(
            mode=mode,
            threads=threads,
            outdir=outdir,
            log_dir=log_dir,
            sample_sheet=sample_sheet,
        )
        if runtime_engine == "local" and smoke:
            overrides = overrides | {"mock_tools": True}

        plugin = get_plugin(analysis_type)
        cfg = plugin.load_config(_optional_path(config_path), profile=profile, overrides=overrides)
        plan = plugin.build_plan(cfg, check_files=check_files)
        options = RuntimeOptions(
            engine=runtime_engine,
            smoke=smoke,
            nextflow_bin=_optional_path(nextflow_bin),
            work_dir=_optional_path(work_dir),
            workflow=_optional_path(workflow),
            nxf_home=_optional_path(nxf_home),
            mamba_root=_optional_path(mamba_root),
            profile=nextflow_profile,
            executor=executor,
            resume=resume,
        )
        runtime = (
            LocalRuntime(plugin, options=options)
            if runtime_engine == "local"
            else NextflowRuntime(plugin, options=options)
        )
        result = runtime.run(plan, cfg)
        return {
            "analysis_type": analysis_type,
            "engine": runtime_engine,
            "runtime_status": result.status,
            "return_code": result.return_code,
            "outputs": result.outputs,
        }

    def _export_nextflow(
        self,
        *,
        analysis_type: str,
        output: Union[str, Path],
        config_path: Optional[Union[str, Path]],
        sample_sheet: Optional[Union[str, Path]],
        profile: str,
        mode: Optional[str],
        threads: Optional[int],
        outdir: Optional[str],
        log_dir: Optional[str],
        smoke: bool,
        mamba_root: Optional[Union[str, Path]],
        check_files: bool,
    ) -> Dict[str, Any]:
        plugin, cfg, plan = self._build_plan(
            analysis_type=analysis_type,
            config_path=config_path,
            sample_sheet=sample_sheet,
            profile=profile,
            mode=mode,
            threads=threads,
            outdir=outdir,
            log_dir=log_dir,
            check_files=check_files,
        )
        workflow_path = NextflowExporter().write(
            plan,
            cfg,
            plugin.registry(),
            output,
            smoke=smoke,
            mamba_root=_optional_path(mamba_root),
        )
        return {
            "analysis_type": analysis_type,
            "workflow": workflow_path,
            "steps": len(getattr(plan, "steps", [])),
            "smoke": smoke,
        }

    def _build_plan(
        self,
        *,
        analysis_type: str,
        config_path: Optional[Union[str, Path]],
        sample_sheet: Optional[Union[str, Path]],
        profile: str,
        mode: Optional[str],
        threads: Optional[int],
        outdir: Optional[str],
        log_dir: Optional[str],
        check_files: bool,
    ) -> Tuple[ABIPlugin, Mapping[str, Any], Any]:
        plugin = get_plugin(analysis_type)
        cfg = plugin.load_config(
            _optional_path(config_path),
            profile=profile,
            overrides=_common_overrides(
                mode=mode,
                threads=threads,
                outdir=outdir,
                log_dir=log_dir,
                sample_sheet=sample_sheet,
            ),
        )
        plan = plugin.build_plan(cfg, check_files=check_files)
        return plugin, cfg, plan


def _common_overrides(
    *,
    mode: Optional[str] = None,
    threads: Optional[int] = None,
    outdir: Optional[str] = None,
    log_dir: Optional[str] = None,
    sample_sheet: Optional[Union[str, Path]] = None,
    dry_run: Optional[bool] = None,
    progress: Optional[bool] = None,
) -> Dict[str, Any]:
    overrides: Dict[str, Any] = {
        "mode": mode,
        "threads": threads,
        "outdir": outdir,
        "log_dir": log_dir,
        "dry_run": dry_run,
    }
    if sample_sheet:
        overrides["input"] = {"sample_sheet": str(sample_sheet)}
    if progress is not None:
        overrides["execution"] = {"progress": progress}
    return compact_overrides(overrides)


def _optional_path(value: Optional[Union[str, Path]]) -> Optional[Path]:
    return Path(value) if value is not None else None


def _plan_dict(plan: Any, analysis_type: str) -> Dict[str, Any]:
    data: Dict[str, Any] = dict(plan.to_dict())
    data.setdefault("analysis_type", analysis_type)
    return data


def _read_tsv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def _json_dump(payload: Mapping[str, Any]) -> str:
    return json.dumps(_jsonable(payload), indent=2, ensure_ascii=False)


def _jsonable(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value
