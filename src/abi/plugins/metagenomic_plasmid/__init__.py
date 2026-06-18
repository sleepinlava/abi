"""Metagenomic Plasmid Analysis Plugin -- ABI adapter for the AutoPlasm pipeline.

Architecture / 架构说明
------------------------
This module is the public entry-point of a **self-contained plugin package**
located at ``abi/plugins/metagenomic_plasmid/``.  The heavy logic lives in the
private ``_engine/`` sub-package so that the plugin boundary stays thin: every
interface method on ``MetagenomicPlasmidPlugin`` delegates directly to a
corresponding ``_engine`` module.

本模块是 **独立插件包** ``abi/plugins/metagenomic_plasmid/`` 的公开入口。核心
逻辑位于私有的 ``_engine/`` 子包中，保证插件边界保持轻量：``MetagenomicPlasmidPlugin``
上的每个接口方法都直接委托给对应的 ``_engine`` 模块。

Delegation map / 委托映射
~~~~~~~~~~~~~~~~~~~~~~~~~~
* ``load_config``         → ``_engine.config.load_config``
* ``build_plan``          → ``_engine.planner.build_plan``
* ``registry``            → ``tool_registry.yaml``  (same directory)
* ``execute_dry_run``     → ``_engine.pipeline.PipelineExecutor``
* ``parse_outputs``       → ``_engine.parsers.parse_standard_outputs``
* ``write_report``        → ``_engine.report.markdown`` / ``_engine.report.html``
* ``table_schemas``       → ``_engine.standard_tables.TABLE_SCHEMAS``

Data flow / 数据流
~~~~~~~~~~~~~~~~~~
1. User provides a config dict → ``load_config`` normalizes it.
2. The config drives ``build_plan`` → an ``ExecutionPlan`` of ``PlanStep`` items.
3. The ABI agent executes steps using tools from ``registry()``.
4. After execution, ``write_report`` serializes the plan (possibly from a JSON
   dict via ``_plan_from_dict``) and generates Markdown + HTML reports under
   ``<result_dir>/report/``.

The ``_plan_from_dict`` helper / ``_plan_from_dict`` 辅助函数
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
When a report is generated from previously-saved JSON (e.g. after a job service
restart or from a remote run), the plan arrives as a plain ``Mapping``.  The
helper reconstructs a fully-typed ``ExecutionPlan`` including its nested
``SampleInput``, ``SampleContext``, and ``PlanStep`` objects so the report
writers can traverse it with attribute access.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Mapping, Optional

from abi.config import PLUGIN_ROOT
from abi.provenance import RunLogger
from abi.schemas import ExecutionPlan, PlanStep, SampleContext, SampleInput
from abi.tools import ToolRegistry

from ._engine.config import load_config as load_autoplasm_config
from ._engine.parsers import parse_standard_outputs
from ._engine.pipeline import PipelineExecutor
from ._engine.planner import build_plan, build_plan_from_dag
from ._engine.report.html import write_html_report
from ._engine.report.markdown import write_markdown_report
from ._engine.standard_tables import TABLE_SCHEMAS, summarize_standard_tables


class MetagenomicPlasmidPlugin:
    """ABI plugin wrapping the AutoPlasm metagenomic plasmid analysis engine.

    Implements the ``ABIPlugin`` interface so the ABI agent can discover tools,
    build execution plans, parse tool outputs, and generate reports without
    knowing the internal pipeline details.

    实现 ``ABIPlugin`` 接口的 AutoPlasm 宏基因组质粒分析插件。ABI agent 通过该接口
    发现工具、构建执行计划、解析工具输出并生成报告，无需了解内部管道细节。
    """

    # Static metadata consumed by the ABI agent for plugin discovery
    # ABI agent 插件发现用的静态元数据
    plugin_id = "metagenomic_plasmid"
    display_name = "Metagenomic Plasmid Analysis"
    description = "AutoPlasm adapter using the existing plasmid-analysis planner and executor."
    report_title = "AutoPlasm ABI Report"

    @property
    def root(self) -> Path:
        """Filesystem root for plugin data (configs, tool registry, etc.).

        插件数据（配置文件、工具注册表等）的文件系统根目录。
        """
        return PLUGIN_ROOT / self.plugin_id

    # ── Configuration / 配置 ──────────────────────────────────────────────

    def load_config(
        self,
        config_path: str | Path | None = None,
        *,
        profile: str | None = None,
        overrides: Optional[Mapping[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Load and normalize the pipeline configuration.

        Delegates to ``_engine.config.load_config`` which merges the default
        config with any user-provided overrides.  The ``profile`` defaults to
        ``"dry_run"`` so that config loading is always safe even without a
        real profile.

        加载并规范化管道配置。委托给 ``_engine.config.load_config``，
        合并默认配置与用户提供的覆盖项。``profile`` 默认为 ``"dry_run"``，
        确保即使没有真实 profile 也能安全加载配置。
        """
        return load_autoplasm_config(config_path, profile=profile or "dry_run", overrides=overrides)

    # ── Sample context / 样本上下文 ──────────────────────────────────────

    def build_sample_context(self, config: Mapping[str, Any], *, check_files: bool = True) -> Any:
        """Return the sample context for the pipeline (unused by AutoPlasm).

        AutoPlasm discovers samples from the plan itself rather than a
        pre-parsed sample sheet, so this always returns ``None``.  The method
        exists only to satisfy the ``ABIPlugin`` interface contract.

        返回管道的样本上下文（AutoPlasm 不使用）。AutoPlasm 从计划本身获取样本信息，
        而非预解析的样本表，因此始终返回 ``None``。该方法仅为满足 ``ABIPlugin``
        接口约定而存在。
        """
        del check_files
        return None

    # ── Plan construction / 计划构建 ─────────────────────────────────────

    def build_plan(
        self, config: Mapping[str, Any], *, check_files: bool = True, use_dag: bool = True
    ) -> Any:
        """Build an execution plan from the normalized configuration.

        When ``use_dag=True`` (default), reads the canonical
        ``pipeline_dag.yaml`` spec and generates steps from it.  When
        ``use_dag=False``, falls back to the legacy hardcoded planner.

        从规范化配置构建执行计划。use_dag=True（默认）时读取规范的
        pipeline_dag.yaml 并从中生成步骤。use_dag=False 时回退到旧的硬编码规划器。
        """
        if use_dag:
            return build_plan_from_dag(config, check_files=check_files)
        return build_plan(config, check_files=check_files)

    # ── Tool registry / 工具注册表 ───────────────────────────────────────

    def registry(self) -> ToolRegistry:
        """Return the tool registry loaded from ``tool_registry.yaml``.

        The registry defines every tool (command-template, container image,
        resource requirements) the pipeline may invoke.  It lives alongside
        this plugin under ``plugins/metagenomic_plasmid/``.

        返回从 ``tool_registry.yaml`` 加载的工具注册表。注册表定义了管道可能调用的
        每个工具（命令模板、容器镜像、资源需求），位于 ``plugins/metagenomic_plasmid/``
        目录中。
        """
        return ToolRegistry.from_path(self.root / "tool_registry.yaml")

    # ── Standard tables / 标准表格 ───────────────────────────────────────

    def table_schemas(self) -> Mapping[str, list[str]]:
        """Return the expected column schemas for standard output tables.

        These schemas drive validation and summarization of pipeline results.

        返回标准输出表的预期列结构，用于验证和汇总管道结果。
        """
        return TABLE_SCHEMAS

    # ── Output parsing / 输出解析 ────────────────────────────────────────

    def parse_outputs(
        self,
        tool_id: str,
        output_dir: str | Path,
        sample_id: str,
    ) -> Mapping[str, Any]:
        """Parse the standard output files produced by ``tool_id``.

        Delegates to ``_engine.parsers.parse_standard_outputs``, which knows
        the expected file layout for each tool in the AutoPlasm pipeline.

        解析 ``tool_id`` 生成的标准输出文件。委托给
        ``_engine.parsers.parse_standard_outputs``，后者了解 AutoPlasm 管道中
        每个工具的预期文件布局。
        """
        return parse_standard_outputs(tool_id, output_dir, sample_id)

    # ── Dry-run execution / 演习执行 ─────────────────────────────────────

    def execute_dry_run(self, plan: Any, config: Mapping[str, Any]) -> Dict[str, Path]:
        """Simulate pipeline execution using mock tools (no real computation).

        Creates a ``PipelineExecutor`` in mock mode so the agent can validate
        the plan shape and output directory structure before committing to a
        real run.

        使用模拟工具模拟管道执行（不进行真实计算）。在模拟模式下创建
        ``PipelineExecutor``，使 agent 能够在提交真实运行之前验证计划结构和
        输出目录布局。
        """
        logger = RunLogger(str(config["log_dir"]))
        executor = PipelineExecutor(self.registry(), logger, mock_tools=True)
        return executor.dry_run(plan, config)

    # ── Report generation / 报告生成 ─────────────────────────────────────

    def write_report(self, plan: Any, result_dir: str | Path) -> Dict[str, Path]:
        """Generate Markdown and HTML reports for a completed pipeline run.

        If ``plan`` arrives as a plain ``Mapping`` (e.g. deserialized from
        JSON after a remote run), it is first converted to a typed
        ``ExecutionPlan`` via ``_plan_from_dict``.  Both Markdown and HTML
        reports are written under ``<result_dir>/report/``, and standard
        table summaries are also generated.

        Figures are rendered via ``abi_sciplot`` (PDF+SVG+PNG+provenance+lint)
        and embedded in the HTML report.

        为已完成的管道运行生成 Markdown 和 HTML 报告。如果 ``plan`` 以普通
        ``Mapping`` 形式传入（例如远程运行后从 JSON 反序列化），会先通过
        ``_plan_from_dict`` 转换为类型化的 ``ExecutionPlan``。Markdown 和 HTML
        报告均写入 ``<result_dir>/report/``，同时生成标准表格汇总。

        图形通过 ``abi_sciplot`` 渲染（PDF+SVG+PNG+provenance+lint）并嵌入 HTML 报告。
        """
        # Reconstruct typed plan from JSON dict if needed / 如有需要，从 JSON 字典重建类型化计划
        if isinstance(plan, Mapping):
            plan = _plan_from_dict(plan)
        root = Path(result_dir)
        tables_dir = root / "tables"
        provenance_dir = root / "provenance"
        figures_dir = root / "figures"

        # ── Render figures via abi_sciplot ──
        rendered_figures = _render_plasmid_figures(self, tables_dir, figures_dir)

        report_path = write_markdown_report(
            plan,
            root / "report",
            tables_dir=tables_dir,
            provenance_dir=provenance_dir,
            dry_run=False,
        )
        report_html_path = write_html_report(
            plan,
            root / "report",
            tables_dir=tables_dir,
            provenance_dir=provenance_dir,
            dry_run=False,
            rendered_figures=rendered_figures,
        )
        # Summarize standard tables for quick inspection / 汇总标准表格以便快速查看
        summarize_standard_tables(tables_dir)
        return {"report": report_path, "report_html": report_html_path}


