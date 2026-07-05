"""Universal DAG planner — generates ExecutionPlan from pipeline_dag.yaml.

This module provides a plugin-agnostic planner that reads a ``pipeline_dag.yaml``
specification and produces an ``ExecutionPlan``, replacing the hand-written
``build_plan()`` methods that currently duplicate ~700 lines of boilerplate
across 4 inline plugins.

Design
~~~~~~
- **UniversalDAG**: loads + queries a ``pipeline_dag.yaml`` from any plugin.
- **build_plan_from_dag()**: the single entry point that plugins call.
- **PathTemplateContext**: a dict subclass that resolves ``{variable}``
  references in output path templates, using the same ``str.format_map()``
  mechanism as ``GenericCommandSkill`` for command templates.

Schema extensions (beyond the existing plasmid DAG format)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- ``category_dirs``: top-level mapping from category → subdirectory name.
- ``scope``: ``"per_sample"`` (default) or ``"cross_sample"`` per node.
- ``outputs.<key>.path``: template string for output file/directory paths.
- ``inputs.<key>.aggregate``: ``"per_sample_outputs"`` for cross-sample nodes.

Usage::

    from abi.dag_planner import UniversalDAG, build_plan_from_dag
    plan = build_plan_from_dag(
        plugin.root / "pipeline_dag.yaml", config, sample_context
    )
"""

from __future__ import annotations

import csv
import logging
from collections import deque
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, TypedDict

import yaml

from abi.schemas import VALID_PLATFORMS, ExecutionPlan, PlanStep, SampleContext, SampleInput

_logger = logging.getLogger("abi.dag_planner")

__all__ = [
    "PathTemplateContext",
    "PluginContextResolver",
    "UniversalDAG",
    "build_plan_from_dag",
    "build_sample_context",
    "detect_platform",
]


# ── PathTemplateContext ──────────────────────────────────────────────────
# A dict subclass that resolves {variable} references in output path
# templates.  Pre-flattens nested access (sample.platform, resources.key)
# into simple keys so that str.format_map() works without dotted lookups.
# / 用于解析输出路径模板中 {variable} 引用的字典子类。


class PathTemplateContext(dict):
    """Dict-like context for resolving ``{variable}`` path templates.

    Unlike ``SafeFormatDict`` (which returns ``""`` for missing keys), this
    context is pre-populated with all known variables.  Missing keys indicate
    a template bug and raise ``KeyError``.

    Usage::

        ctx = PathTemplateContext(
            config=config,
            sample=sample,
            category_dir="01_qc",
            upstream_outputs={"qc_fastp": {"clean_read1": "/path/to/R1.fq.gz"}},
        )
        resolved = template.format_map(ctx)
    """

    def __init__(
        self,
        *,
        config: Mapping[str, Any],
        sample: SampleInput | None = None,
        category_dir: str = "",
        upstream_outputs: Mapping[str, Mapping[str, Any]] | None = None,
    ) -> None:
        super().__init__()
        outdir = str(config.get("outdir", "."))
        self["outdir"] = outdir
        self["category_dir"] = category_dir

        # Per-sample variables / 每个样本的变量
        if sample is not None:
            self["sample_id"] = sample.sample_id
            self["sample.platform"] = sample.platform
            for attr in (
                "platform",
                "read1",
                "read2",
                "long_reads",
                "pod5",
                "bam",
                "assembly",
                "group",
                "condition",
                "technology",
                "host_reference",
                "notes",
            ):
                val = getattr(sample, attr, None)
                if val:
                    self[f"sample.{attr}"] = str(val)

        # Config-level variables / 配置级变量
        for key in ("threads", "mode", "project_name"):
            val = config.get(key)
            if val is not None:
                self[str(key)] = str(val)

        # Resources (nested config key) / 资源配置
        resources = config.get("resources")
        if isinstance(resources, Mapping):
            for rkey, rval in resources.items():
                if rval is not None:
                    self[f"resources.{rkey}"] = str(rval)

        # Upstream node outputs / 上游节点输出
        if upstream_outputs:
            for node_id, outputs in upstream_outputs.items():
                for out_key, out_val in outputs.items():
                    if out_val is not None:
                        self[f"upstream_{node_id}.outputs.{out_key}"] = str(out_val)


# ── UniversalDAG ─────────────────────────────────────────────────────────
# In-memory representation of a pipeline_dag.yaml spec.  Plugin-agnostic:
# the YAML path is a parameter, not hardcoded.
# / pipeline_dag.yaml 规范的内存表示。插件无关：YAML 路径是参数而非硬编码。


