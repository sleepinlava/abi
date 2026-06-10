"""Command-line interface for the ABI prototype."""

from __future__ import annotations

import csv
import json
import shutil
from pathlib import Path
from typing import Any, Dict, Optional

import typer

from abi.agent import ABIAgentInterface
from abi.config import compact_overrides
from abi.executor import GenericABIExecutor
from abi.exporters import NextflowExporter
from abi.openai_contracts import export_openai_tools
from abi.plugins import get_plugin, list_plugins
from abi.runtimes import LocalRuntime, NextflowRuntime, RuntimeOptions
from abi.schemas import ABIError
from abi.tables import StandardTableManager
from abi._compat.logger import RunLogger

app = typer.Typer(
    help=(
        "Agent-Bioinformatics Interface prototype. It runs analysis-type plugins "
        "through a common plan, dry-run, provenance, inspect, and report interface."
    ),
    no_args_is_help=True,
)


def _fail(exc: Exception) -> None:
    typer.secho(f"Error: {exc}", fg=typer.colors.RED, err=True)
    raise typer.Exit(code=1)


def _emit_agent_json(payload: str) -> None:
    typer.echo(payload)
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return
    status = data.get("status")
    if status == "error":
        raise typer.Exit(code=1)
    if status == "confirmation_required":
        raise typer.Exit(code=2)


