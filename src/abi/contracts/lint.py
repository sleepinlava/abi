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
import string
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterator, List, Mapping, Optional, Set

import yaml

__all__ = [
    "LintFinding",
    "lint_assertion_syntax",
    "lint_dag",
    "lint_tool_contracts",
    "run_contract_lint",
    "validate_pipeline_template_params",
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
# Pipeline template parameter checks
# ═══════════════════════════════════════════════════════════════════════════

_STATIC_TEMPLATE_FIELDS = {
    "outdir",
    "category_dir",
    "threads",
    "mode",
    "project_name",
    "sample",
    "resources",
}
_DYNAMIC_TEMPLATE_PREFIXES = ("active_", "upstream_")


def validate_pipeline_template_params(plugin_root: Path) -> list[str]:
    """Return unresolved template fields in a plugin ``pipeline_dag.yaml``.

    DAG path and param templates are resolved from a small planning context:
    config defaults, per-node params, standard path fields such as ``outdir``,
    and dynamic upstream selector names such as ``active_assembly_node``.
    Missing fields usually mean a runtime command template will receive an
    unresolved placeholder instead of a concrete parameter.
    """
    root = Path(plugin_root)
    dag_path = root / "pipeline_dag.yaml"
    if not dag_path.exists():
        return []

    with dag_path.open("r", encoding="utf-8") as handle:
        dag_spec = yaml.safe_load(handle) or {}
    if not isinstance(dag_spec, Mapping):
        return [f"{dag_path}: pipeline_dag.yaml must contain a mapping"]

    config_fields = _pipeline_config_fields(root)
    violations: list[str] = []
    for node in _normalize_dag_nodes(dag_spec):
        node_id = str(node.get("id", "<unknown>"))
        node_params = node.get("params")
        node_param_fields = (
            set(str(key) for key in node_params) if isinstance(node_params, Mapping) else set()
        )
        allowed_fields = set(_STATIC_TEMPLATE_FIELDS) | config_fields | node_param_fields
        if str(node.get("scope", "per_sample")) != "cross_sample":
            allowed_fields.add("sample_id")

        for location, template in _iter_pipeline_template_strings(node):
            for field in _template_field_roots(template):
                if _is_allowed_template_field(field, allowed_fields):
                    continue
                violations.append(
                    f"{dag_path}: {node_id}.{location} references unresolved "
                    f"template field {field!r}"
                )
    return violations


def _pipeline_config_fields(plugin_root: Path) -> set[str]:
    config_path = plugin_root / "config_default.yaml"
    if not config_path.exists():
        return set()
    with config_path.open("r", encoding="utf-8") as handle:
        config = yaml.safe_load(handle) or {}
    if not isinstance(config, Mapping):
        return set()
    return {str(key) for key in config}


def _iter_pipeline_template_strings(node: Mapping[str, Any]) -> Iterator[tuple[str, str]]:
    for location, value in _iter_template_values(node.get("params"), ("params",)):
        yield location, value

    for command_key in ("command", "command_template"):
        command_value = node.get(command_key)
        if isinstance(command_value, str) and "{" in command_value:
            yield command_key, command_value

    inputs = node.get("inputs")
    if isinstance(inputs, Mapping):
        for input_name, input_spec in inputs.items():
            if not isinstance(input_spec, Mapping):
                continue
            for key in ("path", "source", "fallback", "default"):
                input_value = input_spec.get(key)
                if isinstance(input_value, str) and "{" in input_value:
                    yield f"inputs.{input_name}.{key}", input_value

    outputs = node.get("outputs")
    if isinstance(outputs, Mapping):
        for output_name, output_spec in outputs.items():
            if not isinstance(output_spec, Mapping):
                continue
            output_value = output_spec.get("path")
            if isinstance(output_value, str) and "{" in output_value:
                yield f"outputs.{output_name}.path", output_value


def _iter_template_values(value: Any, path: tuple[str, ...]) -> Iterator[tuple[str, str]]:
    if isinstance(value, str):
        if "{" in value:
            yield ".".join(path), value
        return
    if isinstance(value, Mapping):
        for key, nested in value.items():
            yield from _iter_template_values(nested, (*path, str(key)))
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            yield from _iter_template_values(nested, (*path, str(index)))


def _template_field_roots(template: str) -> set[str]:
    fields: set[str] = set()
    formatter = string.Formatter()
    try:
        parsed = list(formatter.parse(template))
    except ValueError:
        return fields
    for _, field_name, format_spec, _ in parsed:
        if field_name:
            fields.add(field_name.split(".", 1)[0].split("[", 1)[0])
        if format_spec and "{" in format_spec:
            fields.update(_template_field_roots(format_spec))
    return {field for field in fields if field}


def _is_allowed_template_field(field: str, allowed_fields: set[str]) -> bool:
    return field in allowed_fields or field.startswith(_DYNAMIC_TEMPLATE_PREFIXES)


# ═══════════════════════════════════════════════════════════════════════════
# Tool contract checks
# ═══════════════════════════════════════════════════════════════════════════


def lint_tool_contracts(
    contracts: Dict[str, Dict[str, Any]],
    registry_tool_ids: Optional[Set[str]] = None,
    registry_tools: Optional[Mapping[str, Mapping[str, Any]]] = None,
) -> List[LintFinding]:
    """Check tool contracts for consistency with the registry.

    Args:
        contracts: Dict of ``tool_id → contract_dict`` from ``load_tool_contracts()``.
        registry_tool_ids: Optional set of tool IDs from the registry for
            cross-referencing.
        registry_tools: Optional registry metadata keyed by tool ID.  When
            provided, executable, category, and command template parity are
            enforced so the contract cannot describe a command different from
            the one the runtime actually executes.

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

    if registry_tools:
        for tool_id in sorted(set(contracts) & set(registry_tools)):
            contract = contracts[tool_id]
            registry = registry_tools[tool_id]
            execution = contract.get("execution", {})
            if not isinstance(execution, Mapping):
                continue
            comparisons = {
                "category": (registry.get("category"), contract.get("category")),
                "executable": (registry.get("executable"), execution.get("executable")),
                "command_template": (
                    registry.get("command_template"),
                    execution.get("command_template"),
                ),
            }
            for field, (runtime_value, contract_value) in comparisons.items():
                runtime_normalized = " ".join(str(runtime_value or "").split())
                contract_normalized = " ".join(str(contract_value or "").split())
                if runtime_normalized == contract_normalized:
                    continue
                findings.append(
                    LintFinding(
                        severity="error",
                        check="registry_contract_mismatch",
                        detail=(
                            f"Tool {tool_id!r}: registry {field} differs from tool contract {field}"
                        ),
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
    registry_tools: Mapping[str, Mapping[str, Any]] | None = None,
) -> Dict[str, Any]:
    """Run all contract lint checks and return a structured result.

    Args:
        dag_spec: Parsed ``pipeline_dag.yaml``.
        contracts: Optional parsed tool contracts (tool_id → contract).
        registry_tool_ids: Optional set of tool IDs from the registry.
        registry_tools: Optional runtime registry metadata keyed by tool ID.

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
        all_findings.extend(
            lint_tool_contracts(
                contracts,
                registry_tool_ids,
                registry_tools=registry_tools,
            )
        )
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