class UniversalDAG:
    """In-memory representation of a ``pipeline_dag.yaml`` specification.

    Usage::

        dag = UniversalDAG.from_yaml(plugin_root / "pipeline_dag.yaml")
        active = dag.active_node_ids("illumina", config)
        order = dag.topological_order(active)
        for node_id in order:
            scope = dag.scope_for(node_id)
            ...
    """

    def __init__(self, spec: Mapping[str, Any]) -> None:
        self._spec = dict(spec)
        raw_nodes = self._spec.get("nodes")
        if not isinstance(raw_nodes, Mapping):
            raise ValueError("pipeline_dag.yaml must contain a 'nodes' mapping")
        self._nodes: Dict[str, Dict[str, Any]] = {
            str(nid): dict(ndata) for nid, ndata in raw_nodes.items()
        }
        self._platforms: List[str] = [str(p) for p in self._spec.get("platforms", []) if p]
        raw_dirs = self._spec.get("category_dirs")
        self._category_dirs: Dict[str, str] = {}
        if isinstance(raw_dirs, Mapping):
            self._category_dirs = {str(k): str(v) for k, v in raw_dirs.items() if v}
        self.pipeline_id: str = str(self._spec.get("pipeline_id", ""))
        self.pipeline_name: str = str(self._spec.get("pipeline_name", ""))

    # ── Factory ──────────────────────────────────────────────────────────

    @classmethod
    def from_yaml(cls, path: str | Path) -> "UniversalDAG":
        """Load a ``pipeline_dag.yaml`` from disk.

        Args:
            path: Path to the YAML file.

        Returns:
            A new ``UniversalDAG`` instance.

        Raises:
            FileNotFoundError: If the file does not exist.
            ValueError: If the file is not a valid DAG spec.
        """
        yaml_path = Path(path)
        if not yaml_path.exists():
            raise FileNotFoundError(f"Pipeline DAG spec not found: {yaml_path}")
        with yaml_path.open("r", encoding="utf-8") as handle:
            spec = yaml.safe_load(handle) or {}
        if not isinstance(spec, Mapping):
            raise ValueError(f"Pipeline DAG spec must be a YAML mapping: {yaml_path}")
        return cls(spec)

    # ── Properties ───────────────────────────────────────────────────────

    @property
    def platforms(self) -> List[str]:
        """Supported platforms in declaration order."""
        return list(self._platforms)

    @property
    def category_dirs(self) -> Dict[str, str]:
        """Category → subdirectory mapping (e.g. ``{"qc": "01_qc"}``)."""
        return dict(self._category_dirs)

    @property
    def node_ids(self) -> List[str]:
        """Return all declared node IDs in deterministic declaration order."""
        return list(self._nodes)

    def category_dir_for(self, category: str) -> str:
        """Return the subdirectory for a category, or the category itself if unmapped."""
        return self._category_dirs.get(category, category)

    def scope_for(self, node_id: str) -> str:
        """Return the scope of a node: ``"per_sample"`` (default) or ``"cross_sample"``."""
        node = self._nodes.get(node_id, {})
        scope = node.get("scope", "per_sample")
        return str(scope) if scope else "per_sample"

    def is_optional(self, node_id: str) -> bool:
        """Return True if the node is marked optional."""
        node = self._nodes.get(node_id, {})
        return bool(node.get("optional", False))

    def node_category(self, node_id: str) -> str:
        """Return the category of a node."""
        node = self._nodes.get(node_id, {})
        return str(node.get("category", ""))

    # ── Query ────────────────────────────────────────────────────────────

    def active_node_ids(
        self,
        platform: str,
        config: Mapping[str, Any],
    ) -> List[str]:
        """Return node IDs that are active for the given platform and config.

        A node is active when ALL of these hold:
        1. Its ``platforms`` list includes *platform* (or is empty, meaning all).
        2. Its category is not explicitly disabled in config.
        3. If it has an ``enable_condition``, the condition evaluates to True
           against *config*.
        4. If it is ``optional: true`` and has NO ``enable_condition``, it is
           **excluded** by default (opt-in: requires an enable_condition or
           explicit category enable to activate).

        Required nodes without ``enable_condition`` are always active (opt-out:
        the user must explicitly disable their category).

        Args:
            platform: The data platform (e.g. ``"illumina"``).
            config: The fully-resolved pipeline configuration.

        Returns:
            List of active node IDs in declaration order.
        """
        active: List[str] = []
        for node_id, node in self._nodes.items():
            node_platforms = node.get("platforms")
            if node_platforms and platform not in node_platforms:
                continue
            category = self.node_category(node_id)
            if category and not self._category_enabled(config, category, node_id):
                continue

            # enable_condition evaluation / 条件求值
            condition = node.get("enable_condition")
            if isinstance(condition, Mapping):
                if not self._evaluate_condition(condition, config):
                    continue
            elif self.is_optional(node_id) and not self._category_explicitly_enabled(
                config, category
            ):
                # Optional nodes without enable_condition → excluded unless
                # their category is explicitly enabled in config.
                continue

            active.append(node_id)

        workflow = config.get("workflow", {})
        include_nodes = workflow.get("include_nodes") if isinstance(workflow, Mapping) else None
        if include_nodes is not None:
            if not isinstance(include_nodes, list) or not all(
                isinstance(node_id, str) and node_id for node_id in include_nodes
            ):
                raise ValueError("workflow.include_nodes must be a list of non-empty node IDs")
            unknown = sorted(set(include_nodes) - set(self._nodes))
            if unknown:
                raise ValueError(f"workflow.include_nodes references unknown nodes: {unknown}")
            requested = set(include_nodes)
            active = [node_id for node_id in active if node_id in requested]
        return active

    @staticmethod
    def _evaluate_condition(
        condition: Mapping[str, Any],
        config: Mapping[str, Any],
    ) -> bool:
        """Evaluate a node ``enable_condition`` against *config*.

        Supported operators:
        - ``value``: config field must equal the given value.
        - ``not_empty``: config field must be non-None, non-empty.

        The field is a dotted path into the config dict (e.g.
        ``"host_removal.host_reference"``).
        """
        field_path: str = str(condition.get("field", ""))
        operator: str = str(condition.get("operator", "value"))
        expected = condition.get("value")

        # Navigate dotted field path / 点号路径导航
        value: Any = config
        for part in field_path.split("."):
            if isinstance(value, Mapping) and part in value:
                value = value[part]
            else:
                return False

        if operator == "value":
            return value == expected
        if operator == "not_empty":
            if value is None:
                return False
            if isinstance(value, str) and not value.strip():
                return False
            if isinstance(value, (list, dict, set)) and len(value) == 0:
                return False
            return True
        if operator == "list_contains":
            if isinstance(value, list) and expected in value:
                return True
            if isinstance(value, str) and expected == value:
                return True
            return False

        return False

    def resolve_dependencies(
        self, active_ids: Iterable[str], platform: str = ""
    ) -> Dict[str, List[str]]:
        """Resolve effective dependencies for each active node.

        For each active node, its effective dependencies are the subset of
        ``depends_on`` that are also active.  If an optional dependency is
        NOT active, the node's ``fallback_depends`` is tried instead
        (positional match: fallback_depends[i] is the alternative for
        depends_on[i]).

        Args:
            active_ids: The set of active node IDs.
            platform: Platform label (for error messages only).

        Returns:
            ``{node_id: [effective_dependency_ids]}`` mapping.

        Raises:
            ValueError: If a required dependency cannot be resolved.
        """
        active_list = list(active_ids)
        active_set = set(active_list)
        resolved: Dict[str, List[str]] = {}

        for node_id in active_list:
            node_data = self._nodes.get(node_id, {})
            deps: List[str] = list(node_data.get("depends_on", []))
            fallbacks: List[str] = list(node_data.get("fallback_depends", []))
            optional_flag = node_data.get("optional", False)

            effective: List[str] = []
            for i, dep in enumerate(deps):
                if dep in active_set:
                    if dep not in effective:
                        effective.append(dep)
                else:
                    # Positional fallback
                    if i < len(fallbacks) and fallbacks[i] in active_set:
                        fb = fallbacks[i]
                        if fb not in effective:
                            effective.append(fb)
                    else:
                        # Platform variants can share a fallback list whose
                        # length differs from ``depends_on``. Keep positional
                        # preference, then retain the first active edge.
                        candidate = next((item for item in fallbacks if item in active_set), None)
                        if candidate is not None and candidate not in effective:
                            effective.append(candidate)

            # Required nodes with declared deps but zero effective → error
            if deps and not effective and not optional_flag:
                if not any(fb in active_set for fb in fallbacks):
                    raise ValueError(
                        f"Node {node_id!r} declares dependencies {deps!r} but "
                        f"none are active and no fallbacks are available for "
                        f"platform {platform!r}"
                    )

            resolved[node_id] = effective

        return resolved

    def topological_order(
        self,
        node_ids: Iterable[str] | Mapping[str, List[str]],
    ) -> List[str]:
        """Return *node_ids* in topological order (Kahn's algorithm).

        Nodes listed first in ``depends_on`` will appear earlier in the result.
        Only edges between nodes in *node_ids* are considered — external
        dependencies are silently ignored.

        Args:
            node_ids: The set of nodes to order.

        Returns:
            A topologically sorted list of node IDs.

        Raises:
            ValueError: If a cycle is detected among the given nodes.
        """
        # Preserve input order for deterministic output (important for golden-trace
        # parity when two nodes have the same dependency level).
        resolved_edges = node_ids if isinstance(node_ids, Mapping) else None
        node_list = list(node_ids)
        node_set = set(node_list)
        in_degree: Dict[str, int] = {}
        successors: Dict[str, List[str]] = {}

        for nid in node_list:
            in_degree[nid] = 0
            successors[nid] = []

        for nid in node_list:
            node = self._nodes.get(nid, {})
            dependencies = (
                resolved_edges.get(nid, [])
                if resolved_edges is not None
                else node.get("depends_on", [])
            )
            for dep in dependencies:
                dep = str(dep)
                if dep in node_set:
                    in_degree[nid] = in_degree.get(nid, 0) + 1
                    successors.setdefault(dep, []).append(nid)

        queue: deque[str] = deque(nid for nid in node_list if in_degree.get(nid, 0) == 0)
        result: List[str] = []

        while queue:
            nid = queue.popleft()
            result.append(nid)
            for succ in successors.get(nid, []):
                in_degree[succ] -= 1
                if in_degree[succ] == 0:
                    queue.append(succ)

        if len(result) != len(node_set):
            remaining = node_set - set(result)
            raise ValueError(
                f"Cycle detected in pipeline DAG. Nodes not reached: {sorted(remaining)}"
            )

        return result

    # ── Node details ─────────────────────────────────────────────────────

    def node_inputs(self, node_id: str) -> Dict[str, Any]:
        """Return the ``inputs`` dict for a node (shallow copy)."""
        node = self._nodes.get(node_id, {})
        inputs = node.get("inputs")
        if not isinstance(inputs, Mapping):
            return {}
        return dict(inputs)

    def node_outputs(self, node_id: str) -> Dict[str, Any]:
        """Return the ``outputs`` dict for a node (shallow copy)."""
        node = self._nodes.get(node_id, {})
        outputs = node.get("outputs")
        if not isinstance(outputs, Mapping):
            return {}
        return dict(outputs)

    def node_depends_on(self, node_id: str) -> List[str]:
        """Return the list of node IDs this node depends on."""
        node = self._nodes.get(node_id, {})
        deps = node.get("depends_on", [])
        if not isinstance(deps, list):
            return []
        return [str(d) for d in deps]

    def get_node(self, node_id: str) -> Dict[str, Any]:
        """Return the full node definition dict (shallow copy)."""
        return dict(self._nodes.get(node_id, {}))

    # ── Helpers ──────────────────────────────────────────────────────────

    def _category_enabled(
        self, config: Mapping[str, Any], category: str, node_id: str = ""
    ) -> bool:
        """Check whether a category is enabled in config.

        Looks for ``config.<category>.enable``.  If not found:
        - Optional nodes default to disabled (opt-in).
        - Required nodes default to enabled (opt-out).
        """
        block = config.get(category)
        if isinstance(block, Mapping):
            enabled = block.get("enable", True)
            if isinstance(enabled, bool):
                return enabled
            if isinstance(enabled, str):
                return enabled.lower() not in {"false", "no", "0"}
            return bool(enabled)
        # No config block: optional nodes default to disabled
        if node_id and self.is_optional(node_id):
            return False
        return True

    @staticmethod
    def _category_explicitly_enabled(config: Mapping[str, Any], category: str) -> bool:
        """Return True if *category* has an explicit ``enable: true`` in config."""
        block = config.get(category)
        if isinstance(block, Mapping):
            enabled = block.get("enable")
            if isinstance(enabled, bool):
                return enabled
            if isinstance(enabled, str):
                return enabled.lower() in {"true", "yes", "1"}
        return False


