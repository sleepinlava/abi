"""Canonical runtime schemas for ABI plugins -- the single source of truth.

This module is the CANONICAL home for all ABI data types. Every plugin, agent, and
core subsystem imports its schemas from here so that the entire ecosystem shares a
single type definition. There is no secondary or "convenience" copy of these types;
this avoids drift and keeps validation logic centralized.

Design principles / 设计原则
---------------------------
1. **Single source of truth** -- all dataclasses live in this one file. If a field
   is added or renamed, every consumer picks it up immediately.
   **单一数据源** -- 所有数据类都在此文件中定义，修改立即对全部消费者生效。

2. **Two naming conventions** -- the original ``SampleInput`` / ``SampleContext`` /
   ``PlanStep`` / ``ExecutionPlan`` names are the canonical types used internally.
   The ``ABI*``-prefixed aliases (``ABISample``, ``ABISampleContext``,
   ``ABIPlanStep``, ``ABIExecutionPlan``) are the STABLE PUBLIC API that plugins
   and external agents should depend on. We keep both so that existing autoplasm
   code (which imports the short names) does not break.
   **两套命名规范** -- 原始短名是内部规范类型，ABI 前缀别名是对外稳定 API。

3. **Validation constants** -- ``VALID_PLATFORMS``, ``VALID_MODES``, and
   ``VALID_PLASMID_STRATEGIES`` are frozen sets used by the config parser and
   plan builder to reject unknown values at the boundary. They are not
   configuration; they are part of the schema contract.
   **校验常量** -- 这些冻结集合在配置解析和计划构建时用于边界值校验。

4. **Serialization** -- every dataclass exposes ``to_dict()`` so that plans and
   samples can be round-tripped through JSON for agent context, dry-run
   comparison, and provenance tracking.
   **序列化** -- 所有数据类都提供 ``to_dict()`` 方法，支持 JSON 往返传递。
"""

from __future__ import annotations

from dataclasses import asdict, field
from typing import Any, Dict, List, Optional

from pydantic import Field, field_validator, model_validator
from pydantic.dataclasses import dataclass

from abi.errors import ABIError, ConfigError, SampleSheetError, ToolError
from abi.filesystem import ensure_parent

__all__ = [
    "ABIError",
    "ABIExecutionPlan",
    "ABIPlanStep",
    "ABISample",
    "ABISampleContext",
    "ConfigError",
    "ExecutionPlan",
    "PlanStep",
    "SampleContext",
    "SampleInput",
    "SampleSheetError",
    "ToolError",
    "VALID_MODES",
    "VALID_PLATFORMS",
    "VALID_PLASMID_STRATEGIES",
    "ensure_parent",
]

# ── Validation sets / 校验集合 ──────────────────────────────────────────
# These frozen sets form the schema contract: any value outside them is
# rejected at parse/validation time, not deep in pipeline execution.
# 这些冻结集合构成了 schema 契约：任何不在其中的值都会在解析/校验阶段被拒绝，
# 而不会等到流水线深层执行时才暴露。

VALID_PLATFORMS: frozenset[str] = frozenset(
    {
        "generic",
        "illumina",
        "ont",
        "pacbio_hifi",
        "hybrid",
        "assembly",
    }
)
# Supported sequencing / assembly platforms. Used by SampleSheet parser to
# validate the ``platform`` column and by the plan builder to select
# platform-appropriate tools.
# 支持的测序/组装平台。用于 SampleSheet 解析器校验 platform 列，
# 以及计划构建器选择与平台匹配的工具。

VALID_MODES: frozenset[str] = frozenset({"auto", "interactive"})
# Pipeline execution modes.
# ``auto`` -- fully unattended execution (CI / headless deployments).
# ``interactive`` -- the agent may pause for human confirmation at key
# decision points (dev / exploratory workflows).
# 流水线执行模式。
# auto -- 全自动无人值守执行（CI / 无头部署）。
# interactive -- 智能体在关键决策点可能暂停等待人工确认（开发 / 探索性工作流）。