def _common_overrides(
    *,
    mode: Optional[str] = None,
    threads: Optional[int] = None,
    outdir: Optional[str] = None,
    log_dir: Optional[str] = None,
    sample_sheet: Optional[Path] = None,
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


@app.command("list-types")
def list_types(
    output_json: bool = typer.Option(
        False,
        "--output-json",
        help="Emit the agent JSON envelope.",
    ),
) -> None:
    """List installed ABI analysis plugins."""
    if output_json:
        _emit_agent_json(ABIAgentInterface().list_types())
        return
    rows = [
        {
            "type": plugin.plugin_id,
            "name": plugin.display_name,
            "description": plugin.description,
        }
        for plugin in list_plugins()
    ]
    typer.echo(json.dumps(rows, indent=2, ensure_ascii=False))


@app.command("list")
def list_command(
    output_json: bool = typer.Option(
        False,
        "--output-json",
        help="Emit the agent JSON envelope.",
    ),
) -> None:
    """Alias for list-types."""
    list_types(output_json=output_json)


@app.command("init")
def init_command(
    analysis_type: str = typer.Option(..., "--type", help="ABI analysis type."),
    outdir: Path = typer.Option(Path("."), "--outdir", help="Workspace directory."),
    force: bool = typer.Option(False, "--force", help="Allow overwriting ABI template files."),
) -> None:
    """Initialize a minimal ABI workspace from a plugin template."""
    try:
        plugin = get_plugin(analysis_type)
        if not hasattr(plugin, "root"):
            raise ABIError(f"Plugin {analysis_type!r} does not provide init templates")
        root = Path(plugin.root)
        targets = [
            (root / "config_default.yaml", outdir / "config" / f"{analysis_type}.yaml"),
            (root / "sample_sheet_template.tsv", outdir / "samples.tsv"),
        ]
        for source, target in targets:
            if target.exists() and not force:
                raise ABIError(f"Refusing to overwrite existing file without --force: {target}")
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
        typer.echo(
            json.dumps(
                {
                    "analysis_type": analysis_type,
                    "config": str(targets[0][1]),
                    "sample_sheet": str(targets[1][1]),
                },
                indent=2,
                ensure_ascii=False,
            )
        )
    except Exception as exc:
        _fail(exc)


@app.command("plan")
def plan_command(
    analysis_type: str = typer.Option("metagenomic_plasmid", "--type", help="ABI analysis type."),
    config: Optional[Path] = typer.Option(None, "--config", help="Plugin config YAML."),
    sample_sheet: Optional[Path] = typer.Option(None, "--sample-sheet", help="Sample sheet TSV."),
    profile: str = typer.Option("dry_run", "--profile", help="Profile for adapter plugins."),
    mode: Optional[str] = typer.Option(None, "--mode", help="Execution mode."),
    threads: Optional[int] = typer.Option(None, "--threads", help="Thread count."),
    outdir: Optional[str] = typer.Option(None, "--outdir", help="Output directory."),
    log_dir: Optional[str] = typer.Option(None, "--log-dir", help="Log directory."),
    check_files: bool = typer.Option(True, "--check-files/--no-check-files"),
    output_json: bool = typer.Option(False, "--output-json", help="Emit the agent JSON envelope."),
) -> None:
    """Build and write an ABI execution plan."""
    if output_json:
        _emit_agent_json(
            ABIAgentInterface().plan(
                analysis_type=analysis_type,
                config_path=config,
                sample_sheet=sample_sheet,
                profile=profile,
                mode=mode,
                threads=threads,
                outdir=outdir,
                log_dir=log_dir,
                check_files=check_files,
            )
        )
        return
    try:
        plugin = get_plugin(analysis_type)
        cfg = plugin.load_config(
            config,
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
        outdir_path = Path(str(cfg["outdir"]))
        outdir_path.mkdir(parents=True, exist_ok=True)
        plan_path = outdir_path / "execution_plan.json"
        plan_path.write_text(
            json.dumps(_plan_dict(plan, analysis_type), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        typer.echo(json.dumps({"plan": str(plan_path), "steps": len(plan.steps)}, indent=2))
    except Exception as exc:
        _fail(exc)


@app.command("dry-run")
def dry_run_command(
    analysis_type: str = typer.Option("metagenomic_plasmid", "--type", help="ABI analysis type."),
    config: Optional[Path] = typer.Option(None, "--config", help="Plugin config YAML."),
    sample_sheet: Optional[Path] = typer.Option(None, "--sample-sheet", help="Sample sheet TSV."),
    profile: str = typer.Option("dry_run", "--profile", help="Profile for adapter plugins."),
    mode: Optional[str] = typer.Option(None, "--mode", help="Execution mode."),
    threads: Optional[int] = typer.Option(None, "--threads", help="Thread count."),
    outdir: Optional[str] = typer.Option(None, "--outdir", help="Output directory."),
    log_dir: Optional[str] = typer.Option(None, "--log-dir", help="Log directory."),
    progress: Optional[bool] = typer.Option(None, "--progress/--no-progress"),
    check_files: bool = typer.Option(True, "--check-files/--no-check-files"),
    output_json: bool = typer.Option(False, "--output-json", help="Emit the agent JSON envelope."),
) -> None:
    """Run a plugin dry-run and write ABI provenance artifacts."""
    if output_json:
        _emit_agent_json(
            ABIAgentInterface().dry_run(
                analysis_type=analysis_type,
                config_path=config,
                sample_sheet=sample_sheet,
                profile=profile,
                mode=mode,
                threads=threads,
                outdir=outdir,
                log_dir=log_dir,
                progress=progress,
                check_files=check_files,
            )
        )
        return
    try:
        plugin = get_plugin(analysis_type)
        cfg = plugin.load_config(
            config,
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
            outputs = plugin.execute_dry_run(plan, cfg)
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
        typer.echo(json.dumps({key: str(value) for key, value in outputs.items()}, indent=2))
    except Exception as exc:
        _fail(exc)


@app.command("inspect")
def inspect_command(
    result_dir: Path = typer.Option(..., "--result-dir", help="ABI result directory."),
    output_json: bool = typer.Option(False, "--output-json", help="Emit the agent JSON envelope."),
) -> None:
    """Inspect ABI provenance and summarize run health."""
    if output_json:
        _emit_agent_json(ABIAgentInterface().inspect(result_dir=result_dir))
        return
    try:
        provenance = result_dir / "provenance"
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
        typer.echo(
            json.dumps(
                {
                    "result_dir": str(result_dir),
                    "status": summary.get("status", "unknown"),
                    "step_count": len(commands),
                    "failed_steps": failed,
                    "skipped_steps": skipped,
                    "missing_or_placeholder_inputs": missing_inputs,
                },
                indent=2,
                ensure_ascii=False,
            )
        )
    except Exception as exc:
        _fail(exc)


@app.command("report")
def report_command(
    result_dir: Path = typer.Option(..., "--result-dir", help="ABI result directory."),
    analysis_type: Optional[str] = typer.Option(None, "--type", help="ABI analysis type."),
    output_json: bool = typer.Option(False, "--output-json", help="Emit the agent JSON envelope."),
) -> None:
    """Regenerate a plugin report from ABI results."""
    if output_json:
        _emit_agent_json(
            ABIAgentInterface().report(result_dir=result_dir, analysis_type=analysis_type)
        )
        return
    try:
        plan_path = result_dir / "execution_plan.json"
        if not plan_path.exists():
            raise ABIError(f"Missing execution plan: {plan_path}")
        plan_data = json.loads(plan_path.read_text(encoding="utf-8"))
        plugin_id = analysis_type or str(plan_data.get("analysis_type") or "metagenomic_plasmid")
        plugin = get_plugin(plugin_id)
        outputs = plugin.write_report(plan_data, result_dir)
        typer.echo(json.dumps({key: str(value) for key, value in outputs.items()}, indent=2))
    except Exception as exc:
        _fail(exc)


@app.command("export-nextflow")
def export_nextflow_command(
    analysis_type: str = typer.Option("metagenomic_plasmid", "--type", help="ABI analysis type."),
    output: Path = typer.Option(..., "--output", help="Output Nextflow DSL2 script path."),
    config: Optional[Path] = typer.Option(None, "--config", help="Plugin config YAML."),
    sample_sheet: Optional[Path] = typer.Option(None, "--sample-sheet", help="Sample sheet TSV."),
    profile: str = typer.Option("dry_run", "--profile", help="Profile for adapter plugins."),
    mode: Optional[str] = typer.Option(None, "--mode", help="Execution mode."),
    threads: Optional[int] = typer.Option(None, "--threads", help="Thread count."),
    outdir: Optional[str] = typer.Option(None, "--outdir", help="Output directory."),
    log_dir: Optional[str] = typer.Option(None, "--log-dir", help="Log directory."),
    smoke: bool = typer.Option(False, "--smoke", help="Export a runnable smoke workflow."),
    mamba_root: Optional[Path] = typer.Option(None, "--mamba-root", help="Local mamba root."),
    check_files: bool = typer.Option(True, "--check-files/--no-check-files"),
    output_json: bool = typer.Option(False, "--output-json", help="Emit the agent JSON envelope."),
) -> None:
    """Export an ABI execution plan as a Nextflow DSL2 script."""
    if output_json:
        _emit_agent_json(
            ABIAgentInterface().export_nextflow(
                analysis_type=analysis_type,
                output=output,
                config_path=config,
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
        )
        return
    try:
        plugin = get_plugin(analysis_type)
        cfg = plugin.load_config(
            config,
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
        workflow_path = NextflowExporter().write(
            plan,
            cfg,
            plugin.registry(),
            output,
            smoke=smoke,
            mamba_root=mamba_root,
        )
        typer.echo(
            json.dumps(
                {
                    "workflow": str(workflow_path),
                    "analysis_type": analysis_type,
                    "steps": len(plan.steps),
                    "smoke": smoke,
                },
                indent=2,
                ensure_ascii=False,
            )
        )
    except Exception as exc:
        _fail(exc)


@app.command("run")
def run_command(
    analysis_type: str = typer.Option("metagenomic_plasmid", "--type", help="ABI analysis type."),
    engine: str = typer.Option("local", "--engine", help="Runtime engine: local or nextflow."),
    config: Optional[Path] = typer.Option(None, "--config", help="Plugin config YAML."),
    sample_sheet: Optional[Path] = typer.Option(None, "--sample-sheet", help="Sample sheet TSV."),
    profile: str = typer.Option("dry_run", "--profile", help="Profile for adapter plugins."),
    mode: Optional[str] = typer.Option(None, "--mode", help="Execution mode."),
    threads: Optional[int] = typer.Option(None, "--threads", help="Thread count."),
    outdir: Optional[str] = typer.Option(None, "--outdir", help="Output directory."),
    log_dir: Optional[str] = typer.Option(None, "--log-dir", help="Log directory."),
    workflow: Optional[Path] = typer.Option(None, "--workflow", help="Workflow path to write."),
    work_dir: Optional[Path] = typer.Option(None, "--work-dir", help="Nextflow work directory."),
    nxf_home: Optional[Path] = typer.Option(None, "--nxf-home", help="Nextflow home directory."),
    nextflow_bin: Optional[Path] = typer.Option(None, "--nextflow-bin", help="Nextflow executable."),
    nextflow_profile: Optional[str] = typer.Option(None, "--nextflow-profile", help="Nextflow config profile."),
    executor: Optional[str] = typer.Option(None, "--executor", help="Nextflow process executor override."),
    resume: bool = typer.Option(False, "--resume", help="Pass -resume to Nextflow."),
    mamba_root: Optional[Path] = typer.Option(None, "--mamba-root", help="Local mamba root."),
    smoke: bool = typer.Option(False, "--smoke/--real", help="Use mocked/smoke tools."),
    check_files: bool = typer.Option(True, "--check-files/--no-check-files"),
    confirm_execution: bool = typer.Option(
        False,
        "--confirm-execution",
        help="Required with --output-json before executing run.",
    ),
    output_json: bool = typer.Option(False, "--output-json", help="Emit the agent JSON envelope."),
) -> None:
    """Run an ABI execution plan through a selected runtime backend."""
    if output_json:
        _emit_agent_json(
            ABIAgentInterface().run(
                analysis_type=analysis_type,
                engine=engine,
                config_path=config,
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
        )
        return
    try:
        result = _run_with_runtime(
            analysis_type=analysis_type,
            engine=engine,
            config=config,
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
        )
        typer.echo(json.dumps({key: str(value) for key, value in result.outputs.items()}, indent=2))
    except Exception as exc:
        _fail(exc)


@app.command("export-openai-tools")
def export_openai_tools_command(
    analysis_type: str = typer.Option("metagenomic_plasmid", "--type", help="ABI analysis type."),
    descriptor_format: str = typer.Option(
        "responses", "--format", help="Descriptor format: responses, apps-sdk, or json."
    ),
    include_execution: bool = typer.Option(
        False, "--include-execution", help="Include execution tools such as abi_run in the export."
    ),
) -> None:
    """Export OpenAI-compatible ABI agent tool descriptors."""
    try:
        plugin = get_plugin(analysis_type)
        tools = export_openai_tools(
            plugin,
            descriptor_format=descriptor_format,
            include_execution=include_execution,
        )
        typer.echo(json.dumps(tools, indent=2, ensure_ascii=False))
    except Exception as exc:
        _fail(exc)


def _plan_dict(plan: Any, analysis_type: str) -> Dict[str, Any]:
    data = plan.to_dict()
    data.setdefault("analysis_type", analysis_type)
    return data


def _read_tsv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def _run_with_runtime(
    *,
    analysis_type: str,
    engine: str,
    config: Optional[Path],
    sample_sheet: Optional[Path],
    profile: str,
    mode: Optional[str],
    threads: Optional[int],
    outdir: Optional[str],
    log_dir: Optional[str],
    workflow: Optional[Path],
    work_dir: Optional[Path],
    nxf_home: Optional[Path],
    nextflow_bin: Optional[Path],
    nextflow_profile: Optional[str],
    executor: Optional[str],
    resume: bool,
    mamba_root: Optional[Path],
    smoke: bool,
    check_files: bool,
) -> Any:
    runtime_engine = engine.lower().strip()
    if runtime_engine not in {"local", "nextflow"}:
        raise ABIError(f"Unsupported runtime engine: {engine}. Expected local or nextflow.")

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
    cfg = plugin.load_config(config, profile=profile, overrides=overrides)
    plan = plugin.build_plan(cfg, check_files=check_files)
    options = RuntimeOptions(
        engine=runtime_engine,
        smoke=smoke,
        nextflow_bin=nextflow_bin,
        work_dir=work_dir,
        workflow=workflow,
        nxf_home=nxf_home,
        mamba_root=mamba_root,
        profile=nextflow_profile,
        executor=executor,
        resume=resume,
    )
    if runtime_engine == "local":
        runtime = LocalRuntime(plugin, options=options)
    else:
        runtime = NextflowRuntime(plugin, options=options)
    return runtime.run(plan, cfg)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
