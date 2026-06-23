"""Tests for ABI SDK boundaries."""

from __future__ import annotations

import re
from importlib.metadata import version
from pathlib import Path

import abi
from abi.agent import ABIAgentInterface
from abi.errors import ABIError, ConfigError, SampleSheetError, ToolError
from abi.schemas import ABIError as SchemaABIError
from abi.tools import GenericCommandSkill, RunResult, ToolRegistry, ToolSkill


def test_runtime_version_matches_distribution_metadata():
    assert abi.__version__ == version("abi-agent")


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


def test_no_autoplasm_imports_from_public_sdk_and_standalone_plugin():
    root = Path(__file__).resolve().parents[1]
    checked_paths = [
        root / "src" / "abi" / "openai_contracts.py",
        root / "src" / "abi" / "interfaces.py",
        root / "src" / "abi" / "tools.py",
        root / "src" / "abi" / "errors.py",
        root / "src" / "abi" / "executor.py",
        root / "src" / "abi" / "results.py",
        root / "src" / "abi" / "runtimes" / "local.py",
        root / "src" / "abi" / "runtimes" / "nextflow.py",
    ]
    checked_paths.extend((root / "plugins" / "metatranscriptomics").rglob("*"))
    leaks = []
    for path in checked_paths:
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8").lower()
        if (
            "from autoplasm." in text
            or "import autoplasm." in text
            or "from abi.autoplasm" in text
            or "import abi.autoplasm" in text
        ):
            leaks.append(str(path.relative_to(root)))
    assert leaks == []


def test_core_does_not_import_concrete_plugin_implementations():
    root = Path(__file__).resolve().parents[1]
    source_root = root / "src" / "abi"
    excluded_roots = {
        source_root / "plugins",
        source_root / "autoplasm",
    }
    pattern = re.compile(r"^\s*(?:from|import)\s+abi\.plugins\.", re.MULTILINE)
    leaks = []
    for path in source_root.rglob("*.py"):
        if any(excluded in path.parents for excluded in excluded_roots):
            continue
        if pattern.search(path.read_text(encoding="utf-8")):
            leaks.append(str(path.relative_to(root)))
    assert leaks == []
