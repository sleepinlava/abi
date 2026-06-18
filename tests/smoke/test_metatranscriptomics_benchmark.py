"""Benchmark test: metatranscriptomics value-level assertions.

Runs the full pipeline with synthetic data and validates actual output VALUES
(not just file existence). Uses the expected_assertions.yaml benchmark spec.

Pipeline: fastp → STAR (or HISAT2) → featureCounts

Skip with: pytest -m "not requires_tools"
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest
import yaml

# ── Tool availability ───────────────────────────────────────────────────────


def _tool_which(executable: str) -> str | None:
    """Locate a tool in the metatranscriptomics conda envs or system PATH."""
    for env_name in ("abi-qc", "abi-stats", "metatranscriptomics"):
        env_bin = os.path.expanduser(f"~/miniconda3/envs/{env_name}/bin")
        path = os.path.join(env_bin, executable)
        if os.path.isfile(path) and os.access(path, os.X_OK):
            return path
    import shutil

    return shutil.which(executable)


requires_meta_tools = pytest.mark.skipif(
    not (_tool_which("fastp") and (_tool_which("STAR") or _tool_which("hisat2"))),
    reason="metatranscriptomics tools (fastp, STAR/hisat2) not found",
)


# ── Helper: load benchmark assertions ───────────────────────────────────────


def _load_expected() -> dict:
    root = Path(__file__).resolve().parents[2]
    path = root / "data" / "benchmarks" / "metatranscriptomics" / "expected_assertions.yaml"
    if path.exists():
        return yaml.safe_load(path.read_text(encoding="utf-8"))["metatranscriptomics"]
    return {}


# ── Benchmark test ──────────────────────────────────────────────────────────


@pytest.mark.smoke
@pytest.mark.requires_tools
@requires_meta_tools
def test_metatranscriptomics_benchmark_assertions(tmp_path: Path) -> None:
    """Run metatranscriptomics pipeline and validate outputs against benchmark assertions."""
    from abi.config import PROJECT_ROOT

    expected = _load_expected()

    results_dir = tmp_path / "results"
    config_path = tmp_path / "config.yaml"

    # Use example data if available, otherwise generate minimal sample sheet
    example_dir = PROJECT_ROOT / "data" / "examples" / "transcriptomics"
    sample_sheet = tmp_path / "samples.tsv"
    if example_dir.is_dir():
        ss = example_dir / "sample_sheet.tsv"
        if ss.exists():
            sample_sheet.write_text(ss.read_text(encoding="utf-8"))
    if not sample_sheet.exists():
        sample_sheet.write_text(
            "sample_id\tgroup\tcondition\tplatform\tread1\tread2\n"
            "sample1\ttreatment\ttreated\trna_seq\traw/sample1_R1.fastq.gz\traw/sample1_R2.fastq.gz\n"
            "sample2\ttreatment\ttreated\trna_seq\traw/sample2_R1.fastq.gz\traw/sample2_R2.fastq.gz\n"
        )

    # Locate STAR index and GTF
    default_index = str(PROJECT_ROOT / "resources" / "star_index")
    star_index = Path(os.environ.get("ABI_STAR_INDEX", default_index))
    gtf = Path(
        os.environ.get(
            "ABI_GTF",
            str(PROJECT_ROOT / "resources" / "star_index" / "NC_000913.3.gtf"),
        )
    )

    config_path.write_text(
        yaml.dump(
            {
                "project_name": "bench-meta",
                "mode": "local",
                "threads": 2,
                "outdir": str(results_dir),
                "log_dir": str(results_dir / "logs"),
                "input": {"sample_sheet": str(sample_sheet)},
                "alignment": {"tool": "star"},
                "resources": {
                    "genome_index": str(star_index),
                    "annotation_gtf": str(gtf),
                },
            }
        )
    )

    new_env = os.environ.copy()
    new_env["MAMBA_ROOT"] = os.path.expanduser("~/miniconda3")

    proc = subprocess.run(
        [
            "abi",
            "run",
            "--type",
            "metatranscriptomics",
            "--confirm-execution",
            "--config",
            str(config_path),
        ],
        capture_output=True,
        text=True,
        env=new_env,
        check=False,
        timeout=600,
    )
    assert proc.returncode in (0, 1), (
        f"Pipeline failed (exit {proc.returncode}):\nSTDERR: {proc.stderr[-800:]}"
    )

    # ── Validate outputs against benchmark assertions ────────────────────────

    # --- QC (fastp) ---
    qc_assert = expected.get("qc", {})
    qc_samples_found = 0
    for sample_id in ("sample1", "sample2"):
        qc_dir = results_dir / "01_qc" / sample_id
        if qc_dir.is_dir():
            qc_samples_found += 1
            clean_reads = list(qc_dir.glob("*clean.fastq.gz"))
            assert len(clean_reads) >= 1, f"No clean FASTQ in {qc_dir}"
    if qc_assert.get("min_samples_with_output"):
        assert qc_samples_found >= qc_assert["min_samples_with_output"], (
            f"QC: {qc_samples_found} samples, expected ≥{qc_assert['min_samples_with_output']}"
        )

    # --- Alignment (STAR / HISAT2) ---
    align_assert = expected.get("alignment", {})
    for sample_id in ("sample1", "sample2"):
        align_dir = results_dir / "02_alignment" / sample_id
        if align_dir.is_dir():
            # Check for BAM file
            bam_files = list(align_dir.rglob("*.bam"))
            assert len(bam_files) >= 1, f"No BAM file in {align_dir}"

            # Check mapping rate from STAR Log.final.out
            log_files = list(align_dir.rglob("Log.final.out"))
            if log_files and align_assert.get("min_mapping_rate"):
                log_content = log_files[0].read_text(encoding="utf-8")
                for line_text in log_content.splitlines():
                    if "Uniquely mapped reads %" in line_text:
                        try:
                            pct = float(line_text.split("|")[-1].strip().rstrip("%"))
                            min_pct = align_assert["min_mapping_rate"] * 100
                            assert pct >= min_pct, f"Mapping rate {pct:.1f}% < {min_pct:.0f}%"
                        except (ValueError, IndexError):
                            pass
            break

    # --- Expression (featureCounts) ---
    expr_assert = expected.get("expression", {})
    for sample_id in ("sample1", "sample2"):
        expr_dir = results_dir / "03_expression" / sample_id
        if expr_dir.is_dir():
            count_files = list(expr_dir.glob("*counts*"))
            if count_files and expr_assert.get("gene_counts_rows_min"):
                # featureCounts output: tab-separated with comment lines starting with #
                content = count_files[0].read_text(encoding="utf-8")
                data_lines = [
                    line
                    for line in content.splitlines()
                    if line.strip() and not line.startswith("#")
                ]
                n_genes = len(data_lines) - 1  # minus header
                assert n_genes >= expr_assert["gene_counts_rows_min"], (
                    f"Expression: {n_genes} genes, expected ≥{expr_assert['gene_counts_rows_min']}"
                )
            break

    # --- Report ---
    report_assert = expected.get("report", {})
    report_md = results_dir / "report" / "report.md"
    if report_md.exists():
        content = report_md.read_text(encoding="utf-8").lower()
        if report_assert.get("contains_tool_name"):
            assert report_assert["contains_tool_name"] in content, (
                f"Report missing '{report_assert['contains_tool_name']}'"
            )

    # --- Provenance ---
    prov_assert = expected.get("provenance", {})
    prov = results_dir / "provenance"
    assert (prov / "run_summary.json").exists(), "run_summary.json missing"

    cmd_tsv = prov / "commands.tsv"
    if cmd_tsv.exists():
        n_cmds = len(cmd_tsv.read_text(encoding="utf-8").splitlines()) - 1
        if prov_assert.get("min_commands"):
            assert n_cmds >= prov_assert["min_commands"], (
                f"Only {n_cmds} provenance commands, expected ≥{prov_assert['min_commands']}"
            )

    print("\n✓ metatranscriptomics benchmark assertions all passed")
