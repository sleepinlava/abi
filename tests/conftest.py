"""Shared test fixtures for ABI."""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure src/ is on the path for editable installs
src = Path(__file__).resolve().parents[1] / "src"
if str(src) not in sys.path:
    sys.path.insert(0, str(src))

import pytest  # noqa: E402

from abi.schemas import ABISample, ABISampleContext  # noqa: E402


@pytest.fixture
def mock_sample() -> ABISample:
    """A minimal valid ABISample for use across plugin tests."""
    return ABISample(
        sample_id="S1",
        platform="illumina",
        group="treatment",
        read1="/tmp/S1_R1.fastq.gz",
        read2="/tmp/S1_R2.fastq.gz",
        condition="treated",
    )


@pytest.fixture
def mock_sample_context(mock_sample: ABISample) -> ABISampleContext:
    """A single-sample context with two groups for differential analysis."""
    return ABISampleContext(
        samples=[mock_sample],
        multi_sample=False,
        has_groups=False,
        enable_sample_analysis=False,
        enable_differential_abundance=False,
    )


@pytest.fixture
def mock_contract_dict() -> dict:
    """A minimal valid tool contract dict for lint/test scaffolding."""
    return {
        "tool_id": "fastp",
        "name": "fastp",
        "category": "qc",
        "purpose": "Adapter trimming and quality filtering",
        "execution": {
            "env_name": "abi-qc",
            "executable": "fastp",
            "command_template": "fastp -i {read1} -o {clean_read1}",
            "network": False,
            "writes_output": True,
        },
        "resources": {"cpu": 4, "memory": "4GB", "walltime": "01:00:00"},
    }


@pytest.fixture
def tmp_project(tmp_path: Path) -> Path:
    """Scaffold a minimal project directory with common subdirectories."""
    for sub in ("results", "logs", "provenance", "tables"):
        (tmp_path / sub).mkdir(parents=True, exist_ok=True)
    return tmp_path
