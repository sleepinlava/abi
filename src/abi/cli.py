"""Command-line interface for the ABI (Agent-Bioinformatics Interface) prototype.

ABI CLI — command-line interface for the ABI prototype.

This module defines the Typer application with all subcommands. It serves as
the primary human interface and also as a machine interface via the
``--output-json`` flag, which routes through ``ABIAgentInterface`` to emit
JSON envelopes consumable by LLM agents.

Commands overview
-----------------

============================  ===================================================
Command                       Purpose
============================  ===================================================
``list-types`` / ``list``     List installed ABI analysis plugins.
``init``                      Scaffold a workspace from a plugin template.
``plan``                      Build and write an ABI execution plan.
``dry-run``                   Validate a plan and write provenance (no tool execution).
``run``                       Execute a plan through local or Nextflow runtime.
``run-nextflow``              Convenience alias for ``run --engine nextflow``.
``inspect``                   Inspect ABI provenance and summarize run health.
``report``                    Regenerate a plugin report from ABI results.
``validate-result``           Validate an ABI result directory without modifying it.
``export-nextflow``           Export an execution plan as a Nextflow DSL2 script.
``export-openai-tools``       Export ABI tools as OpenAI-compatible function descriptors.
``export-agent-context``      Export compact machine-readable context for agent callers.
``check-resources``           Check database/index/model resources (read-only).
``setup-resources``           Download/mock/plan resource setup.
``doctor-agent``              Print a safe operating guide for ABI agent callers.
``install-skills``            Install ABI agent skills into ~/.claude/skills/.
``dispatch``                  Headless subprocess dispatch for Job Service workers.
``job-service``               Start the HTTP Job Service for queued operations.
``job submit``                Submit a job to the ABI Job Service.
``job status``                Fetch a queued job's current status.
``job artifacts``             Fetch artifact paths from a completed/running job.
``job cancel``                Request cancellation of a queued/running job.
============================  ===================================================

Key design decisions
--------------------

**Confirmation gate for ``run``**: The ``run`` command requires
``--confirm-execution`` before it will actually execute. Without this flag,
the command returns a JSON confirmation-required envelope (exit code 2)
so agent callers can present a confirmation prompt before incurring cost.

**``--output-json`` flag**: Every command accepts this flag. When set, the
command delegates to ``ABIAgentInterface`` which returns a structured JSON
envelope with ``status`` (success/error/confirmation_required), ``message``,
and ``data`` fields. This is the primary integration point for LLM agents.

**``dispatch`` command**: A headless subprocess entry point used internally
by the Job Service. Workers spawn ``abi dispatch --command <cmd> --arguments
<json>`` subprocesses so that job cancellation can force-kill the subprocess
via SIGTERM without affecting the service process itself.

**Job Service (``job`` / ``job-service``)**: Provides an HTTP API for queuing
long-running ABI operations (plans, runs, resource setup). The ``job-service``
command starts the server; ``job submit/status/artifacts/cancel`` interact
with a running service. Subprocess workers (``--subprocess-workers``) use
``dispatch`` internally for clean cancellation.

ABI CLI 命令行界面。

本模块定义了 Typer 应用及其所有子命令。它既作为主要的人机界面，
也通过 ``--output-json`` 标志作为机器界面，该标志通过 ``ABIAgentInterface``
路由，发出 LLM agent 可消费的 JSON 信封。

关键设计决策：
- ``run`` 的确认门：需要 ``--confirm-execution`` 才实际执行，agent 可以先展示确认提示。
- ``--output-json`` 标志：委托给 ``ABIAgentInterface``，返回结构化 JSON 信封。
- ``dispatch`` 命令：Job Service 内部使用的无头子进程入口点。
- Job Service：为排队长时间运行的 ABI 操作提供 HTTP API。
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

import typer

from abi._shared import _common_overrides
from abi.agent import ABIAgentInterface
from abi.agent.context import build_agent_context, render_doctor_agent
from abi.exporters import NextflowExporter
from abi.json_utils import load_json_object, loads_json
from abi.openai_contracts import export_openai_tools  # backward compat
from abi.plugins import get_plugin, list_plugins
from abi.resources import check_resources, setup_resources
from abi.results import validate_abi_result_dir
from abi.schemas import ABIError
from abi.tool_descriptors import (
    PROVIDER_PROFILES,
    export_anthropic,
    export_gemini,
    export_openai_compatible,
)

# Main Typer app. ``no_args_is_help=True`` means running ``abi`` with no
# arguments prints the help text instead of an error.
# 主 Typer 应用。``no_args_is_help=True`` 表示不带参数运行 ``abi`` 时打印帮助文本而非错误。
app = typer.Typer(
    help=(
        "Agent-Bioinformatics Interface prototype. It runs analysis-type plugins "
        "through a common plan, dry-run, provenance, inspect, and report interface."
    ),
    no_args_is_help=True,
)
# Sub-Typer for Job Service operations, mounted at ``abi job``.
# 用于 Job Service 操作的子 Typer，挂载在 ``abi job`` 下。
job_app = typer.Typer(help="Submit and inspect queued ABI Job Service operations.")
app.add_typer(job_app, name="job")


def _resolve_skills_source() -> Path:
    """Resolve the bundled skills directory inside the ABI package.

    Uses ``importlib.resources`` (Python ≥ 3.9) when available, falling back
    to ``Path(abi.__file__).parent / "skills"`` for compatibility with
    zip-imports and frozen environments.

    解析 ABI 包内的 skills 目录。优先使用 importlib.resources，
    在 zip 导入或冻结环境中回退到 __file__ 路径。
    """
    try:
        from importlib.resources import files as _resources_files

        _path = _resources_files("abi") / "skills"
        if _path.is_dir():
            return Path(str(_path))
    except Exception:
        pass
    import abi

    _path = Path(abi.__file__).parent / "skills"
    if not _path.is_dir():
        raise ABIError(f"ABI skills directory not found: {_path}")
    return _path


def _fail(exc: Exception) -> None:
    """Handle CLI errors: print to stderr in red and exit with code 1.

    ``MemoryError`` is re-raised because it indicates a terminal resource
    exhaustion that should not be caught as a normal error.

    处理 CLI 错误：以红色输出到 stderr 并以代码 1 退出。
    ``MemoryError`` 被重新抛出，因为它表示终端资源耗尽，不应作为普通错误捕获。
    """
    if isinstance(exc, MemoryError):
        raise
    typer.secho(f"Error: {exc}", fg=typer.colors.RED, err=True)
    raise typer.Exit(code=1)


def _emit_agent_json(payload: str) -> None:
    """Emit an agent JSON envelope and interpret its status code.

    When ``--output-json`` is active, the CLI outputs a JSON envelope with
    a ``status`` field. This function:
    - Echos the payload to stdout.
    - Parses it to check the status.
    - Exits with code 1 for ``"error"`` and code 2 for
      ``"confirmation_required"`` (used by the ``run`` confirmation gate).

    Exit code 2 is the signal that tells an agent caller "please confirm
    before proceeding"; the caller should present the confirmation message
    to the user and re-invoke with ``--confirm-execution``.

    发出 agent JSON 信封并解释其状态码。

    当 ``--output-json`` 激活时，CLI 输出带有 ``status`` 字段的 JSON 信封。
    退出码 2 是告诉 agent 调用者"请在继续前确认"的信号。
    """
    typer.echo(payload)
    try:
        data = loads_json(payload, label="agent response")
    except ABIError:
        raise typer.Exit(code=1)
    if not isinstance(data, dict):
        raise typer.Exit(code=1)
    status = data.get("status")
    if status == "error":
        raise typer.Exit(code=1)
    if status == "confirmation_required":
        raise typer.Exit(code=2)


def _agent_result(payload: str) -> Dict[str, Any]:
    """Unwrap an agent envelope for the human-readable CLI transport."""
    data = loads_json(payload, label="agent response")
    if not isinstance(data, dict):
        raise ABIError("Agent response must be a JSON object")
    status = data.get("status")
    if status == "confirmation_required":
        raise typer.Exit(code=2)
    if status == "error":
        code = data.get("error_code", "internal_error")
        raise ABIError(f"{code}: {data.get('error', 'ABI command failed')}")
    result = data.get("result")
    if status != "success" or not isinstance(result, dict):
        raise ABIError("Agent response is missing a success result")
    return result


def _emit_json_payload(payload: Any) -> None:
    """Emit a JSON payload to stdout with consistent formatting.

    以一致的格式将 JSON 负载输出到 stdout。
    """
    typer.echo(json.dumps(payload, indent=2, ensure_ascii=False))


def _load_plugin_config(
    *,
    analysis_type: str,
    config: Optional[Path],
    profile: str,
    overrides: Mapping[str, Any],
) -> Dict[str, Any]:
    """Load and resolve a plugin configuration.

    Gets the plugin by analysis type, then calls its ``load_config`` with
    the given profile and overrides. The result is a fully-resolved config
    dict with all defaults, profile layers, and CLI overrides merged.

    加载并解析插件配置。
    根据分析类型获取插件，然后使用给定的 profile 和覆盖项调用其 ``load_config``。
    结果是一个完全解析的配置字典，包含所有默认值、profile 层和 CLI 覆盖项。
    """
    plugin = get_plugin(analysis_type)
    return plugin.load_config(config, profile=profile, overrides=overrides)


@app.command("list-types")
def list_types(
    output_json: bool = typer.Option(
        False,
        "--output-json",
        help="Emit the agent JSON envelope.",
    ),
) -> None:
    """List installed ABI analysis plugins.

    When ``--output-json`` is set, routes through ``ABIAgentInterface`` for
    a structured agent envelope. Otherwise prints a simple JSON array of
    plugin descriptors (type, name, description).

    列出已安装的 ABI 分析插件。
    当 ``--output-json`` 设置时，通过 ``ABIAgentInterface`` 路由以获取结构化的 agent 信封。
    否则打印插件描述符的简单 JSON 数组。
    """
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
    """Alias for list-types. Lists installed ABI analysis plugins.

    list-types 的别名。列出已安装的 ABI 分析插件。
    """
    list_types(output_json=output_json)


@app.command("init")
def init_command(
    analysis_type: str = typer.Option(..., "--type", help="ABI analysis type."),
    outdir: Path = typer.Option(Path("."), "--outdir", help="Workspace directory."),
    force: bool = typer.Option(False, "--force", help="Allow overwriting ABI template files."),
) -> None:
    """Initialize a minimal ABI workspace from a plugin template.

    Copies the plugin's default config YAML and sample sheet template into
    the target workspace. Refuses to overwrite existing files unless
    ``--force`` is set.

    从插件模板初始化最小的 ABI 工作空间。
    将插件的默认配置 YAML 和样本表模板复制到目标工作空间。
    除非设置 ``--force``，否则拒绝覆盖已有文件。
    """
    try:
        plugin = get_plugin(analysis_type)
        if not hasattr(plugin, "root"):
            raise ABIError(f"Plugin {analysis_type!r} does not provide init templates")
        root = Path(plugin.root)
        # Target files: config YAML and sample sheet TSV template.
        # 目标文件：配置 YAML 和样本表 TSV 模板。
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
    analysis_type: str = typer.Option(..., "--type", help="ABI analysis type."),
    config: Optional[Path] = typer.Option(None, "--config", help="Plugin config YAML."),
    sample_sheet: Optional[Path] = typer.Option(None, "--sample-sheet", help="Sample sheet TSV."),
    profile: str = typer.Option("dry_run", "--profile", help="Profile for adapter plugins."),
    mode: Optional[str] = typer.Option(None, "--mode", help="Execution mode."),
    threads: Optional[int] = typer.Option(None, "--threads", help="Thread count."),
    outdir: Optional[str] = typer.Option(None, "--outdir", help="Output directory."),
    log_dir: Optional[str] = typer.Option(None, "--log-dir", help="Log directory."),
    check_files: bool = typer.Option(True, "--check-files/--no-check-files"),
    output_json: bool = typer.Option(
        False,
        "--output-json",
        help="Emit the agent JSON envelope.",
    ),
) -> None:
    """Build and write an ABI execution plan to ``<outdir>/execution_plan.json``.

    This command resolves the plugin configuration, builds a step plan via
    ``plugin.build_plan()``, and persists it as JSON. The plan encodes every
    step: tool_id, inputs, params, outputs, and the command to run.

    ``check_files`` controls whether input file existence is validated during
    plan construction. Disable with ``--no-check-files`` for offline planning.

    构建 ABI 执行计划并写入 ``<outdir>/execution_plan.json``。
    该命令解析插件配置，通过 ``plugin.build_plan()`` 构建步骤计划，并持久化为 JSON。
    计划编码了每个步骤：tool_id、inputs、params、outputs 以及要运行的命令。
    """
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
        result = _agent_result(
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
        typer.echo(
            json.dumps({"plan": str(result["plan_path"]), "steps": result["steps"]}, indent=2)
        )
    except Exception as exc:
        _fail(exc)


@app.command("dry-run")
def dry_run_command(
    analysis_type: str = typer.Option(..., "--type", help="ABI analysis type."),
    config: Optional[Path] = typer.Option(None, "--config", help="Plugin config YAML."),
    sample_sheet: Optional[Path] = typer.Option(None, "--sample-sheet", help="Sample sheet TSV."),
    profile: str = typer.Option("dry_run", "--profile", help="Profile for adapter plugins."),
    mode: Optional[str] = typer.Option(None, "--mode", help="Execution mode."),
    threads: Optional[int] = typer.Option(None, "--threads", help="Thread count."),
    outdir: Optional[str] = typer.Option(None, "--outdir", help="Output directory."),
    log_dir: Optional[str] = typer.Option(None, "--log-dir", help="Log directory."),
    progress: Optional[bool] = typer.Option(None, "--progress/--no-progress"),
    check_files: bool = typer.Option(True, "--check-files/--no-check-files"),
    output_json: bool = typer.Option(
        False,
        "--output-json",
        help="Emit the agent JSON envelope.",
    ),
    resource_profile: Optional[str] = typer.Option(
        None,
        "--resource-profile",
        help="Resource profile preset (dev_small, hpc_standard, hpc_large).",
    ),
    cpu_override: Optional[int] = typer.Option(
        None,
        "--cpu",
        help="CPU cores for all steps.",
    ),
    memory_override: Optional[str] = typer.Option(
        None,
        "--memory",
        help="Memory per step (e.g. 16GB).",
    ),
    walltime_override: Optional[str] = typer.Option(
        None,
        "--walltime",
        help="Walltime per step (e.g. 04:00:00).",
    ),
    accelerator_override: Optional[str] = typer.Option(
        None,
        "--accelerator",
        help="GPU/accelerator (e.g. gpu:v100:1).",
    ),
    container_image: Optional[str] = typer.Option(
        None,
        "--container-image",
        help="Container image for all steps.",
    ),
    container_runtime: Optional[str] = typer.Option(
        None,
        "--container-runtime",
        help="Container runtime: docker, singularity, podman, apptainer.",
    ),
) -> None:
    """Run a plugin dry-run and write ABI provenance artifacts.

    A dry run validates the execution plan without invoking any real external
    tools. It produces the same provenance artifacts as a real run (commands.tsv,
    resolved_inputs.tsv, run_summary.json, report, etc.) but every step is
    marked ``"dry_run"`` and no computation occurs.

    If the plugin has a custom ``execute_dry_run`` method, it is used;
    otherwise the generic ``GenericABIExecutor`` runs in dry_run mode.

    运行插件预演并写出 ABI 溯源产物。
    预演验证执行计划而不调用任何真实的外部工具。它产生与实际运行相同的溯源产物，
    但每个步骤都标记为 ``"dry_run"``，且不发生实际计算。
    """
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
                resource_profile=resource_profile,
                cpu_override=cpu_override,
                memory_override=memory_override,
                walltime_override=walltime_override,
                accelerator_override=accelerator_override,
                container_image=container_image,
                container_runtime=container_runtime,
            )
        )
        return
    try:
        result = _agent_result(
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
                resource_profile=resource_profile,
                cpu_override=cpu_override,
                memory_override=memory_override,
                walltime_override=walltime_override,
                accelerator_override=accelerator_override,
                container_image=container_image,
                container_runtime=container_runtime,
            )
        )
        typer.echo(json.dumps(result["outputs"], indent=2))
    except Exception as exc:
        _fail(exc)


@app.command("inspect")
def inspect_command(
    result_dir: Path = typer.Option(..., "--result-dir", help="ABI result directory."),
    output_json: bool = typer.Option(
        False,
        "--output-json",
        help="Emit the agent JSON envelope.",
    ),
) -> None:
    """Inspect ABI provenance and summarize run health.

    Reads commands.tsv and resolved_inputs.tsv from the provenance directory,
    then reports:
    - Overall run status (success/failed/unknown).
    - Count of all steps and number of failed/skipped steps.
    - Detailed failure rows with reason strings.
    - Missing or placeholder input paths (files that don't exist on disk or
      contain "NOT_CONFIGURED").

    This is the primary post-mortem diagnostic command. Run it after a failed
    pipeline to quickly identify which steps failed and why.

    检查 ABI 溯源并总结运行健康状况。
    从溯源目录中读取 commands.tsv 和 resolved_inputs.tsv，报告运行状态、
    失败/跳过步骤及详细的失败原因。这是主要的事后诊断命令。
    """
    if output_json:
        _emit_agent_json(ABIAgentInterface().inspect(result_dir=result_dir))
        return
    try:
        result = _agent_result(ABIAgentInterface().inspect(result_dir=result_dir))
        typer.echo(json.dumps(result, indent=2, ensure_ascii=False))
    except Exception as exc:
        _fail(exc)


@app.command("query")
def query_command(
    analysis_type: str = typer.Option(..., "--type", help="ABI analysis type."),
    what: str = typer.Option(
        ...,
        "--what",
        help="What to query: stages, tools, platforms, resources, inputs, outputs.",
    ),
    step: Optional[str] = typer.Option(
        None,
        "--step",
        help="Pipeline node ID (required for resources/inputs/outputs).",
    ),
    output_json: bool = typer.Option(
        False,
        "--output-json",
        help="Emit the agent JSON envelope.",
    ),
) -> None:
    """Lightweight metadata query — no plan construction, no config loading.

    Reads the plugin's ``pipeline_dag.yaml`` and tool registry to answer
    structural questions about the pipeline. Much faster and cheaper than
    ``plan`` (~50ms vs ~300ms) — suitable for agent reasoning loops.

    Examples::

        abi query --type rnaseq_expression --what stages
        abi query --type metagenomic_plasmid --what tools
        abi query --type rnaseq_expression --step qc_fastp --what resources

    轻量级元数据查询 — 不构建执行计划，不加载配置。
    仅读取 pipeline_dag.yaml 和工具注册表，比 plan 快 (~50ms vs ~300ms)。
    """
    if output_json:
        _emit_agent_json(
            ABIAgentInterface().query(
                analysis_type=analysis_type,
                what=what,
                step=step,
            )
        )
        return
    try:
        payload = json.loads(
            ABIAgentInterface().query(
                analysis_type=analysis_type,
                what=what,
                step=step,
            )
        )
        if payload.get("status") == "error":
            typer.echo(json.dumps(payload, indent=2), err=True)
            raise typer.Exit(1)
        typer.echo(json.dumps(payload.get("result", payload), indent=2))
    except typer.Exit:
        raise
    except Exception as exc:
        _fail(exc)


@app.command("report")
def report_command(
    result_dir: Path = typer.Option(..., "--result-dir", help="ABI result directory."),
    analysis_type: Optional[str] = typer.Option(None, "--type", help="ABI analysis type."),
    output_json: bool = typer.Option(
        False,
        "--output-json",
        help="Emit the agent JSON envelope.",
    ),
) -> None:
    """Regenerate a plugin report from ABI results.

    Reads the execution plan from the result directory, determines the analysis
    type (from ``--type`` or the plan itself), and invokes the plugin's
    ``write_report`` method. This is useful for regenerating reports after
    manual edits to result files, or for re-rendering with an updated plugin.

    从 ABI 结果重新生成插件报告。
    从结果目录中读取执行计划，确定分析类型，并调用插件的 ``write_report`` 方法。
    适用于在手动编辑结果文件后重新生成报告，或使用更新后的插件重新渲染。
    """
    if output_json:
        _emit_agent_json(
            ABIAgentInterface().report(result_dir=result_dir, analysis_type=analysis_type)
        )
        return
    try:
        result = _agent_result(
            ABIAgentInterface().report(result_dir=result_dir, analysis_type=analysis_type)
        )
        typer.echo(json.dumps(result["outputs"], indent=2))
    except Exception as exc:
        _fail(exc)


@app.command("validate-result")
def validate_result_command(
    result_dir: Path = typer.Option(..., "--result-dir", help="ABI result directory."),
    allow_empty_tables: bool = typer.Option(
        True,
        "--allow-empty-tables/--require-nonempty-tables",
        help="Allow standard tables with headers and zero data rows.",
    ),
    output_json: bool = typer.Option(
        False,
        "--output-json",
        help="Emit the agent JSON envelope.",
    ),
) -> None:
    """Validate an ABI result directory without modifying it.

    Checks that the result directory has the expected structure: execution plan,
    provenance artifacts, standard tables with correct schemas, and report files.
    By default, empty tables (headers only) are allowed; use
    ``--require-nonempty-tables`` to enforce at least one data row.

    Returns ``{"valid": true/false, "issues": [...]}``. Exits with code 1 if
    validation fails.

    验证 ABI 结果目录而不修改它。
    检查结果目录是否具有预期结构：执行计划、溯源产物、具有正确模式的标准表格和报告文件。
    默认允许空表格；使用 ``--require-nonempty-tables`` 强制要求至少有一行数据。
    """
    if output_json:
        _emit_agent_json(
            ABIAgentInterface().abi_validate_result(
                result_dir=result_dir,
                allow_empty_tables=allow_empty_tables,
            )
        )
        return
    try:
        result = validate_abi_result_dir(result_dir, allow_empty_tables=allow_empty_tables)
        typer.echo(json.dumps(result, indent=2, ensure_ascii=False))
        if not result["valid"]:
            raise typer.Exit(code=1)
    except Exception as exc:
        _fail(exc)


@app.command("export-nextflow")
def export_nextflow_command(
    analysis_type: str = typer.Option(..., "--type", help="ABI analysis type."),
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
    output_json: bool = typer.Option(
        False,
        "--output-json",
        help="Emit the agent JSON envelope.",
    ),
) -> None:
    """Export an ABI execution plan as a Nextflow DSL2 script.

    Builds the execution plan, then uses ``NextflowExporter`` to generate a
    Nextflow DSL2 workflow file. The resulting ``.nf`` file can be run
    independently with ``nextflow run``, enabling HPC and cloud execution.

    ``--smoke`` generates a workflow that uses mock tools for quick validation.

    将 ABI 执行计划导出为 Nextflow DSL2 脚本。
    构建执行计划，然后使用 ``NextflowExporter`` 生成 Nextflow DSL2 工作流文件。
    生成的 ``.nf`` 文件可以用 ``nextflow run`` 独立运行，支持 HPC 和云执行。
    """
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
    analysis_type: str = typer.Option(..., "--type", help="ABI analysis type."),
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
    nextflow_bin: Optional[Path] = typer.Option(
        None,
        "--nextflow-bin",
        help="Nextflow executable.",
    ),
    nextflow_profile: Optional[str] = typer.Option(
        None,
        "--nextflow-profile",
        help="Nextflow config profile to pass to `nextflow run`.",
    ),
    executor: Optional[str] = typer.Option(
        None,
        "--executor",
        help="Nextflow process executor override.",
    ),
    resume: bool = typer.Option(False, "--resume", help="Pass -resume to Nextflow."),
    mamba_root: Optional[Path] = typer.Option(None, "--mamba-root", help="Local mamba root."),
    smoke: bool = typer.Option(False, "--smoke/--real", help="Use mocked/smoke tools."),
    check_files: bool = typer.Option(True, "--check-files/--no-check-files"),
    confirm_execution: bool = typer.Option(
        False,
        "--confirm-execution",
        help="Required before executing run.",
    ),
    output_json: bool = typer.Option(
        False,
        "--output-json",
        help="Emit the agent JSON envelope.",
    ),
    resource_profile: Optional[str] = typer.Option(
        None,
        "--resource-profile",
        help="Resource profile preset (dev_small, hpc_standard, hpc_large).",
    ),
    cpu_override: Optional[int] = typer.Option(
        None,
        "--cpu",
        help="CPU cores for all steps.",
    ),
    memory_override: Optional[str] = typer.Option(
        None,
        "--memory",
        help="Memory per step (e.g. 16GB).",
    ),
    walltime_override: Optional[str] = typer.Option(
        None,
        "--walltime",
        help="Walltime per step (e.g. 04:00:00).",
    ),
    accelerator_override: Optional[str] = typer.Option(
        None,
        "--accelerator",
        help="GPU/accelerator (e.g. gpu:v100:1).",
    ),
    container_image: Optional[str] = typer.Option(
        None,
        "--container-image",
        help="Container image for all steps.",
    ),
    container_runtime: Optional[str] = typer.Option(
        None,
        "--container-runtime",
        help="Container runtime: docker, singularity, podman, apptainer.",
    ),
) -> None:
    """Run an ABI execution plan through a selected runtime backend.

    **Confirmation gate**: This command requires ``--confirm-execution`` before
    it will actually execute. Without it (and without ``--output-json``), the
    command returns a ``confirmation_required`` envelope (via agent interface)
    and exits with code 2. This prevents accidental execution and lets agent
    callers present a confirmation prompt.

    **Execution flow**: Loads the plugin config, builds the plan, selects a
    runtime (``LocalRuntime`` or ``NextflowRuntime`` based on ``--engine``),
    and executes. ``--smoke`` uses mock tool wrappers for smoke testing.

    通过选定的运行时后端运行 ABI 执行计划。

    确认门：需要 ``--confirm-execution`` 才实际执行。若无此标志且无 ``--output-json``，
    命令返回 ``confirmation_required`` 信封并以代码 2 退出。这防止意外执行，
    并允许 agent 调用者展示确认提示。

    执行流程：加载插件配置，构建计划，选择运行时（基于 ``--engine`` 选择
    ``LocalRuntime`` 或 ``NextflowRuntime``），然后执行。
    """
    if not confirm_execution:
        # No confirmation and not in output-json mode — route through agent
        # interface to get the confirmation_required envelope (exit code 2).
        # 未确认且不在 output-json 模式——通过 agent 接口路由以获取
        # confirmation_required 信封（退出码 2）。
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
                confirm_execution=False,
                resource_profile=resource_profile,
                cpu_override=cpu_override,
                memory_override=memory_override,
                walltime_override=walltime_override,
                accelerator_override=accelerator_override,
                container_image=container_image,
                container_runtime=container_runtime,
            )
        )
        return
    if output_json:
        # Confirmed execution with --output-json: agent interface returns the
        # result envelope after the run completes.
        # 已确认执行且带有 --output-json：agent 接口在运行完成后返回结果信封。
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
                resource_profile=resource_profile,
                cpu_override=cpu_override,
                memory_override=memory_override,
                walltime_override=walltime_override,
                accelerator_override=accelerator_override,
                container_image=container_image,
                container_runtime=container_runtime,
            )
        )
        return
    try:
        result = _agent_result(
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
                confirm_execution=True,
                resource_profile=resource_profile,
                cpu_override=cpu_override,
                memory_override=memory_override,
                walltime_override=walltime_override,
                accelerator_override=accelerator_override,
                container_image=container_image,
                container_runtime=container_runtime,
            )
        )
        typer.echo(json.dumps(result["outputs"], indent=2))
    except Exception as exc:
        _fail(exc)


@app.command("run-nextflow")
def run_nextflow_command(
    analysis_type: str = typer.Option(..., "--type", help="ABI analysis type."),
    config: Optional[Path] = typer.Option(None, "--config", help="Plugin config YAML."),
    sample_sheet: Optional[Path] = typer.Option(None, "--sample-sheet", help="Sample sheet TSV."),
    profile: str = typer.Option("dry_run", "--profile", help="Profile for adapter plugins."),
    mode: Optional[str] = typer.Option(None, "--mode", help="Execution mode."),
    threads: Optional[int] = typer.Option(None, "--threads", help="Thread count."),
    outdir: Optional[str] = typer.Option(None, "--outdir", help="Output directory."),
    log_dir: Optional[str] = typer.Option(None, "--log-dir", help="Log directory."),
    workflow: Optional[Path] = typer.Option(None, "--workflow", help="Workflow path to write."),
    work_dir: Optional[Path] = typer.Option(None, "--work-dir", help="Nextflow work directory."),
    nextflow_bin: Optional[Path] = typer.Option(
        None,
        "--nextflow-bin",
        help="Nextflow executable.",
    ),
    mamba_root: Optional[Path] = typer.Option(None, "--mamba-root", help="Local mamba root."),
    nxf_home: Optional[Path] = typer.Option(None, "--nxf-home", help="Nextflow home directory."),
    nextflow_profile: Optional[str] = typer.Option(
        None,
        "--nextflow-profile",
        help="Nextflow config profile to pass to `nextflow run`.",
    ),
    executor: Optional[str] = typer.Option(
        None,
        "--executor",
        help="Nextflow process executor override.",
    ),
    resume: bool = typer.Option(False, "--resume", help="Pass -resume to Nextflow."),
    smoke: bool = typer.Option(True, "--smoke/--real", help="Run smoke or real tool workflow."),
    check_files: bool = typer.Option(True, "--check-files/--no-check-files"),
    confirm_execution: bool = typer.Option(
        False,
        "--confirm-execution",
        help="Required before executing run.",
    ),
    output_json: bool = typer.Option(
        False,
        "--output-json",
        help="Emit the agent JSON envelope.",
    ),
) -> None:
    """Compatibility alias for ``run --engine nextflow``.

    Works identically to ``run`` but defaults ``--engine`` to ``"nextflow"``
    and ``--smoke`` to ``True``. This is kept for backward compatibility with
    scripts and agents that use the older ``run-nextflow`` command name.

    ``run --engine nextflow`` 的兼容性别名。
    行为与 ``run`` 相同，但默认 ``--engine`` 为 ``"nextflow"``，``--smoke`` 为 ``True``。
    保留此命令是为了与使用旧 ``run-nextflow`` 命令名的脚本和 agent 保持向后兼容。
    """
    if not confirm_execution:
        # Same confirmation gate as run_command.
        # 与 run_command 相同的确认门。
        _emit_agent_json(
            ABIAgentInterface().run(
                analysis_type=analysis_type,
                engine="nextflow",
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
                confirm_execution=False,
            )
        )
        return
    if output_json:
        _emit_agent_json(
            ABIAgentInterface().run(
                analysis_type=analysis_type,
                engine="nextflow",
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
        result = _agent_result(
            ABIAgentInterface().run(
                analysis_type=analysis_type,
                engine="nextflow",
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
                confirm_execution=True,
            )
        )
        typer.echo(json.dumps(result["outputs"], indent=2))
    except Exception as exc:
        _fail(exc)


@app.command("export-openai-tools")
def export_openai_tools_command(
    analysis_type: str = typer.Option(..., "--type", help="ABI analysis type."),
    descriptor_format: str = typer.Option(
        "responses",
        "--format",
        help="Descriptor format: responses, apps-sdk, or json.",
    ),
    include_execution: bool = typer.Option(
        False,
        "--include-execution",
        help="Include execution tools such as abi_run in the export.",
    ),
) -> None:
    """Export OpenAI-compatible ABI agent tool descriptors.

    Generates function definitions for each ABI tool (plan, dry-run, inspect,
    report, etc.) in a format compatible with the OpenAI Chat Completions /
    Responses API ``tools`` parameter. Supports ``responses``, ``apps-sdk``,
    and ``json`` descriptor formats.

    ``--include-execution`` adds execution tools like ``abi_run`` to the export
    (off by default for safety).

    导出与 OpenAI 兼容的 ABI agent 工具描述符。
    以与 OpenAI Chat Completions / Responses API ``tools`` 参数兼容的格式
    为每个 ABI 工具（plan、dry-run、inspect、report 等）生成函数定义。
    支持 ``responses``、``apps-sdk`` 和 ``json`` 描述符格式。
    """
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


# Build the list of known providers for CLI help text.
_KNOWN_PROVIDERS = sorted(PROVIDER_PROFILES)
_PROVIDER_HELP = (
    "LLM provider for OpenAI-compatible format quirks. "
    f"Known: {', '.join(_KNOWN_PROVIDERS)}. "
    "Ignored for anthropic and gemini formats."
)

# Build the list of known format families for CLI help text.
_FORMAT_HELP = "Descriptor format family: openai (default), anthropic, or gemini."


@app.command("export-tools")
def export_tools_command(
    analysis_type: str = typer.Option(..., "--type", help="ABI analysis type."),
    descriptor_format: str = typer.Option(
        "openai",
        "--format",
        help=_FORMAT_HELP,
    ),
    provider: str = typer.Option(
        "openai",
        "--provider",
        help=_PROVIDER_HELP,
    ),
    include_execution: bool = typer.Option(
        False,
        "--include-execution",
        help="Include execution tools such as abi_run in the export.",
    ),
) -> None:
    """Export ABI tool descriptors for any supported LLM provider.

    Supports three format families and all major LLM providers:

    \b
      --format openai   → OpenAI / DeepSeek / 智谱 GLM / Kimi / Qwen / MiniMax
      --format anthropic → Anthropic Claude
      --format gemini    → Google Gemini

    Use ``--provider`` to select provider-specific quirks within the
    OpenAI-compatible family (e.g. ``--provider deepseek`` or
    ``--provider zhipu``).  The ``--provider`` flag is ignored for
    the anthropic and gemini formats.

    导出适用于任何支持的大模型的 ABI 工具描述符。
    支持三种格式家族: openai (OpenAI / DeepSeek / 智谱 / Kimi / Qwen / MiniMax)、
    anthropic (Claude)、gemini (Google)。
    """
    try:
        plugin = get_plugin(analysis_type)
        fmt = descriptor_format.lower().strip()
        if fmt == "openai":
            tools = export_openai_compatible(
                plugin,
                include_execution=include_execution,
                provider=provider,
            )
        elif fmt == "anthropic":
            tools = export_anthropic(plugin, include_execution=include_execution)
        elif fmt == "gemini":
            result = export_gemini(plugin, include_execution=include_execution)
            typer.echo(json.dumps(result, indent=2, ensure_ascii=False))
            return
        else:
            raise ValueError(
                f"Unknown format {descriptor_format!r}. Expected: openai, anthropic, or gemini."
            )
        typer.echo(json.dumps(tools, indent=2, ensure_ascii=False))
    except Exception as exc:
        _fail(exc)


@app.command("export-agent-context")
def export_agent_context_command(
    analysis_type: str = typer.Option(..., "--type", help="ABI analysis type."),
    context_format: str = typer.Option(
        "json",
        "--format",
        help="Context format. Currently only json is supported.",
    ),
) -> None:
    """Export compact machine-readable context for agent callers.

    Produces a JSON object describing the plugin's capabilities, tools,
    configuration schema, and sample sheet format. Agent callers use this
    to understand what a plugin can do without having to parse its source.

    为 agent 调用者导出紧凑的机器可读上下文。
    产生一个 JSON 对象，描述插件的能力、工具、配置模式和样本表格式。
    Agent 调用者使用此信息来理解插件的功能，而无需解析其源代码。
    """
    try:
        if context_format != "json":
            raise ABIError("Unsupported agent context format. Expected: json.")
        plugin = get_plugin(analysis_type)
        _emit_json_payload(build_agent_context(plugin))
    except Exception as exc:
        _fail(exc)


@app.command("check-resources")
def check_resources_command(
    analysis_type: str = typer.Option(
        "metagenomic_plasmid",
        "--type",
        help="ABI analysis type.",
    ),
    config: Optional[Path] = typer.Option(None, "--config", help="Plugin config YAML."),
    resource: Optional[List[str]] = typer.Option(
        None,
        "--resource",
        help="Resource id to check. Repeatable.",
    ),
    profile: str = typer.Option("local", "--profile", help="Profile for adapter plugins."),
    mode: Optional[str] = typer.Option(None, "--mode", help="Execution mode."),
    threads: Optional[int] = typer.Option(None, "--threads", help="Thread count."),
    outdir: Optional[str] = typer.Option(None, "--outdir", help="Output directory."),
    log_dir: Optional[str] = typer.Option(None, "--log-dir", help="Log directory."),
) -> None:
    """Check configured database, index, and model resources without downloading them.

    Read-only operation: inspects whether each resource (database, index, model)
    is present at its configured path. Returns a JSON array with status per
    resource. Use ``--resource`` to limit checks to specific resource IDs.

    检查配置的数据库、索引和模型资源，而不下载它们。
    只读操作：检查每个资源（数据库、索引、模型）是否存在于其配置的路径。
    返回带有每个资源状态的 JSON 数组。使用 ``--resource`` 将检查限制到特定资源 ID。
    """
    try:
        cfg = _load_plugin_config(
            analysis_type=analysis_type,
            config=config,
            profile=profile,
            overrides=_common_overrides(
                mode=mode,
                threads=threads,
                outdir=outdir,
                log_dir=log_dir,
            ),
        )
        rows = check_resources(analysis_type=analysis_type, config=cfg, resource_ids=resource)
        _emit_json_payload(rows)
    except Exception as exc:
        _fail(exc)


@app.command("setup-resources")
def setup_resources_command(
    analysis_type: str = typer.Option(
        "metagenomic_plasmid",
        "--type",
        help="ABI analysis type.",
    ),
    config: Optional[Path] = typer.Option(None, "--config", help="Plugin config YAML."),
    resource: Optional[List[str]] = typer.Option(
        None,
        "--resource",
        help="Resource id to prepare. Repeatable.",
    ),
    profile: str = typer.Option("local", "--profile", help="Profile for adapter plugins."),
    mode: Optional[str] = typer.Option(None, "--mode", help="Execution mode."),
    threads: Optional[int] = typer.Option(None, "--threads", help="Thread count."),
    outdir: Optional[str] = typer.Option(None, "--outdir", help="Output directory."),
    log_dir: Optional[str] = typer.Option(None, "--log-dir", help="Log directory."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show resource setup plan only."),
    mock: bool = typer.Option(False, "--mock", help="Create mock resource directories."),
    confirm: bool = typer.Option(
        False,
        "--confirm",
        help="Confirm execution. Required for real resource setup (S13 fix).",
    ),
) -> None:
    """Download, mock, or plan setup for ABI analysis resources.

    Prepares resources (databases, indexes, models) required by the analysis
    type. Three modes:
    - Normal: downloads and installs resources to configured paths.
    - ``--dry-run``: shows what would be done without making changes.
    - ``--mock``: creates empty mock directories for smoke testing.

    Real execution requires ``--confirm`` for safety, similar to ``abi run``.

    Resources are downloaded once and reused across runs.

    下载、模拟或规划 ABI 分析资源的设置。
    准备分析类型所需的资源（数据库、索引、模型）。三种模式：
    - 正常：下载并安装资源到配置的路径。
    - ``--dry-run``：显示将要执行的操作而不做更改。
    - ``--mock``：创建空的 mock 目录用于 smoke 测试。

    真实执行需要 ``--confirm`` 以确保安全，类似 ``abi run``。
    """
    if not dry_run and not mock and not confirm:
        typer.echo(
            "Resource setup requires --confirm for real execution. "
            "Use --dry-run to preview or --mock for smoke testing, "
            "then re-run with --confirm to proceed.",
            err=True,
        )
        raise typer.Exit(2)
    try:
        cfg = _load_plugin_config(
            analysis_type=analysis_type,
            config=config,
            profile=profile,
            overrides=_common_overrides(
                mode=mode,
                threads=threads,
                outdir=outdir,
                log_dir=log_dir,
            ),
        )
        rows = setup_resources(
            analysis_type=analysis_type,
            config=cfg,
            resource_ids=resource,
            dry_run=dry_run,
            mock=mock,
        )
        _emit_json_payload(rows)
    except Exception as exc:
        _fail(exc)


@app.command("doctor-agent")
def doctor_agent_command(
    analysis_type: str = typer.Option(..., "--type", help="ABI analysis type."),
    output_json: bool = typer.Option(
        False,
        "--output-json",
        help="Emit the agent JSON envelope.",
    ),
) -> None:
    """Print the shortest safe operating guide for ABI agent callers.

    Emits a condensed text guide explaining the correct command sequence for
    running an ABI analysis (plan -> dry-run -> run with confirmation) along
    with common pitfalls and suggested next steps. Designed to be pasted into
    an LLM system prompt so the agent knows how to use the ABI tools correctly.

    为 ABI agent 调用者打印最简洁的安全操作指南。
    发出一份简明的文本指南，解释运行 ABI 分析的正确命令序列
    （plan -> dry-run -> 确认后 run）以及常见的陷阱和建议的后续步骤。
    设计用于粘贴到 LLM 系统提示中，使 agent 知道如何正确使用 ABI 工具。
    """
    if output_json:
        _emit_agent_json(ABIAgentInterface().doctor_agent(analysis_type=analysis_type))
        return
    try:
        plugin = get_plugin(analysis_type)
        typer.echo(render_doctor_agent(plugin), nl=False)
    except Exception as exc:
        _fail(exc)


@app.command("install-skills")
def install_skills_command(
    target: Optional[Path] = typer.Option(
        None,
        "--target",
        help="Target skills directory (default: ~/.claude/skills/abi).",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        help="Overwrite existing skill files.",
    ),
    output_json: bool = typer.Option(
        False,
        "--output-json",
        help="Emit the agent JSON envelope.",
    ),
) -> None:
    """Install ABI agent skills into a Claude Code skills directory.

    Copies all SKILL.md files from the ABI package's bundled skills directory
    into the target directory (default ``~/.claude/skills/abi/``). After
    installation, Claude Code will automatically load these skills and
    know how to use the ``abi`` CLI and its bioinformatics tools.

    Skills installed:

    - ``abi_agent`` — operating guide for the ``abi`` CLI (lifecycle, transport
      methods, error recovery).
    - Per-tool skills for 40+ bioinformatics tools (fastp, megahit, genomad,
      bakta, etc.).

    Use ``abi doctor-agent --type <analysis_type>`` for a text guide you can
    paste directly into an LLM system prompt.

    将 ABI agent skills 安装到 Claude Code skills 目录。

    将所有 SKILL.md 文件从 ABI 包捆绑的 skills 目录复制到目标目录
    （默认 ``~/.claude/skills/abi/``）。安装后，Claude Code 将自动加载
    这些 skills，并知道如何使用 ``abi`` CLI 及其生物信息学工具。
    """
    try:
        _source = _resolve_skills_source()
        dest = target or (Path.home() / ".claude" / "skills" / "abi")
        copied: List[str] = []
        skipped: List[str] = []

        # Collect skill files: only SKILL.md files in subdirectories (skip bare
        # files like README.md that are human documentation, not agent skills).
        install_plan: list[tuple[Path, Path, Path]] = []  # (skill_file, dest_subdir, dest_file)
        for item in sorted(_source.iterdir()):
            if not item.is_dir():
                continue
            skill_file = item / "SKILL.md"
            if not skill_file.is_file():
                continue
            dest_subdir = dest / item.name
            dest_file = dest_subdir / "SKILL.md"
            if dest_file.exists() and not force:
                skipped.append(str(dest_file))
                continue
            install_plan.append((skill_file, dest_subdir, dest_file))

        # Atomic install: copy to temp dir first, then rename into place.
        tmp_dest: Optional[Path] = None
        try:
            if install_plan:
                import tempfile

                tmp_dest = Path(tempfile.mkdtemp(prefix=".abi-skills-", dir=dest.parent))
                for skill_file, dest_subdir, dest_file in install_plan:
                    tmp_subdir = tmp_dest / dest_subdir.name
                    tmp_subdir.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(skill_file, tmp_subdir / "SKILL.md")
                # Ensure target directory exists for the rename
                dest.mkdir(parents=True, exist_ok=True)
                for skill_file, dest_subdir, dest_file in install_plan:
                    dest_subdir.mkdir(parents=True, exist_ok=True)
                    final_src = tmp_dest / dest_subdir.name / "SKILL.md"
                    shutil.copy2(final_src, dest_file)
                    copied.append(str(dest_file))
                # Clean up temp directory
                shutil.rmtree(tmp_dest, ignore_errors=True)
                tmp_dest = None
            elif not skipped and not any(
                (dest / d.name / "SKILL.md").exists()
                for d in sorted(_source.iterdir())
                if d.is_dir()
            ):
                pass  # No skills to install and dest is empty — still report success
        finally:
            if tmp_dest is not None:
                shutil.rmtree(tmp_dest, ignore_errors=True)

        result = {
            "source": str(_source),
            "target": str(dest),
            "copied": copied,
            "skipped": skipped,
            "count": len(copied),
        }
        if output_json:
            _emit_agent_json(json.dumps({"status": "success", "result": result}))
        else:
            typer.echo(json.dumps(result, indent=2, ensure_ascii=False))
        if skipped:
            typer.secho(
                f"Skipped {len(skipped)} existing files (use --force to overwrite).",
                fg=typer.colors.YELLOW,
                err=True,
            )
        typer.secho(
            f"Installed {len(copied)} skill(s) to {dest}",
            fg=typer.colors.GREEN,
            err=True,
        )
    except Exception as exc:
        _fail(exc)


@job_app.command("submit")
def job_submit_command(
    service_url: str = typer.Option(
        "http://127.0.0.1:18791",
        "--service-url",
        help="ABI Job Service base URL.",
    ),
    command: str = typer.Option("run", "--command", help="ABI command to queue."),
    payload: Optional[Path] = typer.Option(
        None,
        "--payload",
        help="JSON file containing a full Job API payload.",
    ),
    arguments_json: Optional[str] = typer.Option(
        None,
        "--arguments-json",
        help="JSON object merged into the Job API arguments.",
    ),
    backend: Optional[str] = typer.Option(
        None,
        "--backend",
        help="Execution backend: local, nextflow, hpc, or cloud.",
    ),
    analysis_type: Optional[str] = typer.Option(
        None,
        "--analysis-type",
        help="ABI analysis type.",
    ),
    config_path: Optional[Path] = typer.Option(
        None,
        "--config-path",
        help="Optional plugin config YAML path.",
    ),
    sample_sheet: Optional[Path] = typer.Option(
        None,
        "--sample-sheet",
        help="Optional sample sheet TSV path.",
    ),
    profile: Optional[str] = typer.Option(None, "--profile", help="Plugin config profile."),
    mode: Optional[str] = typer.Option(None, "--mode", help="Execution mode."),
    threads: Optional[int] = typer.Option(None, "--threads", help="Thread count."),
    outdir: Optional[str] = typer.Option(None, "--outdir", help="Output directory."),
    log_dir: Optional[str] = typer.Option(None, "--log-dir", help="Log directory."),
    engine: Optional[str] = typer.Option(None, "--engine", help="Runtime engine."),
    workflow: Optional[Path] = typer.Option(None, "--workflow", help="Workflow path to write."),
    nextflow_bin: Optional[Path] = typer.Option(
        None,
        "--nextflow-bin",
        help="Nextflow executable.",
    ),
    nextflow_profile: Optional[str] = typer.Option(
        None,
        "--nextflow-profile",
        help="Nextflow config profile.",
    ),
    executor: Optional[str] = typer.Option(
        None,
        "--executor",
        help="Nextflow process executor override.",
    ),
    work_dir: Optional[Path] = typer.Option(None, "--work-dir", help="Nextflow work directory."),
    nxf_home: Optional[Path] = typer.Option(None, "--nxf-home", help="Nextflow home directory."),
    mamba_root: Optional[Path] = typer.Option(None, "--mamba-root", help="Local mamba root."),
    resume: bool = typer.Option(False, "--resume", help="Pass -resume to Nextflow."),
    smoke: bool = typer.Option(False, "--smoke", help="Use mocked/smoke tools."),
    confirm_execution: bool = typer.Option(
        False,
        "--confirm-execution",
        help="Required before queueing execution jobs.",
    ),
    check_files: Optional[bool] = typer.Option(None, "--check-files/--no-check-files"),
) -> None:
    """Submit a job to an ABI Job Service for asynchronous execution.

    Builds a job payload from the provided arguments (or from ``--payload``
    if a full JSON file is given), then POSTs it to the Job Service at
    ``--service-url``. The Job Service queues the job and returns a job ID
    that can be used with ``job status``, ``job artifacts``, and ``job cancel``.

    ``--confirm-execution`` is required for commands that execute (e.g., run).

    向 ABI Job Service 提交作业以进行异步执行。
    从提供的参数（或通过 ``--payload`` 提供的完整 JSON 文件）构建作业负载，
    然后 POST 到 ``--service-url`` 处的 Job Service。
    Job Service 将作业排队并返回作业 ID，
    可用于 ``job status``、``job artifacts`` 和 ``job cancel``。
    """
    from abi.jobs.client import JobClientError, submit_job

    try:
        request_payload = _build_job_payload(
            command=command,
            payload_path=payload,
            arguments_json=arguments_json,
            backend=backend,
            analysis_type=analysis_type,
            config_path=config_path,
            sample_sheet=sample_sheet,
            profile=profile,
            mode=mode,
            threads=threads,
            outdir=outdir,
            log_dir=log_dir,
            engine=engine,
            workflow=workflow,
            nextflow_bin=nextflow_bin,
            nextflow_profile=nextflow_profile,
            executor=executor,
            work_dir=work_dir,
            nxf_home=nxf_home,
            mamba_root=mamba_root,
            resume=resume,
            smoke=smoke,
            confirm_execution=confirm_execution,
            check_files=check_files,
        )
        _, response = submit_job(request_payload, base_url=service_url)
        _emit_json_payload(response)
    except JobClientError as exc:
        # Surface the server's error payload directly.
        # 直接展示服务器的错误负载。
        _emit_json_payload(exc.payload)
        if exc.payload.get("status") == "confirmation_required":
            raise typer.Exit(code=2) from None
        raise typer.Exit(code=1) from None
    except Exception as exc:
        _fail(exc)


@job_app.command("list")
def job_list_command(
    service_url: str = typer.Option(
        "http://127.0.0.1:18791",
        "--service-url",
        help="ABI Job Service base URL.",
    ),
) -> None:
    """List jobs currently known to the ABI Job Service.

    Returns a JSON array of job records with IDs, statuses, and timestamps.

    列出 ABI Job Service 当前已知的作业。
    返回带有 ID、状态和时间戳的作业记录 JSON 数组。
    """
    from abi.jobs.client import JobClientError, list_jobs

    try:
        _, response = list_jobs(base_url=service_url)
        _emit_json_payload(response)
    except JobClientError as exc:
        _emit_json_payload(exc.payload)
        raise typer.Exit(code=1) from None
    except Exception as exc:
        _fail(exc)


@job_app.command("status")
def job_status_command(
    job_id: str = typer.Argument(..., help="ABI Job Service job id."),
    service_url: str = typer.Option(
        "http://127.0.0.1:18791",
        "--service-url",
        help="ABI Job Service base URL.",
    ),
) -> None:
    """Fetch one queued job's current status.

    Returns the job record including status (pending/running/completed/failed),
    progress, and any error information.

    获取一个排队作业的当前状态。
    返回作业记录，包括状态（pending/running/completed/failed）、进度和任何错误信息。
    """
    from abi.jobs.client import JobClientError, get_job

    try:
        _, response = get_job(job_id, base_url=service_url)
        _emit_json_payload(response)
    except JobClientError as exc:
        _emit_json_payload(exc.payload)
        raise typer.Exit(code=1) from None
    except Exception as exc:
        _fail(exc)


@job_app.command("artifacts")
def job_artifacts_command(
    job_id: str = typer.Argument(..., help="ABI Job Service job id."),
    service_url: str = typer.Option(
        "http://127.0.0.1:18791",
        "--service-url",
        help="ABI Job Service base URL.",
    ),
) -> None:
    """Fetch artifact paths reported by a completed or running job.

    Artifacts include plan, config, commands, tables, report, and log file
    paths. These can be inspected or downloaded directly from the filesystem
    (when co-located) or via the Job Service API.

    获取已完成或运行中作业报告的产物路径。
    产物包括计划、配置、命令、表格、报告和日志文件路径。
    """
    from abi.jobs.client import JobClientError, get_artifacts

    try:
        _, response = get_artifacts(job_id, base_url=service_url)
        _emit_json_payload(response)
    except JobClientError as exc:
        _emit_json_payload(exc.payload)
        raise typer.Exit(code=1) from None
    except Exception as exc:
        _fail(exc)


@job_app.command("cancel")
def job_cancel_command(
    job_id: str = typer.Argument(..., help="ABI Job Service job id."),
    service_url: str = typer.Option(
        "http://127.0.0.1:18791",
        "--service-url",
        help="ABI Job Service base URL.",
    ),
) -> None:
    """Request cancellation for a queued or running ABI job.

    If the job is still pending, it is removed from the queue. If running
    and ``--subprocess-workers`` is enabled on the service, the subprocess
    is terminated via SIGTERM.

    请求取消一个排队或运行中的 ABI 作业。
    如果作业仍在等待中，则将其从队列中移除。如果正在运行且服务启用了
    ``--subprocess-workers``，则通过 SIGTERM 终止子进程。
    """
    from abi.jobs.client import JobClientError, cancel_job

    try:
        _, response = cancel_job(job_id, base_url=service_url)
        _emit_json_payload(response)
    except JobClientError as exc:
        _emit_json_payload(exc.payload)
        raise typer.Exit(code=1) from None
    except Exception as exc:
        _fail(exc)


@app.command("job-service")
def job_service_command(
    host: str = typer.Option("127.0.0.1", "--host", help="Host interface to bind."),
    port: int = typer.Option(18791, "--port", help="HTTP port to bind."),
    workers: int = typer.Option(1, "--workers", help="Background ABI job worker count."),
    store: Optional[Path] = typer.Option(
        None,
        "--store",
        help="Optional JSON file used to persist job records.",
    ),
    subprocess_workers: bool = typer.Option(
        False,
        "--subprocess-workers",
        help="Run each job in an abi-dispatch subprocess so cancel can force-kill via SIGTERM.",
    ),
) -> None:
    """Start the ABI HTTP Job Service for queued long-running operations.

    The Job Service provides an HTTP API for queuing ABI commands (plan,
    dry-run, run, setup-resources, etc.) as asynchronous jobs. Clients
    submit jobs via ``abi job submit`` or direct HTTP POST, then poll
    with ``abi job status``.

    **Architecture**:
    - A thread pool (``--workers``) processes jobs concurrently.
    - ``--subprocess-workers`` spawns each job as a separate ``abi dispatch``
      subprocess. This enables clean cancellation: the parent process can
      SIGTERM the subprocess without affecting the service or other jobs.
    - ``--store`` persists job records to a JSON file for crash recovery.

    Press Ctrl+C to stop gracefully.

    启动 ABI HTTP Job Service 用于排队长时间运行的操作。

    架构：
    - 线程池并发处理作业。
    - ``--subprocess-workers`` 将每个作业作为独立的子进程运行，
      支持通过 SIGTERM 干净地取消作业。
    - ``--store`` 将作业记录持久化到 JSON 文件以进行崩溃恢复。
    """
    try:
        from abi.jobs import serve

        typer.echo(f"ABI Job Service listening on http://{host}:{port}")
        serve(
            host=host,
            port=port,
            max_workers=workers,
            store_path=store,
            subprocess_workers=subprocess_workers,
        )
    except KeyboardInterrupt:
        typer.echo("ABI Job Service stopped.")
    except Exception as exc:
        _fail(exc)


def _build_job_payload(
    *,
    command: str,
    payload_path: Optional[Path],
    arguments_json: Optional[str],
    backend: Optional[str],
    analysis_type: Optional[str],
    config_path: Optional[Path],
    sample_sheet: Optional[Path],
    profile: Optional[str],
    mode: Optional[str],
    threads: Optional[int],
    outdir: Optional[str],
    log_dir: Optional[str],
    engine: Optional[str],
    workflow: Optional[Path],
    nextflow_bin: Optional[Path],
    nextflow_profile: Optional[str],
    executor: Optional[str],
    work_dir: Optional[Path],
    nxf_home: Optional[Path],
    mamba_root: Optional[Path],
    resume: bool,
    smoke: bool,
    confirm_execution: bool,
    check_files: Optional[bool],
) -> Dict[str, Any]:
    """Build a Job Service request payload from CLI arguments.

    Merges three sources of arguments:
    1. A base payload from ``--payload`` (full JSON file).
    2. ``--arguments-json`` (inline JSON merged into arguments).
    3. Individual CLI flags (e.g., ``--analysis-type``, ``--outdir``).

    The result is a ``{"command": ..., "arguments": {...}, "backend": ...}``
    dict ready for POST to the Job Service API.

    从 CLI 参数构建 Job Service 请求负载。
    合并三个来源的参数：基础负载（``--payload``）、内联 JSON（``--arguments-json``）
    和单独的 CLI 标志。结果是准备 POST 到 Job Service API 的字典。
    """
    # Start with a full payload if provided, otherwise empty dict.
    # 如果提供了完整负载，则以其为基础；否则使用空字典。
    payload: Dict[str, Any] = _load_json_object(payload_path) if payload_path else {}
    payload.setdefault("command", command)
    raw_arguments = payload.get("arguments", {})
    if not isinstance(raw_arguments, dict):
        raise ABIError("Job payload field 'arguments' must be a JSON object.")
    arguments: Dict[str, Any] = dict(raw_arguments)
    # Merge inline JSON arguments on top of the base arguments.
    # 将内联 JSON 参数合并到基础参数之上。
    if arguments_json:
        extra_arguments = loads_json(arguments_json, label="--arguments-json")
        if not isinstance(extra_arguments, dict):
            raise ABIError("--arguments-json must be a JSON object.")
        arguments.update(extra_arguments)
    # Apply individual CLI flags as argument overrides.
    # 将单独的 CLI 标志作为参数覆盖应用。
    _set_if_not_none(arguments, "analysis_type", analysis_type)
    _set_if_not_none(arguments, "config_path", _path_string(config_path))
    _set_if_not_none(arguments, "sample_sheet", _path_string(sample_sheet))
    _set_if_not_none(arguments, "profile", profile)
    _set_if_not_none(arguments, "mode", mode)
    _set_if_not_none(arguments, "threads", threads)
    _set_if_not_none(arguments, "outdir", outdir)
    _set_if_not_none(arguments, "log_dir", log_dir)
    _set_if_not_none(arguments, "engine", engine)
    _set_if_not_none(arguments, "workflow", _path_string(workflow))
    _set_if_not_none(arguments, "nextflow_bin", _path_string(nextflow_bin))
    _set_if_not_none(arguments, "nextflow_profile", nextflow_profile)
    _set_if_not_none(arguments, "executor", executor)
    _set_if_not_none(arguments, "work_dir", _path_string(work_dir))
    _set_if_not_none(arguments, "nxf_home", _path_string(nxf_home))
    _set_if_not_none(arguments, "mamba_root", _path_string(mamba_root))
    # Boolean flags are only set when True to avoid polluting arguments.
    # 布尔标志仅在为 True 时设置，以避免污染参数。
    if resume:
        arguments["resume"] = True
    if smoke:
        arguments["smoke"] = True
    if confirm_execution:
        arguments["confirm_execution"] = True
    if check_files is not None:
        arguments["check_files"] = check_files
    payload["arguments"] = arguments
    if backend:
        payload["backend"] = backend
    return payload


def _load_json_object(path: Path) -> Dict[str, Any]:
    """Load a JSON file into a dict, with error context in the exception message.

    将 JSON 文件加载为字典，异常消息中包含错误上下文。
    """
    return load_json_object(path)


def _set_if_not_none(target: Dict[str, Any], key: str, value: Any) -> None:
    """Set a key in target dict only if value is not None.

    Prevents overwriting explicitly-set None values from one source with
    a missing value from another source.

    仅在 value 非 None 时在目标字典中设置键。
    防止用来自一个源的缺失值覆盖另一个源中显式设置的 None 值。
    """
    if value is not None:
        target[key] = value


def _path_string(path: Optional[Path]) -> Optional[str]:
    """Convert a Path to string, preserving None.

    将 Path 转换为字符串，保留 None。
    """
    return str(path) if path is not None else None


@app.command("dispatch")
def dispatch_command(
    command: str = typer.Option(..., "--command", "-c", help="ABI command to dispatch."),
    arguments_json: Optional[str] = typer.Option(
        None,
        "--arguments",
        "-a",
        help="JSON arguments (inline or file path). Reads stdin if omitted.",
    ),
    arguments_file: Optional[Path] = typer.Option(
        None, "--arguments-file", help="Path to JSON file containing arguments."
    ),
) -> None:
    """Dispatch a single ABI command and print the JSON envelope.

    **This is a headless subprocess entry point used internally by the
    Job Service.** When ``job-service --subprocess-workers`` is active,
    each job is executed as ``abi dispatch --command <cmd> --arguments <json>``
    in a separate subprocess. This architecture enables clean cancellation:
    the parent service process can SIGTERM the subprocess without affecting
    other jobs or the service itself.

    Arguments are resolved in this priority order:
    1. ``--arguments-file`` — explicit JSON file path.
    2. ``--arguments`` — inline JSON string or a file path (auto-detected).
    3. stdin — reads raw JSON from standard input.

    The output is a JSON envelope with status, message, and data fields,
    printed directly to stdout.

    分发单个 ABI 命令并打印 JSON 信封。

    这是 Job Service 内部使用的无头子进程入口点。
    每个作业作为单独的 ``abi dispatch`` 子进程运行，使得父服务进程可以
    通过 SIGTERM 干净地取消作业，而不会影响其他作业或服务本身。

    参数解析优先级：``--arguments-file`` > ``--arguments`` > stdin。
    输出是带有 status、message 和 data 字段的 JSON 信封。
    """
    try:
        # Resolve arguments from the highest-priority source.
        # 从最高优先级来源解析参数。
        if arguments_file is not None:
            arguments = load_json_object(arguments_file, label=f"arguments file {arguments_file}")
        elif arguments_json is not None:
            # Try parsing as inline JSON first; if that fails, treat it as a file path.
            # 首先尝试作为内联 JSON 解析；如果失败，将其视为文件路径。
            try:
                arguments = json.loads(arguments_json)
            except json.JSONDecodeError:
                arguments = load_json_object(
                    Path(arguments_json), label=f"arguments path {arguments_json}"
                )
        else:
            # Read arguments from stdin — the default for subprocess piped input.
            # 从 stdin 读取参数——子进程管道输入的默认方式。
            import sys as _sys

            raw = _sys.stdin.read()
            if raw.strip():
                arguments = json.loads(raw)
            else:
                arguments = {}
        if not isinstance(arguments, dict):
            raise typer.BadParameter("Arguments must be a JSON object.")
        interface = ABIAgentInterface()
        typer.echo(interface.dispatch(command, arguments), nl=False)
    except typer.Exit:
        raise
    except Exception as exc:
        _fail(exc)


@app.command("contract-lint")
def contract_lint_command(
    analysis_type: str = typer.Option(
        "metagenomic_plasmid",
        "--type",
        help="ABI analysis type whose DAG and contracts to lint.",
    ),
    strict: bool = typer.Option(
        False,
        "--strict",
        help="Treat warnings as errors (non-zero exit code on warnings).",
    ),
) -> None:
    """Lint pipeline DAG and tool contracts for structural errors (B18/B20/B19).

    Checks performed:

    - **DAG cyclics** — detects cycles in ``depends_on`` via topological sort.
    - **Broken dependencies** — ``depends_on`` references to non-existent nodes.
    - **Orphan nodes** — nodes with no dependents and no dependencies.
    - **Assertion syntax** — compiles every assertion expression to check validity.
    - **Contract consistency** — cross-references contracts with the tool registry.

    Exit code 0 means no errors found.  Use ``--strict`` to also fail on warnings.

    对管道 DAG 和工具合约进行结构错误静态检查。
    """
    try:
        from abi.contracts.lint import run_contract_lint
        from abi.plugins import get_plugin

        plugin = get_plugin(analysis_type)
        if not hasattr(plugin, "root"):
            typer.echo(
                json.dumps(
                    {
                        "findings": [
                            {
                                "severity": "error",
                                "check": "missing_root",
                                "detail": (
                                    f"Plugin {analysis_type!r} does not provide "
                                    f"a filesystem root — cannot lint."
                                ),
                                "location": "",
                            }
                        ],
                        "error_count": 1,
                        "warning_count": 0,
                        "passed": False,
                    },
                    indent=2,
                )
            )
            raise typer.Exit(code=1)
        # Load DAG spec
        root = Path(plugin.root)
        dag_path = root / "pipeline_dag.yaml"
        if not dag_path.exists():
            typer.echo(
                json.dumps(
                    {
                        "findings": [
                            {
                                "severity": "error",
                                "check": "missing_dag",
                                "detail": f"DAG file not found: {dag_path}",
                                "location": str(dag_path),
                            }
                        ],
                        "error_count": 1,
                        "warning_count": 0,
                        "passed": False,
                    },
                    indent=2,
                )
            )
            raise typer.Exit(code=1)

        import yaml as _yaml

        with dag_path.open("r", encoding="utf-8") as fh:
            dag_spec = _yaml.safe_load(fh)

        # Load tool contracts if available
        contracts = None
        registry_ids = None
        contracts_dir = root / "tool_contracts"
        if contracts_dir.exists():
            from abi.contracts import load_tool_contracts

            try:
                contracts = load_tool_contracts(str(root))
            except Exception:
                contracts = None
            if hasattr(plugin, "registry"):
                registry = plugin.registry()
                registry_ids = {str(t.get("id", "")) for t in registry.list_tools()}

        result = run_contract_lint(dag_spec, contracts=contracts, registry_tool_ids=registry_ids)

        typer.echo(json.dumps(result, indent=2, ensure_ascii=False))

        if not result["passed"]:
            raise typer.Exit(code=1)
        if strict and result["warning_count"] > 0:
            raise typer.Exit(code=1)
    except typer.Exit:
        raise
    except Exception as exc:
        _fail(exc)


def main() -> None:
    """Entry point for the ``abi`` console script.

    ``abi`` 控制台脚本的入口点。
    """
    app()


if __name__ == "__main__":
    main()
