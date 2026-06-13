"""AutoPlasm command-line interface."""

from __future__ import annotations

import json
from html import escape
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

import typer
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
)

from abi.plugins.metagenomic_plasmid._engine.config import load_config
from abi.plugins.metagenomic_plasmid._engine.dashboard import DashboardServer
from abi.plugins.metagenomic_plasmid._engine.json_utils import load_json_object
from abi.plugins.metagenomic_plasmid._engine.logger import RunLogger
from abi.plugins.metagenomic_plasmid._engine.pipeline import PipelineExecutor
from abi.plugins.metagenomic_plasmid._engine.planner import build_plan
from abi.plugins.metagenomic_plasmid._engine.resources import (
    check_resources as check_resource_status,
)
from abi.plugins.metagenomic_plasmid._engine.resources import (
    fetch_example_dataset,
    required_resource_issues,
)
from abi.plugins.metagenomic_plasmid._engine.resources import (
    setup_resources as setup_resource_files,
)
from abi.plugins.metagenomic_plasmid._engine.result_validation import validate_result_dir
from abi.plugins.metagenomic_plasmid._engine.sample_sheet import (
    parse_sample_sheet,
    single_sample_context,
)
from abi.plugins.metagenomic_plasmid._engine.schemas import AutoPlasmError
from abi.plugins.metagenomic_plasmid._engine.skills.registry import ToolRegistry
from abi.plugins.metagenomic_plasmid._engine.standard_tables import (
    read_standard_table,
    summarize_standard_tables,
)

APP_HELP = (
    "AutoPlasm 宏基因组质粒分析 CLI。支持样本表校验、工具检查、执行计划生成、"
    "dry-run provenance 生成，以及通过仓库本地 .mamba 环境实际调用已注册的"
    "生物信息学工具。AutoPlasm CLI for metagenomic plasmid analysis: validate "
    "sample sheets, check tools, build plans, write dry-run provenance, and run "
    "registered tools from repository-local .mamba environments. Recommended "
    "workflow: validate-sample-sheet, then plan or dry-run, then run."
)

CONFIG_HELP = "项目配置 / Project YAML config."
SAMPLE_SHEET_HELP = "TSV 样本表 / TSV sample sheet."
MODE_HELP = "模式 / Mode: auto or interactive."
THREADS_HELP = "线程数 / Thread count."
OUTDIR_HELP = "结果目录 / Output directory."
LOG_DIR_HELP = "日志目录 / Log directory."
PROFILE_HELP = "profile 名称 / Profile name."
RESUME_HELP = "记录 resume / Record resume intent."
FORCE_HELP = "记录 force / Record force intent."
DRY_RUN_HELP = "不执行外部工具 / Do not execute external tools."
PARALLEL_HELP = "样本级并行 / Run samples in parallel."
WORKERS_HELP = "pipeline 并行样本数 / Number of parallel sample workers."
PROGRESS_HELP = "显示 CLI 进度 / Show CLI progress."
DASHBOARD_HELP = "启动本地 Web dashboard / Start local Web dashboard."
OPEN_DASHBOARD_HELP = "打开浏览器 / Open dashboard in browser."

app = typer.Typer(help=APP_HELP, no_args_is_help=True)


def _common_overrides(
    *,
    mode: Optional[str],
    threads: Optional[int],
    outdir: Optional[str],
    log_dir: Optional[str],
    resume: bool,
    force: bool,
    dry_run: bool,
    parallel: Optional[bool] = None,
    workers: Optional[int] = None,
    progress: Optional[bool] = None,
    dashboard: Optional[bool] = None,
    open_dashboard: Optional[bool] = None,
) -> Dict[str, Any]:
    overrides: Dict[str, Any] = {
        "mode": mode,
        "threads": threads,
        "outdir": outdir,
        "log_dir": log_dir,
        "resume": resume,
        "force": force,
        "dry_run": dry_run,
    }
    execution: Dict[str, Any] = {}
    if parallel is True and workers is None:
        workers = 2
    if parallel is not None:
        execution["parallel"] = parallel
    if workers is not None:
        execution["workers"] = workers
    if progress is not None:
        execution["progress"] = progress
    dashboard_overrides: Dict[str, Any] = {}
    if dashboard is not None:
        dashboard_overrides["enable"] = dashboard
    if open_dashboard is not None:
        dashboard_overrides["open_browser"] = open_dashboard
    if dashboard_overrides:
        execution["dashboard"] = dashboard_overrides
    if execution:
        overrides["execution"] = execution
    return overrides


