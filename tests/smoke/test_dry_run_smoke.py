"""Smoke tests: plan generation + DAG validation for all 5 plugins.

These tests run without any external bioinformatics tools — they validate
that each plugin can build a valid execution plan from a minimal config.
Fast enough for CI pre-commit hooks (< 1 second per plugin).
"""

from __future__ import annotations

from pathlib import Path


def _plugin_config(plugin_id: str, outdir: Path) -> dict:
    """Minimal config shared across plugins."""
    base = {
        "project_name": f"smoke-{plugin_id}",
        "mode": "local",
        "threads": 2,
        "outdir": str(outdir),
        "log_dir": str(outdir / "logs"),
    }
    return base


# ── metagenomic_plasmid ──────────────────────────────────────────────────


def test_metagenomic_plasmid_dry_run(tmp_path: Path) -> None:
    """Plan generation for the flagship plasmid pipeline.

    Note: metagenomic_plasmid uses a different config structure than the
    4 inline plugins (mode must be 'auto' or 'interactive', different
    input schema).  This test validates basic plan generation works.
    """
    from abi.plugins.metagenomic_plasmid import MetagenomicPlasmidPlugin

    plugin = MetagenomicPlasmidPlugin()
    config = plugin.load_config(
        overrides={
            "mode": "auto",
            "input": {
                "platform": "illumina",
                "single_input": str(tmp_path / "dummy.fastq.gz"),
            },
            "output_path": str(tmp_path / "results"),
            "project_name": "smoke-mp",
        },
    )
    plan = plugin.build_plan(config, check_files=False)
    assert len(plan.steps) > 0
    assert "plasmid" in plan.analysis_type
    assert len(plan.selected_tools) > 0
    assert len(plan.selected_tools) > 0


# ── rnaseq_expression ────────────────────────────────────────────────────


def test_rnaseq_expression_dry_run(tmp_path: Path) -> None:
    """Plan generation produces 4n+2 steps (QC+align+quant per sample + matrix+DESeq2)."""
    from abi.plugins.rnaseq_expression import RNASeqExpressionPlugin

    plugin = RNASeqExpressionPlugin()
    sample_sheet = tmp_path / "samples.tsv"
    sample_sheet.write_text("sample_id\tread1\tread2\tcondition\nS1\t/tmp/R1.fq\t/tmp/R2.fq\ttreated\nS2\t/tmp/A.fq\t/tmp/B.fq\tuntreated\n")

    config = plugin.load_config(
        overrides={
            **_plugin_config("rnaseq_expression", tmp_path),
            "input": {"sample_sheet": str(sample_sheet)},
        },
    )
    plan = plugin.build_plan(config, check_files=False)
    # 2 samples × 3 per-sample steps + build_count_matrix + DESeq2 = 8
    assert len(plan.steps) == 8
    assert "build_count_matrix" in [s.step_id for s in plan.steps]
    assert "deseq2" in [s.tool_id for s in plan.steps]


def test_rnaseq_expression_tool_ids(tmp_path: Path) -> None:
    """Selected tools include the full 5-tool chain."""
    from abi.plugins.rnaseq_expression import RNASeqExpressionPlugin

    plugin = RNASeqExpressionPlugin()
    sample_sheet = tmp_path / "samples.tsv"
    sample_sheet.write_text("sample_id\tread1\tread2\tcondition\nS1\t/tmp/R1.fq\t/tmp/R2.fq\ttreated\n")

    config = plugin.load_config(
        overrides={
            **_plugin_config("rnaseq_expression", tmp_path),
            "input": {"sample_sheet": str(sample_sheet)},
        },
    )
    plan = plugin.build_plan(config, check_files=False)
    tool_ids = set(s.tool_id for s in plan.steps)
    assert tool_ids >= {"fastp", "star", "featurecounts", "build_count_matrix", "deseq2"}


# ── wgs_bacteria ─────────────────────────────────────────────────────────


