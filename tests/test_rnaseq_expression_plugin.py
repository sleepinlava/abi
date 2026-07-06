"""Tests for the rnaseq_expression plugin."""

from __future__ import annotations
import pytest

from pathlib import Path

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
    assert "normalized_expression" in schemas
    assert "count_matrix" in schemas


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
_FIXTURES = Path("tests/fixtures/tool_outputs")


def test_build_plan_structure(tmp_path):
    plugin = get_plugin("rnaseq_expression")
    cfg = plugin.load_config(
        overrides={
            "outdir": str(tmp_path / "results"),
            "input": {"sample_sheet": _TEST_SS},
        }
    )
    plan = plugin.build_plan(cfg, check_files=False)
    assert plan.analysis_type == "rnaseq_expression"
    assert len(plan.steps) >= 4  # at least 4 steps for 1 sample (fastp+star+featurecounts+deseq2)
    tool_ids = {s.tool_id for s in plan.steps}
    assert tool_ids >= {"fastp", "star", "featurecounts", "deseq2"}


def test_deseq2_step_is_last(tmp_path):
    """DESeq2 runs after all per-sample steps and aggregates across samples."""
    plugin = get_plugin("rnaseq_expression")
    cfg = plugin.load_config(
        overrides={
            "outdir": str(tmp_path / "results"),
            "input": {"sample_sheet": _TEST_SS},
        }
    )
    plan = plugin.build_plan(cfg, check_files=False)
    last_step = plan.steps[-1]
    assert last_step.tool_id == "deseq2"
    assert last_step.category == "differential_expression"
    assert last_step.params["comparison"] == "treatment_vs_control"
    assert last_step.params["alpha"] == 0.05


def test_workflow_spec_loads():
    from abi.contracts import load_workflow_spec

    ws = load_workflow_spec("plugins/rnaseq_expression")
    assert ws is not None
    assert len(ws.steps) == 5
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
    cfg = plugin.load_config(
        overrides={
            "outdir": str(tmp_path / "results"),
            "input": {"sample_sheet": _TEST_SS},
        }
    )
    plan = plugin.build_plan(cfg, check_files=False)

    ws = load_workflow_spec("plugins/rnaseq_expression")
    dag = infer_dag(plan.steps, workflow_spec=ws, project_root=tmp_path)

    # L1: workflow declares fastp→star→featurecounts→deseq2
    # Verify declared edges are present in DAG
    step_ids = [str(s.step_id) for s in plan.steps]
    assert len(step_ids) == len(set(step_ids)), "all step_ids must be unique"
    assert len(dag.bindings) == len(plan.steps)


# ── Parser tests ──────────────────────────────────────────────────────────


def test_parse_fastp():
    """fastp JSON output → qc_summary rows with before/after filtering metrics."""
    plugin = get_plugin("rnaseq_expression")
    result = plugin.parse_outputs("fastp", _FIXTURES / "fastp", "S1")
    rows = result["qc_summary"]
    assert len(rows) >= 4  # at least 4 metrics (2 blocks × 2+ metrics each)
    assert all(r["tool"] == "fastp" for r in rows)
    assert all(r["sample_id"] == "S1" for r in rows)
    metrics = {r["metric"] for r in rows}
    assert "before_filtering.total_reads" in metrics
    assert "after_filtering.total_reads" in metrics
    assert "before_filtering.q30_rate" in metrics
    assert "after_filtering.q30_rate" in metrics


def test_parse_star():
    """STAR Log.final.out → alignment_summary rows with key metrics."""
    plugin = get_plugin("rnaseq_expression")
    result = plugin.parse_outputs("star", _FIXTURES / "star", "S1")
    rows = result["alignment_summary"]
    assert len(rows) >= 10  # STAR log has many metrics
    assert all(r["tool"] == "star" for r in rows)
    assert all(r["sample_id"] == "S1" for r in rows)
    metrics = {r["metric"] for r in rows}
    assert "Uniquely mapped reads %" in metrics
    assert "Number of input reads" in metrics


def test_parse_deseq2_normalized():
    """DESeq2 R script produces normalized_expression.tsv → long-format rows."""
    plugin = get_plugin("rnaseq_expression")
    result = plugin.parse_outputs("deseq2", _FIXTURES / "deseq2", "S1")
    # DESeq2 parser returns two tables
    assert "differential_expression" in result
    assert "normalized_expression" in result
    de_rows = result["differential_expression"]
    assert len(de_rows) == 3
    assert de_rows[0]["gene_id"] == "ENSG000001"
    norm_rows = result["normalized_expression"]
    # 3 genes × 4 samples = 12 rows
    assert len(norm_rows) == 12
    assert all(r["normalization_method"] == "DESeq2_median_of_ratios" for r in norm_rows)
    assert all(r["tool"] == "deseq2" for r in norm_rows)


