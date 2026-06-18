"""Smoke tests: real tool execution with synthetic data.

These tests require conda environments with bioinformatics tools installed.
Skip in CI with: pytest -m "not requires_tools"

Each test generates minimal synthetic input data, runs the pipeline via the
plugin Python API, and verifies that key output artifacts exist.
"""

from __future__ import annotations

import gzip
import os
import random
from pathlib import Path

import pytest

# ── Synthetic data generation ────────────────────────────────────────────

# E. coli K-12 MG1655 lacZ gene fragment (first 1000 bp) for synthetic reads
_LACZ_TEMPLATE = (
    "ATGACCATGATTACGGATTCACTGGCCGTCGTTTTACAACGTCGTGACTGGGAAAACCCT"
    "GGCGTTACCCAACTTAATCGCCTTGCAGCACATCCCCCTTTCGCCAGCTGGCGTAATAGC"
    "GAAGAGGCCCGCACCGATCGCCCTTCCCAACAGTTGCGCAGCCTGAATGGCGAATGGCGC"
    "TTTGCCTGGTTTCCGGCACCAGAAGCGGTGCCGGAAAGCTGGCTGGAGTGCGATCTTCCT"
    "GAGGCCGATACTGTCGTCGTCCCCTCAAACTGGCAGATGCACGGTTACGATGCGCCCATC"
    "TACACCAACGTGACCTATCCCATTACGGTCAATCCGCCGTTTGTTCCCACGGAGAATCCG"
    "ACGGGTTGTTACTCGCTCACATTTAATGTTGATGAAAGCTGGCTACAGGAAGGCCAGACG"
    "CGAATTATTTTTGATGGCGTTAACTCGGCGTTTCATCTGTGGTGCAACGGGCGCTGGGTC"
    "GGTTACGGCCAGGACAGTCGTTTGCCGTCTGAATTTGACCTGAGCGCATTTTTACGCGCC"
    "GGAGAAAACCGCCTCGCGGTGATGGTGCTGCGTTGGAGTGACGGCAGTTATCTGGAAGAT"
    "CAGGATATGTGGCGGATGAGCGGCATTTTCCGTGACGTCTCGTTGCTGCATAAACCGACT"
    "ACACAAATCAGCGATTTCCATGTTGCCACTCGCTTTAATGATGATTTCAGCCGCGCTGTA"
    "CTGGAGGCTGAAGTTCAGATGTGCGGCGAGTTGCGTGACTACCTACGGGTAACAGTTTCT"
    "TTATGGCAGGGTGAAACGCAGGTCGCCAGCGGCACCGCGCCTTTCGGCGGTGAAATTATC"
    "GATGAGCGTGGTGGTTATGCCGATCGCGTCACACTACGTCTGAACGTCGAAAACCCGAAA"
    "CTGTGGAGCGCCGAAATCCCGAATCTCTATCGTGCGGTGGTTGAACTGCACACCGCCGAC"
    "GGCACGCTGATTGAAGCAGAAGCCTGCGATGTCGGTTTCCGCGAGGTGCGGATTGAAAAT"
)


def _generate_synthetic_fastq(
    path: Path, n_reads: int = 100, read_len: int = 150, seed: int = 42
) -> Path:
    """Generate a minimal paired-end FASTQ file from lacZ template.

    Uses simple random sampling with a small mutation rate to simulate
    sequencing reads.  Output is gzip-compressed.
    """
    rng = random.Random(seed)
    template_len = len(_LACZ_TEMPLATE)
    max_start = template_len - read_len

    with gzip.open(path, "wt", encoding="utf-8") as fh:
        for i in range(n_reads):
            start = rng.randint(0, max(max_start, 1))
            fragment = _LACZ_TEMPLATE[start : start + read_len]
            # Pad if near end
            while len(fragment) < read_len:
                fragment += _LACZ_TEMPLATE[rng.randint(0, template_len - 1)]
            # 1% mutation rate
            bases = list(fragment)
            for j in range(len(bases)):
                if rng.random() < 0.01:
                    bases[j] = rng.choice("ACGT")
            seq = "".join(bases)
            # Quality: all "I" (Phred 40)
            qual = "I" * read_len
            fh.write(f"@read_{i}\n{seq}\n+\n{qual}\n")
    return path


def _generate_synthetic_data(tmp_path: Path, n_reads: int = 100) -> tuple[Path, Path, Path]:
    """Generate paired-end synthetic FASTQ and sample sheet.

    Returns (read1_path, read2_path, sample_sheet_path).
    """
    # Paired reads: R1 from forward strand, R2 from reverse-complement region
    r1 = tmp_path / "S1_R1.fastq.gz"
    r2 = tmp_path / "S1_R2.fastq.gz"
    _generate_synthetic_fastq(r1, n_reads=n_reads, seed=42)
    _generate_synthetic_fastq(r2, n_reads=n_reads, seed=99)  # different seed for "pair"

    sample_sheet = tmp_path / "samples.tsv"
    sample_sheet.write_text(
        f"sample_id\tread1\tread2\tcondition\n"
        f"S1\t{r1}\t{r2}\ttreated\n"
        f"S2\t{r1}\t{r2}\tuntreated\n"
    )
    return r1, r2, sample_sheet


# ── Tool availability check ──────────────────────────────────────────────


def _tool_available(executable: str) -> bool:
    """Check if a tool executable is on PATH."""
    import shutil

    return shutil.which(executable) is not None


def _env_available(env_name: str) -> bool:
    """Check if a conda environment name has its bin directory."""
    from abi.config import PROJECT_ROOT

    mamba_root = Path(os.environ.get("MAMBA_ROOT", str(PROJECT_ROOT / ".mamba")))
    env_bin = mamba_root / "envs" / env_name / "bin"
    return env_bin.is_dir()


