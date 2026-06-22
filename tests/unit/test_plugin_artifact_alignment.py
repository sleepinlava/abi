from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from abi.contracts import load_workflow_spec
from abi.dag import infer_dag
from abi.plugins import get_plugin

PLUGIN_ROOT = Path("plugins")
INLINE_PLUGINS = (
    "amplicon_16s",
    "metatranscriptomics",
    "rnaseq_expression",
    "wgs_bacteria",
)
ALL_PLUGINS = ("metagenomic_plasmid", *INLINE_PLUGINS)


def _load(path: Path):
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


@pytest.mark.parametrize("plugin_id", ALL_PLUGINS)
def test_registry_dag_and_contracts_share_one_tool_set(plugin_id):
    """Prevent tools from becoming phantom, stale, or uncontracted again."""
    root = PLUGIN_ROOT / plugin_id
    registry = _load(root / "tool_registry.yaml")
    dag = _load(root / "pipeline_dag.yaml")

    registry_tools = {str(tool["id"]) for tool in registry.get("tools", [])}
    dag_tools = {
        str(node["tool_id"])
        for node in dag.get("nodes", {}).values()
        if str(node["tool_id"]) != "internal"
    }
    contract_tools = {
        str(_load(path).get("tool_id")) for path in (root / "tool_contracts").glob("*.yaml")
    }

    assert registry_tools == dag_tools, (
        f"{plugin_id}: registry-only={sorted(registry_tools - dag_tools)}, "
        f"DAG-only={sorted(dag_tools - registry_tools)}"
    )
    assert contract_tools == dag_tools, (
        f"{plugin_id}: contract files do not match DAG tools; "
        f"missing={sorted(dag_tools - contract_tools)}, "
        f"extra={sorted(contract_tools - dag_tools)}"
    )


@pytest.mark.parametrize("plugin_id", INLINE_PLUGINS)
def test_inline_plugin_manifest_core_contracts_match_dag(plugin_id):
    root = PLUGIN_ROOT / plugin_id
    dag = _load(root / "pipeline_dag.yaml")
    manifest = _load(root / "abi-plugin.yaml")
    dag_tools = {str(node["tool_id"]) for node in dag.get("nodes", {}).values()}
    core_contracts = {str(tool_id) for tool_id in manifest.get("core_contracts", [])}

    assert core_contracts == dag_tools, (
        f"{plugin_id}: stale core_contracts; missing={sorted(dag_tools - core_contracts)}, "
        f"extra={sorted(core_contracts - dag_tools)}"
    )

    plugin = get_plugin(plugin_id)
    config = plugin.load_config(
        overrides={"outdir": "/tmp/abi-contract-plan", "log_dir": "/tmp/abi-contract-log"}
    )
    plan = plugin.build_plan(config, check_files=False)
    infer_dag(
        plan.steps,
        workflow_spec=load_workflow_spec(plugin.root),
        strict_workflow=True,
    )


def test_environment_assignments_match_every_plugin_registry():
    assignments = _load(Path("environments.yaml")).get("tool_assignments", {})
    for registry_path in sorted(PLUGIN_ROOT.glob("*/tool_registry.yaml")):
        plugin_id = registry_path.parent.name
        registry_tools = {str(tool["id"]) for tool in _load(registry_path).get("tools", [])}
        assigned_tools = set(assignments.get(plugin_id, {}))
        assert assigned_tools == registry_tools, (
            f"{plugin_id}: unassigned={sorted(registry_tools - assigned_tools)}, "
            f"stale assignments={sorted(assigned_tools - registry_tools)}"
        )
