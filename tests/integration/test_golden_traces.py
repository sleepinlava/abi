"""Golden trace replay tests for untrained agent workflows."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from abi.agent import ABIAgentInterface

TRACE_DIR = Path(__file__).resolve().parents[2] / "golden_traces"


@pytest.mark.parametrize(
    "trace_name",
    [
        "amplicon_16s.jsonl",
        "metagenomic_plasmid.jsonl",
        "metatranscriptomics.jsonl",
        "rnaseq_expression.jsonl",
        "wgs_bacteria.jsonl",
    ],
)
def test_golden_trace_replays_agent_lifecycle(trace_name: str, tmp_path: Path) -> None:
    agent = ABIAgentInterface()
    records = _load_trace(TRACE_DIR / trace_name, tmp_path=tmp_path)

    seen_tools = []
    for index, record in enumerate(records, start=1):
        tool = record["tool"]
        payload = json.loads(agent.dispatch(tool, record.get("arguments", {})))
        assert payload["status"] == record["expect_status"], (
            trace_name,
            index,
            payload,
        )
        assert payload["command"]
        seen_tools.append(tool)
        if payload["status"] == "error":
            assert payload["error_code"]
            assert payload["diagnostic_hints"]
        if tool in {"abi_plan", "abi_report"}:
            assert payload["result"]["written_files"]
        if tool == "abi_dry_run":
            # dry_run no longer includes written_files (agents use inspect)
            assert "outdir" in payload["result"]
        if tool == "abi_run":
            assert payload["status"] == "confirmation_required"

    assert seen_tools[:5] == [
        "abi_list_types",
        "abi_plan",
        "abi_dry_run",
        "abi_inspect",
        "abi_report",
    ]
    assert {
        "abi_validate_result",
        "abi_export_agent_context",
        "abi_doctor_agent",
        "abi_run",
    } <= set(seen_tools)


def _load_trace(path: Path, *, tmp_path: Path) -> list[dict[str, Any]]:
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        records.append(_replace_tmpdir(json.loads(line), tmp_path=tmp_path))
    return records


def _replace_tmpdir(value: Any, *, tmp_path: Path) -> Any:
    if isinstance(value, str):
        return value.replace("{tmpdir}", str(tmp_path))
    if isinstance(value, dict):
        return {key: _replace_tmpdir(item, tmp_path=tmp_path) for key, item in value.items()}
    if isinstance(value, list):
        return [_replace_tmpdir(item, tmp_path=tmp_path) for item in value]
    return value
