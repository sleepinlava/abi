"""Metatranscriptomics ABI Plugin -- portability demonstration.

Purpose / 目的
~~~~~~~~~~~~~~
This plugin is a **portability demo** that proves the ABI framework is not
tied to plasmid analysis.  It models a classic RNA-seq / metatranscriptomics
workflow (QC → alignment → quantification) while reusing the exact same
``ABIAgentInterface`` machinery that drives the plasmid pipeline.

这是一个 **可移植性演示** 插件，证明 ABI 框架不局限于质粒分析。它模拟经典的
RNA-seq / 宏转录组学工作流程（质控 → 比对 → 定量），同时复用驱动质粒管道的
完全相同的 ``ABIAgentInterface`` 机制。

Tool chain / 工具链
~~~~~~~~~~~~~~~~~~~
::

   fastp ──→ STAR ──→ featureCounts
   (QC)       (alignment)      (quantification)

Standard table / 标准表格
~~~~~~~~~~~~~~~~~~~~~~~~~~
The primary output is ``gene_expression`` (written to
``<tables_dir>/gene_expression.tsv``) with columns: ``sample_id``, ``gene_id``,
``count``, ``tpm``, ``tool``, ``source_file``.  Only ``featureCounts`` results
are parsed into this table; QC and alignment tools produce no standard-table
data.

Architecture / 架构
~~~~~~~~~~~~~~~~~~~
* ``load_config`` merges ``config_default.yaml`` + user config + CLI overrides,
  then resolves relative paths against ``PROJECT_ROOT``.
* ``build_sample_context`` parses the sample sheet (TSV with columns
  ``sample_id``, ``read1``, ``read2``) and validates file existence.
* ``build_plan`` constructs a linear 3-step-per-sample plan (QC → align →
  quantify) -- no DAG, no auto-detection -- so the code is intentionally
  simple and readable.
* ``parse_outputs`` only handles ``featurecounts``; other tools return ``{}``.
* ``write_report`` delegates to the generic ``write_generic_report`` helper
  from ``abi.report``.
* ``_validate_config`` checks for mandatory top-level keys and a positive
  thread count before any work begins (fail-fast).

Key difference from the plasmid plugin / 与质粒插件的主要区别
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Unlike ``MetagenomicPlasmidPlugin``, this plugin does **not** delegate to
an ``_engine/`` sub-package -- all logic is inline in this single module.
This keeps the demo self-contained and easy to audit as a reference
implementation.

与 ``MetagenomicPlasmidPlugin`` 不同，此插件**不**将逻辑委托给 ``_engine/``
子包——所有逻辑都内联在此单一模块中。这使得演示自包含且易于审计，可作为参考实现。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional

from abi._shared import (
    _execute_generic_dry_run,
    _offline_sample_context,
    _parse_fastp,
    _parse_sample_sheet_tabular,
    _parse_star,
    _resolve_path,
)
from abi.config import PLUGIN_ROOT, PROJECT_ROOT, compact_overrides, deep_merge, load_yaml
from abi.report import write_plugin_report
from abi.schemas import ABIExecutionPlan, ABISample, ABISampleContext
from abi.tools import ToolRegistry


class MetatranscriptomicsPlugin:
    """ABI plugin modelling a standard RNA-seq / metatranscriptomics workflow.

    Implements the ``ABIPlugin`` interface to demonstrate that the ABI
    framework can drive **any** bioinformatics pipeline, not just plasmid
    analysis.  The three-tool chain (fastp, STAR, featureCounts) mirrors
    what a typical RNA-seq pipeline looks like.

    实现 ``ABIPlugin`` 接口，演示 ABI 框架可以驱动**任何**生物信息学管道，
    不仅限于质粒分析。三工具链（fastp、STAR、featureCounts）反映了典型的
    RNA-seq 管道。

    Design decisions / 设计决策
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~
    * The plan is a simple **per-sample linear chain** -- no DAG or
      auto-detection -- to keep the code as clear as possible.
    * No ``sample_context`` object is handed to the plan builder; the
      sample sheet is parsed once in ``build_sample_context`` and the
      resulting ``ABISampleContext`` is stored on the plan.
    * ``parse_outputs`` only targets ``featurecounts`` because QC and
      alignment outputs are not tabular by nature.
    """

    # Static metadata for ABI agent discovery / ABI agent 发现用的静态元数据
    plugin_id = "metatranscriptomics"
    display_name = "Metatranscriptomics Demo"
    description = "Minimal RNA-seq style ABI portability demo: fastp, STAR, featureCounts."
    report_title = "Metatranscriptomics ABI Report"

    @property
    def root(self) -> Path:
        """Filesystem root for plugin data (configs, tool registry, etc.).

        插件数据（配置文件、工具注册表等）的文件系统根目录。
        """
        return PLUGIN_ROOT / self.plugin_id

    @property
    def _tsv_mapper(self):
        if not hasattr(self, "_tsv_mapper_cache"):
            from abi.tsv_mapping import TSVMapper

            self._tsv_mapper_cache = TSVMapper.from_yaml(self.root / "parsers.yaml")
        return self._tsv_mapper_cache

    # ── Configuration / 配置 ──────────────────────────────────────────────

    def load_config(
        self,
        config_path: str | Path | None = None,
        *,
        profile: str | None = None,
        overrides: Optional[Mapping[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Load, merge, and validate the metatranscriptomics configuration.

        Merges three layers in priority order / 按优先级合并三层配置：
        1. ``config_default.yaml``  (baseline / 基线)
        2. ``config_path``          (user-provided / 用户提供)
        3. ``overrides``            (CLI flags / 命令行标志)

        After merging, resolves relative paths (e.g. sample sheet location)
        against ``PROJECT_ROOT`` and validates required keys.

        合并后，将相对路径（如样本表位置）解析到 ``PROJECT_ROOT``，
        并验证必需的键。
        """
        del profile  # Not used by this plugin / 此插件不使用
        config = load_yaml(self.root / "config_default.yaml")
        if config_path:
            config = deep_merge(config, load_yaml(config_path))
        config = deep_merge(config, compact_overrides(overrides))
        # Resolve paths so downstream code never deals with raw relative paths
        # 解析路径，下游代码不再处理原始相对路径
        _resolve_config_paths(config)
        # Fail-fast: surface missing keys before any work starts
        # 快速失败：在任何工作开始前暴露缺失的键
        self._validate_config(config)
        self._last_config = config
        return config

    # ── Sample context / 样本上下文 ──────────────────────────────────────

    def build_sample_context(
        self,
        config: Mapping[str, Any],
        *,
        check_files: bool = True,
    ) -> ABISampleContext:
        """Parse the sample sheet and build a typed ``ABISampleContext``.

        The sample sheet must be a TSV with at least three columns:
        ``sample_id``, ``read1``, ``read2``.  File paths are resolved
        relative to the sample-sheet directory and ``PROJECT_ROOT``.

        解析样本表并构建类型化的 ``ABISampleContext``。样本表必须是至少包含
        ``sample_id``、``read1``、``read2`` 三列的 TSV 文件。文件路径会相对于
        样本表目录和 ``PROJECT_ROOT`` 进行解析。
        """
        input_config = config.get("input", {})
        if not isinstance(input_config, Mapping):
            raise ValueError("input must be a mapping")
        sample_sheet = input_config.get("sample_sheet")
        if not sample_sheet:
            raise ValueError("metatranscriptomics requires input.sample_sheet")
        return _parse_sample_sheet(sample_sheet, check_files=check_files)

    # ── Plan construction / 计划构建 ─────────────────────────────────────

    def build_plan(
        self,
        config: Mapping[str, Any],
        *,
        check_files: bool = True,
    ) -> ABIExecutionPlan:
        """Build a linear 3-step-per-sample execution plan.

        For every sample in the sample sheet we emit three ``ABIPlanStep``
        items in order / 按顺序为每个样本生成三个 ``ABIPlanStep``：

        1. **QC** (fastp)      -- trim adapters, filter low-quality reads
        2. **Alignment**       -- map reads to reference genome (STAR or HISAT2)
        3. **Quantification**  -- count reads per gene (featureCounts)

        The output directory structure mirrors this three-stage layout:

        ::

            <outdir>/01_qc/<sample_id>/        -- clean FASTQ files
            <outdir>/02_alignment/<sample_id>/ -- sorted BAM file
            <outdir>/03_expression/<sample_id>/-- featureCounts output
        """
        context = self.build_sample_context(config, check_files=check_files)
        from abi.dag_planner import build_plan_from_dag

        return build_plan_from_dag(self.root / "pipeline_dag.yaml", config, context)

    def registry(self) -> ToolRegistry:
        """Return the tool registry loaded from ``tool_registry.yaml``.

        Contains command templates and container images for fastp, STAR,
        and featureCounts.

        返回从 ``tool_registry.yaml`` 加载的工具注册表，包含 fastp、STAR、
        featureCounts 的命令模板及容器镜像。
        """
        return ToolRegistry.from_path(self.root / "tool_registry.yaml")

    def execute_dry_run(self, plan: Any, config: Mapping[str, Any]) -> Dict[str, Path]:
        return _execute_generic_dry_run(self, plan, config)

    # ── Standard tables / 标准表格 ───────────────────────────────────────

    def table_schemas(self) -> Mapping[str, Iterable[str]]:
        """Return expected column schemas from ``standard_tables.yaml``.

        Defines the ``gene_expression`` table with columns
        ``[sample_id, gene_id, count, tpm, tool, source_file]``.

        从 ``standard_tables.yaml`` 返回预期列结构，定义 ``gene_expression`` 表，
        包含 ``[sample_id, gene_id, count, tpm, tool, source_file]`` 列。
        """
        data = load_yaml(self.root / "standard_tables.yaml")
        tables = data.get("tables", {})
        if not isinstance(tables, Mapping):
            raise ValueError("standard_tables.yaml must contain a tables mapping")
        return tables

    # ── Output parsing / 输出解析 ────────────────────────────────────────

    def parse_outputs(
        self,
        tool_id: str,
        output_dir: str | Path,
        sample_id: str,
    ) -> Mapping[str, List[Dict[str, Any]]]:
        # Try declarative TSV mapper first
        if self._tsv_mapper.has_parser(tool_id):
            rows = self._tsv_mapper.parse(tool_id, output_dir, sample_id=sample_id)
            if rows:
                target = self._tsv_mapper.get_target_table(tool_id)
                return {target: rows} if target else {}
        # Fall back to hand-written parsers
        if tool_id == "fastp":
            return {"qc_summary": _parse_fastp(Path(output_dir), sample_id)}
        if tool_id == "star":
            return {"alignment_summary": _parse_star(Path(output_dir), sample_id)}
        # featurecounts is handled by TSVMapper above
        return {}

    # ── Report generation / 报告生成 ─────────────────────────────────────

    def write_report(self, plan: Any, result_dir: str | Path) -> Dict[str, Path]:
        """Generate a full ABI report with methods, citations, and limitations.

        Delegates to ``write_plugin_report`` which handles table summaries,
        figure rendering, methods, and resource manifest generation.
        """
        return write_plugin_report(self, plan, result_dir)

    # ── Validation / 验证 ────────────────────────────────────────────────

    def _validate_config(self, config: Mapping[str, Any]) -> None:
        """Fail-fast validation of top-level config keys.

        Checks that all mandatory keys are present and that ``threads`` is
        a positive integer.  Called during ``load_config`` so bad configs
        are rejected before any plan is built.

        对顶层配置键进行快速失败验证。检查所有必需键是否存在，且 ``threads``
        为正整数。在 ``load_config`` 中调用，以便在构建计划之前拒绝错误配置。
        """
        required = ["project_name", "mode", "threads", "outdir", "log_dir", "input"]
        missing = [key for key in required if key not in config]
        if missing:
            raise ValueError(f"Missing metatranscriptomics config keys: {', '.join(missing)}")
        threads = config.get("threads")
        try:
            threads = int(threads)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            raise ValueError("threads must be a positive integer") from None
        if threads < 1:
            raise ValueError("threads must be a positive integer")


