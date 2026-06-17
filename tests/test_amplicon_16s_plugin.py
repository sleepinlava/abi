"""Tests for the amplicon_16s plugin."""

from __future__ import annotations

from pathlib import Path

from abi.plugins import get_plugin, list_plugins
from abi.testing import assert_plugin_contract


def test_plugin_registered():
    ids = [p.plugin_id for p in list_plugins()]
    assert "amplicon_16s" in ids


def test_get_plugin():
    plugin = get_plugin("amplicon_16s")
    assert plugin.plugin_id == "amplicon_16s"
    assert "16S" in plugin.display_name


def test_table_schemas():
    plugin = get_plugin("amplicon_16s")
    schemas = plugin.table_schemas()
    assert "asv_table" in schemas
    assert "taxonomy" in schemas
    assert "alpha_diversity" in schemas
    assert "beta_diversity" in schemas
    # Verify taxonomy columns include standard ranks
    assert "genus" in schemas["taxonomy"]
    assert "species" in schemas["taxonomy"]


def test_registry():
    plugin = get_plugin("amplicon_16s")
    registry = plugin.registry()
    for tool_id in ("cutadapt", "vsearch_derep", "vsearch_denoise",
                     "vsearch_taxonomy", "diversity_metrics"):
        assert registry.has(tool_id), f"registry missing {tool_id}"


def test_load_config():
    plugin = get_plugin("amplicon_16s")
    cfg = plugin.load_config()
    assert cfg["project_name"] == "amplicon_16s_run"
    assert cfg["primers"]["forward"] == "GTGCCAGCMGCCGCGGTAA"
    assert cfg["primers"]["reverse"] == "GGACTACHVGGGTWTCTAAT"


def test_plugin_contract():
    plugin = get_plugin("amplicon_16s")
    assert_plugin_contract(plugin)


def test_pipeline_dag_exists():
    dag_path = Path("plugins/amplicon_16s/pipeline_dag.yaml")
    assert dag_path.exists(), "pipeline_dag.yaml required for L1/L2/L3 DAG validation"


def test_build_plan_structure(tmp_path):
    plugin = get_plugin("amplicon_16s")
    cfg = plugin.load_config(overrides={"outdir": str(tmp_path / "results"),
                                        "input": {"sample_sheet": "/tmp/abi_test_ss.tsv"}})
    plan = plugin.build_plan(cfg, check_files=False)
    assert plan.analysis_type == "amplicon_16s"
    # 1 sample → 4 per-sample steps + 1 cross-sample diversity
    assert len(plan.steps) >= 5
    tool_ids = {s.tool_id for s in plan.steps}
    assert tool_ids >= {"cutadapt", "vsearch_derep", "vsearch_denoise", "vsearch_taxonomy", "diversity_metrics"}


def test_optional_otu_disabled_by_default(tmp_path):
    """OTU clustering is optional and disabled in default config."""
    plugin = get_plugin("amplicon_16s")
    cfg = plugin.load_config(overrides={"outdir": str(tmp_path / "results"),
                                        "input": {"sample_sheet": "/tmp/abi_test_ss.tsv"}})
    plan = plugin.build_plan(cfg, check_files=False)
    assert "vsearch_otu" not in {s.tool_id for s in plan.steps}


def test_workflow_spec_loads():
    from abi.contracts import load_workflow_spec
    ws = load_workflow_spec("plugins/amplicon_16s")
    assert ws is not None
    assert len(ws.steps) == 6
    for s in ws.steps:
        assert s.citation is not None, f"step {s.id} missing citation"


def test_dag_cross_validation(tmp_path):
    from abi.contracts import load_workflow_spec
    from abi.dag import infer_dag

    plugin = get_plugin("amplicon_16s")
    cfg = plugin.load_config(overrides={"outdir": str(tmp_path / "results"),
                                        "input": {"sample_sheet": "/tmp/abi_test_ss.tsv"}})
    plan = plugin.build_plan(cfg, check_files=False)
    ws = load_workflow_spec("plugins/amplicon_16s")
    dag = infer_dag(plan.steps, workflow_spec=ws, project_root=tmp_path)
    assert len(dag.bindings) == len(plan.steps)
