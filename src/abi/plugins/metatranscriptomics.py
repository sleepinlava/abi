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

   fastp ──→ STAR / HISAT2 ──→ featureCounts
   (QC)       (alignment)      (quantification)

The aligner is configurable via ``config.alignment.tool`` (default: ``star``).

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

import csv
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional

from abi._shared import _clean, _parse_fastp, _parse_star, _resolve_path
from abi.config import PLUGIN_ROOT, PROJECT_ROOT, compact_overrides, deep_merge, load_yaml
from abi.report import write_plugin_report
from abi.schemas import ABIExecutionPlan, ABIPlanStep, ABISample, ABISampleContext
from abi.timeouts import mapping_block
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
        outdir = Path(str(config["outdir"]))
        threads = int(config["threads"])
        # Allow the user to choose STAR or HISAT2 / 允许用户选择 STAR 或 HISAT2
        aligner = str(mapping_block(config, "alignment").get("tool", "star"))
        resources = config.get("resources", {})
        if not isinstance(resources, Mapping):
            resources = {}
        # Sentinels so plan generation succeeds even without real indices
        # 哨兵值保证即使没有真实索引也能生成计划
        genome_index = str(resources.get("genome_index", "GENOME_INDEX_NOT_CONFIGURED"))
        annotation_gtf = str(resources.get("annotation_gtf", "ANNOTATION_GTF_NOT_CONFIGURED"))
        steps: List[ABIPlanStep] = []

        for sample in context.samples:
            # ── Step 1: QC / 第 1 步：质控 ──
            sample_out_qc = outdir / "01_qc" / sample.sample_id
            clean_read1 = sample_out_qc / f"{sample.sample_id}_R1.clean.fastq.gz"
            clean_read2 = sample_out_qc / f"{sample.sample_id}_R2.clean.fastq.gz"
            steps.append(
                ABIPlanStep(
                    step_id=f"{sample.sample_id}_qc_fastp",
                    sample_id=sample.sample_id,
                    step_name="read_qc",
                    tool_id="fastp",
                    category="qc",
                    inputs={"read1": sample.read1, "read2": sample.read2},
                    outputs={
                        "output_dir": str(sample_out_qc),
                        "clean_read1": str(clean_read1),
                        "clean_read2": str(clean_read2),
                    },
                    params={
                        "sample_id": sample.sample_id,
                        "threads": threads,
                        "mode": config["mode"],
                    },
                )
            )

            # ── Step 2: Alignment / 第 2 步：比对 ──
            align_out = outdir / "02_alignment" / sample.sample_id
            bam = align_out / f"{sample.sample_id}.Aligned.sortedByCoord.out.bam"
            steps.append(
                ABIPlanStep(
                    step_id=f"{sample.sample_id}_alignment_{aligner}",
                    sample_id=sample.sample_id,
                    step_name="alignment",
                    tool_id=aligner,
                    category="alignment",
                    inputs={"read1": str(clean_read1), "read2": str(clean_read2)},
                    outputs={"output_dir": str(align_out), "bam": str(bam)},
                    params={
                        "sample_id": sample.sample_id,
                        "threads": threads,
                        "mode": config["mode"],
                        "genome_index": genome_index,
                        "output_prefix": str(align_out / f"{sample.sample_id}."),
                    },
                )
            )

            # ── Step 3: Quantification / 第 3 步：定量 ──
            expression_out = outdir / "03_expression" / sample.sample_id
            counts = expression_out / f"{sample.sample_id}.featureCounts.txt"
            steps.append(
                ABIPlanStep(
                    step_id=f"{sample.sample_id}_expression_featurecounts",
                    sample_id=sample.sample_id,
                    step_name="gene_quantification",
                    tool_id="featurecounts",
                    category="expression",
                    inputs={"bam": str(bam), "annotation_gtf": annotation_gtf},
                    outputs={"output_dir": str(expression_out), "counts": str(counts)},
                    params={
                        "sample_id": sample.sample_id,
                        "threads": threads,
                        "mode": config["mode"],
                    },
                )
            )

        # Track which tools were selected so the agent knows what to register /
        # 跟踪选中的工具，agent 据此注册所需工具
        selected_tools = sorted({step.tool_id for step in steps if step.tool_id != "internal"})
        return ABIExecutionPlan(
            project_name=str(config["project_name"]),
            analysis_type=self.plugin_id,
            mode=str(config["mode"]),
            threads=threads,
            outdir=str(outdir),
            log_dir=str(config["log_dir"]),
            samples=context.samples,
            sample_context=context,
            selected_tools=selected_tools,
            steps=steps,
            provenance_dir=str(outdir / "provenance"),
        )

    # ── Tool registry / 工具注册表 ───────────────────────────────────────

    def registry(self) -> ToolRegistry:
        """Return the tool registry loaded from ``tool_registry.yaml``.

        Contains command templates and container images for fastp, STAR,
        HISAT2, and featureCounts.

        返回从 ``tool_registry.yaml`` 加载的工具注册表，包含 fastp、STAR、
        HISAT2 和 featureCounts 的命令模板及容器镜像。
        """
        return ToolRegistry.from_path(self.root / "tool_registry.yaml")

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
        if tool_id == "fastp":
            return {"qc_summary": _parse_fastp(Path(output_dir), sample_id)}
        if tool_id in ("star", "hisat2"):
            return {"alignment_summary": _parse_star(Path(output_dir), sample_id)}
        if tool_id == "featurecounts":
            return {"gene_expression": _parse_featurecounts(Path(output_dir), sample_id)}
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
    if check_files and not sample_sheet.exists():
        raise ValueError(f"Sample sheet does not exist: {sample_sheet}")
    with sample_sheet.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if reader.fieldnames is None:
            raise ValueError(f"Sample sheet is empty: {sample_sheet}")
        columns = set(reader.fieldnames)
        required = {"sample_id", "read1", "read2"}
        missing = required - columns
        if missing:
            raise ValueError(f"Sample sheet missing required columns: {sorted(missing)}")
        samples = []
        # start=2 so error messages reference the correct spreadsheet row
        # start=2 使错误信息引用正确的电子表格行号
        for index, row in enumerate(reader, start=2):
            sample_id = _clean(row.get("sample_id"))
            read1 = _clean(row.get("read1"))
            read2 = _clean(row.get("read2"))
            if not sample_id or not read1 or not read2:
                raise ValueError(f"Row {index}: sample_id, read1, and read2 are required")
            # Resolve READ paths relative to the sample-sheet directory first, then PROJECT_ROOT /
            # 先相对于样本表目录解析 READ 路径，再相对于 PROJECT_ROOT
            read1 = str(_resolve_path(read1, base_dirs=[sample_sheet.parent, PROJECT_ROOT]))
            read2 = str(_resolve_path(read2, base_dirs=[sample_sheet.parent, PROJECT_ROOT]))
            samples.append(
                ABISample(
                    sample_id=sample_id,
                    # Default platform to "rna_seq" when not specified / 未指定时默认为 "rna_seq"
                    platform=_clean(row.get("platform")) or "rna_seq",
                    # group falls back to condition for DE-tool compatibility
                    # group 回退到 condition 以兼容差异表达工具
                    group=_clean(row.get("group")) or _clean(row.get("condition")),
                    read1=read1,
                    read2=read2,
                    condition=_clean(row.get("condition")),
                )
            )
    if not samples:
        raise ValueError("Sample sheet contains no sample rows")
    # Upfront file-existence check: fail with all missing paths at once
    # 预先检查文件存在性：一次性报告所有缺失的路径
    if check_files:
        missing_files = []
        for sample in samples:
            for field in ("read1", "read2"):
                value = getattr(sample, field)
                if value and not Path(str(value)).exists():
                    missing_files.append(f"{sample.sample_id}:{field}={value}")
        if missing_files:
            raise ValueError("Input files do not exist: " + "; ".join(missing_files))
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