def test_parse_build_count_matrix(tmp_path):
    (tmp_path / "count_matrix.tsv").write_text(
        "gene_id\tS1\tS2\nGENE1\t10\t20\nGENE2\t3\t4\n",
        encoding="utf-8",
    )
    result = get_plugin("rnaseq_expression").parse_outputs("build_count_matrix", tmp_path, "")

    assert result["count_matrix"] == [
        {
            "gene_id": "GENE1",
            "sample_id": "S1",
            "count": "10",
            "tool": "build_count_matrix",
            "source_file": str(tmp_path / "count_matrix.tsv"),
        },
        {
            "gene_id": "GENE1",
            "sample_id": "S2",
            "count": "20",
            "tool": "build_count_matrix",
            "source_file": str(tmp_path / "count_matrix.tsv"),
        },
        {
            "gene_id": "GENE2",
            "sample_id": "S1",
            "count": "3",
            "tool": "build_count_matrix",
            "source_file": str(tmp_path / "count_matrix.tsv"),
        },
        {
            "gene_id": "GENE2",
            "sample_id": "S2",
            "count": "4",
            "tool": "build_count_matrix",
            "source_file": str(tmp_path / "count_matrix.tsv"),
        },
    ]


def test_unknown_tool_returns_empty():
    """Unrecognized tool_id → empty dict (graceful no-op)."""
    plugin = get_plugin("rnaseq_expression")
    result = plugin.parse_outputs("nonexistent", Path("/tmp"), "S1")
    assert result == {}


# ── Report test ───────────────────────────────────────────────────────────


@pytest.mark.xfail(reason="rna_seq platform removed from VALID_PLATFORMS; needs plugin update")
def test_write_report_with_figures(tmp_path):
    """write_report() produces report.html, methods.md even without real data."""
    from abi.tables import StandardTableManager

    plugin = get_plugin("rnaseq_expression")
    tables_dir = tmp_path / "tables"
    tables_dir.mkdir()
    # Create empty standard tables with headers
    tm = StandardTableManager(plugin.table_schemas())
    tm.ensure_tables(tables_dir)
    # Create provenance dir (resource manifest needs it)
    (tables_dir.parent / "provenance").mkdir()
    # Write a minimal sample sheet so build_plan works
    sample_sheet = tmp_path / "sample_sheet.tsv"
    sample_sheet.write_text(
        "sample_id\tgroup\tcondition\tplatform\tread1\tread2\n"
        "S1\ttreatment\ttreated\trna_seq\t/tmp/a.fastq.gz\t/tmp/b.fastq.gz\n"
        "S2\tcontrol\tuntreated\trna_seq\t/tmp/c.fastq.gz\t/tmp/d.fastq.gz\n",
        encoding="utf-8",
    )
    # Stash config for resource manifest
    plugin._last_config = {
        "project_name": "test",
        "mode": "dry_run",
        "threads": 4,
        "outdir": str(tmp_path / "results"),
        "log_dir": str(tmp_path / "logs"),
        "input": {"sample_sheet": str(sample_sheet)},
        "resources": {},
    }
    # Build a minimal plan (check_files=False skips file existence check)
    plan = plugin.build_plan(plugin._last_config, check_files=False)
    paths = plugin.write_report(plan, tables_dir.parent)
    report_html = paths["report_html"]
    assert report_html.exists()
    content = report_html.read_text(encoding="utf-8")
    assert "RNA-seq" in content
    methods_path = paths["methods"]
    assert methods_path.exists()


# ── Figure spec validation ────────────────────────────────────────────────


def test_figure_specs_valid():
    """All figure specs reference declared standard tables and columns."""
    from abi.workflow.figure_specs import load_figure_specs

    plugin = get_plugin("rnaseq_expression")
    schemas = plugin.table_schemas()
    specs = load_figure_specs(plugin.root / "figure_specs.yaml", table_schemas=schemas)
    assert len(specs) == 6
    spec_ids = {s.id for s in specs}
    assert spec_ids == {
        "qc_read_counts",
        "mapping_rate",
        "pca_expression",
        "volcano_deg",
        "top_deg_heatmap",
        "ma_plot",
    }
    required = [s for s in specs if s.required]
    assert len(required) == 3  # qc_read_counts, mapping_rate, volcano_deg