# ── Helpers / 辅助函数 ──────────────────────────────────────────────────────


def _render_plasmid_figures(
    plugin: Any,
    tables_dir: Path,
    figures_dir: Path,
) -> Mapping[str, Path]:
    """Render plasmid figures via abi_sciplot.

    Loads ``figure_specs.yaml`` from the plugin root, adapts to abi_sciplot
    FigureSpec format, and renders each figure.  Returns ``{spec_id: png_path}``
    for HTML report embedding.
    """
    from abi.config import load_yaml
    from abi.sciplot.adapters import adapt_spec
    from abi.sciplot.api import render_figure

    fig_specs_path = plugin.root / "figure_specs.yaml"
    if not fig_specs_path.exists():
        return {}

    data = load_yaml(fig_specs_path)
    old_specs: list[dict] = list(data.get("figures", []))
    if not old_specs:
        return {}

    abi_version = getattr(plugin, "abi_version", None)
    rendered: dict[str, Path] = {}
    for old in old_specs:
        spec_id = old.get("id", "")
        if not spec_id:
            continue

        # Skip optional figures whose source table doesn't exist
        source_table = old.get("source_table", "")
        table_path = tables_dir / f"{source_table}.tsv"
        if not table_path.exists():
            continue

        try:
            spec = adapt_spec(
                old,
                tables_dir,
                figures_dir,
                plugin_name="metagenomic_plasmid",
                abi_version=abi_version,
            )
            result = render_figure(spec)
            png_files = [p for p in result.output_files if p.suffix == ".png"]
            if png_files and not result.errors:
                rendered[spec_id] = png_files[0]
        except Exception:
            pass
    return rendered