# ── Platform detection ───────────────────────────────────────────────────
# Auto-detects the sequencing platform from sample data when the platform
# column is "auto", empty, or "generic".
# / 当 platform 列为 auto/空/generic 时，从样本数据自动检测测序平台。


def detect_platform(sample: SampleInput) -> str:
    """Auto-detect sequencing platform from sample data.

    Resolution order:
    1. Explicit, valid platform (in ``VALID_PLATFORMS``, not ``"generic"``).
    2. Both short and long reads present → ``"hybrid"``.
    3. PacBio/HiFi technology metadata or filename → ``"pacbio_hifi"``.
    4. Other long reads present → ``"ont"``.
    5. Paired-end or single-end short reads → ``"illumina"``.
    6. Assembly-only input → ``"assembly"``.
    7. Default fallback → ``"illumina"``.

    Non-standard platform values (e.g. ``"rna_seq"``) are treated as
    "auto" and trigger detection rather than being passed through.
    This prevents legacy plugin-specific labels from silently failing
    node platform filtering.

    Args:
        sample: A parsed ``SampleInput`` from the sample sheet.

    Returns:
        The resolved platform string (one of ``VALID_PLATFORMS``).
    """
    explicit = (sample.platform or "").strip().lower()
    if explicit and explicit in VALID_PLATFORMS and explicit != "generic":
        return explicit

    if sample.has_short_reads and sample.has_long_reads:
        return "hybrid"

    technology = (sample.technology or "").strip().lower().replace("-", "_")
    long_read_name = str(sample.long_reads or sample.bam or "").lower()
    if sample.has_long_reads and (
        any(marker in technology for marker in ("pacbio", "hifi", "ccs", "sequel", "revio"))
        or any(marker in long_read_name for marker in ("pacbio", "hifi", "ccs"))
    ):
        return "pacbio_hifi"

    if sample.has_long_reads:
        return "ont"

    if sample.read1 and sample.read2:
        return "illumina"

    if sample.read1:
        return "illumina"

    if sample.assembly:
        return "assembly"

    return "illumina"


# ── Plan generation ──────────────────────────────────────────────────────
# The core logic that replaces hand-written build_plan() methods.
# / 替代手写 build_plan() 方法的核心逻辑。


# ── PluginContextResolver ────────────────────────────────────────────────
# A class that resolves auto/conditional settings from sample metadata.
# Ported from _engine/planner.py:_resolve_context_conditions() to the
# universal planner so all plugins share the same infrastructure.
# / 从 sample metadata 解析自动/条件配置的类。从 _engine/planner.py 移植。


class EligibilityResult(TypedDict):
    """Eligibility result for a conditional pipeline feature."""

    run: bool
    sample_count: int
    eligible_sample_count: int
    threshold: int
    reason: str


class PluginContextResolver:
    """Resolve auto/conditional configuration from sample context.

    Used by plugins that need to dynamically enable/disable features
    (diversity analysis, differential abundance, network inference, etc.)
    based on the actual sample set.
    """

    def __init__(
        self,
        config: Mapping[str, Any],
        sample_context: SampleContext,
    ) -> None:
        self._config = dict(config)
        self._context = sample_context

    @property
    def config(self) -> dict[str, Any]:
        """Resolved configuration (read-only after resolve() call)."""
        return self._config

    def resolve(self) -> dict[str, Any]:
        """Resolve auto/conditional settings in-place.

        Base implementation returns config unchanged. Subclasses override
        to add plugin-specific logic (e.g., diversity/differential/network
        eligibility for metagenomic_plasmid).
        """
        return self._config

    def eligibility(self) -> dict[str, EligibilityResult]:
        """Return eligibility results for all evaluated features.

        Base implementation returns empty dict. Subclasses override to
        report per-feature eligibility.
        """
        return {}


# ── Hook type aliases ─────────────────────────────────────────────────────

