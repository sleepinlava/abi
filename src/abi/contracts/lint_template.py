"""Template linting — validate all path and command templates for missing parameters.

This module provides ``lint_templates()`` which runs every template string
through ``SafeFormatDict`` in strict mode and reports all missing parameter
references.  Use it via ``abi lint-template`` to catch template bugs early.
"""

from __future__ import annotations

import logging
import string
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, List, Mapping

from abi.errors import MissingTemplateParamError
from abi.tools import SafeFormatDict

_logger = logging.getLogger("abi.lint_template")

__all__ = ["TemplateFinding", "lint_templates"]


_COMMON_TEMPLATE_FIELDS = {
    "abundance",
    "abundance_label",
    "alignment",
    "bam",
    "category_dir",
    "database",
    "env_name",
    "mode",
    "outdir",
    "output_dir",
    "project_root",
    "sample_id",
    "threads",
}


@dataclass
class TemplateFinding:
    """A single template validation finding (error or warning)."""

    severity: str  # "error" | "warning"
    location: str  # step_id or tool_id
    template_key: str  # e.g. "outputs.path", "command_template"
    message: str
    missing_keys: List[str] = field(default_factory=list)


def lint_templates(
    analysis_type: str,
    config: Mapping[str, Any],
    plugin: Any,
    *,
    verbose: bool = False,
) -> dict:
    """Validate all command and path templates for missing parameters.

    Args:
        analysis_type: Plugin ID (e.g. ``"rnaseq_expression"``).
        config: Resolved configuration dict from ``plugin.load_config()``.
        plugin: The plugin instance.
        verbose: If True, include per-template details even when no errors.

    Returns:
        A dict with keys: ``analysis_type``, ``findings``, ``error_count``,
        ``warning_count``, ``passed``.

    Raises:
        FileNotFoundError: If the plugin's ``pipeline_dag.yaml`` is missing.
    """
    SafeFormatDict.clear_all_missing_keys()
    findings: List[TemplateFinding] = []

    # ── 1. Tool command templates / 工具命令模板 ──
    _lint_tool_templates(plugin, config, findings)

    # ── 2. DAG path templates / DAG 路径模板 ──
    _lint_dag_templates(plugin, config, findings)

    # ── 3. Summary / 汇总 ──
    all_missing = SafeFormatDict.get_all_missing_keys()
    if all_missing and verbose:
        _logger.info("All missing template keys: %s", sorted(all_missing))

    return {
        "analysis_type": analysis_type,
        "findings": [asdict(f) for f in findings],
        "error_count": sum(1 for f in findings if f.severity == "error"),
        "warning_count": sum(1 for f in findings if f.severity == "warning"),
        "missing_keys": sorted(all_missing),
        "passed": not any(f.severity == "error" for f in findings),
    }


def _lint_tool_templates(
    plugin: Any,
    config: Mapping[str, Any],
    findings: List[TemplateFinding],
) -> None:
    """Check every tool's ``command_template`` for unknown params."""
    try:
        registry = plugin.registry()
    except Exception as exc:
        findings.append(
            TemplateFinding(
                severity="warning",
                location="plugin.registry()",
                template_key="",
                message=f"Cannot load tool registry: {exc}",
            )
        )
        return

    config_fields = _flatten_mapping_keys(config)
    dag_fields_by_tool = _dag_fields_by_tool(plugin)

    for tool_spec in registry.list_tools():
        tool_id = str(tool_spec.get("id", "unknown"))
        template = tool_spec.get("command_template", "")
        if not isinstance(template, str) or "{" not in template:
            continue

        allowed = set(_COMMON_TEMPLATE_FIELDS)
        allowed.update(config_fields)
        allowed.update(_tool_declared_fields(tool_spec))
        allowed.update(dag_fields_by_tool.get(tool_id, set()))

        create = getattr(registry, "create", None)
        if callable(create):
            try:
                skill = create(tool_id)
                selected = skill.select_params(_placeholder_params(allowed), mode="auto")
                allowed.update(str(key) for key in selected)
            except Exception as exc:  # pragma: no cover - defensive for custom registries
                _logger.debug("Cannot instantiate tool %s for template lint: %s", tool_id, exc)

        sfd = SafeFormatDict(_placeholder_params(allowed), strict=True, tool_name=tool_id)
        try:
            template.format_map(sfd)
        except MissingTemplateParamError as exc:
            findings.append(
                TemplateFinding(
                    severity="error",
                    location=f"tool.{tool_id}",
                    template_key="command_template",
                    message=str(exc),
                    missing_keys=list(sfd.missing_keys),
                )
            )

        if sfd.missing_keys:
            _logger.debug(
                "Tool %s command_template unknown keys: %s",
                tool_id,
                sfd.missing_keys,
            )


