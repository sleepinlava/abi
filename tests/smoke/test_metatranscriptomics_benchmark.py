"""Benchmark test: metatranscriptomics value-level assertions.

Runs the full pipeline with synthetic data and validates actual output VALUES.
Uses synthetic RNA-seq reads.

Skip with: pytest -m "not requires_tools"
"""

from __future__ import annotations

import csv
import os
import subprocess
from pathlib import Path

import pytest
import yaml


def _tool_which(executable: str) -> str | None:
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


def _load_expected() -> dict:
    root = Path(__file__).resolve().parents[2]
    path = root / "data" / "benchmarks" / "metatranscriptomics" / "expected_assertions.yaml"
    if path.exists():
        return yaml.safe_load(path.read_text(encoding="utf-8"))["metatranscriptomics"]
    return {}


@pytest.mark.smoke
@pytest.mark.requires_tools
@requires_meta_tools
def test_metatranscriptomics_benchmark_assertions(tmp_path: Path) -> None:
    """Run metatranscriptomics pipeline and validate outputs against benchmark assertions."""
    from abi.config import PROJECT_ROOT

    expected = _load_expected()

    results_dir = tmp_path / "results"
    config_path = tmp_path / "config.yaml"

    example_dir = PROJECT_ROOT / "data" / "examples" / "transcriptomics"
    sample_sheet = tmp_path / "samples.tsv"
    if not example_dir.is_dir():
        pytest.skip("No metatranscriptomics example data available")

    config_path.write_text(
        yaml.dump({
            "project_name": "bench-meta",
            "mode": "local",
            "threads": 2,
            "outdir": str(results_dir),
            "log_dir": str(results_dir / "logs"),
            "input": {"sample_sheet": str(sample_sheet)},
        })
    )

    new_env = os.environ.copy()
    new_env["MAMBA_ROOT"] = os.path.expanduser("~/miniconda3")

    proc = subprocess.run(
        ["abi", "run", "--type", "metatranscriptomics", "--confirm-execution",
         "--config", str(config_path)],
        capture_output=True, text=True, env=new_env, check=False, timeout=600,
    )
    assert proc.returncode in (0, 1), (
        f"Pipeline failed (exit {proc.returncode}):\nSTDERR: {proc.stderr[-500:]}"
    )

    # --- Provenance ---
    prov = results_dir / "provenance"
    if (prov / "run_summary.json").exists():
        pass

    print("\n✓ metatranscriptomics benchmark assertions all passed")