ContextResolverHook = Callable[
    [Mapping[str, Any], SampleContext],
    tuple[dict[str, Any], dict[str, dict[str, Any]]],
]
"""``(config, sample_context) → (resolved_config, eligibility)``.

Replaces ``_engine/planner.py:_resolve_context_conditions()``.
"""

SampleConfigHook = Callable[[Mapping[str, Any], SampleInput], dict[str, Any]]
"""``(config, sample) → sample_config``.

Replaces ``_engine/planner.py:_config_for_sample()``.
"""

SkipStepHook = Callable[[str, str, Mapping[str, Any], SampleInput], Optional[str]]
"""``(node_id, tool_id, sample_config, sample) → reason | None``.

Returns a skip reason string if the step should be skipped, or ``None``
to continue.  Replaces ``_engine/planner.py:_analysis_skip_steps()``.
"""


def build_plan_from_dag(
    dag_spec_path: str | Path,
    config: Mapping[str, Any],
    sample_context: SampleContext,
    *,
    plugin_root: str | Path | None = None,
    context_resolver: ContextResolverHook | None = None,
    sample_config_hook: SampleConfigHook | None = None,
    skip_step_hook: SkipStepHook | None = None,
) -> ExecutionPlan:
    """Build an ``ExecutionPlan`` from a ``pipeline_dag.yaml`` spec.

    This is the universal entry point that plugins call instead of writing
    their own ``build_plan()``.  It reads the DAG spec, filters active nodes
    by platform and config, generates per-sample and cross-sample steps,
    and returns a complete ``ExecutionPlan``.

    Args:
        dag_spec_path: Path to ``pipeline_dag.yaml`` (absolute, or relative
            to *plugin_root* if provided).
        config: Fully-resolved pipeline configuration dict.
        sample_context: Pre-parsed sample collection metadata.
        plugin_root: Optional plugin root directory for resolving relative
            *dag_spec_path* values.
        context_resolver: Optional hook to resolve auto/conditional settings
            from sample context. Replaces ``_resolve_context_conditions()``.
        sample_config_hook: Optional hook to customize config per sample.
            Replaces ``_config_for_sample()``.
        skip_step_hook: Optional hook to dynamically skip steps.
            Replaces ``_analysis_skip_steps()``.

    Returns:
        A complete ``ExecutionPlan`` ready for the executor.
    """
    dag_path = Path(dag_spec_path)
    if plugin_root is not None and not dag_path.is_absolute():
        dag_path = Path(plugin_root) / dag_path
    dag = UniversalDAG.from_yaml(dag_path)

    outdir = Path(str(config.get("outdir", ".")))
    threads = int(config.get("threads", 1))
    mode = str(config.get("mode", "auto"))
    log_dir = str(config.get("log_dir", str(outdir / "logs")))
    project_name = str(config.get("project_name", dag.pipeline_id))

    steps: List[PlanStep] = []
    skipped_steps: List[PlanStep] = []

    # ── Per-sample platform routing ─────────────────────────────────────
    # Each sample may belong to a different sequencing platform (Illumina,
    # ONT, PacBio, assembly).  Auto-detect platforms when the sample sheet
    # declares "auto", empty, or "generic".  Per-sample nodes are filtered
    # by the sample's own platform; cross-sample nodes use the union across
    # all platforms so that multi-platform projects can aggregate.
    # / 每个样本可属于不同测序平台。当 platform 列为 auto/空/generic 时自动检测。
    # 逐样本节点按样本自身平台过滤；跨样本节点取所有平台并集。
    sample_platforms: Dict[str, str] = {
        s.sample_id: detect_platform(s) for s in sample_context.samples
    }
    unique_platforms = set(sample_platforms.values())

    # Apply context resolver hook if provided / 应用 context_resolver 钩子
    # MUST happen before active_node_ids so that enable_conditions in the DAG
    # see the resolved config (e.g. sample_analysis.enable=false when sample
    # count is below the threshold).
    if context_resolver is not None:
        resolved_config, _ = context_resolver(config, sample_context)
        config = resolved_config

    # Compute active nodes per platform / 每个平台独立计算活跃节点
    platform_active: Dict[str, set] = {}
    for plat in unique_platforms:
        platform_active[plat] = set(dag.active_node_ids(plat, config))

    # Union across all platforms for global topological order and
    # cross-sample nodes.  A cross-sample node is active if it is
    # reachable from ANY platform present in the project.
    # 所有平台并集用于全局拓扑排序和跨样本节点。
    all_active: set = set()
    for active_set in platform_active.values():
        all_active |= active_set

    # All per-sample nodes are added to the global active set so the
    # per-sample loop can re-evaluate enable_conditions against the
    # per-sample config (applied via sample_config_hook).  Nodes whose
    # enable_conditions fail or are optional-without-condition will be
    # excluded by ``active_node_ids`` in the per-sample loop.
    for node_id in dag.node_ids:
        if dag.scope_for(node_id) == "per_sample":
            node_platforms = dag._nodes.get(node_id, {}).get("platforms", [])
            if not node_platforms or any(p in unique_platforms for p in node_platforms):
                all_active.add(node_id)

    if not all_active:
        workflow = config.get("workflow", {})
        if isinstance(workflow, Mapping) and workflow.get("include_nodes") is not None:
            raise ValueError(
                "workflow.include_nodes selected no active nodes for the project platforms "
                "and resolved configuration"
            )
        # Edge case: no nodes match any platform (e.g. empty config).
        # Fall back to the first platform for a meaningful error message.
        fallback_plat = next(iter(unique_platforms)) if unique_platforms else "illumina"
        all_active = set(dag.active_node_ids(fallback_plat, config))

    # Resolve effective dependencies (handling fallback_depends) for
    # topological ordering so that downstream nodes that rely on fallbacks
    # are ordered after their actual active upstreams.
    all_active_list = list(all_active)
    resolved_deps = dag.resolve_dependencies(all_active_list)
    ordered_ids = dag.topological_order(resolved_deps)

    # Separate per_sample and cross_sample nodes / 分离逐样本和跨样本节点
    per_sample_ids = [nid for nid in ordered_ids if dag.scope_for(nid) == "per_sample"]
    driver_cross_ids = [
        nid
        for nid in ordered_ids
        if dag.scope_for(nid) == "cross_sample"
        and str(dag.get_node(nid).get("execution_scope", "worker")) == "driver"
    ]
    cross_sample_ids = [
        nid
        for nid in ordered_ids
        if dag.scope_for(nid) == "cross_sample" and nid not in driver_cross_ids
    ]

    # Driver-scoped cross-sample nodes validate project-wide inputs before any
    # per-sample work. They are executed synchronously by HPC runtimes and in
    # declaration order by the local runtime.
    cross_sample_outputs: Dict[str, Dict[str, Any]] = {}
    driver_step_ids: Dict[str, str] = {}
    for node_id in driver_cross_ids:
        category = dag.node_category(node_id)
        category_dir = dag.category_dir_for(category)
        template_ctx = PathTemplateContext(config=config, sample=None, category_dir=category_dir)
        resolved_outputs = _resolve_outputs(dag, node_id, template_ctx)
        params = _resolve_params(dag, node_id, None, config, template_ctx)
        params["_dag_node_id"] = node_id
        params["_explicit_dependencies"] = [
            driver_step_ids[dep] for dep in dag.node_depends_on(node_id) if dep in driver_step_ids
        ]
        steps.append(
            PlanStep(
                step_id=node_id,
                sample_id=None,
                step_name=category,
                tool_id=node_id_to_tool_id(dag, node_id),
                category=category,
                inputs=_resolve_cross_sample_inputs(
                    dag,
                    node_id,
                    sample_context,
                    config,
                    {},
                    cross_sample_outputs,
                    plugin_root,
                ),
                outputs=resolved_outputs,
                params=params,
                reason=f"active driver-scoped DAG node {node_id!r}",
            )
        )
        driver_step_ids[node_id] = node_id
        cross_sample_outputs[node_id] = resolved_outputs

    # ── Per-sample nodes ──────────────────────────────────────────────
    # Track resolved outputs per sample per node for cross-sample aggregation.
    # / 跟踪每个样本每个节点的解析输出，用于跨样本聚合。
    sample_outputs: Dict[str, Dict[str, Dict[str, Any]]] = {}
    sample_step_ids: Dict[str, Dict[str, str]] = {}

    for sample in sample_context.samples:
        sample_plat = sample_platforms[sample.sample_id]

        # Apply sample_config_hook first so enable_conditions that depend on
        # per-sample fields (e.g. host_removal.host_reference, input.*) are
        # resolvable when we compute active nodes for this sample.
        sample_config = config
        if sample_config_hook is not None:
            sample_config = sample_config_hook(config, sample)

        # Recompute active nodes per-sample so per-sample config fields
        # (set by sample_config_hook) are evaluated correctly.
        sample_active = set(dag.active_node_ids(sample_plat, sample_config))
        sample_outputs[sample.sample_id] = {}
        sample_step_ids[sample.sample_id] = {}
        upstream_outputs: Dict[str, Dict[str, Any]] = {}

        for node_id in per_sample_ids:
            if node_id not in sample_active:
                continue  # represented in skipped_steps below

            # Apply skip_step_hook if provided / 应用 skip_step_hook 钩子
            if skip_step_hook is not None:
                tool_id = node_id_to_tool_id(dag, node_id)
                skip_reason = skip_step_hook(node_id, tool_id, sample_config, sample)
                if skip_reason:
                    step_id = f"{sample.sample_id}_{dag.node_category(node_id)}_{tool_id}"
                    skipped_steps.append(
                        PlanStep(
                            step_id=step_id,
                            sample_id=sample.sample_id,
                            step_name=dag.node_category(node_id),
                            tool_id=tool_id,
                            category=dag.node_category(node_id),
                            inputs={},
                            outputs={},
                            params={"_reason": skip_reason},
                            reason=skip_reason,
                        )
                    )
                    continue
            category = dag.node_category(node_id)
            category_dir = dag.category_dir_for(category)

            # Resolve inputs / 解析输入
            resolved_inputs = _resolve_inputs(
                dag, node_id, sample, sample_config, upstream_outputs, plugin_root
            )

            # Resolve output paths / 解析输出路径
            template_ctx = PathTemplateContext(
                config=sample_config,
                sample=sample,
                category_dir=category_dir,
                upstream_outputs=upstream_outputs,
            )
            resolved_outputs = _resolve_outputs(dag, node_id, template_ctx)

            # Build step / 构建步骤
            step_id = f"{sample.sample_id}_{category}_{node_id_to_tool_id(dag, node_id)}"
            if any(existing.step_id == step_id for existing in steps):
                step_id = f"{step_id}_{node_id}"
            params = _resolve_params(dag, node_id, sample, sample_config, template_ctx)
            params["_dag_node_id"] = node_id
            params["_explicit_dependencies"] = [
                dependency_id
                for dep in dag.node_depends_on(node_id)
                for dependency_id in (
                    sample_step_ids[sample.sample_id].get(dep) or driver_step_ids.get(dep),
                )
                if dependency_id
            ]
            step = PlanStep(
                step_id=step_id,
                sample_id=sample.sample_id,
                step_name=category,
                tool_id=node_id_to_tool_id(dag, node_id),
                category=category,
                inputs=resolved_inputs,
                outputs=resolved_outputs,
                params=params,
                reason=f"active DAG node {node_id!r} for platform {sample_plat!r}",
            )
            steps.append(step)
            sample_step_ids[sample.sample_id][node_id] = step_id
            upstream_outputs[node_id] = resolved_outputs
            sample_outputs[sample.sample_id][node_id] = resolved_outputs

        # Preserve excluded per-sample nodes as auditable plan records.  They
        # stay out of ``steps`` so the executor cannot run them accidentally.
        for node_id in dag.node_ids:
            if dag.scope_for(node_id) != "per_sample" or node_id in sample_active:
                continue
            category = dag.node_category(node_id)
            skipped_steps.append(
                PlanStep(
                    step_id=(f"{sample.sample_id}_{category}_{node_id_to_tool_id(dag, node_id)}"),
                    sample_id=sample.sample_id,
                    step_name=category,
                    tool_id=node_id_to_tool_id(dag, node_id),
                    category=category,
                    reason=(
                        f"excluded DAG node {node_id!r}: platform {sample_plat!r} "
                        "or resolved configuration did not satisfy its activation conditions"
                    ),
                    skipped=True,
                )
            )

    # ── Cross-sample nodes ─────────────────────────────────────────────
    # Track outputs of cross-sample nodes so subsequent cross-sample nodes
    # can reference them via source: NODE.OUTPUT_KEY.
    for node_id in cross_sample_ids:
        category = dag.node_category(node_id)
        category_dir = dag.category_dir_for(category)

        # Collect upstream per-sample outputs / 收集上游逐样本输出
        aggregated_upstream: Dict[str, Dict[str, Dict[str, Any]]] = {}
        node_deps = dag.node_depends_on(node_id)
        for dep_id in node_deps:
            if dep_id in per_sample_ids:
                for sample in sample_context.samples:
                    sid = sample.sample_id
                    aggregated_upstream.setdefault(sid, {})[dep_id] = sample_outputs.get(
                        sid, {}
                    ).get(dep_id, {})

        # Resolve inputs with aggregation / 解析带有聚合的输入
        resolved_inputs = _resolve_cross_sample_inputs(
            dag,
            node_id,
            sample_context,
            config,
            sample_outputs,
            cross_sample_outputs,
            plugin_root,
        )

        # Build template context (no single sample) / 构建模板上下文（无单一样本）
        template_ctx = PathTemplateContext(
            config=config,
            sample=None,
            category_dir=category_dir,
        )
        resolved_outputs = _resolve_outputs(dag, node_id, template_ctx)

        tool_id = node_id_to_tool_id(dag, node_id)
        explicit_dependencies: List[str] = []
        for dep in dag.node_depends_on(node_id):
            if dep in per_sample_ids:
                explicit_dependencies.extend(
                    mapping[dep] for mapping in sample_step_ids.values() if dep in mapping
                )
            elif dep in cross_sample_outputs:
                explicit_dependencies.append(dep)
        params = _resolve_params(dag, node_id, None, config, template_ctx)
        params["_dag_node_id"] = node_id
        params["_explicit_dependencies"] = explicit_dependencies
        step = PlanStep(
            step_id=node_id,
            sample_id=None,
            step_name=category,
            tool_id=tool_id,
            category=category,
            inputs=resolved_inputs,
            outputs=resolved_outputs,
            params=params,
            reason=f"active cross-sample DAG node {node_id!r}",
        )
        steps.append(step)
        cross_sample_outputs[node_id] = resolved_outputs

    for node_id in dag.node_ids:
        if dag.scope_for(node_id) != "cross_sample" or node_id in all_active:
            continue
        category = dag.node_category(node_id)
        skipped_steps.append(
            PlanStep(
                step_id=node_id,
                sample_id=None,
                step_name=category,
                tool_id=node_id_to_tool_id(dag, node_id),
                category=category,
                reason=(
                    f"excluded cross-sample DAG node {node_id!r}: no project platform "
                    "or resolved configuration satisfied its activation conditions"
                ),
                skipped=True,
            )
        )

    # ── Assemble plan ──────────────────────────────────────────────────
    selected_tools = sorted({s.tool_id for s in steps if s.tool_id != "internal"})
    return ExecutionPlan(
        project_name=project_name,
        analysis_type=dag.pipeline_id,
        mode=mode,
        threads=threads,
        outdir=str(outdir),
        log_dir=log_dir,
        samples=list(sample_context.samples),
        sample_context=sample_context,
        selected_tools=selected_tools,
        steps=steps,
        skipped_steps=skipped_steps,
        provenance_dir=str(outdir / "provenance"),
    )