def _plan_from_dict(data: Mapping[str, Any]) -> ExecutionPlan:
    """Reconstruct a fully-typed ``ExecutionPlan`` from a serialized JSON dict.

    Design rationale / 设计理由
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~
    When ``write_report`` is called after a job-service restart or from a
    remote execution, the plan arrives as a plain ``Mapping`` because JSON
    carries no Python type information.  This helper rehydrates it into an
    ``ExecutionPlan`` so that downstream report writers can use attribute
    access (``plan.steps``, ``plan.sample_context``, etc.) instead of
    fragile dict-key lookups.

    当 ``write_report`` 在作业服务重启后或从远程执行被调用时，计划以普通 ``Mapping``
    形式传入（JSON 不携带 Python 类型信息）。此辅助函数将其恢复为 ``ExecutionPlan``，
    使下游报告编写器可以使用属性访问（``plan.steps``、``plan.sample_context`` 等），
    而非脆弱的字典键查找。
    """
    # Reconstruct sample inputs / 重建样本输入
    samples = [SampleInput(**sample) for sample in data.get("samples", [])]
    context_data = data.get("sample_context", {})
    if not isinstance(context_data, Mapping):
        context_data = {}
    # Build sample context with sensible defaults / 使用合理默认值构建样本上下文
    sample_context = SampleContext(
        samples=samples,
        multi_sample=bool(context_data.get("multi_sample", len(samples) > 1)),
        has_groups=bool(context_data.get("has_groups", False)),
        enable_sample_analysis=bool(context_data.get("enable_sample_analysis", False)),
        enable_differential_abundance=bool(
            context_data.get("enable_differential_abundance", False)
        ),
    )
    return ExecutionPlan(
        project_name=str(data.get("project_name", "autoplasm_project")),
        mode=str(data.get("mode", "auto")),
        threads=int(data.get("threads", 1)),
        outdir=str(data.get("outdir", "")),
        log_dir=str(data.get("log_dir", "log")),
        samples=samples,
        steps=[PlanStep(**step) for step in data.get("steps", [])],
        sample_context=sample_context,
        selected_tools=[str(tool) for tool in data.get("selected_tools", [])],
        skipped_steps=[PlanStep(**step) for step in data.get("skipped_steps", [])],
        provenance_dir=data.get("provenance_dir"),
    )
