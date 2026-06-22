"""DAG helpers for ABI execution plans.

DAG inference now uses a three-layer correctness model:

L1 — Literature-backed workflow declarations (:class:`WorkflowSpec`)
     serve as ground truth.  Each plugin may declare a ``workflow``
     section in its ``abi-plugin.yaml`` that specifies the correct
     tool execution order with citations.

L2 — Path-level dataflow inference cross-validates the declared
     dependencies by matching output paths to input paths.

L3 — When L1 and L2 disagree, a WARNING is emitted so the plugin
     author can investigate.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping

from abi.config import PROJECT_ROOT
from abi.contracts import WorkflowSpec
from abi.schemas import ABIError

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class StepBinding:
    """Stable binding between an ABI step and a generated workflow node."""

    step: Any
    process_name: str
    dependencies: List[str]
    produced_paths: Dict[str, str]
    consumed_paths: Dict[str, str]


@dataclass(frozen=True)
class ABIDAG:
    """Path-derived dependency graph for ABI plan steps."""

    bindings: List[StepBinding]
    edges: Dict[str, List[str]]
    roots: List[str]
    topological_order: List[str]

    def binding_for(self, step_id: str) -> StepBinding:
        for binding in self.bindings:
            if str(binding.step.step_id) == step_id:
                return binding
        raise ABIError(f"Unknown DAG step: {step_id}")


def infer_dag(
    steps: Iterable[Any],
    *,
    project_root: str | Path | None = None,
    sequential_fallback: bool = False,
    workflow_spec: WorkflowSpec | None = None,
    strict_workflow: bool = False,
) -> ABIDAG:
    """Infer a DAG with L1 (literature) / L2 (path) / L3 (validation).

    Parameters
    ----------
    steps:
        Plan step objects. Each must have ``step_id``, ``inputs``,
        ``outputs``, and optionally ``tool_id`` attributes.
    project_root:
        Root directory for resolving relative paths.
    sequential_fallback:
        When *True*, steps without inferred dependencies inherit the
        preceding step as a dependency (used by the Nextflow runtime
        for linear execution).
    workflow_spec:
        Optional :class:`~abi.contracts.WorkflowSpec` loaded from the
        plugin's ``abi-plugin.yaml``.  When provided:

        * **L1** — the declared ``after`` relationships become the
          ground-truth dependency edges.
        * **L2** — the existing path-level inference cross-validates
          the declared edges.
        * **L3** — mismatches between L1 and L2 emit a ``WARNING``.

        Edges from L1 take priority; L2 supplements edges for steps
        that are not covered by the workflow declaration.
    strict_workflow:
        Raise ``ABIError`` on L1/L2 mismatches instead of only logging them.
        Intended for CI and plugin validation.
    """
    root = Path(project_root or PROJECT_ROOT).resolve()
    step_list = [step for step in steps if not getattr(step, "skipped", False)]

    # ── L1: Literature-declared dependencies ────────────────────────────────
    declared_edges: Dict[str, List[str]] = {}
    if workflow_spec is not None:
        declared_edges = _resolve_declared_edges(step_list, workflow_spec)

    # ── L2: Path-level dataflow inference ───────────────────────────────────
    output_map: Dict[str, tuple[str, str]] = {}
    produced_by_step: Dict[str, Dict[str, str]] = {}

    for step in step_list:
        step_id = str(step.step_id)
        produced: Dict[str, str] = {}
        for key, value in getattr(step, "outputs", {}).items():
            normalized = _normalize_path(value, root)
            if not normalized:
                continue
            produced[str(key)] = normalized
            if _is_shared_output_path(step, str(key), normalized):
                continue
            if normalized in output_map:
                previous_step, previous_key = output_map[normalized]
                raise ABIError(
                    "Duplicate ABI output path in DAG: "
                    f"{normalized} from {previous_step}.{previous_key} and {step_id}.{key}"
                )
            output_map[normalized] = (step_id, str(key))
        produced_by_step[step_id] = produced

    inferred_edges: Dict[str, List[str]] = {str(step.step_id): [] for step in step_list}
    previous_step_id = ""
    for step in step_list:
        step_id = str(step.step_id)
        dependencies: List[str] = []
        consumed: Dict[str, str] = {}
        for key, value in getattr(step, "inputs", {}).items():
            for item_key, normalized in _normalized_input_paths(str(key), value, root):
                consumed[item_key] = normalized
                producer = output_map.get(normalized)
                if producer and producer[0] != step_id and producer[0] not in dependencies:
                    dependencies.append(producer[0])
                elif _input_is_directory(step, str(key)):
                    input_dir = Path(normalized)
                    for output_path, (producer_id, _producer_key) in output_map.items():
                        try:
                            Path(output_path).relative_to(input_dir)
                        except ValueError:
                            continue
                        if producer_id != step_id and producer_id not in dependencies:
                            dependencies.append(producer_id)
        if sequential_fallback and not dependencies and previous_step_id:
            dependencies.append(previous_step_id)
        inferred_edges[step_id] = dependencies
        previous_step_id = step_id

    # ── L3: Cross-validation (only when workflow_spec is provided) ──────────
    if workflow_spec is not None:
        _cross_validate_edges(declared_edges, inferred_edges, strict=strict_workflow)

    # ── Merge: L1 (declared) priority, L2 (inferred) supplement ────────────
    merged_edges: Dict[str, List[str]] = {str(s.step_id): [] for s in step_list}
    for step in step_list:
        step_id = str(step.step_id)
        explicit = getattr(step, "params", {}).get("_explicit_dependencies", [])
        if not isinstance(explicit, list):
            raise ABIError(f"Step {step_id} _explicit_dependencies must be a list")
        unknown = sorted(str(dep) for dep in explicit if str(dep) not in merged_edges)
        if unknown:
            raise ABIError(f"Step {step_id} has unknown explicit dependencies: {unknown}")
        declared = declared_edges.get(step_id, [])
        inferred = inferred_edges.get(step_id, [])
        # Declared edges take priority; inferred edges fill gaps
        combined: Dict[str, None] = {}
        for dep in explicit:
            combined[str(dep)] = None
        for dep in declared:
            combined[dep] = None
        for dep in inferred:
            if dep not in combined:
                combined[dep] = None
        merged_edges[step_id] = list(combined)

    # ── Build StepBindings from merged edges ────────────────────────────────
    bindings: List[StepBinding] = []
    for step in step_list:
        step_id = str(step.step_id)
        consumed_paths: Dict[str, str] = {}
        for key, value in getattr(step, "inputs", {}).items():
            for item_key, normalized in _normalized_input_paths(str(key), value, root):
                consumed_paths[item_key] = normalized
        bindings.append(
            StepBinding(
                step=step,
                process_name=process_name(step_id),
                dependencies=merged_edges.get(step_id, []),
                produced_paths=produced_by_step.get(step_id, {}),
                consumed_paths=consumed_paths,
            )
        )

    order = _topological_order([str(s.step_id) for s in step_list], merged_edges)
    roots = [sid for sid in order if not merged_edges.get(sid)]
    return ABIDAG(bindings=bindings, edges=merged_edges, roots=roots, topological_order=order)


def _resolve_declared_edges(
    step_list: List[Any],
    workflow_spec: WorkflowSpec,
) -> Dict[str, List[str]]:
    """Map a :class:`WorkflowSpec` onto plan steps via ``tool_id`` matching.

    Returns a dict ``{plan_step_id: [dependency_plan_step_ids]}`` built
    from the workflow's ``after`` declarations.
    """
    # Preserve every occurrence.  A tool commonly appears once per sample;
    # binding through a single tool_id would otherwise connect all samples to
    # whichever occurrence happened to be listed last.
    tool_to_plan: Dict[str, List[Any]] = {}
    for step in step_list:
        tool_id = str(getattr(step, "tool_id", ""))
        if tool_id:
            tool_to_plan.setdefault(tool_id, []).append(step)

    # Build workflow_step_id → workflow_step mapping
    wf_by_id: Dict[str, Any] = {s.id: s for s in workflow_spec.steps}
    for wf_step in workflow_spec.steps:
        missing = [dependency for dependency in wf_step.after if dependency not in wf_by_id]
        if missing:
            raise ABIError(
                f"Workflow step {wf_step.id!r} references undefined dependencies: {missing}"
            )

    declared: Dict[str, List[str]] = {}
    for wf_step in workflow_spec.steps:
        plan_steps = tool_to_plan.get(wf_step.tool, [])
        if not plan_steps:
            # Workflow step references a tool not in the current plan;
            # this is normal — the tool may be in an optional path.
            continue
        for plan_step in plan_steps:
            plan_step_id = str(plan_step.step_id)
            sample_id = getattr(plan_step, "sample_id", None)
            deps: List[str] = []
            for after_id in wf_step.after:
                dep_step = wf_by_id.get(after_id)
                if dep_step is None:
                    continue
                candidates = list(tool_to_plan.get(dep_step.tool, []))
                if sample_id is not None:
                    candidates = [
                        candidate
                        for candidate in candidates
                        if getattr(candidate, "sample_id", None) in {sample_id, None}
                    ]
                for candidate in candidates:
                    dep_plan_id = str(candidate.step_id)
                    if dep_plan_id != plan_step_id and dep_plan_id not in deps:
                        deps.append(dep_plan_id)
            declared[plan_step_id] = deps

    return declared


def _cross_validate_edges(
    declared: Dict[str, List[str]],
    inferred: Dict[str, List[str]],
    *,
    strict: bool = False,
) -> None:
    """L3: emit WARNING when declared and inferred edges disagree.

    An edge present in *declared* but absent from *inferred* suggests
    that the plugin author asserts a dependency the dataflow does not
    capture (e.g. a semantic dependency).  An edge present in *inferred*
    but absent from *declared* suggests a path-level dependency that the
    workflow declaration may have omitted — possibly a genuine gap.
    """
    mismatch_messages: List[str] = []
    all_steps = set(declared) | set(inferred)
    for step_id in sorted(all_steps):
        declared_deps = set(declared.get(step_id, []))
        inferred_deps = set(inferred.get(step_id, []))
        if declared_deps == inferred_deps:
            continue
        only_declared = declared_deps - inferred_deps
        only_inferred = inferred_deps - declared_deps
        parts: List[str] = [f"DAG mismatch for step {step_id!r}:"]
        if only_declared:
            parts.append(f"declared-but-not-inferred={sorted(only_declared)}")
        if only_inferred:
            parts.append(f"inferred-but-not-declared={sorted(only_inferred)}")
        message = " ".join(parts)
        mismatch_messages.append(message)
        logger.warning(message)
    if strict and mismatch_messages:
        raise ABIError("; ".join(mismatch_messages))


def process_name(step_id: str) -> str:
    """Return a Nextflow-safe process name for an ABI step id."""
    name = re.sub(r"[^A-Za-z0-9_]+", "_", step_id).strip("_").upper()
    if not name:
        name = "ABI_STEP"
    if name[0].isdigit():
        name = f"STEP_{name}"
    return name


def _normalize_path(value: Any, project_root: Path) -> str:
    if value in (None, ""):
        return ""
    if not isinstance(value, (str, Path)):
        return ""
    text = str(value)
    path = Path(text)
    if not path.is_absolute():
        path = project_root / path
    return str(path)


def _input_is_directory(step: Any, key: str) -> bool:
    """Return whether a consumed input is declared as a directory."""
    contract = getattr(step, "params", {}).get("_contract", {})
    if not isinstance(contract, Mapping):
        return False
    input_specs = contract.get("inputs", {})
    if not isinstance(input_specs, Mapping):
        return False
    spec = input_specs.get(key, {})
    return isinstance(spec, Mapping) and str(spec.get("type", "")) == "directory"


def _normalized_input_paths(key: str, value: Any, project_root: Path) -> List[tuple[str, str]]:
    """Normalize scalar or list-valued inputs without dropping aggregation edges."""
    values = value if isinstance(value, (list, tuple, set)) else [value]
    normalized: List[tuple[str, str]] = []
    for index, item in enumerate(values):
        path = _normalize_path(item, project_root)
        if path:
            item_key = key if len(values) == 1 else f"{key}[{index}]"
            normalized.append((item_key, path))
    return normalized


def _is_shared_output_path(step: Any, key: str, normalized_path: str) -> bool:
    contract = getattr(step, "params", {}).get("_contract", {})
    if isinstance(contract, Mapping):
        output_specs = contract.get("outputs", {})
        spec = output_specs.get(key, {}) if isinstance(output_specs, Mapping) else {}
        if isinstance(spec, Mapping):
            declared_type = str(spec.get("type", ""))
            if declared_type == "directory":
                return True
            if declared_type == "file":
                return False
    if key in {"output_dir", "outdir", "work_dir", "report_dir", "tables_dir"}:
        return True
    path = Path(normalized_path)
    if path.exists():
        return path.is_dir()
    if not path.suffix:
        # Extensionless paths may be directories OR files like README/Makefile.
        # Only treat as shared-output dir if the name suggests a directory.
        # 无扩展名路径可能是目录也可能是 README/Makefile 这样的文件。
        # 仅当名称表明是目录时才视为共享输出目录。
        dir_indicators = {"output", "result", "tmp", "temp", "log", "db", "index", "ref"}
        return path.name.lower() in dir_indicators or path.name.endswith("_dir")
    return False


def _topological_order(step_ids: List[str], edges: Mapping[str, List[str]]) -> List[str]:
    visited: Dict[str, str] = {}
    order: List[str] = []

    def visit(step_id: str) -> None:
        state = visited.get(step_id)
        if state == "done":
            return
        if state == "visiting":
            raise ABIError(f"Cycle detected in ABI DAG at step {step_id}")
        visited[step_id] = "visiting"
        for dependency in edges.get(step_id, []):
            visit(dependency)
        visited[step_id] = "done"
        order.append(step_id)

    for step_id in step_ids:
        visit(step_id)
    return order