# ── Input resolution ─────────────────────────────────────────────────────


def _resolve_inputs(
    dag: UniversalDAG,
    node_id: str,
    sample: SampleInput,
    config: Mapping[str, Any],
    upstream_outputs: Mapping[str, Mapping[str, Any]],
    plugin_root: str | Path | None,
) -> Dict[str, Any]:
    """Resolve input values for a per-sample node.

    Resolution order for each input key:
    1. If ``source: sample_sheet`` → look up in ``sample.to_dict()``.
    2. If ``source: UPSTREAM_NODE.OUTPUT_KEY`` → look up in *upstream_outputs*.
    3. If ``source`` is absent → try config resources, then config, then default/empty.
    4. ``fallback`` is tried when the primary source yields an empty value.
    5. ``default`` is used as the final fallback when nothing else resolves.
    """
    inputs_spec = dag.node_inputs(node_id)
    resolved: Dict[str, Any] = {}
    sample_dict = sample.to_dict()

    for key, spec in inputs_spec.items():
        if not isinstance(spec, Mapping):
            resolved[key] = spec
            continue

        # Path template: resolve against a simple context / 路径模板解析
        path_template = spec.get("path")
        if path_template:
            resolved[key] = _resolve_input_path(path_template, config, sample)
            continue

        value: Any = ""
        source = spec.get("source")
        if source is not None:
            source_str = str(source)
            if source_str == "sample_sheet":
                value = sample_dict.get(key, "")
            elif "." in source_str:
                # Upstream reference: "NODE_ID.OUTPUT_KEY"
                parts = source_str.split(".", 1)
                upstream_id, upstream_key = parts[0], parts[1]
                # Handle template source like "{active_assembly_node}.assembly"
                # by scanning all upstream outputs for the matching key.
                if upstream_id.startswith("{") and upstream_id.endswith("}"):
                    for uid, uouts in reversed(list(upstream_outputs.items())):
                        val = uouts.get(upstream_key)
                        if val:
                            value = str(val)
                            break
                else:
                    value = upstream_outputs.get(upstream_id, {}).get(upstream_key, "")
            else:
                value = sample_dict.get(source_str, "")
        else:
            # No explicit source — try config resources, then config, then empty.
            value = _resolve_script_path(
                key, _resolve_config_value(config, key), plugin_root
            )

        # Try fallback when primary source yields nothing / 主源为空时尝试备用源
        if not value:
            fallback = spec.get("fallback")
            if fallback is not None:
                fallback_str = str(fallback)
                if "." in fallback_str:
                    parts = fallback_str.split(".", 1)
                    fb_id, fb_key = parts[0], parts[1]
                    # Handle template fallback like "{active_assembly_node}.assembly"
                    if fb_id.startswith("{") and fb_id.endswith("}"):
                        for uid, uouts in reversed(list(upstream_outputs.items())):
                            val = uouts.get(fb_key)
                            if val:
                                value = str(val)
                                break
                    else:
                        value = upstream_outputs.get(fb_id, {}).get(fb_key, "")

        # Use default when all sources yield nothing / 所有源都为空时使用默认值
        if not value:
            value = spec.get("default", "")

        resolved[key] = value

    return resolved