def _parse_featurecounts(output_dir: Path, sample_id: str) -> List[Dict[str, Any]]:
    """Parse all featureCounts output files in ``output_dir``.

    featureCounts files have comment lines starting with ``#`` which are
    stripped before CSV parsing.  The last column (index ``-1``) holds the
    count value because featureCounts appends a per-sample count column to
    the right of the gene-annotation columns.

    featureCounts 文件中以 ``#`` 开头的注释行在 CSV 解析前被剥离。
    最后一列（索引 ``-1``）存放计数值，因为 featureCounts 会在基因注释列
    右侧追加每个样本的计数列。
    """
    rows: List[Dict[str, Any]] = []
    for path in sorted(output_dir.glob("*featureCounts*.txt")):
        with path.open("r", encoding="utf-8", newline="") as handle:
            # Skip comment lines (featureCounts header metadata)
            # 跳过注释行（featureCounts 头部元数据）
            reader = csv.DictReader(
                (line for line in handle if not line.startswith("#")),
                delimiter="\t",
            )
            if not reader.fieldnames:
                continue
            # The last column is the per-sample count / 最后一列是每个样本的计数值
            count_field = reader.fieldnames[-1]
            for row in reader:
                gene_id = row.get("Geneid")
                if not gene_id:
                    continue
                rows.append(
                    {
                        "sample_id": sample_id,
                        "gene_id": gene_id,
                        "count": row.get(count_field, ""),
                        "tpm": "",  # TPM not computed by featureCounts alone
                        # TPM 不由 featureCounts 单独计算
                        "tool": "featurecounts",
                        "source_file": str(path),
                    }
                )
    return rows