# ── Sample sheet parser / 样本表解析器 ──────────────────────────────────


def _parse_sample_sheet(path: str | Path, *, check_files: bool) -> ABISampleContext:
    """Parse a TSV sample sheet into a typed ``ABISampleContext``.

    Design decisions / 设计决策
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~
    * The sample sheet is resolved against ``PROJECT_ROOT`` first, so
      relative paths in configs "just work" from the project directory.
    * ``enumerate(reader, start=2)`` makes error messages human-friendly
      (row 1 = header, rows 2+ = data).
    * ``group`` falls back to ``condition`` so sample sheets written for
      differential-expression tools work without renaming columns.
    * ``check_files=True`` performs an upfront file-existence check so
      the user sees all missing files at once rather than one-by-one
      during execution.

    将 TSV 样本表解析为类型化的 ``ABISampleContext``。
    """
    # Resolve sample sheet path relative to project root / 相对于项目根目录解析样本表路径
    sample_sheet = _resolve_path(path, base_dirs=[PROJECT_ROOT])
    if not sample_sheet.exists():
        if check_files:
            raise ValueError(f"Sample sheet does not exist: {sample_sheet}")
        return _offline_sample_context()
    rows = _parse_sample_sheet_tabular(
        sample_sheet,
        check_files=check_files,
        base_dirs=[PROJECT_ROOT],
    )
    samples = [
        ABISample(
            sample_id=str(row["sample_id"]),
            platform=str(row.get("platform") or "illumina"),
            group=row.get("group") or row.get("condition"),
            read1=str(row["read1"]),
            read2=str(row["read2"]),
            condition=row.get("condition"),
        )
        for row in rows
    ]
    # Derive context flags from the parsed data / 从解析数据中导出上下文标志
    groups = {sample.group for sample in samples if sample.group}
    return ABISampleContext(
        samples=samples,
        multi_sample=len(samples) > 1,
        has_groups=len(groups) >= 2,
        enable_sample_analysis=len(samples) > 1,
        enable_differential_abundance=len(groups) >= 2,
    )


# ── Config path resolution / 配置路径解析 ──────────────────────────────


def _resolve_config_paths(config: Dict[str, Any]) -> None:
    """Resolve relative paths in the config dict in-place.

    Currently only resolves ``input.sample_sheet`` against ``PROJECT_ROOT``.
    Called during ``load_config`` so all downstream code sees absolute paths.

    就地解析配置字典中的相对路径。目前仅将 ``input.sample_sheet`` 相对于
    ``PROJECT_ROOT`` 解析。在 ``load_config`` 中调用，确保下游代码看到绝对路径。
    """
    input_config = config.get("input", {})
    if not isinstance(input_config, dict):
        return
    sample_sheet = input_config.get("sample_sheet")
    if sample_sheet:
        input_config["sample_sheet"] = str(_resolve_path(sample_sheet, base_dirs=[PROJECT_ROOT]))


# (``_clean``, ``_resolve_path`` are imported from abi._shared)


# ── featureCounts parser / featureCounts 解析器 ──────────────────────────