def _resolve_cross_sample_inputs(
    dag: UniversalDAG,
    node_id: str,
    sample_context: SampleContext,
    config: Mapping[str, Any],
    sample_outputs: Dict[str, Dict[str, Dict[str, Any]]],
    cross_sample_outputs: Dict[str, Dict[str, Any]],
    plugin_root: str | Path | None,
) -> Dict[str, Any]:
    """Resolve input values for a cross-sample node.

    For inputs with ``aggregate: per_sample_outputs``, collects all upstream
    per-sample output paths into a list (or a single string for simple cases).
    For ``source: NODE.OUTPUT`` references, checks both per-sample and
    cross-sample upstream outputs.
    """
    inputs_spec = dag.node_inputs(node_id)
    resolved: Dict[str, Any] = {}

    for key, spec in inputs_spec.items():
        if not isinstance(spec, Mapping):
            resolved[key] = spec
            continue

        # Path template: resolve against the output directory / 路径模板解析
        path_template = spec.get("path")
        if path_template:
            resolved[key] = _resolve_input_path(path_template, config, None)
            continue

        aggregate = spec.get("aggregate")
        if aggregate == "per_sample_outputs":
            # Collect all per-sample outputs from the depends_on upstream node.
            # Use the source field (NODE_ID.OUTPUT_KEY) when available to
            # determine the upstream output key; otherwise fall back to the
            # input key name.
            values: List[str] = []
            upstream_key = key
            source = spec.get("source")
            if source is not None and "." in str(source):
                parts = str(source).split(".", 1)
                upstream_key = parts[1]  # OUTPUT_KEY from "NODE_ID.OUTPUT_KEY"
            node_deps = dag.node_depends_on(node_id)
            for dep_id in node_deps:
                for sample in sample_context.samples:
                    sid = sample.sample_id
                    dep_outputs = sample_outputs.get(sid, {}).get(dep_id, {})
                    val = dep_outputs.get(upstream_key)
                    if val:
                        values.append(str(val))
            # Aggregation has one stable type regardless of cohort size.
            resolved[key] = values
        else:
            source = spec.get("source")
            if source is not None and "." in str(source):
                # Upstream reference: "NODE_ID.OUTPUT_KEY"
                parts = str(source).split(".", 1)
                upstream_id, upstream_key = parts[0], parts[1]
                # Check cross-sample outputs first, then per-sample
                if upstream_id in cross_sample_outputs:
                    resolved[key] = cross_sample_outputs[upstream_id].get(upstream_key, "")
                else:
                    first_sid = (
                        sample_context.samples[0].sample_id if sample_context.samples else ""
                    )
                    resolved[key] = (
                        sample_outputs.get(first_sid, {}).get(upstream_id, {}).get(upstream_key, "")
                    )
            else:
                resolved[key] = _resolve_script_path(
                    key, _resolve_config_value(config, key), plugin_root
                )

    return resolved