requires_rnaseq_tools = pytest.mark.skipif(
    not (_tool_available("fastp") or _tool_available("STAR")),
    reason="rnaseq tools (fastp, STAR, featureCounts, Rscript) not on PATH",
)


# ── Smoke: rnaseq_expression dry-run (fast, always runs) ─────────────────


def test_rnaseq_synthetic_plan_generation(tmp_path: Path) -> None:
    """Plan generation with synthetic data — validates the full plan structure."""
    from abi.plugins.rnaseq_expression import RNASeqExpressionPlugin

    _generate_synthetic_data(tmp_path, n_reads=10)

    plugin = RNASeqExpressionPlugin()
    config = plugin.load_config(
        overrides={
            "project_name": "smoke-rnaseq",
            "mode": "local",
            "threads": 2,
            "outdir": str(tmp_path / "results"),
            "log_dir": str(tmp_path / "logs"),
            "input": {"sample_sheet": str(tmp_path / "samples.tsv")},
        },
    )
    plan = plugin.build_plan(config, check_files=True)
    assert len(plan.steps) == 8  # 2 samples × 3 + matrix + DESeq2
    # Verify per-sample steps
    s1_steps = [s for s in plan.steps if s.sample_id == "S1"]
    assert len(s1_steps) == 3  # fastp, STAR, featureCounts
    # Verify build_count_matrix feeds into DESeq2
    deseq2_step = next(s for s in plan.steps if s.tool_id == "deseq2")
    matrix_step = next(s for s in plan.steps if s.tool_id == "build_count_matrix")
    assert deseq2_step.inputs["count_matrix"] == matrix_step.outputs["count_matrix"]


# ── Smoke: rnaseq_expression real execution ──────────────────────────────


@pytest.mark.smoke
@pytest.mark.requires_tools
def test_rnaseq_real_execution(tmp_path: Path) -> None:
    """Full rnaseq_expression pipeline with synthetic E. coli lacZ reads.

    Generates 200 paired-end synthetic reads, runs fastp → STAR →
    featureCounts → build_count_matrix → DESeq2, and verifies key
    output artifacts exist.

    Requires: fastp, STAR, featureCounts, Rscript in rnaseq conda env.
    """
    from abi.plugins.rnaseq_expression import RNASeqExpressionPlugin

    # Generate data
    _generate_synthetic_data(tmp_path, n_reads=200)
    results_dir = tmp_path / "results"

    # Check tool availability
    fastp_ok = _tool_available("fastp")
    star_ok = _tool_available("STAR")
    fc_ok = _tool_available("featureCounts")
    r_ok = _tool_available("Rscript")
    tools_ok = fastp_ok and star_ok and fc_ok and r_ok
    if not tools_ok:
        missing = []
        if not fastp_ok:
            missing.append("fastp")
        if not star_ok:
            missing.append("STAR")
        if not fc_ok:
            missing.append("featureCounts")
        if not r_ok:
            missing.append("Rscript")
        pytest.skip(f"Required tools not found: {', '.join(missing)}")

    # Check for STAR index
    from abi.config import PROJECT_ROOT

    default_index = str(PROJECT_ROOT / "data" / "star_index" / "ecoli")
    star_index = Path(os.environ.get("ABI_STAR_INDEX", default_index))
    gtf = Path(os.environ.get("ABI_GTF", str(PROJECT_ROOT / "data" / "ecoli.gtf")))
    if not star_index.is_dir():
        pytest.skip(f"STAR index not found: {star_index}")
    if not gtf.exists():
        pytest.skip(f"Annotation GTF not found: {gtf}")

    plugin = RNASeqExpressionPlugin()
    config = plugin.load_config(
        overrides={
            "project_name": "smoke-rnaseq",
            "mode": "local",
            "threads": 2,
            "outdir": str(results_dir),
            "log_dir": str(results_dir / "logs"),
            "input": {"sample_sheet": str(tmp_path / "samples.tsv")},
            "resources": {
                "genome_index": str(star_index),
                "annotation_gtf": str(gtf),
            },
        },
    )
    plan = plugin.build_plan(config, check_files=True)

    # Execute via the plugin's registry using GenericABIExecutor
    from abi.executor import GenericABIExecutor

    executor = GenericABIExecutor(plugin)
    result = executor.run(plan)

    assert result is not None

    # Verify key outputs exist
    for sample_id in ("S1", "S2"):
        qc_dir = results_dir / "01_qc" / sample_id
        assert qc_dir.is_dir(), f"QC dir missing: {qc_dir}"
        assert list(qc_dir.glob("*clean.fastq.gz")), f"No clean FASTQ in {qc_dir}"

        align_dir = results_dir / "02_alignment" / sample_id
        assert align_dir.is_dir(), f"Alignment dir missing: {align_dir}"

        expr_dir = results_dir / "03_expression" / sample_id
        assert expr_dir.is_dir(), f"Expression dir missing: {expr_dir}"

    # Verify count matrix and DESeq2 results
    de_dir = results_dir / "04_differential_expression"
    assert (de_dir / "count_matrix.tsv").exists(), "count_matrix.tsv missing"
    assert (de_dir / "deseq2_results.tsv").exists(), "deseq2_results.tsv missing"
    assert list(de_dir.glob("*normalized*")), "normalized_expression missing"

    # Verify provenance artifacts
    prov_dir = results_dir / "provenance"
    assert (prov_dir / "commands.tsv").exists(), "commands.tsv missing"
    assert (prov_dir / "run_summary.json").exists(), "run_summary.json missing"
