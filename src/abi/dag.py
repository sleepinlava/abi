"""DAG helpers for ABI execution plans."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping

from abi.config import PROJECT_ROOT
from abi.schemas import ABIError

__all__ = [
    "ABIDAG",
    "StepBinding",
    "infer_dag",
    "process_name",
]


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
) -> ABIDAG:
    """Infer a DAG by matching normalized input paths to prior output paths."""
    root = Path(project_root or PROJECT_ROOT).resolve()
    step_list = [
        step
        for step in steps
        if not getattr(step, "skipped", False) and getattr(step, "tool_id", "") != "internal"
    ]
    output_map: Dict[str, tuple[str, str]] = {}
    produced_by_step: Dict[str, Dict[str, str]] = {}

    for step in step_list:
        step_id = str(step.step_id)
        produced: Dict[str, str] = {}
        for key, value in getattr(step, "outputs", {}).items():
            normalized = _normalize_path(value, root)
            if not normalized:
                continue
            if normalized in output_map:
                previous_step, previous_key = output_map[normalized]
                raise ABIError(
                    "Duplicate ABI output path in DAG: "
                    f"{normalized} from {previous_step}.{previous_key} and {step_id}.{key}"
                )
            output_map[normalized] = (step_id, str(key))
            produced[str(key)] = normalized
        produced_by_step[step_id] = produced

    edges: Dict[str, List[str]] = {str(step.step_id): [] for step in step_list}
    bindings: List[StepBinding] = []
    for step in step_list:
        step_id = str(step.step_id)
        dependencies: List[str] = []
        consumed: Dict[str, str] = {}
        for key, value in getattr(step, "inputs", {}).items():
            normalized = _normalize_path(value, root)
            if not normalized:
                continue
            consumed[str(key)] = normalized
            producer = output_map.get(normalized)
            if producer and producer[0] != step_id and producer[0] not in dependencies:
                dependencies.append(producer[0])
        edges[step_id] = dependencies
        bindings.append(
            StepBinding(
                step=step,
                process_name=process_name(step_id),
                dependencies=dependencies,
                produced_paths=produced_by_step.get(step_id, {}),
                consumed_paths=consumed,
            )
        )

    order = _topological_order([str(step.step_id) for step in step_list], edges)
    roots = [step_id for step_id in order if not edges.get(step_id)]
    return ABIDAG(bindings=bindings, edges=edges, roots=roots, topological_order=order)


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
    text = str(value)
    if "NOT_CONFIGURED" in text:
        return ""
    path = Path(text)
    if not path.is_absolute():
        path = project_root / path
    return str(path)


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