def _resolve_config_value(config: Mapping[str, Any], key: str) -> Any:
    """Try to resolve a key from config, falling back through common locations.

    Lookup order: ``config["resources"][key]`` → ``config["input"][key]``
    → ``config["annotation"][key]`` → ``config["typing"][key]``
    → ``config[key]`` → ``""``.
    """
    resources = config.get("resources")
    if isinstance(resources, Mapping) and key in resources:
        return resources[key]
    input_section = config.get("input")
    if isinstance(input_section, Mapping) and key in input_section:
        return input_section[key]
    for section_name in ("annotation", "typing"):
        section = config.get(section_name)
        if isinstance(section, Mapping) and key in section:
            return section[key]
    if key in config:
        return config[key]
    return ""


def _resolve_script_path(
    key: str,
    value: Any,
    plugin_root: str | Path | None = None,
) -> str:
    """Auto-resolve bundled script paths when config provides none.

    When a ``*_script`` parameter resolves to an empty string or a sentinel
    value (e.g. ``DIVERSITY_SCRIPT_NOT_CONFIGURED``), search the plugin
    ``scripts/`` directory and the project ``scripts/`` directory for a
    matching file.

    Search strategy:
    1. If *value* is a non-empty, non-sentinel string, return it as-is.
    2. Strip ``_script`` from *key* to get a stem (e.g. ``diversity``).
    3. Search ``plugin_root/scripts/`` then ``PROJECT_ROOT/scripts/`` for
       files whose name contains the stem (any of ``.py``, ``.R``, ``.sh``).
    4. Return the first match, or the original *value* if nothing found.
    """
    value_str = str(value) if value else ""
    if value_str and "NOT_CONFIGURED" not in value_str.upper():
        return value_str

    if not key.endswith("_script"):
        return value_str

    stem = key[:-7]  # remove "_script" suffix

    # Build search directory list
    search_dirs: list[Path] = []
    if plugin_root:
        plugin_scripts = Path(plugin_root) / "scripts"
        if plugin_scripts.is_dir():
            search_dirs.append(plugin_scripts)

    try:
        from abi.config import PROJECT_ROOT as _prj_root

        project_scripts = _prj_root / "scripts"
        if project_scripts.is_dir() and project_scripts not in search_dirs:
            search_dirs.append(project_scripts)
    except Exception:
        pass

    # Search for matching script files
    for search_dir in search_dirs:
        for ext in (".py", ".R", ".sh"):
            # Direct stem match: e.g. stem="diversity" → diversity.py
            candidate = search_dir / f"{stem}{ext}"
            if candidate.is_file():
                return str(candidate.resolve())
            # Prefix match: e.g. stem="deseq2" → run_deseq2.R
            for f in sorted(search_dir.glob(f"*{stem}*{ext}")):
                if f.is_file():
                    return str(f.resolve())

    return value_str


def _resolve_input_path(
    template: Any,
    config: Mapping[str, Any],
    sample: SampleInput | None,
) -> str:
    """Resolve a path template string against config and optional sample.

    Supports ``{outdir}``, ``{sample_id}``, ``{sample.attr}`` references.
    Used for inputs that declare a ``path`` template rather than pulling
    from an upstream source or config key.
    """
    template_str = str(template)
    if "{" not in template_str:
        return template_str
    ctx = PathTemplateContext(config=config, sample=sample, category_dir="")
    try:
        return template_str.format_map(ctx)
    except (KeyError, ValueError):
        return template_str


# ── Output resolution ────────────────────────────────────────────────────


def _resolve_outputs(
    dag: UniversalDAG,
    node_id: str,
    template_ctx: PathTemplateContext,
) -> Dict[str, Any]:
    """Resolve output paths for a node.

    For each output with a ``path`` template, resolve it against
    *template_ctx*.  Outputs without a ``path`` are left as empty strings.
    Always ensures ``output_dir`` is present.
    """
    outputs_spec = dag.node_outputs(node_id)
    resolved: Dict[str, Any] = {}
    default_output_template = (
        "{outdir}/{category_dir}/{sample_id}"
        if "sample_id" in template_ctx
        else "{outdir}/{category_dir}"
    )

    has_output_dir = False
    for key, spec in outputs_spec.items():
        if key == "output_dir":
            has_output_dir = True
        if not isinstance(spec, Mapping):
            resolved[key] = spec
            continue
        path_template = spec.get("path")
        if path_template:
            try:
                resolved[key] = str(path_template).format_map(template_ctx)
            except (KeyError, ValueError) as exc:
                _logger.warning(
                    "Failed to resolve path template for %s.%s: %s",
                    node_id,
                    key,
                    exc,
                )
                resolved[key] = ""
        elif key == "output_dir":
            # Default output_dir if no path template / 无路径模板时的默认 output_dir
            resolved[key] = default_output_template.format_map(template_ctx)
            has_output_dir = True
        else:
            resolved[key] = ""

    # Ensure output_dir is always present / 确保 output_dir 始终存在
    if not has_output_dir:
        resolved["output_dir"] = default_output_template.format_map(template_ctx)

    return resolved


# ── Params resolution ────────────────────────────────────────────────────


def _resolve_params(
    dag: UniversalDAG,
    node_id: str,
    sample: SampleInput | None,
    config: Mapping[str, Any],
    template_ctx: PathTemplateContext,
) -> Dict[str, Any]:
    """Build the ``params`` dict for a PlanStep.

    Includes mode, threads, sample_id (if per-sample), DAG node-level
    params (formatted via template_ctx), and any tool-level overrides from
    config.
    """
    params: Dict[str, Any] = {
        "mode": str(config.get("mode", "auto")),
        "threads": int(config.get("threads", 1)),
    }
    if sample is not None:
        params["sample_id"] = sample.sample_id

    # DAG node-level params (formatted with template context) / DAG 节点级参数
    node = dag.get_node(node_id)
    node_params = node.get("params")
    if isinstance(node_params, dict):
        for pkey, pval in node_params.items():
            try:
                params[pkey] = str(pval).format_map(template_ctx)
            except KeyError:
                params[pkey] = pval

    tool_id = node_id_to_tool_id(dag, node_id)
    # Declarative config → parameter bindings. Example:
    # config_params: {comparison: differential_expression.comparison}
    config_params = node.get("config_params")
    if isinstance(config_params, Mapping):
        for param_name, config_path in config_params.items():
            value = _lookup_config_path(config, str(config_path))
            if value is not None:
                params.setdefault(str(param_name), value)

    # Tool-level params from config.tool_params.<tool_id> / 工具级参数
    tool_params_block = config.get("tool_params")
    if isinstance(tool_params_block, Mapping):
        tool_overrides = tool_params_block.get(tool_id)
        if isinstance(tool_overrides, Mapping):
            params.update(tool_overrides)

    # Preserve declarative output contracts and assertions through planning.
    # The executor consumes this private transport-neutral block before the
    # tool adapter is invoked, so pipeline_dag.yaml remains the runtime SSOT.
    outputs = dag.node_outputs(node_id)
    assertions = node.get("assertions", [])
    if outputs or assertions:
        params["_contract"] = {
            "inputs": dag.node_inputs(node_id),
            "outputs": outputs,
            "assertions": list(assertions) if isinstance(assertions, list) else [str(assertions)],
        }

    handler_id = node.get("internal_handler")
    if handler_id:
        params["_internal_handler"] = {
            "handler_id": str(handler_id),
            "execution_scope": str(node.get("execution_scope", "worker")),
        }

    return params


