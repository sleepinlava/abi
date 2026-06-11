"""Tests for ABI SDK boundaries."""

from __future__ import annotations

from pathlib import Path

from abi.agent import ABIAgentInterface
from abi.errors import ABIError, ConfigError, SampleSheetError, ToolError
from abi.schemas import ABIError as SchemaABIError
from abi.tools import GenericCommandSkill, RunResult, ToolRegistry, ToolSkill


def test_public_sdk_imports():
    assert SchemaABIError is ABIError
    assert issubclass(ConfigError, ABIError)
    assert issubclass(SampleSheetError, ABIError)
    assert issubclass(ToolError, ABIError)
    assert ToolRegistry
    assert GenericCommandSkill
    assert ToolSkill
    assert RunResult


def test_agent_plan_requires_analysis_type(tmp_path):
    payload = ABIAgentInterface().dispatch("abi_plan", {"outdir": str(tmp_path)})
    assert '"status": "error"' in payload
    assert "analysis_type" in payload


def test_no_autoplasm_leakage_from_core_sdk_and_demo_plugin():
    root = Path(__file__).resolve().parents[1]
    checked_paths = [
        root / "README.md",
        root / "src" / "abi" / "openai_contracts.py",
        root / "src" / "abi" / "interfaces.py",
        root / "src" / "abi" / "tools.py",
        root / "src" / "abi" / "errors.py",
        root / "src" / "abi" / "runtimes" / "nextflow.py",
    ]
    checked_paths.extend((root / "plugins" / "metatranscriptomics").rglob("*"))
    leaks = []
    for path in checked_paths:
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8").lower()
        if "autoplasm" in text:
            leaks.append(str(path.relative_to(root)))
    assert leaks == []