VALID_PLASMID_STRATEGIES: frozenset[str] = frozenset(
    {
        "single_tool",
        "union",
        "intersection",
        "majority_vote",
        "weighted_vote",
    }
)
# Plasmid-calling consensus strategies. The plan builder chooses tool
# combinations based on the selected strategy.
# ``single_tool``  -- run one tool only.
# ``union``        -- combine all detected plasmids (maximise sensitivity).
# ``intersection`` -- keep only plasmids reported by every tool (maximise precision).
# ``majority_vote`` -- keep plasmids reported by > 50 % of tools.
# ``weighted_vote`` -- use per-tool confidence scores as votes.
# 质粒检出共识策略。计划构建器根据所选策略选择工具组合。
# single_tool  -- 仅运行单一工具。
# union        -- 取所有检出质粒的并集（最大化灵敏度）。
# intersection -- 仅保留所有工具都检出的质粒（最大化精确度）。
# majority_vote -- 保留超过半数工具检出的质粒。
# weighted_vote -- 使用每个工具的置信度评分作为加权投票。


@dataclass
class SampleInput:
    """Canonical sample descriptor -- unified superset of autoplasm and ABI fields.

    This is the single sample model used everywhere: in the plan builder, in
    agent context, in provenance tracking, and in report generation. It is
    deliberately a superset so that plugins can populate only the fields they
    understand while the ABI core handles the rest.

    **Data flow / 数据流:**
    SampleSheet (CSV) → parse → ``SampleInput`` → validate platform / reads →
    ``SampleContext`` → ``ExecutionPlan`` → tool dispatch.

    ``attributes`` is an extension escape-hatch: plugins may store arbitrary
    key-value pairs there without modifying the schema. Use sparingly;
    prefer typed fields when a property becomes widely used.
    ``attributes`` 是扩展出口：插件可在此存储任意键值对而无需修改 schema。
    慎用；当某个属性被广泛使用时，应优先提升为类型化字段。
    """

    model_config = {"extra": "allow"}

    # ── Identity / 标识 ──
    sample_id: str = Field(..., min_length=1)
    # Unique sample identifier. Maps to the ``sample_id`` column in the
    # SampleSheet and is the primary key throughout the pipeline.
    # 样品唯一标识符。对应 SampleSheet 中的 sample_id 列，是流水线中的主键。

    # ── Sequencing / 测序信息 ──
    platform: str = Field(default="generic")
    # Sequencing platform. Must be one of ``VALID_PLATFORMS``.
    # Determines which tools are eligible and how reads are paired.
    # 测序平台。必须是 VALID_PLATFORMS 之一。决定哪些工具有效以及 reads 如何配对。

    read1: Optional[str] = None
    # Path to paired-end read 1 FASTQ. Required for Illumina short-read analysis.
    # 双端测序 read 1 FASTQ 文件路径。Illumina 短读分析必需。

    read2: Optional[str] = None
    # Path to paired-end read 2 FASTQ. Only meaningful when ``read1`` is set.
    # 双端测序 read 2 FASTQ 文件路径。仅当 read1 设置时有意义。

    long_reads: Optional[str] = None
    # Path to long-read FASTQ (ONT / PacBio). Mutually independent of short reads.
    # 长读长 FASTQ 文件路径（ONT/PacBio）。与短读独立。

    pod5: Optional[str] = None
    # Path to an ONT POD5 file or directory requiring basecalling.

    bam: Optional[str] = None
    # Path to an ONT/PacBio BAM that must be converted to FASTQ for read workflows.

    assembly: Optional[str] = None
    # Path to a pre-computed assembly FASTA. Bypasses read-based tools.
    # 预组装 FASTA 文件路径。可跳过基于 reads 的工具直接分析。

    # ── Metadata / 元数据 ──
    group: Optional[str] = None
    # Experimental group label for differential-abundance comparisons.
    # 实验分组标签，用于差异丰度比较分析。

    technology: Optional[str] = None
    # Free-form technology descriptor (e.g. "metagenomics", "isolate").
    # 自由格式的技术描述符（如 "metagenomics"、"isolate"）。

    host_reference: Optional[str] = None
    # Path to a host reference genome for read decontamination / subtraction.
    # 宿主参考基因组路径，用于 reads 去宿主/去污染。

    condition: Optional[str] = None
    # Experimental condition label (e.g. "treated", "control").
    # 实验条件标签（如 "treated"、"control"）。

    notes: Optional[str] = None
    # Free-form notes column from the SampleSheet.
    # SampleSheet 中的自由格式备注列。

    # ── Extension / 扩展 ──
    attributes: Dict[str, Any] = field(default_factory=dict)
    # Extension dictionary for plugin-specific metadata not yet promoted to
    # typed fields. Do NOT use for data that affects pipeline execution
    # decisions -- promote those to first-class fields instead.
    # 扩展字典，用于尚未提升为类型化字段的插件特定元数据。
    # 不要将影响流水线执行决策的数据放在这里 -- 应提升为一级字段。

    @field_validator("platform")
    @classmethod
    def validate_platform(cls, v: str) -> str:
        """Reject unknown platform values at construction time.

        Validated against ``VALID_PLATFORMS`` so that downstream tools never
        encounter an unrecognized platform string.
        """
        if v not in VALID_PLATFORMS:
            raise ValueError(f"Invalid platform {v!r}. Must be one of {sorted(VALID_PLATFORMS)}")
        return v

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a JSON-round-trip-safe dictionary.

        Serialization contract / 序列化契约:
        Every schema type in this module supports ``to_dict()`` so that the
        full execution plan can be serialized for agent context sharing,
        provenance tracking, and dry-run diffing.
        本模块中每个 schema 类型都支持 to_dict()，以便完整的执行计划可以被
        序列化，用于智能体上下文共享、溯源追踪和 dry-run 差异比较。
        """
        return asdict(self)

    # ── Derived type indicators / 派生类型指示器 ──
    # These properties let the plan builder and tools quickly answer "what kind
    # of data do we have?" without inspecting individual fields.
    # 这些属性让计划构建器和工具可以快速判断"我们拥有什么类型的数据"，
    # 而无需逐一检查字段。

    @property
    def has_short_reads(self) -> bool:
        """True when at least one of ``read1`` or ``read2`` is set."""
        return bool(self.read1 or self.read2)

    @property
    def has_long_reads(self) -> bool:
        """True when ``long_reads`` is set (ONT / PacBio)."""
        return bool(self.long_reads or self.pod5 or self.bam)

    @property
    def has_assembly(self) -> bool:
        """True when a pre-computed ``assembly`` is provided."""
        return bool(self.assembly)


@dataclass
class SampleContext:
    """Aggregate metadata about the sample collection as a whole.

    Whereas ``SampleInput`` describes a single sample, ``SampleContext``
    captures the *collection-level* state that the plan builder needs:
    are we in single-sample or multi-sample mode? Do groups exist for
    differential-abundance analysis? Should per-sample analysis be enabled?

    **Why a separate type? / 为何需要单独的类型？**
    The plan builder needs collection-level information (e.g. "is this
    multi-sample?") *before* it can build steps. Embedding this in
    ``ExecutionPlan`` makes the builder's decisions inspectable; putting
    it in a dedicated ``SampleContext`` keeps it testable in isolation.
    计划构建器需要在构建步骤*之前*知道集合级信息（如"这是多样本吗？"）。
    将其嵌入 ExecutionPlan 使构建器决策可检查；放入专用的 SampleContext 则
    使其可以独立测试。
    """

    model_config = {"extra": "allow"}

    # ── Collection / 样本集合 ──
    samples: List[SampleInput]
    # The full list of samples in this run. Must be non-empty.
    # 本次运行中的完整样本列表。必须非空。

    # ── Derived flags / 派生标志 ──
    multi_sample: bool
    # True when ``len(samples) > 1``. Gates multi-sample aggregation steps
    # like combined reports and cross-sample statistics.
    # 当样本数大于 1 时为 True。控制多样本聚合步骤（合并报告、跨样本统计等）。

    has_groups: bool
    # True when at least two distinct ``group`` values are present across
    # samples. Enables differential-abundance tool selection.
    # 当样本间至少存在两个不同的 group 值时为 True。启用差异丰度工具选择。

    # ── Analysis toggles / 分析开关 ──
    enable_sample_analysis: bool = False
    # If True, generate per-sample detailed analysis reports. Expensive for
    # large cohorts; defaults to False.
    # 若为 True，为每个样本生成详细分析报告。大队列时开销大，默认为 False。

    enable_differential_abundance: bool = False
    # If True (requires ``has_groups``), run statistical tests comparing
    # plasmid abundance across groups. Overridden to False when ``has_groups``
    # is False.
    # 若为 True（需要 has_groups），运行跨组质粒丰度统计检验。
    # 当 has_groups 为 False 时强制为 False。

    @model_validator(mode="after")
    def validate_consistency(self) -> SampleContext:
        """Ensure sample collection invariants hold.

        - ``samples`` must be non-empty.
        - ``multi_sample`` must be consistent with ``len(samples)``.
        - ``has_groups`` must be consistent with distinct sample group values.
        - ``enable_differential_abundance`` is forced to False when groups
          are absent.
        """
        if not self.samples:
            raise ValueError("SampleContext.samples must be non-empty")

        # Auto-correct multi_sample to match reality.
        expected_multi = len(self.samples) > 1
        if self.multi_sample != expected_multi:
            object.__setattr__(self, "multi_sample", expected_multi)

        # Auto-correct has_groups to match reality.
        distinct_groups = {s.group for s in self.samples if s.group is not None}
        expected_has_groups = len(distinct_groups) >= 2
        if self.has_groups != expected_has_groups:
            object.__setattr__(self, "has_groups", expected_has_groups)

        # Force enable_differential_abundance to False when no groups exist.
        if not self.has_groups and self.enable_differential_abundance:
            object.__setattr__(self, "enable_differential_abundance", False)

        return self

    def to_dict(self) -> Dict[str, Any]:
        """Serialize sample context for JSON round-tripping."""
        return {
            "samples": [sample.to_dict() for sample in self.samples],
            "multi_sample": self.multi_sample,
            "has_groups": self.has_groups,
            "enable_sample_analysis": self.enable_sample_analysis,
            "enable_differential_abundance": self.enable_differential_abundance,
        }


@dataclass
class PlanStep:
    """A single unit of work in the execution plan.

    Each ``PlanStep`` represents one tool invocation for one sample (or for
    the whole project when ``sample_id`` is ``None``). Steps are ordered;
    later steps may depend on the outputs of earlier steps. The plan builder
    creates these, the executor runs them in sequence, and the provenance
    system records them.
    每个 PlanStep 代表对一样本（或当 sample_id 为 None 时对整个项目）的一次
    工具调用。步骤有序；后续步骤可能依赖前面步骤的输出。计划构建器创建步骤，
    执行器按序运行，溯源系统记录它们。

    **Design note / 设计说明:**
    ``inputs`` and ``outputs`` are dictionaries, not typed structs. This is
    deliberate: tool I/O schemas vary widely and evolve independently.
    Validation is done at the tool boundary, not in the plan model.
    inputs 和 outputs 是字典而非类型化结构体。这是有意为之：工具的 I/O schema
    差异很大且独立演化。校验在工具边界进行，而非在计划模型中。
    """

    model_config = {"extra": "allow"}

    # ── Identity / 标识 ──
    step_id: str = Field(..., min_length=1)
    # Unique step identifier within the plan (e.g. "step_001").
    # 计划内唯一的步骤标识符（如 "step_001"）。

    step_name: str = Field(..., min_length=1)
    # Human-readable step name for logs and reports (e.g. "Quality Control").
    # 人类可读的步骤名称，用于日志和报告（如 "Quality Control"）。

    # ── Tool binding / 工具绑定 ──
    tool_id: str = Field(..., min_length=1)
    # ID of the registered tool that will execute this step.
    # Must exist in ``ToolRegistry`` at execution time.
    # 注册工具的 ID，将执行此步骤。执行时必须在 ToolRegistry 中存在。

    category: str = Field(..., min_length=1)
    # Logical category for grouping steps in the plan (e.g. "qc", "assembly",
    # "plasmid_calling", "reporting"). Used by the dashboard and reports.
    # 步骤分组的逻辑类别（如 "qc"、"assembly"、"plasmid_calling"、"reporting"）。
    # 用于仪表盘和报告。

    # ── Scope / 作用域 ──
    sample_id: Optional[str] = None
    # Sample this step operates on. ``None`` means "project-level" (e.g.
    # a combined report or aggregation step).
    # 此步骤操作的样本。None 表示"项目级"（如合并报告或聚合步骤）。

    # ── I/O contract / 输入输出契约 ──
    inputs: Dict[str, Any] = field(default_factory=dict)
    # Files, directories, and parameters this step consumes.
    # Populated by the plan builder; validated by the tool before execution.
    # 此步骤消费的文件、目录和参数。由计划构建器填充，执行前由工具校验。

    outputs: Dict[str, Any] = field(default_factory=dict)
    # Files and directories this step produces. Populated after execution.
    # Downstream steps reference these by key in their own ``inputs``.
    # 此步骤产生的文件和目录。执行后填充。
    # 下游步骤通过键名在自己的 inputs 中引用这些输出。

    params: Dict[str, Any] = field(default_factory=dict)
    # Extra tool parameters (e.g. ``--min-length``, ``--threads``).
    # 额外的工具参数（如 --min-length、--threads）。

    # ── Metadata / 元数据 ──
    reason: Optional[str] = None
    # Why this step was included. Written by the plan builder so that agents
    # and users can inspect plan rationale.
    # 为何包含此步骤。由计划构建器写入，方便智能体和用户检查计划理由。

    skipped: bool = False
    # When True, the executor will skip this step but still record it in
    # provenance. Used when a step's preconditions are not met (e.g. a tool
    # that requires short reads but the sample has only long reads).
    # 为 True 时，执行器跳过此步骤但仍会在溯源中记录。用于步骤前置条件不满足
    # 的情况（如工具需要短读但样本仅有长读）。

    def to_dict(self) -> Dict[str, Any]:
        """Serialize plan step for JSON round-tripping."""
        return asdict(self)


@dataclass
class ExecutionPlan:
    """Top-level container for the complete analysis plan.

    ``ExecutionPlan`` is the primary data structure that flows between the
    plan builder, the executor, the provenance system, and the reports. It
    is deliberately self-contained: serializing an ``ExecutionPlan`` to JSON
    captures everything needed to reproduce or audit a run.
    ExecutionPlan 是计划构建器、执行器、溯源系统和报告之间的主要数据结构。
    它被设计为自包含的：将一个 ExecutionPlan 序列化为 JSON 即可捕获复现
    或审计一次运行所需的全部信息。

    **Data flow / 数据流:**
    1. Plugin.``build_plan()`` creates the plan.
    2. Agent / CLI may inspect or modify it.
    3. ``abi_run`` iterates ``steps`` and dispatches each to the tool executor.
    4. After execution, the plan + outputs form the provenance bundle.
    1. Plugin.build_plan() 创建计划。
    2. 智能体/CLI 可能检查或修改计划。
    3. abi_run 迭代 steps 并将每个步骤分派到工具执行器。
    4. 执行后，计划 + 输出构成溯源包。
    """

    model_config = {"extra": "allow"}

    # ── Project identity / 项目标识 ──
    project_name: str
    # Human-readable project name. Used in report titles and log prefixes.
    # 人类可读的项目名称。用于报告标题和日志前缀。

    # ── Execution parameters / 执行参数 ──
    mode: str
    # Execution mode. Must be one of ``VALID_MODES``: "auto" or "interactive".
    # 执行模式。必须是 VALID_MODES 之一："auto" 或 "interactive"。

    threads: int
    # Number of CPU threads allocated for parallel tool execution.
    # 分配给并行工具执行的 CPU 线程数。

    outdir: str
    # Root output directory. All tool outputs are placed under here.
    # 根输出目录。所有工具输出都放在此目录下。

    log_dir: str
    # Directory for per-step log files. Usually ``<outdir>/logs``.
    # 每个步骤的日志文件目录。通常为 <outdir>/logs。

    # ── Data references / 数据引用 ──
    samples: List[SampleInput]
    # All samples in the project. The executor iterates this list for
    # per-sample tool dispatch.
    # 项目中的所有样本。执行器遍历此列表进行逐样本工具分派。

    # ── Plan structure / 计划结构 ──
    steps: List[PlanStep]
    # Ordered list of steps to execute. Step ordering matters: downstream
    # steps may reference outputs of earlier steps.
    # 有序的执行步骤列表。步骤顺序很重要：下游步骤可能引用前面步骤的输出。

    selected_tools: List[str]
    # Tool IDs that the plan builder selected for this run. Used by the
    # dashboard to show which tools are active and by the provenance system
    # to record tool versions.
    # 计划构建器为本次运行选择的工具 ID 列表。用于仪表盘显示活跃工具和
    # 溯源系统记录工具版本。

    # ── Context / 上下文 ──
    sample_context: SampleContext
    # Aggregate sample collection metadata (see ``SampleContext`` docs).
    # 样本集合的聚合元数据（见 SampleContext 文档）。

    # ── Fields with defaults / 带默认值的字段 ──
    # These must be declared AFTER all required fields (dataclass rule).
    # 这些字段必须在所有必填字段之后声明（数据类规则）。

    analysis_type: str = Field(default="metagenomic_plasmid", min_length=1)
    # Analysis workflow type. Future extension point for non-plasmid workflows
    # (e.g. "amr", "viral"). Currently always "metagenomic_plasmid".
    # 分析工作流类型。为非质粒工作流（如 "amr"、"viral"）预留的扩展点。
    # 目前始终为 "metagenomic_plasmid"。

    plasmid_strategy: str = Field(default="single_tool", min_length=1)
    # Consensus strategy for plasmid detection: "single_tool", "union",
    # "intersection", "majority_vote", or "weighted_vote". Used by the report
    # phase for consensus table generation.
    # 质粒检测共识策略："single_tool"、"union"、"intersection"、"majority_vote"
    # 或 "weighted_vote"。由报告阶段用于共识表生成。

    skipped_steps: List[PlanStep] = field(default_factory=list)
    # Steps that were planned but marked ``skipped=True``. Stored separately
    # so the executor does not run them, but they remain in the provenance
    # record for auditability.
    # 已计划但被标记为 skipped=True 的步骤。单独存储以便执行器不运行它们，
    # 但它们仍保留在溯源记录中以供审计。

    provenance_dir: Optional[str] = None
    # Directory for storing provenance artifacts (plan snapshots, tool
    # versions, output checksums). If None, the executor uses
    # ``<outdir>/provenance``.
    # 存储溯源制品（计划快照、工具版本、输出校验和）的目录。
    # 若为 None，执行器使用 ``<outdir>/provenance``。

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the full execution plan for JSON round-tripping."""
        return {
            "project_name": self.project_name,
            "analysis_type": self.analysis_type,
            "mode": self.mode,
            "threads": self.threads,
            "outdir": self.outdir,
            "log_dir": self.log_dir,
            "samples": [sample.to_dict() for sample in self.samples],
            "sample_context": self.sample_context.to_dict(),
            "selected_tools": self.selected_tools,
            "steps": [step.to_dict() for step in self.steps],
            "skipped_steps": [step.to_dict() for step in self.skipped_steps],
            "provenance_dir": self.provenance_dir,
            "plasmid_strategy": self.plasmid_strategy,
        }


# ── Stable ABI-prefixed aliases / ABI 前缀稳定别名 ──────────────────────
# These are the PUBLIC API names. External code (plugins, agents, CLI) should
# import and reference the ``ABI*`` names. The short names (SampleInput, etc.)
# are kept for backward compatibility with autoplasm-era code. Over time,
# internal code should migrate to the ``ABI*`` names as well.
# 这些是对外 API 名称。外部代码（插件、智能体、CLI）应导入和使用 ABI* 名称。
# 短名称（SampleInput 等）保留以向后兼容 autoplasm 时代的代码。
# 随着时间的推移，内部代码也应迁移到 ABI* 名称。

ABISample = SampleInput
ABISampleContext = SampleContext
ABIPlanStep = PlanStep
ABIExecutionPlan = ExecutionPlan
