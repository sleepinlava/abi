"""Compiled Execution Plan — backend-neutral compilation from ExecutionPlan.

Design doc ref: §4.4 Compiled Execution Plan, C08.

Converts a planner-resolved ``ExecutionPlan`` into an immutable ``CompiledPlan``
with resolved resources, environments, execution kinds, and validated invariants.
Runs in shadow mode initially: compile and validate every built-in plugin without
changing runtime behavior.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Mapping, Set

from abi.errors import PlanIntegrityError, ToolResolutionError, UnsupportedExecutionError
from abi.execution_policy import ExecutionPolicy, apply_resource_policy
from abi.path_policy import InputPolicyError, resolve_within
from abi.tool_catalog import ToolCatalog
from abi.tools import ResourceSpec

__all__ = [
    "ExecutionKind",
    "CompiledStep",
    "CompiledPlan",
    "compile_plan",
    "CompilationWarning",
]


class ExecutionKind(str, Enum):
    """Backend-neutral execution kind for a compiled step."""

    EXTERNAL = "external"
    INTERNAL_WORKER = "internal_worker"
    INTERNAL_DRIVER = "internal_driver"


@dataclass
class CompilationWarning:
    """Non-fatal difference between compiled and current behavior."""

    step_id: str
    message: str


@dataclass(frozen=True)
class CompiledStep:
    """A single step as resolved by the compiler.

    All fields that downstream adapters need are resolved here; adapters
    must not re-resolve resources, environments, or execution kinds.
    """

    step_id: str
    tool_id: str
    category: str
    sample_id: str | None
    execution_kind: ExecutionKind

    # ── Dependencies ──
    dependencies: List[str] = field(default_factory=list)

    # ── Resolved resources ──
    resources: ResourceSpec = field(default_factory=ResourceSpec)

    # ── Resolved environment ──
    env_name: str = ""
    container_image: str | None = None

    # ── I/O ──
    inputs: Dict[str, Any] = field(default_factory=dict)
    outputs: Dict[str, Any] = field(default_factory=dict)
    params: Dict[str, Any] = field(default_factory=dict)

    # ── Validation ──
    validated_paths: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class CompiledPlan:
    """Validated, backend-neutral compilation of an ``ExecutionPlan``.

    Every invariant tested by :func:`compile_plan` is guaranteed by
    construction after a successful compile.
    """

    project_name: str
    mode: str
    threads: int
    outdir: Path

    steps: List[CompiledStep]
    enabled_steps: List[str] = field(default_factory=list)
    selected_tools: List[str] = field(default_factory=list)
    analysis_type: str = "metagenomic_plasmid"

    # ── Non-fatal compilation notes ──
    warnings: List[CompilationWarning] = field(default_factory=list)

    def get(self, step_id: str) -> CompiledStep:
        """Return the compiled step for *step_id*."""
        for s in self.steps:
            if s.step_id == step_id:
                return s
        raise KeyError(step_id)

    @property
    def step_ids(self) -> List[str]:
        return [s.step_id for s in self.steps]

    @property
    def external_steps(self) -> List[CompiledStep]:
        return [s for s in self.steps if s.execution_kind == ExecutionKind.EXTERNAL]

    @property
    def internal_worker_steps(self) -> List[CompiledStep]:
        return [s for s in self.steps if s.execution_kind == ExecutionKind.INTERNAL_WORKER]

    @property
    def internal_driver_steps(self) -> List[CompiledStep]:
        return [s for s in self.steps if s.execution_kind == ExecutionKind.INTERNAL_DRIVER]


# ── Compilation ──────────────────────────────────────────────────────────────


def compile_plan(
    plan: Any,  # ExecutionPlan — avoids hard import cycle
    *,
    catalog: ToolCatalog | None = None,
    policy: ExecutionPolicy | None = None,
    outdir: Path | None = None,
) -> CompiledPlan:
    """Compile an ``ExecutionPlan`` into a validated ``CompiledPlan``.

    Parameters
    ----------
    plan:
        Planner-resolved ``ExecutionPlan``.
    catalog:
        ``ToolCatalog`` for resolving tool environments and resources.
        If ``None``, builds one from the project root.
    policy:
        ``ExecutionPolicy`` with invocation and workflow overrides.
    outdir:
        Explicit output root.  Defaults to ``plan.outdir`` as a ``Path``.

    Returns
    -------
    CompiledPlan
        Validated, frozen compiled plan.  Raises on invariant violations.

    Raises
    ------
    PlanIntegrityError
        A compiled-plan invariant is violated (e.g., missing or duplicate
        steps, undefined dependencies, cycle).
    UnsupportedExecutionError
        A step has an execution kind the caller cannot handle.
    """
    if catalog is None:
        catalog = ToolCatalog.from_project_root()

    steps = plan.steps or []
    planned_dir = Path(outdir) if outdir else Path(plan.outdir)
    warnings: List[CompilationWarning] = []

    compiled_steps: List[CompiledStep] = []
    enabled_step_ids: Set[str] = set()

    for pstep in steps:
        if getattr(pstep, "skipped", False):
            continue

        sid = pstep.step_id
        enabled_step_ids.add(sid)

        kind = _resolve_execution_kind(pstep, warnings)
        if kind == ExecutionKind.EXTERNAL and not catalog.has(str(pstep.tool_id)):
            raise ToolResolutionError(
                f"Step {sid!r} references unknown external tool {pstep.tool_id!r}"
            )
        resources = _resolve_resources(pstep, catalog, policy, warnings)
        env_name = _resolve_environment(pstep, catalog, warnings)
        container = _resolve_container(pstep, catalog, warnings)
        deps = _resolve_dependencies(pstep)
        validated = _validate_paths(pstep, planned_dir)

        cstep = CompiledStep(
            step_id=sid,
            tool_id=pstep.tool_id,
            category=pstep.category,
            sample_id=pstep.sample_id,
            execution_kind=kind,
            dependencies=deps,
            resources=resources,
            env_name=env_name,
            container_image=container,
            inputs=dict(pstep.inputs or {}),
            outputs=dict(pstep.outputs or {}),
            params=dict(pstep.params or {}),
            validated_paths=validated,
        )
        compiled_steps.append(cstep)

    # ── Invariants ──
    compiled = CompiledPlan(
        project_name=plan.project_name or "",
        mode=plan.mode or "auto",
        threads=plan.threads or 1,
        outdir=planned_dir,
        steps=compiled_steps,
        enabled_steps=sorted(enabled_step_ids),
        selected_tools=list(plan.selected_tools or []),
        analysis_type=plan.analysis_type or "",
        warnings=warnings,
    )

    _validate_invariants(compiled, enabled_step_ids)
    return compiled


# ── Resolvers ────────────────────────────────────────────────────────────────


def _resolve_execution_kind(pstep: Any, warnings: List[CompilationWarning]) -> ExecutionKind:
    """Determine execution kind from step metadata."""
    tool_id = str(getattr(pstep, "tool_id", "") or "")
    params = dict(getattr(pstep, "params", {}) or {})

    handler = params.get("_internal_handler")
    if handler is not None:
        scope = _get_execution_scope(handler)
        if scope == "worker":
            return ExecutionKind.INTERNAL_WORKER
        if scope == "driver":
            return ExecutionKind.INTERNAL_DRIVER
        warnings.append(
            CompilationWarning(
                step_id=pstep.step_id,
                message=f"Internal handler with unrecognized scope {scope!r}; treating as worker",
            )
        )
        return ExecutionKind.INTERNAL_WORKER

    # tool_id == "internal" without a handler is an error
    if tool_id == "internal":
        raise UnsupportedExecutionError(
            f"Step {pstep.step_id!r} has tool_id='internal' but no _internal_handler"
        )

    return ExecutionKind.EXTERNAL


def _get_execution_scope(handler: Any) -> str:
    """Extract execution_scope from a handler object or dict."""
    if hasattr(handler, "execution_scope"):
        return str(handler.execution_scope)
    if isinstance(handler, Mapping):
        return str(handler.get("execution_scope", "worker"))
    return "worker"


def _resolve_resources(
    pstep: Any,
    catalog: ToolCatalog,
    policy: ExecutionPolicy | None,
    warnings: List[CompilationWarning],
) -> ResourceSpec:
    """Resolve resources for *pstep* using catalog defaults and policy."""
    tool_id = str(getattr(pstep, "tool_id", "") or "")

    # Base from tool catalog
    try:
        if catalog.has(tool_id):
            catalog_spec = catalog.get(tool_id).resources
        else:
            catalog_spec = None
    except Exception:
        catalog_spec = None

    # Apply policy chain
    if policy:
        # catalog_spec holds recommended defaults; use as base.
        # Catalog-level overrides (ResourceOverride form) come later.
        resolved = apply_resource_policy(
            base=catalog_spec or ResourceSpec(),
            catalog=None,
            workflow=None,
            invocation=policy.invocation_overrides,
        )
    else:
        resolved = catalog_spec or ResourceSpec()

    return resolved


def _resolve_environment(
    pstep: Any,
    catalog: ToolCatalog,
    warnings: List[CompilationWarning],
) -> str:
    """Resolve environment name for a step."""
    tool_id = str(getattr(pstep, "tool_id", "") or "")

    try:
        if catalog.has(tool_id):
            return catalog.get(tool_id).env_name
    except Exception:
        pass

    warnings.append(
        CompilationWarning(
            step_id=pstep.step_id,
            message=f"Tool {tool_id!r} not in catalog; no environment resolved",
        )
    )
    return ""


def _resolve_container(
    pstep: Any,
    catalog: ToolCatalog,
    warnings: List[CompilationWarning],
) -> str | None:
    """Resolve container image for a step."""
    tool_id = str(getattr(pstep, "tool_id", "") or "")

    try:
        if catalog.has(tool_id):
            return catalog.get(tool_id).container_image
    except Exception:
        pass

    return None


def _resolve_dependencies(pstep: Any) -> List[str]:
    """Resolve step dependencies from explicit params."""
    params = dict(getattr(pstep, "params", {}) or {})
    deps = params.get("_explicit_dependencies")
    if isinstance(deps, list):
        return [str(d) for d in deps]
    return []


def _validate_paths(pstep: Any, outdir: Path) -> List[str]:
    """Validate every declared output path within *outdir*."""
    validated: List[str] = []
    outputs = dict(getattr(pstep, "outputs", {}) or {})

    for name, value in outputs.items():
        if value is None or value == "":
            continue
        if not isinstance(value, (str, Path)):
            raise PlanIntegrityError(
                f"Step {pstep.step_id!r} output {name!r} must be a path, got {type(value).__name__}"
            )
        try:
            resolve_within(outdir, value, label=f"output {name!r}")
        except InputPolicyError as exc:
            raise PlanIntegrityError(f"Step {pstep.step_id!r}: {exc}") from exc
        validated.append(str(value))

    return validated


# ── Invariant checks ─────────────────────────────────────────────────────────


def _validate_invariants(
    compiled: CompiledPlan,
    enabled_step_ids: Set[str],
) -> None:
    """Validate compiled plan invariants.  Raises on violation."""
    compiled_ids = {s.step_id for s in compiled.steps}

    # Must have at least one step
    if not compiled_ids:
        return

    # Duplicate step IDs
    if len(compiled_ids) != len(compiled.steps):
        seen: Set[str] = set()
        for s in compiled.steps:
            if s.step_id in seen:
                raise PlanIntegrityError(f"Duplicate step_id {s.step_id!r} in compiled plan")
            seen.add(s.step_id)

    # Reference: enabled_steps == compiled_steps
    if enabled_step_ids != compiled_ids:
        extra = compiled_ids - enabled_step_ids
        missing = enabled_step_ids - compiled_ids
        msg_parts: List[str] = []
        if missing:
            msg_parts.append(f"missing={sorted(missing)}")
        if extra:
            msg_parts.append(f"extra={sorted(extra)}")
        raise PlanIntegrityError(
            "Compiled plan steps do not match enabled plan steps: " + "; ".join(msg_parts)
        )

    # All dependencies are defined
    for s in compiled.steps:
        for dep in s.dependencies:
            if dep not in compiled_ids:
                raise PlanIntegrityError(f"Step {s.step_id!r} depends on undefined step {dep!r}")

    # No self-dependency
    for s in compiled.steps:
        if s.step_id in s.dependencies:
            raise PlanIntegrityError(f"Step {s.step_id!r} depends on itself")

    # Cycle check via Kahn's algorithm
    _check_acyclic(compiled)


def _check_acyclic(compiled: CompiledPlan) -> None:
    """Kahn's algorithm: raise if the compiled plan has a cycle."""
    graph: Dict[str, List[str]] = {s.step_id: list(s.dependencies) for s in compiled.steps}
    in_degree: Dict[str, int] = {sid: 0 for sid in graph}

    for sid, deps in graph.items():
        for dep in deps:
            in_degree[sid] += 1

    queue = [sid for sid, deg in in_degree.items() if deg == 0]
    removed = 0

    while queue:
        node = queue.pop(0)
        removed += 1
        for sid, deps in graph.items():
            if node in deps:
                in_degree[sid] -= 1
                if in_degree[sid] == 0:
                    queue.append(sid)

    if removed != len(graph):
        remaining = [sid for sid, deg in in_degree.items() if deg > 0]
        raise PlanIntegrityError(f"Cycle detected in compiled plan: {sorted(remaining)}")
