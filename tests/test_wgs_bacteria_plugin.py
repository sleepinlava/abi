"""Tests for the wgs_bacteria plugin."""

from __future__ import annotations

from pathlib import Path

from abi.plugins import get_plugin, list_plugins
from abi.testing import assert_plugin_contract


def test_plugin_registered():
    ids = [p.plugin_id for p in list_plugins()]
    assert "wgs_bacteria" in ids


def test_get_plugin():
    plugin = get_plugin("wgs_bacteria")
    assert plugin.plugin_id == "wgs_bacteria"
    assert "WGS" in plugin.display_name or "Bacterial" in plugin.display_name


def test_table_schemas():
    plugin = get_plugin("wgs_bacteria")
    schemas = plugin.table_schemas()
    assert "genome_assembly_stats" in schemas
    assert "genome_annotation" in schemas
    assert "mlst_profile" in schemas
    assert "amr_profile" in schemas
    # MLST profile must include sequence_type and allele columns
    mlst_cols = schemas["mlst_profile"]
    assert "sequence_type" in mlst_cols
    assert any(c.startswith("allele_") for c in mlst_cols)


def test_registry():
    plugin = get_plugin("wgs_bacteria")
    registry = plugin.registry()
    for tool_id in ("fastp", "spades", "prokka", "mlst", "amrfinderplus"):
        assert registry.has(tool_id), f"registry missing {tool_id}"


def test_load_config():
    plugin = get_plugin("wgs_bacteria")
    cfg = plugin.load_config()
    assert cfg["project_name"] == "wgs_bacteria_run"
    assert cfg["annotation"]["genus"] == "Escherichia"


def test_plugin_contract():
    plugin = get_plugin("wgs_bacteria")
    assert_plugin_contract(plugin)


def test_pipeline_dag_exists():
    dag_path = Path("plugins/wgs_bacteria/pipeline_dag.yaml")
    assert dag_path.exists(), "pipeline_dag.yaml required for L1/L2/L3 DAG validation"


def test_build_plan_structure(tmp_path):
    plugin = get_plugin("wgs_bacteria")
    cfg = plugin.load_config(overrides={"outdir": str(tmp_path / "results"),
                                        "input": {"sample_sheet": "/tmp/abi_test_ss.tsv"}})
    plan = plugin.build_plan(cfg, check_files=False)
    assert plan.analysis_type == "wgs_bacteria"
    # 1 sample → 5 steps
    assert len(plan.steps) >= 5
    tool_ids = {s.tool_id for s in plan.steps}
    assert tool_ids >= {"fastp", "spades", "prokka", "mlst", "amrfinderplus"}


def test_mlst_depends_on_assembly_not_annotation(tmp_path):
    """MLST runs on assembly FASTA directly, not on Prokka output."""
    plugin = get_plugin("wgs_bacteria")
    cfg = plugin.load_config(overrides={"outdir": str(tmp_path / "results"),
                                        "input": {"sample_sheet": "/tmp/abi_test_ss.tsv"}})
    plan = plugin.build_plan(cfg, check_files=False)
    mlst_step = next(s for s in plan.steps if s.tool_id == "mlst")
    assert "assembly_fasta" in mlst_step.inputs or "contigs_fasta" in str(mlst_step.inputs)


def test_amr_depends_on_annotation(tmp_path):
    """AMRFinderPlus requires Prokka protein FASTA as input."""
    plugin = get_plugin("wgs_bacteria")
    cfg = plugin.load_config(overrides={"outdir": str(tmp_path / "results"),
                                        "input": {"sample_sheet": "/tmp/abi_test_ss.tsv"}})
    plan = plugin.build_plan(cfg, check_files=False)
    amr_step = next(s for s in plan.steps if s.tool_id == "amrfinderplus")
    assert "prokka_faa" in amr_step.inputs or "faa" in str(amr_step.inputs)


def test_workflow_spec_loads():
    from abi.contracts import load_workflow_spec
    ws = load_workflow_spec("plugins/wgs_bacteria")
    assert ws is not None
    assert len(ws.steps) == 5
    for s in ws.steps:
        assert s.citation is not None, f"step {s.id} missing citation"


def test_dag_cross_validation(tmp_path):
    from abi.contracts import load_workflow_spec
    from abi.dag import infer_dag

    plugin = get_plugin("wgs_bacteria")
    cfg = plugin.load_config(overrides={"outdir": str(tmp_path / "results"),
                                        "input": {"sample_sheet": "/tmp/abi_test_ss.tsv"}})
    plan = plugin.build_plan(cfg, check_files=False)
    ws = load_workflow_spec("plugins/wgs_bacteria")
    dag = infer_dag(plan.steps, workflow_spec=ws, project_root=tmp_path)
    assert len(dag.bindings) == len(plan.steps)
