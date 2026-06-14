"""Pipeline DAG — load, query, and resolve the canonical workflow specification.

This module reads ``pipeline_dag.yaml`` and provides a ``PipelineDAG`` class
that the planner uses to generate execution steps. It replaces the old
hardcoded ``_route_for_platform()`` / ``_sample_steps()`` logic with a
data-driven approach: the YAML spec is the single source of truth for which
tools run on which platform in which order.

Design principles / 设计原则
----------------------------
1. **Spec is truth** — the planner does not decide *which* tools to run;
   the DAG spec does. The planner only resolves *how* (paths, params).
2. **Platform filtering** — nodes declare their ``platforms``; the loader
   filters them at query time.
3. **Explicit dependencies** — every edge is declared via ``depends_on``;
   no path-matching heuristics.
4. **Fallback chains** — when an optional node is disabled, downstream
   nodes fall back to ``fallback_depends``.
5. **Topological sort** — enabled nodes are sorted so upstream always
   executes before downstream.
"""

from __future__ import annotations

from collections import deque
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Set

import yaml

from abi.config import PLUGIN_ROOT

# Path to the canonical DAG specification relative to the plugin root.
_DAG_SPEC_PATH: Path = PLUGIN_ROOT / "metagenomic_plasmid" / "pipeline_dag.yaml"


class PipelineDAG:
    """In-memory representation of the AutoPlasm pipeline DAG specification.

    Usage::

        dag = PipelineDAG.from_yaml()
        nodes = dag.nodes_for_platform("illumina")
        enabled = dag.resolve(config, "illumina")
        order = dag.topological_order(enabled)
    """

    def __init__(self, spec: Mapping[str, Any]) -> None:
        self._spec = dict(spec)
        self._nodes: Dict[str, Dict[str, Any]] = dict(self._spec.get("nodes", {}))
        self._platforms: List[str] = list(self._spec.get("platforms", []))
        self._resolution: Dict[str, Dict[str, List[str]]] = dict(
            self._spec.get("platform_resolution", {})
        )
        self._standard_tables: Dict[str, Any] = dict(self._spec.get("standard_tables", {}))

    # ── Factory / 工厂方法 ─────────────────────────────────────────────────

    @classmethod
    def from_yaml(cls, path: str | Path | None = None) -> "PipelineDAG":
        """Load the DAG from a YAML file.

        Args:
            path: Path to ``pipeline_dag.yaml``. Defaults to the bundled spec
                  under ``plugins/metagenomic_plasmid/pipeline_dag.yaml``.
        """
        yaml_path = Path(path or _DAG_SPEC_PATH)
        if not yaml_path.exists():
            raise FileNotFoundError(f"Pipeline DAG spec not found: {yaml_path}")
        with yaml_path.open("r", encoding="utf-8") as handle:
            spec = yaml.safe_load(handle) or {}
        if not isinstance(spec, Mapping):
            raise ValueError(f"Pipeline DAG spec must be a YAML mapping: {yaml_path}")
        return cls(spec)

    # ── Query / 查询 ───────────────────────────────────────────────────────

    @property
    def platforms(self) -> List[str]:
        """Supported platforms in declaration order."""
        return list(self._platforms)

    @property
    def all_node_ids(self) -> List[str]:
        """All node IDs defined in the spec (unsorted)."""
        return list(self._nodes.keys())

    @property
    def standard_tables(self) -> Dict[str, Any]:
        """Standard table definitions from the spec."""
        return dict(self._standard_tables)

    def node(self, node_id: str) -> Dict[str, Any]:
        """Return the raw spec dict for a single node.

        Raises:
            KeyError: if *node_id* is not in the spec.
        """
        if node_id not in self._nodes:
            raise KeyError(f"Unknown DAG node: {node_id}")
        return dict(self._nodes[node_id])

    def nodes_for_platform(self, platform: str) -> Dict[str, Dict[str, Any]]:
        """Return all nodes whose ``platforms`` list includes *platform*.

        Args:
            platform: One of ``illumina``, ``ont``, ``pacbio_hifi``, ``hybrid``,
                      ``assembly``.
        """
        return {
            node_id: dict(node_data)
            for node_id, node_data in self._nodes.items()
            if platform in node_data.get("platforms", [])
        }

    def active_node_ids(
        self, platform: str, config: Mapping[str, Any]
    ) -> Set[str]:
        """Return the set of node IDs that should be ACTIVE for this run.

        "Active" means:
        1. The node lists *platform* in its ``platforms``.
        2. If the node has an ``enable_condition``, the config satisfies it.
        3. If the node is ``optional: true`` and no enable_condition fires,
           it is **excluded** (the downstream fallback chain handles it).

        Args:
            platform: Target sequencing platform.
            config: Fully-resolved pipeline configuration.
        """
        platform_nodes = self.nodes_for_platform(platform)
        active: Set[str] = set()

        for node_id, node_data in platform_nodes.items():
            optional = node_data.get("optional", False)
            condition = node_data.get("enable_condition")

            if condition:
                # Explicit enable_condition: active only if config satisfies it.
                if _evaluate_condition(condition, config):
                    active.add(node_id)
                # else: disabled (optional with unmet condition → excluded)
            elif not optional:
                # Required node with no conditions: always active.
                active.add(node_id)
            # else: optional with no enable_condition → excluded by default
            # (typically QC sub-steps like individual FastQC runs)

        return active

    def resolve_dependencies(
        self, active_ids: Set[str], platform: str
    ) -> Dict[str, List[str]]:
        """Resolve effective dependencies for each active node.

        For each active node, its effective dependencies are the subset of
        ``depends_on`` that are also active. If an optional dependency is
        NOT active, the node's ``fallback_depends`` is tried instead.

        Returns:
            ``{node_id: [effective_dependency_ids]}`` mapping. A node with
            no active dependencies has an empty list.

        Raises:
            ValueError: if a required dependency cannot be resolved.
        """
        resolved: Dict[str, List[str]] = {}

        for node_id in active_ids:
            node_data = self._nodes.get(node_id, {})
            deps: List[str] = list(node_data.get("depends_on", []))
            fallbacks: List[str] = list(node_data.get("fallback_depends", []))
            optional_flag = node_data.get("optional", False)

            effective: List[str] = []
            for i, dep in enumerate(deps):
                if dep in active_ids:
                    if dep not in effective:
                        effective.append(dep)
                else:
                    # Positional fallback: fallback_depends[i] is the alternative
                    # for depends_on[i] when the primary dep is not active.
                    if i < len(fallbacks) and fallbacks[i] in active_ids:
                        fb = fallbacks[i]
                        if fb not in effective:
                            effective.append(fb)

            # For required nodes with declared dependencies but zero effective
            # deps after fallback resolution, verify that at least one fallback
            # is available. If not, the node cannot execute.
            if deps and not effective and not optional_flag:
                if not _has_active_fallback(fallbacks, active_ids):
                    raise ValueError(
                        f"Node {node_id!r} declares dependencies {deps!r} but "
                        f"none are active and no fallbacks are available for "
                        f"platform {platform!r}"
                    )

            resolved[node_id] = effective

        return resolved

    def topological_order(self, resolved_deps: Dict[str, List[str]]) -> List[str]:
        """Return active node IDs in topological order.

        Uses Kahn's algorithm (BFS). Nodes with no dependencies come first.

        Args:
            resolved_deps: ``{node_id: [dependency_ids]}`` as returned by
                           ``resolve_dependencies()``.

        Returns:
            Node IDs in execution order. Nodes at the same depth are ordered
            by their appearance in the spec (stable ordering).

        Raises:
            ValueError: if a cycle is detected.
        """
        # Build in-degree map and adjacency list
        in_degree: Dict[str, int] = {nid: 0 for nid in resolved_deps}
        adjacency: Dict[str, List[str]] = {nid: [] for nid in resolved_deps}

        for node_id, deps in resolved_deps.items():
            in_degree[node_id] = len(deps)
            for dep in deps:
                if dep in adjacency:
                    adjacency[dep].append(node_id)

        # Kahn's algorithm
        queue: deque[str] = deque(
            nid for nid, deg in in_degree.items() if deg == 0
        )
        # Stable order: when multiple nodes have in-degree 0, prioritize
        # by spec order (the order they appear in _nodes).
        spec_order = {nid: i for i, nid in enumerate(self._nodes)}
        queue = deque(sorted(queue, key=lambda nid: spec_order.get(nid, 9999)))

        order: List[str] = []
        while queue:
            current = queue.popleft()
            order.append(current)
            for neighbor in adjacency.get(current, []):
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    # Insert maintaining spec-order stability
                    _insert_sorted(queue, neighbor, spec_order)

        if len(order) != len(resolved_deps):
            remaining = set(resolved_deps) - set(order)
            raise ValueError(
                f"Cycle detected in pipeline DAG. "
                f"Unresolved nodes: {sorted(remaining)}"
            )

        return order

    def category_for(self, node_id: str) -> str:
        """Return the category string for a node."""
        return str(self._nodes.get(node_id, {}).get("category", ""))

    def tool_id_for(self, node_id: str) -> str:
        """Return the tool_id for a node."""
        return str(self._nodes.get(node_id, {}).get("tool_id", "internal"))

    def inputs_for(self, node_id: str) -> Dict[str, Any]:
        """Return the inputs spec for a node."""
        return dict(self._nodes.get(node_id, {}).get("inputs", {}))

    def outputs_for(self, node_id: str) -> Dict[str, Any]:
        """Return the outputs spec for a node."""
        return dict(self._nodes.get(node_id, {}).get("outputs", {}))


