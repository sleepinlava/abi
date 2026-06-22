"""Tests for the amplicon_16s plugin."""

from __future__ import annotations

from pathlib import Path

from abi.plugins import get_plugin, list_plugins
from abi.testing import assert_plugin_contract

_FIXTURES = Path("tests/fixtures/tool_outputs")


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
    assert "primer_trim_summary" in schemas
    assert "denoising_stats" in schemas
    assert "otu_table" in schemas
    assert "phylogeny_artifacts" in schemas


def test_registry():
    plugin = get_plugin("amplicon_16s")
    registry = plugin.registry()
    for tool_id in (
        "cutadapt",
        "vsearch_derep",
        "vsearch_denoise",
        "vsearch_taxonomy",
        "diversity_metrics",
    ):
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
    cfg = plugin.load_config(
        overrides={
            "outdir": str(tmp_path / "results"),
            "input": {"sample_sheet": "/tmp/abi_test_ss.tsv"},
        }
    )
    plan = plugin.build_plan(cfg, check_files=False)
    assert plan.analysis_type == "amplicon_16s"
    # 1 sample → 5 per-sample steps + 4 cross-sample (3 phylogeny + diversity)
    assert len(plan.steps) >= 9
    tool_ids = {s.tool_id for s in plan.steps}
    assert tool_ids >= {
        "cutadapt",
        "vsearch_mergepairs",
        "vsearch_derep",
        "vsearch_denoise",
        "vsearch_taxonomy",
        "phylogeny_combine",
        "phylogeny_mafft",
        "phylogeny_tree",
        "diversity_metrics",
    }


def test_optional_otu_disabled_by_default(tmp_path):
    """OTU clustering is optional and disabled in default config."""
    plugin = get_plugin("amplicon_16s")
    cfg = plugin.load_config(
        overrides={
            "outdir": str(tmp_path / "results"),
            "input": {"sample_sheet": "/tmp/abi_test_ss.tsv"},
        }
    )
    plan = plugin.build_plan(cfg, check_files=False)
    assert "vsearch_otu" not in {s.tool_id for s in plan.steps}


def test_workflow_spec_loads():
    from abi.contracts import load_workflow_spec

    ws = load_workflow_spec("plugins/amplicon_16s")
    assert ws is not None
    assert len(ws.steps) == 10
    for s in ws.steps:
        assert s.citation is not None, f"step {s.id} missing citation"


def test_dag_cross_validation(tmp_path):
    from abi.contracts import load_workflow_spec
    from abi.dag import infer_dag

    plugin = get_plugin("amplicon_16s")
    cfg = plugin.load_config(
        overrides={
            "outdir": str(tmp_path / "results"),
            "input": {"sample_sheet": "/tmp/abi_test_ss.tsv"},
        }
    )
    plan = plugin.build_plan(cfg, check_files=False)
    ws = load_workflow_spec("plugins/amplicon_16s")
    dag = infer_dag(plan.steps, workflow_spec=ws, project_root=tmp_path)
    assert len(dag.bindings) == len(plan.steps)


# ── Parser tests ──────────────────────────────────────────────────────────


def test_parse_cutadapt():
    """cutadapt log → primer_trim_summary with trimming stats."""
    plugin = get_plugin("amplicon_16s")
    result = plugin.parse_outputs("cutadapt", _FIXTURES / "cutadapt", "S1")
    rows = result["primer_trim_summary"]
    assert len(rows) == 1
    row = rows[0]
    assert row["sample_id"] == "S1"
    assert row["tool"] == "cutadapt"
    assert int(row["total_reads"]) == 100000
    assert int(row["reads_trimmed"]) == 42310
    assert int(row["reads_too_short"]) == 1234
    assert int(row["reads_written"]) == 98766


def test_parse_vsearch_derep():
    """vsearch derep FASTA → denoising_stats."""
    plugin = get_plugin("amplicon_16s")
    result = plugin.parse_outputs("vsearch_derep", _FIXTURES / "vsearch_derep", "S1")
    rows = result["denoising_stats"]
    assert len(rows) == 1
    row = rows[0]
    assert row["stage"] == "dereplication"
    assert int(row["input_reads"]) == 11223  # 5423+3100+1500+800+400
    assert int(row["output_reads"]) == 5  # 5 unique sequences


def test_parse_vsearch_denoise():
    """vsearch UNOISE3 output → denoising_stats."""
    plugin = get_plugin("amplicon_16s")
    result = plugin.parse_outputs("vsearch_denoise", _FIXTURES / "vsearch_denoise", "S1")
    rows = result["denoising_stats"]
    assert len(rows) == 1
    row = rows[0]
    assert row["stage"] == "denoising"
    assert int(row["output_reads"]) == 3  # 3 ASVs


def test_parse_vsearch_otu(tmp_path):
    (tmp_path / "S1_otu.tsv").write_text("#OTU ID\tS1\nOTU_1\t12\nOTU_2\t3\n", encoding="utf-8")
    rows = get_plugin("amplicon_16s").parse_outputs("vsearch_otu", tmp_path, "S1")["otu_table"]
    assert [(row["otu_id"], row["abundance"]) for row in rows] == [
        ("OTU_1", "12"),
        ("OTU_2", "3"),
    ]


def test_parse_phylogeny_stages(tmp_path):
    (tmp_path / "combined.fasta").write_text(">ASV1\nACGT\n>ASV2\nTGCA\n", encoding="utf-8")
    (tmp_path / "aligned.fasta").write_text(">ASV1\nACGT\n>ASV2\nTGCA\n", encoding="utf-8")
    (tmp_path / "phylogeny.nwk").write_text("(ASV1:0.1,ASV2:0.1);\n", encoding="utf-8")
    plugin = get_plugin("amplicon_16s")

    combine = plugin.parse_outputs("phylogeny_combine", tmp_path, "")
    alignment = plugin.parse_outputs("phylogeny_mafft", tmp_path, "")
    tree = plugin.parse_outputs("phylogeny_tree", tmp_path, "")

    assert combine["phylogeny_artifacts"][0]["record_count"] == 2
    assert alignment["phylogeny_artifacts"][0]["artifact_type"] == "aligned_fasta"
    assert tree["phylogeny_artifacts"][0]["artifact_type"] == "newick_tree"


def test_parse_outputs_unknown():
    plugin = get_plugin("amplicon_16s")
    assert plugin.parse_outputs("nonexistent", Path("/tmp"), "S1") == {}