def _load(
    config: Optional[Path],
    profile: str,
    overrides: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    return load_config(config, profile=profile, overrides=overrides)


def _fail(exc: Exception) -> None:
    if isinstance(exc, MemoryError):
        raise
    typer.secho(f"Error: {exc}", fg=typer.colors.RED, err=True)
    raise typer.Exit(code=1)


def _true_count(rows: list[Dict[str, str]]) -> int:
    return sum(1 for row in rows if str(row.get("final_plasmid_call", "")).lower() == "true")


def _raise_resource_issues_for_real_run(
    config: Dict[str, Any], selected_tools: List[str], *, dry_run: bool
) -> None:
    if dry_run or config.get("mock_tools"):
        return
    issues = required_resource_issues(config, selected_tools)
    if issues:
        raise AutoPlasmError(
            "Required resources are missing or invalid:\n"
            + "\n".join(f"- {issue}" for issue in issues)
        )


def _execution_config(config: Dict[str, Any]) -> Dict[str, Any]:
    execution = config.get("execution", {})
    return execution if isinstance(execution, dict) else {}


def _dashboard_config(config: Dict[str, Any]) -> Dict[str, Any]:
    dashboard = _execution_config(config).get("dashboard", {})
    return dashboard if isinstance(dashboard, dict) else {}


def _run_pipeline_with_interfaces(
    executor: PipelineExecutor,
    plan: Any,
    config: Dict[str, Any],
    *,
    dry_run: bool,
    use_dry_run_method: bool = False,
) -> Dict[str, Path]:
    execution = _execution_config(config)
    dashboard = _dashboard_config(config)
    dashboard_server: DashboardServer | None = None
    if dashboard.get("enable", False):
        dashboard_server = DashboardServer(
            plan.outdir,
            host=str(dashboard.get("host", "127.0.0.1")),
            port=int(dashboard.get("port", 18790)),
        )
        url = dashboard_server.start(open_browser=bool(dashboard.get("open_browser", True)))
        typer.echo(f"Dashboard: {url}")

    show_progress = bool(execution.get("progress", True))
    try:
        if not show_progress:
            return (
                executor.dry_run(plan, config)
                if use_dry_run_method
                else executor.run(plan, config, dry_run=dry_run)
            )

        with Progress(
            SpinnerColumn(),
            TextColumn("{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            TimeElapsedColumn(),
            transient=False,
        ) as progress:
            task_id = progress.add_task("Preparing pipeline...", total=len(plan.steps))

            def progress_callback(event: Mapping[str, Any]) -> None:
                event_name = event.get("event", "")
                payload = event.get("payload", {})
                if event_name == "step_started":
                    step_id = payload.get("step_id", "")
                    sample_id = payload.get("sample_id", "")
                    label = f"{sample_id}: {step_id}" if sample_id else str(step_id)
                    progress.update(task_id, description=f"Running {label}")
                elif event_name in {"step_completed", "step_failed"}:
                    step_id = payload.get("step_id", "")
                    status = payload.get("status", "")
                    progress.advance(task_id)
                    progress.update(task_id, description=f"{status}: {step_id}")
                elif event_name == "run_completed":
                    progress.update(task_id, description=f"Pipeline {payload.get('status', '')}")

            executor.progress_callback = progress_callback
            return (
                executor.dry_run(plan, config)
                if use_dry_run_method
                else executor.run(plan, config, dry_run=dry_run)
            )
    finally:
        if dashboard_server:
            dashboard_server.stop()


@app.callback()
def callback() -> None:
    """规划、校验并执行 AutoPlasm / Plan, validate, and run AutoPlasm."""


@app.command("init")
def init_project(
    outdir: Path = typer.Option(
        Path("."),
        "--outdir",
        help="工作目录 / Workspace directory.",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        help="允许覆盖 / Allow overwrite intent.",
    ),
) -> None:
    """初始化工作目录 / Initialize workspace hints.

    该命令用于准备一个最小工作目录。它不会下载工具、创建 mamba 环境或生成完整配置。
    This prepares a minimal workspace hint directory. It does not download tools,
    create mamba environments, or generate a complete project config.
    """
    try:
        config_dir = outdir / "config"
        config_dir.mkdir(parents=True, exist_ok=True)
        typer.echo(f"Initialized AutoPlasm workspace hints under {config_dir}")
        if not force:
            typer.echo("Existing files were left untouched.")
    except Exception as exc:  # pragma: no cover - Typer boundary
        _fail(exc)


@app.command("validate-sample-sheet")
def validate_sample_sheet(
    sample_sheet: Path = typer.Option(
        ...,
        "--sample-sheet",
        exists=True,
        readable=True,
        help=SAMPLE_SHEET_HELP,
    ),
    check_files: bool = typer.Option(
        True,
        "--check-files/--no-check-files",
        help="检查文件 / Check files.",
    ),
    mode: Optional[str] = typer.Option(None, "--mode", help=MODE_HELP),
    threads: Optional[int] = typer.Option(None, "--threads", help=THREADS_HELP),
    outdir: Optional[str] = typer.Option(None, "--outdir", help=OUTDIR_HELP),
    log_dir: Optional[str] = typer.Option(None, "--log-dir", help=LOG_DIR_HELP),
    profile: str = typer.Option("local", "--profile", help=PROFILE_HELP),
    resume: bool = typer.Option(False, "--resume", help=RESUME_HELP),
    force: bool = typer.Option(False, "--force", help=FORCE_HELP),
    dry_run: bool = typer.Option(False, "--dry-run", help=DRY_RUN_HELP),
) -> None:
    """校验样本表 / Validate a TSV sample sheet.

    该命令只校验输入表，不生成执行计划，也不会调用外部工具。输出 JSON 会显示样本数、
    分组状态，以及是否会启用多样本分析和差异丰度分析。
    This command only validates input metadata. It does not build a plan or run
    external tools. The JSON output shows sample context and multi-sample flags.
    """
    del mode, threads, outdir, log_dir, profile, resume, force, dry_run
    try:
        context = parse_sample_sheet(sample_sheet, check_files=check_files)
        typer.echo(json.dumps(context.to_dict(), indent=2, ensure_ascii=False))
    except Exception as exc:
        _fail(exc)


@app.command("list-tools")
def list_tools(
    config: Optional[Path] = typer.Option(None, "--config", help=CONFIG_HELP),
    mode: Optional[str] = typer.Option(None, "--mode", help=MODE_HELP),
    threads: Optional[int] = typer.Option(None, "--threads", help=THREADS_HELP),
    outdir: Optional[str] = typer.Option(None, "--outdir", help=OUTDIR_HELP),
    log_dir: Optional[str] = typer.Option(None, "--log-dir", help=LOG_DIR_HELP),
    profile: str = typer.Option("local", "--profile", help=PROFILE_HELP),
    resume: bool = typer.Option(False, "--resume", help=RESUME_HELP),
    force: bool = typer.Option(False, "--force", help=FORCE_HELP),
    dry_run: bool = typer.Option(False, "--dry-run", help=DRY_RUN_HELP),
) -> None:
    """列出工具 / List registered tools.

    输出为 TSV 行：tool_id、category、default/optional、required/recommended、env_name。
    该命令展示 registry 内容，不检查可执行文件是否存在。
    Prints registry rows as TSV. This does not check whether executables exist.
    """
    try:
        _load(
            config,
            profile,
            _common_overrides(
                mode=mode,
                threads=threads,
                outdir=outdir,
                log_dir=log_dir,
                resume=resume,
                force=force,
                dry_run=dry_run,
            ),
        )
        registry = ToolRegistry.from_path()
        for tool in registry.list_tools():
            default = "default" if tool.get("default_enabled") else "optional"
            required = "required" if tool.get("required") else "recommended"
            row = [
                str(tool["id"]),
                str(tool.get("category", "")),
                default,
                required,
                str(tool.get("env_name", "")),
            ]
            typer.echo("\t".join(row))
    except Exception as exc:
        _fail(exc)


@app.command("check-tools")
def check_tools(
    config: Optional[Path] = typer.Option(None, "--config", help=CONFIG_HELP),
    mode: Optional[str] = typer.Option(None, "--mode", help=MODE_HELP),
    threads: Optional[int] = typer.Option(None, "--threads", help=THREADS_HELP),
    outdir: Optional[str] = typer.Option(None, "--outdir", help=OUTDIR_HELP),
    log_dir: Optional[str] = typer.Option(None, "--log-dir", help=LOG_DIR_HELP),
    profile: str = typer.Option("local", "--profile", help=PROFILE_HELP),
    resume: bool = typer.Option(False, "--resume", help=RESUME_HELP),
    force: bool = typer.Option(False, "--force", help=FORCE_HELP),
    dry_run: bool = typer.Option(False, "--dry-run", help=DRY_RUN_HELP),
) -> None:
    """检查工具 / Check registered executables.

    真实检查时，工具必须位于仓库本地 .mamba/envs/{env_name}/bin，或位于
    ABI_MAMBA_ROOT 指向的本地 mamba 根目录下；AUTOPLASM_MAMBA_ROOT 仍作为兼容
    回退。使用 --dry-run 或 mock_tools 时会模拟为可用，用于计划阶段。
    Real checks resolve tools from repository-local mamba environments. With
    --dry-run or mock_tools enabled, checks are mocked for planning.
    """
    try:
        cfg = _load(
            config,
            profile,
            _common_overrides(
                mode=mode,
                threads=threads,
                outdir=outdir,
                log_dir=log_dir,
                resume=resume,
                force=force,
                dry_run=dry_run,
            ),
        )
        registry = ToolRegistry.from_path()
        rows = registry.check_tools(mock_tools=bool(cfg.get("mock_tools") or dry_run), config=cfg)
        typer.echo(json.dumps(rows, indent=2, ensure_ascii=False))
    except Exception as exc:
        _fail(exc)


@app.command("check-resources")
def check_resources_command(
    config: Optional[Path] = typer.Option(None, "--config", help=CONFIG_HELP),
    resource: Optional[List[str]] = typer.Option(
        None,
        "--resource",
        help="资源 ID / Resource id to check. Repeatable.",
    ),
    mode: Optional[str] = typer.Option(None, "--mode", help=MODE_HELP),
    threads: Optional[int] = typer.Option(None, "--threads", help=THREADS_HELP),
    outdir: Optional[str] = typer.Option(None, "--outdir", help=OUTDIR_HELP),
    log_dir: Optional[str] = typer.Option(None, "--log-dir", help=LOG_DIR_HELP),
    profile: str = typer.Option("local", "--profile", help=PROFILE_HELP),
    resume: bool = typer.Option(False, "--resume", help=RESUME_HELP),
    force: bool = typer.Option(False, "--force", help=FORCE_HELP),
    dry_run: bool = typer.Option(False, "--dry-run", help=DRY_RUN_HELP),
) -> None:
    """检查数据库/模型资源 / Check database and model resources.

    该命令只检查资源路径、manifest 可读性和当前状态，不下载资源。
    This checks configured database/model paths without downloading anything.
    """
    try:
        cfg = _load(
            config,
            profile,
            _common_overrides(
                mode=mode,
                threads=threads,
                outdir=outdir,
                log_dir=log_dir,
                resume=resume,
                force=force,
                dry_run=dry_run,
            ),
        )
        rows = check_resource_status(cfg, resource_ids=resource)
        typer.echo(json.dumps(rows, indent=2, ensure_ascii=False))
    except Exception as exc:
        _fail(exc)


@app.command("setup-resources")
def setup_resources_command(
    config: Optional[Path] = typer.Option(None, "--config", help=CONFIG_HELP),
    resource: Optional[List[str]] = typer.Option(
        None,
        "--resource",
        help="资源 ID / Resource id to prepare. Repeatable.",
    ),
    mock: bool = typer.Option(
        False,
        "--mock",
        help="创建 mock 资源 / Create mock resource directories.",
    ),
    mode: Optional[str] = typer.Option(None, "--mode", help=MODE_HELP),
    threads: Optional[int] = typer.Option(None, "--threads", help=THREADS_HELP),
    outdir: Optional[str] = typer.Option(None, "--outdir", help=OUTDIR_HELP),
    log_dir: Optional[str] = typer.Option(None, "--log-dir", help=LOG_DIR_HELP),
    profile: str = typer.Option("local", "--profile", help=PROFILE_HELP),
    resume: bool = typer.Option(False, "--resume", help=RESUME_HELP),
    force: bool = typer.Option(False, "--force", help=FORCE_HELP),
    dry_run: bool = typer.Option(False, "--dry-run", help=DRY_RUN_HELP),
) -> None:
    """下载或准备核心资源 / Download or prepare core resources.

    默认准备 geNomad、Bakta light、MOB-suite 和 PlasmidFinder 资源。真实下载会写入
    resources.root；--dry-run 只输出计划，--mock 只创建测试目录和 manifest。
    By default this prepares geNomad, Bakta light, MOB-suite, and PlasmidFinder.
    """
    try:
        cfg = _load(
            config,
            profile,
            _common_overrides(
                mode=mode,
                threads=threads,
                outdir=outdir,
                log_dir=log_dir,
                resume=resume,
                force=force,
                dry_run=dry_run,
            ),
        )
        if dry_run or mock:
            rows = setup_resource_files(cfg, resource_ids=resource, dry_run=dry_run, mock=mock)
        else:
            with Progress(
                SpinnerColumn(),
                TextColumn("{task.description}"),
                TimeElapsedColumn(),
                transient=True,
            ) as progress:
                task_id = progress.add_task("Preparing resources...", total=None)

                def update_progress(event: str, resource_id: str, message: str) -> None:
                    if event == "start":
                        progress.update(task_id, description=f"{resource_id}: {message}")
                    else:
                        progress.update(
                            task_id,
                            description=f"{resource_id}: {message}",
                        )

                rows = setup_resource_files(
                    cfg,
                    resource_ids=resource,
                    dry_run=dry_run,
                    mock=mock,
                    progress_callback=update_progress,
                )
        failed = [row for row in rows if row.get("status") == "failed"]
        typer.echo(json.dumps(rows, indent=2, ensure_ascii=False))
        if failed:
            raise AutoPlasmError("One or more resources failed to prepare")
    except Exception as exc:
        _fail(exc)


@app.command("fetch-examples")
def fetch_examples_command(
    dataset: str = typer.Option(
        "plasmid_refseq_smoke",
        "--dataset",
        help="示例数据集 / Example dataset id.",
    ),
    outdir: Path = typer.Option(
        Path("data/examples/plasmid_refseq_smoke"),
        "--outdir",
        help="输出目录 / Output directory.",
    ),
    mock: bool = typer.Option(
        False,
        "--mock",
        help="创建 mock FASTA / Create mock FASTA files.",
    ),
) -> None:
    """下载公开 assembly smoke 数据 / Fetch public assembly smoke data.

    默认下载 3 个小型 NCBI RefSeq plasmid FASTA，并生成 sample_sheet.tsv。
    By default this fetches three small RefSeq plasmid FASTA files and writes a
    sample sheet.
    """
    try:
        outputs = fetch_example_dataset(dataset, outdir, mock=mock)
        serialized = {
            key: str(value) if isinstance(value, Path) else value for key, value in outputs.items()
        }
        typer.echo(
            json.dumps(
                serialized,
                indent=2,
                ensure_ascii=False,
            )
        )
    except Exception as exc:
        _fail(exc)


@app.command("plan")
def plan_command(
    config: Optional[Path] = typer.Option(None, "--config", help=CONFIG_HELP),
    sample_sheet: Optional[Path] = typer.Option(None, "--sample-sheet", help=SAMPLE_SHEET_HELP),
    mode: Optional[str] = typer.Option(None, "--mode", help=MODE_HELP),
    threads: Optional[int] = typer.Option(None, "--threads", help=THREADS_HELP),
    outdir: Optional[str] = typer.Option(None, "--outdir", help=OUTDIR_HELP),
    log_dir: Optional[str] = typer.Option(None, "--log-dir", help=LOG_DIR_HELP),
    profile: str = typer.Option("local", "--profile", help=PROFILE_HELP),
    resume: bool = typer.Option(False, "--resume", help=RESUME_HELP),
    force: bool = typer.Option(False, "--force", help=FORCE_HELP),
    dry_run: bool = typer.Option(False, "--dry-run", help=DRY_RUN_HELP),
) -> None:
    """生成执行计划 / Build the JSON execution plan.

    plan 只做配置解析、样本解析和步骤展开，不创建完整 provenance，也不调用外部工具。
    用它检查平台路由、工具选择、输出目录和跳过步骤是否符合预期。
    This parses config and sample metadata, expands workflow steps, and prints
    JSON. It does not write full provenance or execute tools.
    """
    try:
        overrides = _common_overrides(
            mode=mode,
            threads=threads,
            outdir=outdir,
            log_dir=log_dir,
            resume=resume,
            force=force,
            dry_run=dry_run,
        )
        if sample_sheet:
            overrides["input"] = {"sample_sheet": str(sample_sheet)}
        cfg = _load(config, profile, overrides)
        execution_plan = build_plan(cfg, check_files=True)
        typer.echo(json.dumps(execution_plan.to_dict(), indent=2, ensure_ascii=False))
    except Exception as exc:
        _fail(exc)


@app.command("dry-run")
def dry_run_command(
    config: Optional[Path] = typer.Option(None, "--config", help=CONFIG_HELP),
    sample_sheet: Optional[Path] = typer.Option(None, "--sample-sheet", help=SAMPLE_SHEET_HELP),
    mode: Optional[str] = typer.Option(None, "--mode", help=MODE_HELP),
    threads: Optional[int] = typer.Option(None, "--threads", help=THREADS_HELP),
    outdir: Optional[str] = typer.Option(None, "--outdir", help=OUTDIR_HELP),
    log_dir: Optional[str] = typer.Option(None, "--log-dir", help=LOG_DIR_HELP),
    profile: str = typer.Option("dry_run", "--profile", help=PROFILE_HELP),
    resume: bool = typer.Option(False, "--resume", help=RESUME_HELP),
    force: bool = typer.Option(False, "--force", help=FORCE_HELP),
    dry_run: bool = typer.Option(True, "--dry-run", help=DRY_RUN_HELP),
    parallel: Optional[bool] = typer.Option(None, "--parallel/--serial", help=PARALLEL_HELP),
    workers: Optional[int] = typer.Option(None, "--workers", help=WORKERS_HELP),
    progress: Optional[bool] = typer.Option(None, "--progress/--no-progress", help=PROGRESS_HELP),
    dashboard: Optional[bool] = typer.Option(
        None,
        "--dashboard/--no-dashboard",
        help=DASHBOARD_HELP,
    ),
    open_dashboard: Optional[bool] = typer.Option(
        None,
        "--open-dashboard/--no-open-dashboard",
        help=OPEN_DASHBOARD_HELP,
    ),
) -> None:
    """生成 dry-run / Write dry-run provenance.

    dry-run 是推荐的生产运行前检查步骤。它会展开所有命令并写入 provenance，
    但不会调用 fastp、MEGAHIT、geNomad 等外部工具，也不要求数据库真实可用。
    Dry-run is the recommended preflight step. It writes commands and provenance
    without running fastp, MEGAHIT, geNomad, or other external tools.
    """
    try:
        overrides = _common_overrides(
            mode=mode,
            threads=threads,
            outdir=outdir,
            log_dir=log_dir,
            resume=resume,
            force=force,
            dry_run=dry_run,
            parallel=parallel,
            workers=workers,
            progress=progress,
            dashboard=dashboard,
            open_dashboard=open_dashboard,
        )
        overrides["mock_tools"] = True
        if sample_sheet:
            overrides["input"] = {"sample_sheet": str(sample_sheet)}
        cfg = _load(config, profile, overrides)
        execution_plan = build_plan(cfg, check_files=True)
        _raise_resource_issues_for_real_run(cfg, execution_plan.selected_tools, dry_run=dry_run)
        logger = RunLogger(cfg["log_dir"])
        executor = PipelineExecutor(ToolRegistry.from_path(), logger, mock_tools=True)
        outputs = _run_pipeline_with_interfaces(
            executor,
            execution_plan,
            cfg,
            dry_run=True,
            use_dry_run_method=True,
        )
        typer.echo(json.dumps({key: str(value) for key, value in outputs.items()}, indent=2))
    except Exception as exc:
        _fail(exc)


@app.command("run")
def run_command(
    config: Optional[Path] = typer.Option(None, "--config", help=CONFIG_HELP),
    sample_sheet: Optional[Path] = typer.Option(None, "--sample-sheet", help=SAMPLE_SHEET_HELP),
    mode: Optional[str] = typer.Option(None, "--mode", help=MODE_HELP),
    threads: Optional[int] = typer.Option(None, "--threads", help=THREADS_HELP),
    outdir: Optional[str] = typer.Option(None, "--outdir", help=OUTDIR_HELP),
    log_dir: Optional[str] = typer.Option(None, "--log-dir", help=LOG_DIR_HELP),
    profile: str = typer.Option("local", "--profile", help=PROFILE_HELP),
    resume: bool = typer.Option(False, "--resume", help=RESUME_HELP),
    force: bool = typer.Option(False, "--force", help=FORCE_HELP),
    dry_run: bool = typer.Option(False, "--dry-run", help=DRY_RUN_HELP),
    parallel: Optional[bool] = typer.Option(None, "--parallel/--serial", help=PARALLEL_HELP),
    workers: Optional[int] = typer.Option(None, "--workers", help=WORKERS_HELP),
    progress: Optional[bool] = typer.Option(None, "--progress/--no-progress", help=PROGRESS_HELP),
    dashboard: Optional[bool] = typer.Option(
        None,
        "--dashboard/--no-dashboard",
        help=DASHBOARD_HELP,
    ),
    open_dashboard: Optional[bool] = typer.Option(
        None,
        "--open-dashboard/--no-open-dashboard",
        help=OPEN_DASHBOARD_HELP,
    ),
) -> None:
    """按样本表运行 / Run workflow from a sample sheet.

    不带 --dry-run 时会逐步调用 registry 中的外部工具。工具从仓库本地 mamba 环境
    查找；缺失数据库、模型、索引或中间产物时会停止，并把失败原因写入
    provenance/commands.tsv 和 step_logs。
    Without --dry-run, this executes registered external tools. Failures stop
    the run and are recorded in provenance/commands.tsv and step_logs.
    """
    try:
        overrides = _common_overrides(
            mode=mode,
            threads=threads,
            outdir=outdir,
            log_dir=log_dir,
            resume=resume,
            force=force,
            dry_run=dry_run,
            parallel=parallel,
            workers=workers,
            progress=progress,
            dashboard=dashboard,
            open_dashboard=open_dashboard,
        )
        overrides["mock_tools"] = dry_run
        if sample_sheet:
            overrides["input"] = {"sample_sheet": str(sample_sheet)}
        cfg = _load(config, profile, overrides)
        execution_plan = build_plan(cfg, check_files=True)
        logger = RunLogger(cfg["log_dir"])
        executor = PipelineExecutor(
            ToolRegistry.from_path(), logger, mock_tools=bool(cfg.get("mock_tools") or dry_run)
        )
        outputs = _run_pipeline_with_interfaces(
            executor,
            execution_plan,
            cfg,
            dry_run=dry_run,
        )
        typer.echo(json.dumps({key: str(value) for key, value in outputs.items()}, indent=2))
    except Exception as exc:
        _fail(exc)


@app.command("run-single")
def run_single(
    input_path: Path = typer.Option(
        ...,
        "--input",
        exists=True,
        readable=True,
        help="主输入 / Main input file.",
    ),
    read2: Optional[Path] = typer.Option(
        None,
        "--read2",
        help="R2 FASTQ / Illumina read 2.",
    ),
    long_reads: Optional[Path] = typer.Option(
        None,
        "--long-reads",
        help="长读 FASTQ / Long-read FASTQ.",
    ),
    assembly: Optional[Path] = typer.Option(
        None,
        "--assembly",
        help="组装 FASTA / Assembly FASTA.",
    ),
    platform: str = typer.Option(
        ...,
        "--platform",
        help="输入类型 / Input type.",
    ),
    sample_id: str = typer.Option(
        "single_sample",
        "--sample-id",
        help="样本 ID / Sample ID.",
    ),
    group: Optional[str] = typer.Option(
        None,
        "--group",
        help="分组标签 / Group label.",
    ),
    config: Optional[Path] = typer.Option(None, "--config", help=CONFIG_HELP),
    mode: Optional[str] = typer.Option(None, "--mode", help=MODE_HELP),
    threads: Optional[int] = typer.Option(None, "--threads", help=THREADS_HELP),
    outdir: Optional[str] = typer.Option(None, "--outdir", help=OUTDIR_HELP),
    log_dir: Optional[str] = typer.Option(None, "--log-dir", help=LOG_DIR_HELP),
    profile: str = typer.Option("local", "--profile", help=PROFILE_HELP),
    resume: bool = typer.Option(False, "--resume", help=RESUME_HELP),
    force: bool = typer.Option(False, "--force", help=FORCE_HELP),
    dry_run: bool = typer.Option(False, "--dry-run", help=DRY_RUN_HELP),
    parallel: Optional[bool] = typer.Option(None, "--parallel/--serial", help=PARALLEL_HELP),
    workers: Optional[int] = typer.Option(None, "--workers", help=WORKERS_HELP),
    progress: Optional[bool] = typer.Option(None, "--progress/--no-progress", help=PROGRESS_HELP),
    dashboard: Optional[bool] = typer.Option(
        None,
        "--dashboard/--no-dashboard",
        help=DASHBOARD_HELP,
    ),
    open_dashboard: Optional[bool] = typer.Option(
        None,
        "--open-dashboard/--no-open-dashboard",
        help=OPEN_DASHBOARD_HELP,
    ),
) -> None:
    """运行单样本 / Run or dry-run one sample.

    该命令会临时构造一个单样本上下文，然后复用与 run 相同的 planner 和 executor。
    适合快速检查单个 FASTQ 或已有 assembly；正式批量项目建议使用 sample sheet。
    This builds a temporary single-sample context and reuses the same planner and
    executor as run. Use a sample sheet for formal multi-sample projects.
    """
    try:
        overrides = _common_overrides(
            mode=mode,
            threads=threads,
            outdir=outdir,
            log_dir=log_dir,
            resume=resume,
            force=force,
            dry_run=dry_run,
            parallel=parallel,
            workers=workers,
            progress=progress,
            dashboard=dashboard,
            open_dashboard=open_dashboard,
        )
        overrides["mock_tools"] = dry_run
        cfg = _load(config, profile, overrides)
        read1 = str(input_path) if platform == "illumina" else None
        long_value = (
            str(long_reads or input_path) if platform in {"ont", "pacbio_hifi", "hybrid"} else None
        )
        assembly_value: Optional[str]
        if platform == "assembly":
            assembly_value = str(assembly or input_path)
        else:
            assembly_value = str(assembly) if assembly else None
        context = single_sample_context(
            sample_id=sample_id,
            platform=platform,
            read1=read1,
            read2=str(read2) if read2 else None,
            long_reads=long_value,
            assembly=assembly_value,
            group=group,
            check_files=True,
        )
        execution_plan = build_plan(cfg, sample_context=context, check_files=True)
        _raise_resource_issues_for_real_run(cfg, execution_plan.selected_tools, dry_run=dry_run)
        logger = RunLogger(cfg["log_dir"])
        executor = PipelineExecutor(
            ToolRegistry.from_path(), logger, mock_tools=bool(cfg.get("mock_tools") or dry_run)
        )
        outputs = _run_pipeline_with_interfaces(
            executor,
            execution_plan,
            cfg,
            dry_run=dry_run,
        )
        typer.echo(json.dumps({key: str(value) for key, value in outputs.items()}, indent=2))
    except Exception as exc:
        _fail(exc)


@app.command("dashboard")
def dashboard_command(
    result_dir: Path = typer.Option(
        ...,
        "--result-dir",
        help="结果目录 / Result directory.",
    ),
    host: str = typer.Option(
        "127.0.0.1",
        "--host",
        help="监听地址 / Bind host.",
    ),
    port: int = typer.Option(
        18790,
        "--port",
        help="监听端口 / Bind port.",
    ),
    open_browser: bool = typer.Option(
        True,
        "--open/--no-open",
        help=OPEN_DASHBOARD_HELP,
    ),
) -> None:
    """启动本地运行监控面板 / Serve the local run dashboard.

    Dashboard 默认只监听 127.0.0.1。远程服务器建议使用 SSH tunnel 访问，不要直接暴露到公网。
    The dashboard binds to localhost by default. Use an SSH tunnel for remote
    servers instead of exposing the port publicly.
    """
    try:
        if not result_dir.exists():
            raise AutoPlasmError(f"Result directory does not exist: {result_dir}")
        server = DashboardServer(result_dir, host=host, port=port)
        typer.echo(f"Dashboard: http://{host}:{port}/")
        server.serve_forever(open_browser=open_browser)
    except KeyboardInterrupt:
        typer.echo("Dashboard stopped.")
    except Exception as exc:
        _fail(exc)


@app.command("report")
def report_command(
    result_dir: Path = typer.Option(
        ...,
        "--result-dir",
        help="结果目录 / Result directory with execution_plan.json.",
    ),
    mode: Optional[str] = typer.Option(None, "--mode", help=MODE_HELP),
    threads: Optional[int] = typer.Option(None, "--threads", help=THREADS_HELP),
    outdir: Optional[str] = typer.Option(None, "--outdir", help=OUTDIR_HELP),
    log_dir: Optional[str] = typer.Option(None, "--log-dir", help=LOG_DIR_HELP),
    profile: str = typer.Option("local", "--profile", help=PROFILE_HELP),
    resume: bool = typer.Option(False, "--resume", help=RESUME_HELP),
    force: bool = typer.Option(False, "--force", help=FORCE_HELP),
    dry_run: bool = typer.Option(False, "--dry-run", help=DRY_RUN_HELP),
) -> None:
    """生成报告 / Regenerate report/report.html from standard tables.

    report 不重新运行外部工具，也不会重新解析原始结果；它基于 execution_plan.json、
    tables/*.tsv 和 provenance 重新生成 HTML 报告。
    This does not rerun tools or reparse raw outputs. It regenerates an HTML
    report from execution_plan.json, tables/*.tsv, and provenance.
    """
    del mode, threads, outdir, log_dir, profile, resume, force, dry_run
    try:
        plan_path = result_dir / "execution_plan.json"
        if not plan_path.exists():
            raise AutoPlasmError(f"Missing execution plan: {plan_path}")
        data = load_json_object(plan_path)
        report_dir = result_dir / "report"
        report_dir.mkdir(parents=True, exist_ok=True)
        project_name = data.get("project_name", str(result_dir))
        selected_tools = data.get("selected_tools", [])
        tables_dir = result_dir / "tables"
        table_summary = summarize_standard_tables(tables_dir)
        consensus = read_standard_table(tables_dir, "plasmid_consensus")
        annotations = read_standard_table(tables_dir, "annotations")
        hosts = read_standard_table(tables_dir, "host_predictions")
        abundance = read_standard_table(tables_dir, "abundance")
        diversity = read_standard_table(tables_dir, "sample_diversity")
        differential = read_standard_table(tables_dir, "differential_abundance")
        network_edges = read_standard_table(tables_dir, "network_edges")
        network_nodes = read_standard_table(tables_dir, "network_nodes")
        html = report_dir / "report.html"
        table_rows = [
            (
                f"<tr><td>{escape(table_name)}.tsv</td>"
                f"<td>{escape(str(metadata.get('rows', 0)))}</td>"
                f"<td><code>{escape(str(metadata.get('path', '')))}</code></td></tr>"
            )
            for table_name, metadata in sorted(table_summary.items())
        ]
        html.write_text(
            "\n".join(
                [
                    "<!doctype html>",
                    '<html lang="en">',
                    '<head><meta charset="utf-8"><title>AutoPlasm Report</title></head>',
                    "<body>",
                    f"<h1>AutoPlasm Report: {escape(str(project_name))}</h1>",
                    (
                        f"<p>Samples: {len(data.get('samples', []))}. "
                        f"Planned steps: {len(data.get('steps', []))}.</p>"
                    ),
                    "<h2>Selected Tools</h2>",
                    "<ul>",
                    *[f"<li>{escape(str(tool))}</li>" for tool in selected_tools],
                    "</ul>",
                    "<h2>Standard Tables</h2>",
                    "<table><thead><tr><th>Table</th><th>Rows</th><th>Path</th></tr></thead>",
                    "<tbody>",
                    *table_rows,
                    "</tbody></table>",
                    "<h2>Core Result Summary</h2>",
                    "<ul>",
                    f"<li>Consensus plasmid calls: {_true_count(consensus)}</li>",
                    f"<li>Annotation records: {len(annotations)}</li>",
                    f"<li>Host prediction records: {len(hosts)}</li>",
                    f"<li>Abundance records: {len(abundance)}</li>",
                    f"<li>Diversity records: {len(diversity)}</li>",
                    f"<li>Differential abundance records: {len(differential)}</li>",
                    f"<li>Network edges/nodes: {len(network_edges)}/{len(network_nodes)}</li>",
                    "</ul>",
                    "<h2>Interpretation Notes</h2>",
                    "<p>Dry-run proves planning only. Plasmid clusters are operational "
                    "groups, not taxonomic species. Plasmid binning may be incomplete, "
                    "and network correlations are not causal evidence.</p>",
                    "</body>",
                    "</html>",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        typer.echo(f"Wrote {html}")
    except Exception as exc:
        _fail(exc)


@app.command("validate-result")
def validate_result_command(
    result_dir: Path = typer.Option(
        ...,
        "--result-dir",
        help="结果目录 / Result directory.",
    ),
    allow_empty_tables: bool = typer.Option(
        True,
        "--allow-empty-tables/--require-nonempty-tables",
        help="允许标准表只有表头 / Allow header-only standard tables.",
    ),
) -> None:
    """审计结果目录 / Validate a completed result directory.

    This command is read-only. A result with failed steps or a non-success
    run_summary is invalid and must not be used as successful experiment evidence.
    """
    result = validate_result_dir(result_dir, allow_empty_tables=allow_empty_tables)
    typer.echo(json.dumps(result, indent=2, ensure_ascii=False))
    if not result["valid"]:
        raise typer.Exit(code=1)


@app.command("clean")
def clean_command(
    result_dir: Path = typer.Option(
        ...,
        "--result-dir",
        help="结果目录 / Result directory.",
    ),
    mode: Optional[str] = typer.Option(None, "--mode", help=MODE_HELP),
    threads: Optional[int] = typer.Option(None, "--threads", help=THREADS_HELP),
    outdir: Optional[str] = typer.Option(None, "--outdir", help=OUTDIR_HELP),
    log_dir: Optional[str] = typer.Option(None, "--log-dir", help=LOG_DIR_HELP),
    profile: str = typer.Option("local", "--profile", help=PROFILE_HELP),
    resume: bool = typer.Option(False, "--resume", help=RESUME_HELP),
    force: bool = typer.Option(False, "--force", help=FORCE_HELP),
    dry_run: bool = typer.Option(False, "--dry-run", help=DRY_RUN_HELP),
) -> None:
    """显示清理意图 / Show clean intent.

    当前 clean 是非破坏性命令。它只提示目标目录，避免误删生物信息学中间结果。
    This command is non-destructive. It reports what would be inspected rather
    than deleting generated bioinformatics outputs.
    """
    del mode, threads, outdir, log_dir, profile, resume, force
    message = (
        f"Would clean generated outputs under {result_dir}"
        if dry_run
        else (
            "Clean is non-destructive in this skeleton; inspect the result directory manually: "
            f"{result_dir}"
        )
    )
    typer.echo(message)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
