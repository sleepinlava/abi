"""Tests for the wgs_bacteria plugin."""

from __future__ import annotations

from pathlib import Path

from abi.plugins import get_plugin, list_plugins
from abi.testing import assert_plugin_contract

_FIXTURES = Path("tests/fixtures/tool_outputs")


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


def test_load_config_normalizes_amrfinder_parent_database_to_latest(tmp_path):
    db_parent = tmp_path / "amrfinderplus"
    latest = db_parent / "latest"
    latest.mkdir(parents=True)
    (latest / "AMRProt.fa.phr").write_text("phr", encoding="utf-8")
    (latest / "AMRProt.fa.pin").write_text("pin", encoding="utf-8")
    (latest / "AMRProt.fa.psq").write_text("psq", encoding="utf-8")

    plugin = get_plugin("wgs_bacteria")
    cfg = plugin.load_config(overrides={"resources": {"amrfinder_db": str(db_parent)}})

    assert cfg["resources"]["amrfinder_db"] == str(latest)


def test_plugin_contract():
    plugin = get_plugin("wgs_bacteria")
    assert_plugin_contract(plugin)


def test_pipeline_dag_exists():
    dag_path = Path("plugins/wgs_bacteria/pipeline_dag.yaml")
    assert dag_path.exists(), "pipeline_dag.yaml required for L1/L2/L3 DAG validation"


def test_build_plan_structure(tmp_path):
    plugin = get_plugin("wgs_bacteria")
    cfg = plugin.load_config(
        overrides={
            "outdir": str(tmp_path / "results"),
            "input": {"sample_sheet": "/tmp/abi_test_ss.tsv"},
        }
    )
    plan = plugin.build_plan(cfg, check_files=False)
    assert plan.analysis_type == "wgs_bacteria"
    # 1 sample → 5 steps
    assert len(plan.steps) >= 5
    tool_ids = {s.tool_id for s in plan.steps}
    assert tool_ids >= {"fastp", "spades", "prokka", "mlst", "amrfinderplus"}


def test_mlst_depends_on_assembly_not_annotation(tmp_path):
    """MLST runs on assembly FASTA directly, not on Prokka output."""
    plugin = get_plugin("wgs_bacteria")
    cfg = plugin.load_config(
        overrides={
            "outdir": str(tmp_path / "results"),
            "input": {"sample_sheet": "/tmp/abi_test_ss.tsv"},
        }
    )
    plan = plugin.build_plan(cfg, check_files=False)
    mlst_step = next(s for s in plan.steps if s.tool_id == "mlst")
    assert "assembly_fasta" in mlst_step.inputs or "contigs_fasta" in str(mlst_step.inputs)


def test_amr_depends_on_annotation(tmp_path):
    """AMRFinderPlus requires Prokka protein FASTA as input."""
    plugin = get_plugin("wgs_bacteria")
    cfg = plugin.load_config(
        overrides={
            "outdir": str(tmp_path / "results"),
            "input": {"sample_sheet": "/tmp/abi_test_ss.tsv"},
        }
    )
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
    cfg = plugin.load_config(
        overrides={
            "outdir": str(tmp_path / "results"),
            "input": {"sample_sheet": "/tmp/abi_test_ss.tsv"},
        }
    )
    plan = plugin.build_plan(cfg, check_files=False)
    ws = load_workflow_spec("plugins/wgs_bacteria")
    dag = infer_dag(plan.steps, workflow_spec=ws, project_root=tmp_path)
    assert len(dag.bindings) == len(plan.steps)


# ── Parser tests ──────────────────────────────────────────────────────────


def test_parse_fastp_shared():
    """fastp parser (imported from abi._shared) → qc_summary rows."""
    plugin = get_plugin("wgs_bacteria")
    result = plugin.parse_outputs("fastp", _FIXTURES / "fastp", "S1")
    rows = result["qc_summary"]
    assert len(rows) >= 4
    assert all(r["tool"] == "fastp" for r in rows)
    assert all(r["sample_id"] == "S1" for r in rows)
    metrics = {r["metric"] for r in rows}
    assert "before_filtering.total_reads" in metrics
    assert "after_filtering.q30_rate" in metrics


