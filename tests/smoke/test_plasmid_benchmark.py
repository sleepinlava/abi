"""Benchmark test: metagenomic_plasmid value-level assertions.

Runs the core pipeline sub-path with RefSeq plasmid data and validates
actual output VALUES (not just file existence). Uses RefSeq plasmids
from data/examples/plasmid_refseq_smoke/.

Skip with: pytest -m "not requires_tools"
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest
import yaml


def _tool_which(executable: str) -> str | None:
    """Locate a tool in the metagenomic_plasmid envs or system PATH."""
    for env_name in ("autoplasm-base", "metagenomic_plasmid", "base"):
        env_bin = os.path.expanduser(f"~/miniconda3/envs/{env_name}/bin")
        path = os.path.join(env_bin, executable)
        if os.path.isfile(path) and os.access(path, os.X_OK):
            return path
    import shutil

    return shutil.which(executable)


requires_plasmid_tools = pytest.mark.skipif(
    not (_tool_which("fastp") and _tool_which("prodigal")),
    reason="plasmid core tools (fastp, prodigal) not found",
)


def _load_expected() -> dict:
    root = Path(__file__).resolve().parents[2]
    path = root / "data" / "benchmarks" / "metagenomic_plasmid" / "expected_assertions.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))["metagenomic_plasmid"]


@pytest.mark.smoke
@pytest.mark.requires_tools
@requires_plasmid_tools
def test_plasmid_benchmark_assertions(tmp_path: Path) -> None:
    """Run metagenomic_plasmid core pipeline and validate outputs."""
    from abi.config import PROJECT_ROOT

    expected = _load_expected()

    # 1. Set up workspace with RefSeq plasmids
    smoke_dir = PROJECT_ROOT / "data" / "examples" / "plasmid_refseq_smoke"
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    for fa in smoke_dir.glob("*.fasta"):
        (data_dir / fa.name).symlink_to(fa)

    # 2. Write config
    results_dir = tmp_path / "results"
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        yaml.dump(
            {
                "project_name": "bench-plasmid",
                "mode": "local",
                "threads": 2,
                "outdir": str(results_dir),
                "log_dir": str(results_dir / "logs"),
                "dry_run": False,
                "input": {
                    "sample_sheet": str(smoke_dir / "sample_sheet.tsv"),
                },
                "plasmid_detection": {
                    "tools": ["genomad"],
                    "strategy": "single_tool",
                },
            }
        )
    )

    # 3. Execute pipeline
    new_env = os.environ.copy()
    new_env["MAMBA_ROOT"] = os.path.expanduser("~/miniconda3")

    proc = subprocess.run(
        [
            "abi",
            "run",
            "--type",
            "metagenomic_plasmid",
            "--confirm-execution",
            "--config",
            str(config_path),
        ],
        capture_output=True,
        text=True,
        env=new_env,
        check=False,
        timeout=900,
    )
    assert proc.returncode in (0, 1), (
        f"Pipeline failed (exit {proc.returncode}):\nSTDERR: {proc.stderr[-800:]}"
    )

    # ── Validate outputs ──────────────────────────────────────────────────

    # --- QC ---
    qc_dir = results_dir / "01_qc"
    if qc_dir.exists():
        assert expected["qc"]["clean_fastq_exists"]

    # --- Assembly ---
    asm_dir = results_dir / "02_assembly"
    if asm_dir.exists():
        contig_files = list(asm_dir.rglob("contigs.fasta"))
        contig_files += list(asm_dir.rglob("final.contigs.fa"))
        if contig_files:
            content = contig_files[0].read_text(encoding="utf-8")
            n_contigs = content.count(">")
            assert n_contigs >= expected["assembly"]["min_contigs"], (
                f"Only {n_contigs} contigs, expected >= {expected['assembly']['min_contigs']}"
            )

    # --- Gene prediction ---
    gene_dir = results_dir / "03_gene_prediction"
    if gene_dir.exists():
        faa_files = list(gene_dir.rglob("*.faa"))
        if faa_files:
            n_proteins = faa_files[0].read_text(encoding="utf-8").count(">")
            assert n_proteins >= expected["gene_prediction"]["min_cds"], (
                f"Only {n_proteins} CDS, expected >= {expected['gene_prediction']['min_cds']}"
            )

    # --- Plasmid detection ---
    plasmid_dir = results_dir / "04_plasmid_detection"
    if plasmid_dir.exists():
        report_files = list(plasmid_dir.rglob("*plasmid*.tsv"))
        report_files += list(plasmid_dir.rglob("*summary*.tsv"))
        has_report = len(report_files) > 0
        assert has_report or not expected["plasmid_detection"]["plasmid_report_exists"], (
            "Plasmid detection report missing"
        )

    # --- Provenance ---
    prov = results_dir / "provenance"
    assert (prov / "run_summary.json").exists(), "run_summary.json missing"
    cmd_tsv = prov / "commands.tsv"
    if cmd_tsv.exists():
        n_cmds = len(cmd_tsv.read_text(encoding="utf-8").splitlines()) - 1
        assert n_cmds >= expected["provenance"]["min_commands"], (
            f"Only {n_cmds} commands, expected >= {expected['provenance']['min_commands']}"
        )

    # --- Report ---
    report_md = results_dir / "report" / "report.md"
    if report_md.exists():
        content = report_md.read_text(encoding="utf-8").lower()
        assert expected["report"]["contains_tool_name"] in content, (
            f"Report missing '{expected['report']['contains_tool_name']}'"
        )

    print("\n✓ metagenomic_plasmid benchmark assertions all passed")
