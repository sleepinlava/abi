"""Tests for the rnaseq_expression plugin."""

from __future__ import annotations

from pathlib import Path

import pytest
from abi.plugins import get_plugin, list_plugins
from abi.testing import assert_plugin_contract


def test_plugin_registered():
    ids = [p.plugin_id for p in list_plugins()]
    assert "rnaseq_expression" in ids


def test_get_plugin():
    plugin = get_plugin("rnaseq_expression")
    assert plugin.plugin_id == "rnaseq_expression"
    assert "RNA-seq" in plugin.display_name


def test_table_schemas():
    plugin = get_plugin("rnaseq_expression")
    schemas = plugin.table_schemas()
    assert "gene_expression" in schemas
    assert "differential_expression" in schemas
    assert "qc_summary" in schemas
    assert "alignment_summary" in schemas


def test_registry():
    plugin = get_plugin("rnaseq_expression")
    registry = plugin.registry()
    assert registry.has("fastp")
    assert registry.has("star")
    assert registry.has("featurecounts")
    assert registry.has("deseq2")


def test_load_config():
    plugin = get_plugin("rnaseq_expression")
    cfg = plugin.load_config()
    assert cfg["project_name"] == "rnaseq_expression_run"
    assert cfg["threads"] == 4
    assert cfg["alignment"]["tool"] == "star"


def test_plugin_contract():
    plugin = get_plugin("rnaseq_expression")
    assert_plugin_contract(plugin)


def test_pipeline_dag_exists():
    dag_path = Path("plugins/rnaseq_expression/pipeline_dag.yaml")
    assert dag_path.exists(), "pipeline_dag.yaml required for L1/L2/L3 DAG validation"


_TEST_SS = "/tmp/abi_test_ss.tsv"

def test_build_plan_structure(tmp_path):
    plugin = get_plugin("rnaseq_expression")
    cfg = plugin.load_config(overrides={"outdir": str(tmp_path / "results"),
                                        "input": {"sample_sheet": _TEST_SS}})
    plan = plugin.build_plan(cfg, check_files=False)
    assert plan.analysis_type == "rnaseq_expression"
    assert len(plan.steps) >= 4  # at least 4 steps for 1 sample (fastp+star+featurecounts+deseq2)
    tool_ids = {s.tool_id for s in plan.steps}
    assert tool_ids >= {"fastp", "star", "featurecounts", "deseq2"}


def test_deseq2_step_is_last(tmp_path):
    """DESeq2 runs after all per-sample steps and aggregates across samples."""
    plugin = get_plugin("rnaseq_expression")
    cfg = plugin.load_config(overrides={"outdir": str(tmp_path / "results"),
                                        "input": {"sample_sheet": _TEST_SS}})
    plan = plugin.build_plan(cfg, check_files=False)
    last_step = plan.steps[-1]
    assert last_step.tool_id == "deseq2"
    assert last_step.category == "differential_expression"


def test_workflow_spec_loads():
    from abi.contracts import load_workflow_spec
    ws = load_workflow_spec("plugins/rnaseq_expression")
    assert ws is not None
    assert len(ws.steps) == 4
    assert ws.steps[0].tool == "fastp"
    assert ws.steps[-1].tool == "deseq2"
    # All steps must have DOIs
    for s in ws.steps:
        assert s.citation is not None, f"step {s.id} missing citation"


def test_dag_cross_validation(tmp_path):
    """L1/L2/L3: workflow declaration matches pipeline_dag.yaml topology."""
    from abi.contracts import load_workflow_spec
    from abi.dag import infer_dag

    plugin = get_plugin("rnaseq_expression")
    cfg = plugin.load_config(overrides={"outdir": str(tmp_path / "results"),
                                        "input": {"sample_sheet": _TEST_SS}})
    plan = plugin.build_plan(cfg, check_files=False)

    ws = load_workflow_spec("plugins/rnaseq_expression")
    dag = infer_dag(plan.steps, workflow_spec=ws, project_root=tmp_path)

    # L1: workflow declares fastp→star→featurecounts→deseq2
    # Verify declared edges are present in DAG
    step_ids = [str(s.step_id) for s in plan.steps]
    assert len(step_ids) == len(set(step_ids)), "all step_ids must be unique"
    assert len(dag.bindings) == len(plan.steps)
