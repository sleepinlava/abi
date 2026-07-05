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
* ``table_schemas``       → declarative ``standard_tables.yaml``

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

import os
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence

from abi.config import PLUGIN_ROOT, load_yaml
from abi.dag_planner import (
    build_plan_from_dag as _core_build_plan,
)
from abi.dag_planner import (
    build_sample_context as _core_build_sample_context,
)
from abi.provenance import RunLogger
from abi.schemas import ExecutionPlan, PlanStep, SampleContext, SampleInput
from abi.tools import ToolRegistry

from ._engine.config import load_config as load_autoplasm_config
from ._engine.parsers import parse_standard_outputs
from ._engine.pipeline import PipelineExecutor
from ._engine.report.html import write_html_report
from ._engine.report.markdown import write_markdown_report
from ._engine.resources import check_resources as check_plugin_resources
from ._engine.resources import setup_resources as setup_plugin_resources
from ._engine.result_validation import validate_result_dir as validate_plugin_result_dir
from ._engine.standard_tables import summarize_standard_tables

# ── Context resolver & hooks (migrated from _engine/planner.py) ──────────


def _plugin_context_resolver(
    config: Mapping[str, Any], context: SampleContext
) -> tuple[Dict[str, Any], Dict[str, Any]]:
    """Resolve auto/conditional sample-analysis settings from sample metadata.

    Replaces ``_engine/planner.py:_resolve_context_conditions()``.
    """
    from collections import Counter
    from copy import deepcopy

    resolved = deepcopy(dict(config))
    sample_count = len(context.samples)
    abundance_samples = [s for s in context.samples if s.platform != "assembly"]
    abundance_sample_count = len(abundance_samples)
    group_counts = Counter(s.group for s in abundance_samples if s.group)
    has_read_inputs = abundance_sample_count > 0

    # ── sample_analysis section ──────────────────────────────────────────
    sample_analysis = resolved.setdefault("sample_analysis", {})
    if not isinstance(sample_analysis, dict):
        sample_analysis = {}
        resolved["sample_analysis"] = sample_analysis

    def _requested(value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in {"true", "yes", "1", "auto"}
        return bool(value)

    analysis_requested = _requested(sample_analysis.get("enable", "auto"))
    min_diversity = int(sample_analysis.get("min_diversity_samples", 3))
    min_replicates = int(sample_analysis.get("min_group_replicates", 3))
    run_diversity = (
        analysis_requested and has_read_inputs and abundance_sample_count >= min_diversity
    )
    differential_requested = analysis_requested and _requested(
        sample_analysis.get("differential_abundance", "auto")
    )
    run_differential = (
        differential_requested
        and has_read_inputs
        and len(group_counts) >= 2
        and all(count >= min_replicates for count in group_counts.values())
    )

    sample_analysis["enable"] = run_diversity
    sample_analysis["run_diversity"] = run_diversity
    sample_analysis["differential_abundance"] = run_differential
    sample_analysis["run_differential"] = run_differential
    differential_method = str(sample_analysis.get("differential_method", "deseq2"))
    sample_analysis["run_differential_deseq2"] = (
        run_differential and differential_method == "deseq2"
    )
    sample_analysis["run_differential_internal"] = (
        run_differential and differential_method == "internal_effect_size"
    )

    # ── network section ──────────────────────────────────────────────────
    network = resolved.setdefault("network", {})
    if not isinstance(network, dict):
        network = {}
        resolved["network"] = network
    network_requested = _requested(network.get("enable", "auto"))
    min_network = int(network.get("min_samples", 20))
    run_network = network_requested and has_read_inputs and abundance_sample_count >= min_network
    network["enable"] = run_network
    network["run_network"] = run_network

    # ── host_plasmid_linking section ──────────────────────────────────────
    host_linking = resolved.setdefault("host_plasmid_linking", {})
    if not isinstance(host_linking, dict):
        host_linking = {}
        resolved["host_plasmid_linking"] = host_linking
    methods = host_linking.get("methods", [])
    host_linking_enabled = _requested(host_linking.get("enable", False))
    coabundance_requested = (
        host_linking_enabled and isinstance(methods, list) and "co_abundance" in methods
    )
    host_prediction = resolved.get("host_prediction", {})
    host_profile_enabled = isinstance(host_prediction, Mapping) and _requested(
        host_prediction.get("enable", False)
    )
    run_coabundance = (
        coabundance_requested and host_profile_enabled and abundance_sample_count >= min_diversity
    )
    host_linking["enable"] = host_linking_enabled
    host_linking["run_coabundance"] = run_coabundance

    # ── Eligibility ──────────────────────────────────────────────────────
    eligibility: Dict[str, Dict[str, Any]] = {}
    if not run_diversity:
        eligibility["diversity"] = {
            "run": run_diversity,
            "sample_count": sample_count,
            "eligible_sample_count": abundance_sample_count,
            "threshold": min_diversity,
            "reason": (
                f"requires at least {min_diversity} samples with read-based abundance"
                if has_read_inputs
                else "no samples with read-based abundance"
            ),
        }
    if not run_differential:
        eligibility["differential_abundance"] = {
            "run": run_differential,
            "sample_count": sample_count,
            "eligible_sample_count": abundance_sample_count,
            "group_counts": dict(sorted(group_counts.items())),
            "threshold": min_replicates,
            "reason": (
                f"requires at least two groups and {min_replicates} biological replicates per group"
                if has_read_inputs
                else "no samples with read-based abundance"
            ),
        }
    if not run_network:
        eligibility["network"] = {
            "run": run_network,
            "sample_count": sample_count,
            "eligible_sample_count": abundance_sample_count,
            "threshold": min_network,
            "reason": (
                f"requires at least {min_network} samples with read-based abundance"
                if has_read_inputs
                else "no samples with read-based abundance"
            ),
        }
    if not run_coabundance:
        eligibility["host_plasmid_coabundance"] = {
            "run": run_coabundance,
            "report_skip": coabundance_requested,
            "sample_count": sample_count,
            "eligible_sample_count": abundance_sample_count,
            "threshold": min_diversity,
            "reason": (
                "requires co_abundance method, host profile enabled, and "
                f"at least {min_diversity} samples with abundance data"
                if coabundance_requested
                else "co_abundance not requested"
            ),
        }

    # ── Resolve tool lists from config (needed before active_node_ids) ──
    # ``annotation.tools`` resolution from ``general_annotator`` / ``arg_tools`` etc.
    annotation = resolved.get("annotation")
    if isinstance(annotation, dict):
        if any(
            k in annotation
            for k in ("general_annotator", "arg_tools", "vf_tools", "mobile_element_tools")
        ):
            general = annotation.get("general_annotator", "bakta")
            tools = [] if general in {None, "", "none"} else [str(general)]
            tools.extend(str(t) for t in annotation.get("arg_tools", []) if t)
            tools.extend(str(t) for t in annotation.get("vf_tools", []) if t)
            tools.extend(str(t) for t in annotation.get("mobile_element_tools", []) if t)
            annotation["tools"] = tools

    # Resolve ``auto`` tool lists for typed categories.
    # Use the first available sample's platform for data_profile fallback.
    data_profile = None
    workflow = resolved.get("workflow", {})
    if isinstance(workflow, Mapping) and workflow.get("data_profile"):
        data_profile = str(workflow["data_profile"])
    if data_profile is None:
        input_cfg = resolved.get("input", {})
        if isinstance(input_cfg, Mapping) and input_cfg.get("data_profile"):
            data_profile = str(input_cfg["data_profile"])
    if data_profile is None and context.samples:
        first_plat = _detect_platform(context.samples[0])
        data_profile = DATA_PROFILE_BY_PLATFORM.get(first_plat, first_plat)

    for category in ("plasmid_binning", "typing", "host_prediction"):
        block = resolved.get(category)
        if not isinstance(block, dict):
            block = {}
            resolved[category] = block
        configured_tools = block.get("tools", "auto")
        if block.get("enable") and (configured_tools == "auto" or configured_tools is None):
            block["tools"] = _default_tools_for_category(category, data_profile or "")

    # If annotation is already set (from defaults), add mob_suite for isolate
    # profiles even when no arg_tools/vf_tools are present.
    if data_profile and _is_isolate_profile(data_profile):
        annotation_block = resolved.get("annotation")
        if isinstance(annotation_block, dict) and "mob_suite" not in annotation_block.get(
            "tools", []
        ):
            existing = list(annotation_block.get("tools", []))
            existing.append("mob_suite")
            annotation_block["tools"] = existing

    # Enable assembly for assembly-platform samples (so active_node_ids
    # includes assembly_provided and downstream nodes).
    if any(s.platform == "assembly" for s in context.samples):
        assembly_block = resolved.setdefault("assembly", {})
        if isinstance(assembly_block, dict):
            assembly_block["enable"] = True

    return resolved, eligibility


def _detect_platform(sample: SampleInput) -> str:
    """Simple platform detection for data_profile resolution in context_resolver."""
    if sample.platform and sample.platform not in {"auto", "", "generic"}:
        return sample.platform
    if sample.read1 and sample.long_reads:
        return "hybrid"
    if sample.long_reads or sample.pod5 or sample.bam:
        return "ont"
    if sample.read1:
        return "illumina"
    if sample.assembly:
        return "assembly"
    return "illumina"


def _plugin_skip_step_hook(
    node_id: str,
    tool_id: str,
    sample_config: Mapping[str, Any],
    sample: SampleInput,
) -> str | None:
    """Skip assembly-only sample read-QC steps.

    Replaces ``_engine/planner.py:_analysis_skip_steps()`` and the per-sample
    skip logic from ``_dag_step_for_node()``.
    """
    if tool_id == "internal":
        return None
    # Assembly-only input skips read QC
    if (
        sample.platform == "assembly"
        and "qc" in (node_id or "").lower()
        and tool_id not in {"quast", "assembly_qc"}
    ):
        return "Assembly-only input skips read QC"
    return None


# ── Per-sample config hook (replaces _engine/planner.py:_config_for_sample) ──


ISOLATE_PROFILES: set = {"isolate_plasmid", "isolate"}

DATA_PROFILE_BY_PLATFORM: dict[str, str] = {
    "illumina": "illumina_short",
    "ont": "ont_long",
    "pacbio_hifi": "pacbio_hifi",
    "hybrid": "hybrid_short_long",
    "assembly": "assembly_only",
}


def _is_isolate_profile(data_profile: str) -> bool:
    return data_profile in ISOLATE_PROFILES or data_profile.endswith("_isolate")


def _data_profile_dag(sample: SampleInput, config: Mapping[str, Any]) -> str:
    workflow = config.get("workflow", {})
    if isinstance(workflow, Mapping) and workflow.get("data_profile"):
        return str(workflow["data_profile"])
    input_config = config.get("input", {})
    if isinstance(input_config, Mapping) and input_config.get("data_profile"):
        return str(input_config["data_profile"])
    return DATA_PROFILE_BY_PLATFORM.get(sample.platform, sample.platform)


def _annotation_tools(config: Mapping[str, Any], data_profile: str) -> list[str]:
    annotation = config.get("annotation", {})
    if not isinstance(annotation, Mapping):
        return []
    general = annotation.get("general_annotator", "bakta")
    tools = [] if general in {None, "", "none"} else [str(general)]
    tools.extend(str(t) for t in annotation.get("arg_tools", []) if t)
    tools.extend(str(t) for t in annotation.get("vf_tools", []) if t)
    tools.extend(str(t) for t in annotation.get("mobile_element_tools", []) if t)
    if _is_isolate_profile(data_profile):
        tools.append("mob_suite")
    return tools


def _default_tools_for_category(category: str, data_profile: str) -> list[str]:
    if category == "plasmid_detection":
        return ["genomad"]
    if category == "plasmid_binning":
        return ["gplas2"]
    if category == "typing" and _is_isolate_profile(data_profile):
        return ["mob_typer", "plasmidfinder"]
    if category == "host_prediction":
        if data_profile in {"illumina_short", "ont_long", "pacbio_hifi", "hybrid_short_long"}:
            return ["metaphlan"]
        return ["plasmidhostfinder"]
    return []


def _plugin_sample_config_hook(config: Mapping[str, Any], sample: SampleInput) -> dict[str, Any]:
    """Customize config per sample — replaces ``_config_for_sample()``.

    Merges sample-level input fields into ``config.input``, resolves
    ``auto`` tool lists, and sets ``host_removal.host_reference`` from
    the sample's own field.
    """
    from copy import deepcopy

    resolved = deepcopy(dict(config))

    # Merge sample input fields into config for enable_condition resolution
    input_block = resolved.setdefault("input", {})
    if not isinstance(input_block, dict):
        input_block = {}
        resolved["input"] = input_block
    for field in ("long_reads", "pod5", "bam"):
        val = getattr(sample, field, None)
        if val is not None:
            input_block[field] = val

    # host_removal.host_reference from sample
    host_removal = resolved.setdefault("host_removal", {})
    if not isinstance(host_removal, dict):
        host_removal = {}
        resolved["host_removal"] = host_removal
    if sample.host_reference:
        host_removal["host_reference"] = sample.host_reference

    # Assembly defaults
    assembly = resolved.setdefault("assembly", {})
    if not isinstance(assembly, dict):
        assembly = {}
        resolved["assembly"] = assembly
    assembly.setdefault("short_read_assembler", "megahit")
    assembly.setdefault("long_read_assembler", "metaflye")
    assembly.setdefault("pacbio_hifi_assembler", "hifiasm_meta")
    assembly.setdefault("hybrid_assembler", "opera_ms")
    if sample.platform == "assembly":
        assembly["enable"] = True

    data_profile = _data_profile_dag(sample, resolved)

    for category in ("plasmid_binning", "typing", "host_prediction"):
        block = resolved.get(category)
        if not isinstance(block, dict):
            block = {}
            resolved[category] = block
        configured_tools = block.get("tools", "auto")
        if block.get("enable") and (configured_tools == "auto" or configured_tools is None):
            block["tools"] = _default_tools_for_category(category, data_profile)

    annotation = resolved.get("annotation")
    if isinstance(annotation, dict) and (
        _is_isolate_profile(data_profile)
        or any(
            key in annotation
            for key in ("general_annotator", "arg_tools", "vf_tools", "mobile_element_tools")
        )
    ):
        annotation["tools"] = _annotation_tools(resolved, data_profile)

    return resolved


# ── Backward-compatible entry point ───────────────────────────────────────


def build_plan_from_dag(
    config: Mapping[str, Any],
    sample_context: SampleContext | None = None,
    *,
    check_files: bool = True,
) -> ExecutionPlan:
    """Build an execution plan while preserving the legacy planner contract.

    Phase 2 keeps the declarative DAG planner available for migration work,
    but the public metagenomic-plasmid entry point must remain backed by the
    legacy planner until golden traces and route tests match. Set
    ``ABI_USE_CORE_DAG_PLANNER=1`` to opt into the new core DAG path.
    """
    if os.environ.get("ABI_USE_CORE_DAG_PLANNER") != "1":
        from ._engine.planner import build_plan_from_dag as _legacy_build_plan

        return _legacy_build_plan(
            config,
            sample_context=sample_context,
            check_files=check_files,
        )

    ctx = sample_context or _core_build_sample_context(config, check_files=check_files)
    if not sample_context:
        has_abundance = any(s.platform != "assembly" for s in ctx.samples)
        ctx.enable_sample_analysis = ctx.multi_sample
        ctx.enable_differential_abundance = ctx.has_groups and has_abundance

    resolved_config, _ = _plugin_context_resolver(config, ctx)
    return _core_build_plan(
        PLUGIN_ROOT / "metagenomic_plasmid" / "pipeline_dag.yaml",
        resolved_config,
        ctx,
        context_resolver=None,
        skip_step_hook=_plugin_skip_step_hook,
    )


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
        db_profile: str | None = None,
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
        return load_autoplasm_config(
            config_path,
            profile=profile or "dry_run",
            db_profile=db_profile,
            overrides=overrides,
        )

    def check_resources(
        self,
        config: Mapping[str, Any],
        *,
        resource_ids: Optional[Sequence[str]] = None,
    ) -> list[dict[str, Any]]:
        return check_plugin_resources(config, resource_ids=resource_ids)

    def setup_resources(
        self,
        config: Mapping[str, Any],
        *,
        resource_ids: Optional[Sequence[str]] = None,
        dry_run: bool = False,
        mock: bool = False,
    ) -> list[dict[str, Any]]:
        return setup_plugin_resources(
            config,
            resource_ids=resource_ids,
            dry_run=dry_run,
            mock=mock,
        )

    def validate_result_dir(
        self,
        result_dir: str | Path,
        *,
        allow_empty_tables: bool = True,
    ) -> Mapping[str, Any]:
        return validate_plugin_result_dir(
            result_dir,
            allow_empty_tables=allow_empty_tables,
        )

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

    def build_plan(self, config: Mapping[str, Any], *, check_files: bool = True) -> Any:
        """Build an execution plan from the canonical declarative DAG."""
        return build_plan_from_dag(config, check_files=check_files)

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
        data = load_yaml(self.root / "standard_tables.yaml")
        tables = data.get("tables", {})
        if not isinstance(tables, Mapping):
            raise ValueError("standard_tables.yaml must contain a tables mapping")
        return {str(name): [str(column) for column in columns] for name, columns in tables.items()}

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

    Delegates to the shared ``render_figures_via_sciplot()`` from
    ``abi.report.generic_report`` — the same function used by the four
    inline plugins (amplicon_16s, rnaseq_expression, wgs_bacteria,
    metatranscriptomics).  Returns ``{spec_id: png_path}`` for HTML
    report embedding.

    Unlike the previous inline implementation, this version properly
    logs warnings for missing/empty tables, respects the ``required``
    field, and surfaces rendering errors instead of silently swallowing
    them.
    """
    from abi.report.generic_report import render_figures_via_sciplot

    fig_specs_path = plugin.root / "figure_specs.yaml"
    if not fig_specs_path.exists():
        return {}

    return render_figures_via_sciplot(
        plugin,
        fig_specs_path,
        tables_dir,
        figures_dir,
    )


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