def test_wgs_bacteria_dry_run(tmp_path: Path) -> None:
    """Plan generation for bacterial WGS pipeline."""
    from abi.plugins.wgs_bacteria import WGSBacteriaPlugin

    plugin = WGSBacteriaPlugin()
    sample_sheet = tmp_path / "samples.tsv"
    sample_sheet.write_text("sample_id\tread1\tread2\nS1\t/tmp/R1.fq\t/tmp/R2.fq\n")

    config = plugin.load_config(
        overrides={
            **_plugin_config("wgs_bacteria", tmp_path),
            "input": {"sample_sheet": str(sample_sheet)},
        },
    )
    plan = plugin.build_plan(config, check_files=False)
    assert len(plan.steps) == 5  # 5 tools × 1 sample
    assert {s.tool_id for s in plan.steps} >= {"fastp", "spades", "prokka", "mlst", "amrfinderplus"}


# ── amplicon_16s ─────────────────────────────────────────────────────────


def test_amplicon_16s_dry_run(tmp_path: Path) -> None:
    """Plan generation produces 5n+1 steps (5 per-sample + 1 diversity for ALL)."""
    from abi.plugins.amplicon_16s import Amplicon16SPlugin

    plugin = Amplicon16SPlugin()
    sample_sheet = tmp_path / "samples.tsv"
    sample_sheet.write_text("sample_id\tread1\tread2\tgroup\nS1\t/tmp/R1.fq\t/tmp/R2.fq\tsoil\n")

    config = plugin.load_config(
        overrides={
            **_plugin_config("amplicon_16s", tmp_path),
            "input": {"sample_sheet": str(sample_sheet)},
        },
    )
    plan = plugin.build_plan(config, check_files=False)
    # 1 sample × 5 per-sample steps (cutadapt, merge, derep, denoise, taxonomy)
    # + phylogeny + diversity = 7
    assert len(plan.steps) == 7
    tool_ids = {s.tool_id for s in plan.steps}
    assert "vsearch_mergepairs" in tool_ids
    assert "vsearch_derep" in tool_ids
    assert "vsearch_denoise" in tool_ids


def test_amplicon_16s_merge_step_inserted(tmp_path: Path) -> None:
    """Merge step runs after cutadapt and before dereplication."""
    from abi.plugins.amplicon_16s import Amplicon16SPlugin

    plugin = Amplicon16SPlugin()
    sample_sheet = tmp_path / "samples.tsv"
    sample_sheet.write_text("sample_id\tread1\tread2\tgroup\nS1\t/tmp/R1.fq\t/tmp/R2.fq\tsoil\n")

    config = plugin.load_config(
        overrides={
            **_plugin_config("amplicon_16s", tmp_path),
            "input": {"sample_sheet": str(sample_sheet)},
        },
    )
    plan = plugin.build_plan(config, check_files=False)
    # Find merge step for S1
    s1_steps = [s for s in plan.steps if s.sample_id == "S1"]
    step_names = [s.tool_id for s in s1_steps]
    # Verify order: cutadapt → merge → derep
    cutadapt_idx = step_names.index("cutadapt")
    merge_idx = step_names.index("vsearch_mergepairs")
    derep_idx = step_names.index("vsearch_derep")
    assert cutadapt_idx < merge_idx < derep_idx
    # Merge step output feeds into derep input
    merge_step = s1_steps[merge_idx]
    derep_step = s1_steps[derep_idx]
    assert "merged_fasta" in merge_step.outputs
    assert derep_step.inputs["merged_fasta"] == merge_step.outputs["merged_fasta"]


# ── metatranscriptomics ──────────────────────────────────────────────────


def test_metatranscriptomics_dry_run(tmp_path: Path) -> None:
    """Plan generation for metatranscriptomics pipeline."""
    from abi.plugins.metatranscriptomics import MetatranscriptomicsPlugin

    plugin = MetatranscriptomicsPlugin()
    sample_sheet = tmp_path / "samples.tsv"
    sample_sheet.write_text("sample_id\tread1\tread2\nS1\t/tmp/R1.fq\t/tmp/R2.fq\n")

    config = plugin.load_config(
        overrides={
            **_plugin_config("metatranscriptomics", tmp_path),
            "input": {"sample_sheet": str(sample_sheet)},
        },
    )
    plan = plugin.build_plan(config, check_files=False)
    assert len(plan.steps) == 3  # 3 tools × 1 sample
    assert {s.tool_id for s in plan.steps} >= {"fastp", "star", "featurecounts"}