# ── Helpers / 辅助函数 ─────────────────────────────────────────────────────


def _evaluate_condition(
    condition: Mapping[str, Any], config: Mapping[str, Any]
) -> bool:
    """Evaluate a node enable_condition against the config.

    Supported operators:
    - ``value``: config field must equal the given value.
    - ``not_empty``: config field must be non-None, non-empty.
    """
    field_path: str = str(condition.get("field", ""))
    operator: str = str(condition.get("operator", "value"))
    expected = condition.get("value")

    # Navigate dotted field path into config
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

    return False


def _resolve_fallback(
    fallback_list: List[str],
    active_ids: Set[str],
) -> Optional[str]:
    """Find the first active fallback node from *fallback_list*."""
    for fb in fallback_list:
        if fb in active_ids:
            return fb
    return None


def _has_active_fallback(
    fallback_list: List[str],
    active_ids: Set[str],
) -> bool:
    """Check whether *any* fallback node is active."""
    return any(fb in active_ids for fb in fallback_list)


def _insert_sorted(
    queue: deque[str],
    item: str,
    spec_order: Dict[str, int],
) -> None:
    """Insert *item* into *queue* maintaining specification order stability."""
    item_rank = spec_order.get(item, 9999)
    for i, existing in enumerate(queue):
        if spec_order.get(existing, 9999) > item_rank:
            queue.insert(i, item)
            return
    queue.append(item)
