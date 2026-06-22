"""Static analysis for ABI pipeline DAG and tool contracts (B18/B20/B19).

Provides ``run_contract_lint()`` — the entry point called by the
``abi contract-lint`` CLI command — and the individual check functions
that can also be used programmatically.

Checks performed:
  1. DAG cycle detection (topological sort failure → cycle report).
  2. Broken ``depends_on`` references (node references a non-existent node).
  3. Orphan nodes (nodes with no dependents and no dependencies — may be dead code).
  4. Duplicate tool_id or step_id in contracts.
  5. Assertion expression syntax validation (compile-check each expression
     in the restricted eval namespace).

Design / 设计
--------------
- Each lint function returns a list of ``LintFinding`` named tuples so
  callers can filter by severity or check type.
- No runtime tool execution — purely static analysis of YAML metadata.
- Thread-safe: all functions are pure (no shared mutable state).
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Set

__all__ = [
    "LintFinding",
    "lint_assertion_syntax",
    "lint_dag",
    "lint_tool_contracts",
    "run_contract_lint",
]

# ═══════════════════════════════════════════════════════════════════════════
# Data types
# ═══════════════════════════════════════════════════════════════════════════


@dataclass
class LintFinding:
    """A single static analysis finding."""

    severity: str  # "error", "warning"
    check: str  # "cycle", "broken_dep", "orphan", "assertion_syntax", ...
    detail: str
    location: str = ""  # node_id, tool_id, or file path


# ═══════════════════════════════════════════════════════════════════════════
# DAG checks (B18 + B19)
# ═══════════════════════════════════════════════════════════════════════════


def _normalize_dag_nodes(dag_spec: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """Normalize DAG nodes from either list or dict format.

    Both ``[{"id": "A", ...}, {"id": "B", ...}]`` (list format) and
    ``{"A": {...}, "B": {...}}`` (dict/mapping format) are supported.
    Dict-format nodes have their key injected as the ``id`` field.
    """
    nodes_raw = dag_spec.get("nodes", [])
    if isinstance(nodes_raw, Mapping):
        return [
            {"id": str(key), **({} if not isinstance(val, Mapping) else dict(val))}
            for key, val in nodes_raw.items()
        ]
    if isinstance(nodes_raw, list):
        return [dict(n) for n in nodes_raw if isinstance(n, Mapping)]
    return []


def lint_dag(dag_spec: Mapping[str, Any]) -> List[LintFinding]:
    """Check a pipeline DAG for structural issues.

    Args:
        dag_spec: The parsed ``pipeline_dag.yaml`` content.  Expected to have
            a ``nodes`` key containing a list of node dicts or a mapping of
            node-id → node-dict.

    Returns:
        List of ``LintFinding`` — empty if the DAG is clean.
    """
    findings: List[LintFinding] = []

    nodes: List[Dict[str, Any]] = _normalize_dag_nodes(dag_spec)
    if not nodes:
        findings.append(
            LintFinding(
                severity="error",
                check="empty_dag",
                detail="DAG contains no nodes",
                location="pipeline_dag.yaml",
            )
        )
        return findings

    # Build index
    node_ids: Set[str] = {str(n["id"]) for n in nodes if "id" in n}
    node_by_id: Dict[str, Dict[str, Any]] = {str(n["id"]): n for n in nodes if "id" in n}

    # 1. Detect duplicate IDs
    seen: Set[str] = set()
    for node in nodes:
        nid = str(node.get("id", ""))
        if not nid:
            findings.append(
                LintFinding(
                    severity="error",
                    check="missing_id",
                    detail="Node missing 'id' field",
                    location=str(node),
                )
            )
            continue
        if nid in seen:
            findings.append(
                LintFinding(
                    severity="error",
                    check="duplicate_id",
                    detail=f"Duplicate node id {nid!r}",
                    location=nid,
                )
            )
        seen.add(nid)

    # 2. Broken depends_on references (B18)
    for node in nodes:
        nid = str(node.get("id", ""))
        deps = node.get("depends_on", [])
        if isinstance(deps, str):
            deps = [deps]
        for dep in deps:
            dep_str = str(dep)
            if dep_str not in node_ids:
                findings.append(
                    LintFinding(
                        severity="error",
                        check="broken_dep",
                        detail=f"Node {nid!r} depends on {dep_str!r} which does not exist",
                        location=nid,
                    )
                )

    # 3. Cycle detection via Kahn's algorithm (B19)
    # Build adjacency and in-degree
    adj: Dict[str, List[str]] = {nid: [] for nid in node_ids}
    in_degree: Dict[str, int] = {nid: 0 for nid in node_ids}
    for node in nodes:
        nid = str(node.get("id", ""))
        if nid not in adj:
            continue
        deps = node.get("depends_on", [])
        if isinstance(deps, str):
            deps = [deps]
        for dep in deps:
            dep_str = str(dep)
            if dep_str in adj:
                adj[dep_str].append(nid)
                in_degree[nid] = in_degree.get(nid, 0) + 1

    # Topological sort
    queue = [nid for nid, deg in in_degree.items() if deg == 0]
    sorted_count = 0
    while queue:
        current = queue.pop(0)
        sorted_count += 1
        for neighbor in adj.get(current, []):
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    if sorted_count != len(node_ids):
        # Find nodes in cycles
        in_cycle = {nid for nid, deg in in_degree.items() if deg > 0}
        findings.append(
            LintFinding(
                severity="error",
                check="cycle",
                detail=f"DAG contains cycles involving {len(in_cycle)} node(s): "
                f"{', '.join(sorted(in_cycle)[:10])}",
                location="pipeline_dag.yaml",
            )
        )

    # 4. Orphan nodes (no dependencies and no dependents) — warning only
    has_dependents: Set[str] = set()
    for node in nodes:
        deps = node.get("depends_on", [])
        if isinstance(deps, str):
            deps = [deps]
        for dep in deps:
            if str(dep) in node_ids:
                has_dependents.add(str(dep))

    for nid in sorted(node_ids):
        node = node_by_id.get(nid, {})
        deps = node.get("depends_on", [])
        if isinstance(deps, str):
            deps = [deps]
        has_deps = len(deps) > 0
        is_depended_on = nid in has_dependents
        if not has_deps and not is_depended_on:
            findings.append(
                LintFinding(
                    severity="warning",
                    check="orphan",
                    detail=f"Node {nid!r} has no dependencies and no dependents",
                    location=nid,
                )
            )

    contract_keys = {
        "min_size",
        "extensions",
        "contains",
        "min_files",
        "min_contigs",
        "required_keys",
        "schema",
    }
    for node in nodes:
        nid = str(node.get("id", ""))
        outputs = node.get("outputs", {})
        if not isinstance(outputs, Mapping):
            continue
        for output_name, output_spec in outputs.items():
            if not isinstance(output_spec, Mapping):
                continue
            misplaced = sorted(contract_keys & set(output_spec))
            if misplaced:
                findings.append(
                    LintFinding(
                        severity="error",
                        check="misplaced_output_contract",
                        detail=(
                            f"Output {output_name!r} places contract checks {misplaced} "
                            "outside the required 'contract' mapping"
                        ),
                        location=nid,
                    )
                )

    return findings


# ═══════════════════════════════════════════════════════════════════════════
# Assertion syntax checks (B20)
# ═══════════════════════════════════════════════════════════════════════════


def _precheck_assertion_expression(expression: str) -> Optional[str]:
    """Check whether an assertion expression is valid in the runtime namespace.

    This remains a static check: it parses the expression and rejects names
    that the runtime assertion evaluator does not provide.  It never evaluates
    user-controlled YAML.
    """
    # Normalise natural-language syntax
    expr = re.sub(r"(\S+)\s+exists\s*$", r"exists(\1)", expression.strip())
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as exc:
        return f"Syntax error in assertion {expression!r}: {exc}"
    allowed_names = {
        "output_json",
        "output_files",
        "return_code",
        "int",
        "float",
        "str",
        "bool",
        "len",
        "abs",
        "min",
        "max",
        "sum",
        "any",
        "all",
        "exists",
        "isclose",
        "round",
    }
    unknown_names = sorted(
        {
            node.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Name) and node.id not in allowed_names
        }
    )
    if unknown_names:
        return f"Unknown assertion variable(s): {', '.join(unknown_names)}"
    return None


def lint_assertion_syntax(
    dag_spec: Mapping[str, Any],
) -> List[LintFinding]:
    """Check all assertion expressions in a DAG for syntax validity (B20).

    Each node in the DAG may declare ``assertions`` — a list of Python
    expression strings.  This function compiles each one to detect syntax
    errors before runtime.
    """
    findings: List[LintFinding] = []
    nodes = _normalize_dag_nodes(dag_spec)
    for node in nodes:
        nid = str(node.get("id", ""))
        assertions = node.get("assertions", [])
        if isinstance(assertions, str):
            assertions = [assertions]
        for assertion in assertions:
            error = _precheck_assertion_expression(str(assertion))
            if error:
                findings.append(
                    LintFinding(
                        severity="error",
                        check="assertion_syntax",
                        detail=error,
                        location=nid,
                    )
                )
    return findings


# ═══════════════════════════════════════════════════════════════════════════
# Tool contract checks
# ═══════════════════════════════════════════════════════════════════════════


def lint_tool_contracts(
    contracts: Dict[str, Dict[str, Any]],
    registry_tool_ids: Optional[Set[str]] = None,
) -> List[LintFinding]:
    """Check tool contracts for consistency with the registry.

    Args:
        contracts: Dict of ``tool_id → contract_dict`` from ``load_tool_contracts()``.
        registry_tool_ids: Optional set of tool IDs from the registry for
            cross-referencing.

    Returns:
        List of ``LintFinding``.
    """
    findings: List[LintFinding] = []

    for tool_id, contract in contracts.items():
        # Check required fields
        for field in ("name", "category", "purpose"):
            if not contract.get(field):
                findings.append(
                    LintFinding(
                        severity="error",
                        check="missing_field",
                        detail=f"Tool contract {tool_id!r} missing required field {field!r}",
                        location=tool_id,
                    )
                )

        # Check execution block
        execution = contract.get("execution", {})
        if not isinstance(execution, Mapping):
            findings.append(
                LintFinding(
                    severity="error",
                    check="missing_field",
                    detail=f"Tool contract {tool_id!r} missing 'execution' mapping",
                    location=tool_id,
                )
            )
        else:
            for exec_field in ("executable", "command_template"):
                # env_name is resolved at runtime from environments.yaml;
                # omitting it from contracts is no longer a warning.
                if not execution.get(exec_field):
                    findings.append(
                        LintFinding(
                            severity="warning",
                            check="missing_field",
                            detail=f"Tool {tool_id!r}: execution.{exec_field} is empty",
                            location=tool_id,
                        )
                    )

    # Cross-reference with registry
    if registry_tool_ids:
        contract_ids = set(contracts)
        missing_from_registry = contract_ids - registry_tool_ids
        for tool_id in sorted(missing_from_registry):
            findings.append(
                LintFinding(
                    severity="warning",
                    check="missing_contract",
                    detail=f"Tool {tool_id!r} has a contract but is not in the registry",
                    location=tool_id,
                )
            )
        missing_contracts = registry_tool_ids - contract_ids
        for tool_id in sorted(missing_contracts):
            findings.append(
                LintFinding(
                    severity="warning",
                    check="missing_contract",
                    detail=f"Tool {tool_id!r} is in registry but has no contract file",
                    location=tool_id,
                )
            )

    return findings


def lint_resource_blocks(
    contracts: Dict[str, Dict[str, Any]],
) -> List[LintFinding]:
    """Check tool contracts for ``resources:`` blocks (warning-level).

    A missing resources block is a warning, not an error — it is optional
    for backward compatibility but recommended for HPC/Nextflow export.
    / 缺少 resources 块是警告而非错误——对向后兼容性可选，但推荐用于 HPC/Nextflow。
    """
    findings: List[LintFinding] = []
    for tool_id, contract in sorted(contracts.items()):
        resources = contract.get("resources")
        if not isinstance(resources, Mapping):
            findings.append(
                LintFinding(
                    severity="warning",
                    check="missing_resources",
                    detail=f"Tool {tool_id!r}: missing 'resources' block — recommended for HPC",
                    location=tool_id,
                )
            )
            continue
        cpu = resources.get("cpu")
        if cpu is not None and (not isinstance(cpu, int) or cpu < 1):
            findings.append(
                LintFinding(
                    severity="error",
                    check="invalid_resources",
                    detail=f"Tool {tool_id!r}: resources.cpu must be positive integer, got {cpu!r}",
                    location=tool_id,
                )
            )
        for field in ("memory", "walltime"):
            val = resources.get(field)
            if val is not None and (not isinstance(val, str) or not val.strip()):
                findings.append(
                    LintFinding(
                        severity="warning",
                        check="empty_resources",
                        detail=f"Tool {tool_id!r}: resources.{field} is empty",
                        location=tool_id,
                    )
                )
    return findings


# ═══════════════════════════════════════════════════════════════════════════
# Orchestrator
# ═══════════════════════════════════════════════════════════════════════════


def run_contract_lint(
    dag_spec: Mapping[str, Any],
    contracts: Dict[str, Dict[str, Any]] | None = None,
    registry_tool_ids: Set[str] | None = None,
) -> Dict[str, Any]:
    """Run all contract lint checks and return a structured result.

    Args:
        dag_spec: Parsed ``pipeline_dag.yaml``.
        contracts: Optional parsed tool contracts (tool_id → contract).
        registry_tool_ids: Optional set of tool IDs from the registry.

    Returns:
        A dict with keys ``findings`` (list of LintFinding as dicts),
        ``error_count``, ``warning_count``, and ``passed`` (bool).
    """
    all_findings: List[LintFinding] = []

    # DAG checks
    all_findings.extend(lint_dag(dag_spec))

    # Assertion syntax
    all_findings.extend(lint_assertion_syntax(dag_spec))

    # Contract checks
    if contracts is not None:
        all_findings.extend(lint_tool_contracts(contracts, registry_tool_ids))
        all_findings.extend(lint_resource_blocks(contracts))

    error_count = sum(1 for f in all_findings if f.severity == "error")
    warning_count = sum(1 for f in all_findings if f.severity == "warning")

    return {
        "findings": [
            {
                "severity": f.severity,
                "check": f.check,
                "detail": f.detail,
                "location": f.location,
            }
            for f in all_findings
        ],
        "error_count": error_count,
        "warning_count": warning_count,
        "passed": error_count == 0,
    }