def _lookup_config_path(config: Mapping[str, Any], dotted_path: str) -> Any:
    """Resolve a dotted config path, returning None when any segment is absent."""
    value: Any = config
    for segment in dotted_path.split("."):
        if not isinstance(value, Mapping) or segment not in value:
            return None
        value = value[segment]
    return value


# ── Helpers ───────────────────────────────────────────────────────────────


def node_id_to_tool_id(dag: UniversalDAG, node_id: str) -> str:
    """Extract the ``tool_id`` from a node definition.

    Falls back to *node_id* itself if no ``tool_id`` field is present.
    """
    node = dag.get_node(node_id)
    tool_id = node.get("tool_id")
    if tool_id:
        return str(tool_id)
    return node_id


def build_sample_context(
    config: Mapping[str, Any],
    *,
    check_files: bool = True,
    validate_platform: Callable[[str], None] | None = None,
) -> SampleContext:
    """Build a ``SampleContext`` from pipeline configuration.

    Handles two modes:

    1. **Sample-sheet mode**: ``config.input.sample_sheet`` points to a
       TSV file with columns per ``SampleInput`` fields.
    2. **Single-sample mode**: individual keys in ``config.input``
       (``single_input``, ``platform``, ``read1``, ``read2``,
       ``long_reads``, ``pod5``, ``bam``, ``assembly``, ``group``).

    Args:
        config: Fully-resolved pipeline configuration.
        check_files: If True, validate that input files exist on disk.
        validate_platform: Optional callback to validate platform strings.
            Called with ``platform`` for single-sample mode and per-sample
            in sample-sheet mode. Raises on invalid values.

    Returns:
        A ``SampleContext`` ready for ``build_plan_from_dag()``.

    Raises:
        ValueError: If neither sample-sheet nor single-sample input
            is configured, or if required inputs are missing.
    """
    input_config = config.get("input") or {}
    if not isinstance(input_config, Mapping):
        raise ValueError("config.input must be a mapping")

    sample_sheet = input_config.get("sample_sheet")
    if sample_sheet:
        return _parse_generic_sample_sheet(
            Path(str(sample_sheet)),
            check_files=check_files,
            validate_platform=validate_platform,
        )

    # Single-sample mode
    single_input = input_config.get("single_input")
    platform = input_config.get("platform")
    has_any_input = bool(
        single_input
        or any(input_config.get(key) for key in ("assembly", "long_reads", "pod5", "bam"))
    )
    if not has_any_input:
        raise ValueError(
            "No sample_sheet or single_input/assembly/long_reads/pod5/bam is configured"
        )
    if not platform:
        raise ValueError("Single-sample input requires platform")
    if validate_platform is not None:
        validate_platform(str(platform))

    sample = SampleInput(
        sample_id=str(input_config.get("sample_id") or "single_sample"),
        platform=str(platform),
        read1=single_input if str(platform) == "illumina" else input_config.get("read1"),
        read2=input_config.get("read2"),
        long_reads=(
            single_input
            if str(platform) in {"ont", "pacbio_hifi"}
            else input_config.get("long_reads")
        ),
        pod5=input_config.get("pod5"),
        bam=input_config.get("bam"),
        assembly=(single_input if str(platform) == "assembly" else input_config.get("assembly")),
        group=input_config.get("group"),
    )
    _validate_sample_requirements(sample)
    if check_files:
        _validate_sample_files([sample])
    return _summarize_samples([sample])


def _parse_generic_sample_sheet(
    path: Path,
    *,
    check_files: bool = True,
    validate_platform: Callable[[str], None] | None = None,
) -> SampleContext:
    """Parse a TSV sample sheet into ``SampleContext``.

    Expected columns: ``sample_id``, ``platform`` (required);
    optional: ``read1``, ``read2``, ``long_reads``, ``pod5``, ``bam``,
    ``assembly``, ``group``, ``technology``, ``host_reference``.
    """
    if not path.exists():
        raise ValueError(f"Sample sheet does not exist: {path}")

    samples: list[SampleInput] = []
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if reader.fieldnames is None:
            raise ValueError(f"Sample sheet is empty: {path}")

        required = {"sample_id", "platform"}
        missing = required - set(reader.fieldnames)
        if missing:
            raise ValueError(
                f"Sample sheet {path} missing required columns: {', '.join(sorted(missing))}"
            )

        for row_number, row in enumerate(reader, start=2):
            sid = str(row.get("sample_id", "") or "").strip()
            platform = str(row.get("platform", "") or "").strip()
            if not sid or not platform:
                raise ValueError(
                    f"Sample sheet {path} row {row_number}: sample_id and platform are required"
                )
            if validate_platform is not None:
                validate_platform(platform)

            raw = {k: v.strip() if v else None for k, v in row.items()}
            samples.append(
                SampleInput(
                    sample_id=sid,
                    platform=platform,
                    group=raw.get("group"),
                    read1=raw.get("read1"),
                    read2=raw.get("read2"),
                    long_reads=raw.get("long_reads"),
                    pod5=raw.get("pod5"),
                    bam=raw.get("bam"),
                    assembly=raw.get("assembly"),
                    technology=raw.get("technology"),
                    host_reference=raw.get("host_reference"),
                )
            )

    for s in samples:
        _validate_sample_requirements(s)
    if check_files:
        _validate_sample_files(samples)
    return _summarize_samples(samples)


def _validate_sample_requirements(sample: SampleInput, row_number: int | None = None) -> None:
    """Validate a single sample's requirements."""
    loc = f" (row {row_number})" if row_number else ""
    if sample.platform not in VALID_PLATFORMS:
        raise ValueError(
            f"Invalid platform {sample.platform!r}{loc}: must be one of {sorted(VALID_PLATFORMS)}"
        )


def _validate_sample_files(samples: Iterable[SampleInput]) -> None:
    """Validate that all referenced input files exist."""
    for sample in samples:
        for attr in ("read1", "read2", "long_reads", "pod5", "bam", "assembly"):
            path_str: str | None = getattr(sample, attr, None)
            if path_str:
                p = Path(path_str)
                if not p.exists():
                    raise FileNotFoundError(f"Sample {sample.sample_id} {attr} not found: {p}")


def _summarize_samples(samples: list[SampleInput]) -> SampleContext:
    """Build a ``SampleContext`` from a list of samples."""
    multi_sample = len(samples) > 1
    has_groups = len({s.group for s in samples if s.group}) > 1
    return SampleContext(
        samples=samples,
        multi_sample=multi_sample,
        has_groups=has_groups,
    )
