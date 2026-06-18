"""Benchmark test: wgs_bacteria value-level assertions.

Runs the full pipeline with synthetic data and validates actual output VALUES
(not just file existence). Uses the expected_assertions.yaml benchmark spec.

Pipeline: fastp → SPAdes → Prokka → MLST → AMRFinderPlus

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
    """Locate a tool in the wgs conda env or system PATH."""
    env_bin = os.path.expanduser("~/miniconda3/envs/wgs/bin")
    path = os.path.join(env_bin, executable)
    if os.path.isfile(path) and os.access(path, os.X_OK):
        return path
    import shutil

    return shutil.which(executable)


requires_wgs_tools = pytest.mark.skipif(
    not (_tool_which("fastp") and _tool_which("spades.py")),
    reason="wgs tools (fastp, spades.py) not found",
)


# ── Helper: load benchmark assertions ───────────────────────────────────────


def _load_expected() -> dict:
    root = Path(__file__).resolve().parents[2]
    path = root / "data" / "benchmarks" / "wgs_bacteria" / "expected_assertions.yaml"
    if path.exists():
        return yaml.safe_load(path.read_text(encoding="utf-8"))["wgs_bacteria"]
    return {}


# ── Benchmark test ──────────────────────────────────────────────────────────


@pytest.mark.smoke
@pytest.mark.requires_tools
@requires_wgs_tools
def test_wgs_benchmark_assertions(tmp_path: Path) -> None:
    """Run wgs_bacteria pipeline and validate outputs against benchmark assertions."""
    from abi.config import PROJECT_ROOT

    expected = _load_expected()

    results_dir = tmp_path / "results"
    config_path = tmp_path / "config.yaml"

    # Use example sample sheet if available
    example_dir = PROJECT_ROOT / "data" / "examples" / "wgs_bacteria"
    sample_sheet = tmp_path / "samples.tsv"
    if example_dir.is_dir():
        ss = example_dir / "sample_sheet.tsv"
        if ss.exists():
            sample_sheet.write_text(ss.read_text(encoding="utf-8"))

    # Verify that at least one sample's read files exist before proceeding
    _sample_rows = sample_sheet.read_text(encoding="utf-8").strip().split("\n")
    _header = _sample_rows[0].split("\t")
    try:
        _r1_idx = _header.index("read1")
        _r2_idx = _header.index("read2")
    except ValueError:
        pytest.skip("Sample sheet missing read1/read2 columns")
    _found_reads = False
    for _row in _sample_rows[1:]:
        _cols = _row.split("\t")
        _r1 = Path(_cols[_r1_idx])
        _r2 = Path(_cols[_r2_idx])
        if _r1.exists() or _r2.exists():
            _found_reads = True
            break
    if not _found_reads:
        pytest.skip("No read files found for benchmark samples")

    config_path.write_text(
        yaml.dump(
            {
                "use_dag": False,
                "project_name": "bench-wgs",
                "mode": "local",
                "threads": 2,
                "outdir": str(results_dir),
                "log_dir": str(results_dir / "logs"),
                "input": {"sample_sheet": str(sample_sheet)},
                "annotation": {"genus": "Escherichia", "species": "coli"},
                "typing": {"mlst_scheme": "auto"},
            }
        )
    )

    # PATH setup: ensure wgs conda env tools are found
    new_env = os.environ.copy()
    fastp_path = _tool_which("fastp")
    if fastp_path:
        new_env["PATH"] = f"{Path(fastp_path).parent}:{new_env.get('PATH', '')}"
    new_env["MAMBA_ROOT"] = os.path.expanduser("~/miniconda3")

    proc = subprocess.run(
        [
            "abi",
            "run",
            "--type",
            "wgs_bacteria",
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

    # ── Validate outputs against benchmark assertions ────────────────────────

    # --- QC (fastp) ---
    qc_assert = expected.get("qc", {})
    qc_samples_found = 0
    for sample_id in ("isolate1", "isolate2"):
        qc_dir = results_dir / "01_qc" / sample_id
        if qc_dir.is_dir():
            qc_samples_found += 1
            clean_reads = list(qc_dir.glob("*clean.fastq.gz"))
            assert len(clean_reads) >= 1, f"No clean FASTQ in {qc_dir}"
    if qc_assert.get("min_samples_with_output"):
        assert qc_samples_found >= qc_assert["min_samples_with_output"], (
            f"QC: {qc_samples_found} samples, expected ≥{qc_assert['min_samples_with_output']}"
        )

    # --- Assembly (SPAdes) ---
    asm_assert = expected.get("assembly", {})
    for sample_id in ("isolate1", "isolate2"):
        asm_dir = results_dir / "02_assembly" / sample_id
        if asm_dir.is_dir():
            # SPAdes output: contigs.fasta or scaffolds.fasta
            contig_files = list(asm_dir.rglob("contigs.fasta"))
            contig_files += list(asm_dir.rglob("scaffolds.fasta"))
            if contig_files:
                content = contig_files[0].read_text(encoding="utf-8")
                n_contigs = content.count(">")
                if asm_assert.get("min_contigs"):
                    assert n_contigs >= asm_assert["min_contigs"], (
                        f"Assembly: {n_contigs} contigs, expected ≥{asm_assert['min_contigs']}"
                    )
                if asm_assert.get("max_contigs"):
                    assert n_contigs <= asm_assert["max_contigs"], (
                        f"Assembly: {n_contigs} contigs, expected ≤{asm_assert['max_contigs']}"
                    )
                # Rough N50: sum of first half of contig lengths
                lengths = []
                current_len = 0
                for line in content.splitlines():
                    if line.startswith(">"):
                        if current_len > 0:
                            lengths.append(current_len)
                        current_len = 0
                    else:
                        current_len += len(line.strip())
                if current_len > 0:
                    lengths.append(current_len)
                if lengths and asm_assert.get("min_n50"):
                    lengths.sort(reverse=True)
                    total = sum(lengths)
                    half_total = total / 2
                    cumsum = 0
                    n50 = 0
                    for length in lengths:
                        cumsum += length
                        if cumsum >= half_total:
                            n50 = length
                            break
                    assert n50 >= asm_assert["min_n50"], (
                        f"Assembly N50: {n50}, expected ≥{asm_assert['min_n50']}"
                    )
                break  # check first sample only

    # --- Annotation (Prokka) ---
    ann_assert = expected.get("annotation", {})
    for sample_id in ("isolate1", "isolate2"):
        ann_dir = results_dir / "03_annotation" / sample_id
        if ann_dir.is_dir():
            gff_files = list(ann_dir.glob("*.gff"))
            if ann_assert.get("annotation_gff_exists"):
                assert len(gff_files) >= 1, f"No GFF file in {ann_dir}"

            faa_files = list(ann_dir.glob("*.faa"))
            if faa_files and ann_assert.get("min_cds"):
                n_cds = faa_files[0].read_text(encoding="utf-8").count(">")
                assert n_cds >= ann_assert["min_cds"], (
                    f"Annotation: {n_cds} CDS, expected ≥{ann_assert['min_cds']}"
                )
            break

    # --- MLST Typing ---
    typing_assert = expected.get("typing", {})
    for sample_id in ("isolate1", "isolate2"):
        mlst_dir = results_dir / "04_mlst" / sample_id
        if mlst_dir.is_dir():
            tsv_files = list(mlst_dir.glob("*.tsv"))
            if typing_assert.get("mlst_output_exists"):
                assert len(tsv_files) >= 1, f"No MLST TSV in {mlst_dir}"
            break

    # --- AMR Profiling (AMRFinderPlus) ---
    amr_assert = expected.get("amr", {})
    for sample_id in ("isolate1", "isolate2"):
        amr_dir = results_dir / "05_amr" / sample_id
        if amr_dir.is_dir():
            tsv_files = list(amr_dir.glob("*.tsv"))
            if amr_assert.get("amr_output_exists"):
                assert len(tsv_files) >= 1, f"No AMR TSV in {amr_dir}"
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
    if not (prov / "run_summary.json").exists():
        print("  run_summary.json not generated (pipeline may have partially failed)")
    assert (prov / "run_summary.json").exists(), "run_summary.json missing"

    cmd_tsv = prov / "commands.tsv"
    if cmd_tsv.exists():
        n_cmds = len(cmd_tsv.read_text(encoding="utf-8").splitlines()) - 1
        if prov_assert.get("min_commands"):
            assert n_cmds >= prov_assert["min_commands"], (
                f"Only {n_cmds} provenance commands, expected ≥{prov_assert['min_commands']}"
            )

    print("\n✓ wgs_bacteria benchmark assertions all passed")