def test_parse_spades():
    """SPAdes contigs FASTA → genome_assembly_stats with N50/GC metrics."""
    plugin = get_plugin("wgs_bacteria")
    result = plugin.parse_outputs("spades", _FIXTURES / "spades", "S1")
    rows = result["genome_assembly_stats"]
    assert len(rows) == 1  # one sample, one row
    row = rows[0]
    assert row["sample_id"] == "S1"
    assert row["tool"] == "spades"
    assert int(row["num_contigs"]) == 5
    assert int(row["total_length"]) > 0
    # N50 must be ≤ max_contig_length
    assert int(row["n50"]) <= int(row["max_contig_length"])
    # GC content must be between 0 and 100
    gc = row["gc_content"]
    if gc != "":
        assert 0.0 <= float(gc) <= 100.0
    assert 0.0 < float(row["coverage"]) < 100.0


def test_parse_prokka():
    """Prokka GFF → genome_annotation rows with feature types."""
    plugin = get_plugin("wgs_bacteria")
    result = plugin.parse_outputs("prokka", _FIXTURES / "prokka", "S1")
    rows = result["genome_annotation"]
    # 1 source + 4 CDS + 2 tRNA + 1 rRNA + 1 tmRNA = 9 features
    assert len(rows) == 9
    assert all(r["tool"] == "prokka" for r in rows)
    assert all(r["sample_id"] == "S1" for r in rows)
    feature_types = {r["feature_type"] for r in rows}
    assert feature_types >= {"CDS", "tRNA", "rRNA", "tmRNA", "source"}
    # Verify a CDS feature has expected fields
    cds = next(r for r in rows if r["feature_type"] == "CDS")
    assert cds["gene_name"] == "dnaE"
    assert cds["product"] == "DNA polymerase III subunit alpha"
    assert cds["ec_number"] == "2.7.7.7"


def test_parse_amrfinderplus():
    """AMRFinderPlus --plus TSV → amr_profile rows with all --plus columns."""
    plugin = get_plugin("wgs_bacteria")
    result = plugin.parse_outputs("amrfinderplus", _FIXTURES / "amrfinderplus", "S1")
    rows = result["amr_profile"]
    assert len(rows) == 5
    assert all(r["tool"] == "amrfinderplus" for r in rows)
    assert all(r["sample_id"] == "S1" for r in rows)
    # Check AMR gene types are present
    symbols = {r["gene_symbol"] for r in rows}
    assert symbols >= {"tetA", "blaTEM-1", "sul2", "dfrA1", "mcr-1"}
    # Check --plus columns are populated
    tet = next(r for r in rows if r["gene_symbol"] == "tetA")
    assert tet["scope"] == "core"
    assert tet["element_subtype"] == "AMR:TETRACYCLINE"
    assert tet["target_class"] == "TETRACYCLINE"
    assert tet["method"] in ("BLASTP", "HMM")
    assert float(tet["coverage_pct"]) >= 0.0
    assert float(tet["identity_pct"]) >= 0.0


def test_parse_outputs_unknown_tool():
    """Unrecognized tool_id → empty dict."""
    plugin = get_plugin("wgs_bacteria")
    result = plugin.parse_outputs("nonexistent", Path("/tmp"), "S1")
    assert result == {}


def test_write_report_with_parsed_tables(tmp_path):
    """write_report() succeeds with assembly + annotation tables present."""
    from abi.tables import StandardTableManager

    plugin = get_plugin("wgs_bacteria")
    tables_dir = tmp_path / "tables"
    tables_dir.mkdir()
    (tmp_path / "provenance").mkdir()

    tm = StandardTableManager(plugin.table_schemas())
    tm.ensure_tables(tables_dir)

    # Stash config
    plugin._last_config = {
        "project_name": "test",
        "mode": "dry_run",
        "threads": 4,
        "outdir": str(tmp_path / "results"),
        "log_dir": str(tmp_path / "logs"),
        "input": {"sample_sheet": "/tmp/abi_test_ss.tsv"},
        "resources": {},
    }

    plan = plugin.build_plan(plugin._last_config, check_files=False)
    paths = plugin.write_report(plan, tables_dir.parent)

    assert paths["report_html"].exists()
    assert paths["methods"].exists()
    content = paths["report_html"].read_text(encoding="utf-8")
    assert "WGS" in content or "Bacterial" in content