def _lint_dag_templates(
    plugin: Any,
    config: Mapping[str, Any],
    findings: List[TemplateFinding],
) -> None:
    """Build a plan and check every step output path template."""
    try:
        plan = plugin.build_plan(config, check_files=False)
    except Exception as exc:
        findings.append(
            TemplateFinding(
                severity="warning",
                location="plugin.build_plan()",
                template_key="",
                message=f"Cannot build plan for template linting: {exc}",
            )
        )
        return

    for step in plan.steps:
        step_id = step.step_id
        for key, template in step.outputs.items():
            if not isinstance(template, str) or "{" not in template:
                continue
            sfd = SafeFormatDict({}, strict=True, tool_name=step_id)
            try:
                template.format_map(sfd)
            except MissingTemplateParamError as exc:
                findings.append(
                    TemplateFinding(
                        severity="error",
                        location=f"step.{step_id}",
                        template_key=f"outputs.{key}",
                        message=str(exc),
                        missing_keys=list(sfd.missing_keys),
                    )
                )


def _template_fields(template: str) -> set[str]:
    """Return root field names referenced by a format template."""
    fields: set[str] = set()
    formatter = string.Formatter()
    for _, field_name, _, _ in formatter.parse(template):
        if not field_name:
            continue
        root = field_name.split(".", 1)[0].split("[", 1)[0]
        if root:
            fields.add(root)
    return fields


def _tool_declared_fields(tool_spec: Mapping[str, Any]) -> set[str]:
    """Collect parameter names declared directly in a registry tool spec."""
    fields: set[str] = set()
    for key in ("inputs", "outputs"):
        value = tool_spec.get(key, [])
        if isinstance(value, Mapping):
            fields.update(str(item) for item in value)
        elif isinstance(value, list):
            fields.update(str(item) for item in value)

    defaults = tool_spec.get("defaults", {})
    if isinstance(defaults, Mapping):
        fields.update(str(item) for item in defaults)

    params = tool_spec.get("params", {})
    if isinstance(params, Mapping):
        fields.update(str(item) for item in params)
    return fields


def _flatten_mapping_keys(mapping: Mapping[str, Any]) -> set[str]:
    """Collect leaf keys from nested config mappings."""
    fields: set[str] = set()

    def visit(value: Any) -> None:
        if not isinstance(value, Mapping):
            return
        for key, child in value.items():
            fields.add(str(key))
            visit(child)

    visit(mapping)
    return fields


def _dag_fields_by_tool(plugin: Any) -> dict[str, set[str]]:
    """Collect input/output/param names declared in ``pipeline_dag.yaml`` by tool."""
    dag_path = _plugin_root(plugin) / "pipeline_dag.yaml"
    if not dag_path.exists():
        return {}

    try:
        import yaml

        data = yaml.safe_load(dag_path.read_text(encoding="utf-8")) or {}
    except Exception as exc:  # pragma: no cover - invalid YAML is reported elsewhere
        _logger.debug("Cannot load DAG for template linting: %s", exc)
        return {}

    nodes = data.get("nodes", {})
    if not isinstance(nodes, Mapping):
        return {}

    by_tool: dict[str, set[str]] = {}
    for _node_id, node in nodes.items():
        if not isinstance(node, Mapping):
            continue
        tool_id = str(node.get("tool_id", ""))
        if not tool_id:
            continue
        fields = by_tool.setdefault(tool_id, set())
        fields.update(_COMMON_TEMPLATE_FIELDS)
        for key in ("inputs", "outputs", "params", "config_params"):
            block = node.get(key, {})
            if isinstance(block, Mapping):
                fields.update(str(item) for item in block)
                for spec in block.values():
                    if isinstance(spec, Mapping):
                        path_template = spec.get("path")
                        if isinstance(path_template, str):
                            fields.update(_template_fields(path_template))
            elif isinstance(block, list):
                fields.update(str(item) for item in block)
    return by_tool


def _plugin_root(plugin: Any) -> Path:
    """Best-effort plugin root discovery for built-in and test plugins."""
    for attr in ("root", "plugin_root", "path"):
        value = getattr(plugin, attr, None)
        if value:
            return Path(value)
    plugin_id = getattr(plugin, "plugin_id", "")
    if plugin_id:
        return Path("plugins") / str(plugin_id)
    return Path(".")


def _placeholder_params(fields: set[str]) -> dict[str, str]:
    """Build harmless placeholder values for strict template rendering."""
    return {field: f"__{field}__" for field in fields}
