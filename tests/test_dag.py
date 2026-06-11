"""Tests for ABI DAG inference."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict

import pytest

from abi.dag import infer_dag, process_name
from abi.schemas import ABIError


@dataclass
class FakeStep:
    step_id: str
    tool_id: str = "tool"
    inputs: Dict[str, Any] = field(default_factory=dict)
    outputs: Dict[str, Any] = field(default_factory=dict)
    skipped: bool = False


def test_simple_chain(tmp_path):
    s1 = FakeStep(
        step_id="s1",
        outputs={"out": str(tmp_path / "a.txt")},
    )
    s2 = FakeStep(
        step_id="s2",
        inputs={"inp": str(tmp_path / "a.txt")},
    )
    dag = infer_dag([s1, s2], project_root=tmp_path)
    assert dag.topological_order == ["s1", "s2"]
    assert dag.roots == ["s1"]
    assert "s1" in dag.edges["s2"]


def test_independent_steps(tmp_path):
    s1 = FakeStep(step_id="s1", outputs={"out": str(tmp_path / "a.txt")})
    s2 = FakeStep(step_id="s2", outputs={"out": str(tmp_path / "b.txt")})
    dag = infer_dag([s1, s2], project_root=tmp_path)
    assert len(dag.roots) == 2
    assert dag.edges["s1"] == []
    assert dag.edges["s2"] == []


def test_skipped_step_excluded(tmp_path):
    s1 = FakeStep(step_id="s1", outputs={"out": str(tmp_path / "a.txt")})
    s2 = FakeStep(step_id="s2", skipped=True)
    dag = infer_dag([s1, s2], project_root=tmp_path)
    assert len(dag.bindings) == 1


def test_process_name():
    assert process_name("step_1_qc") == "STEP_1_QC"
    assert process_name("123abc") == "STEP_123ABC"


def test_duplicate_output_raises(tmp_path):
    s1 = FakeStep(step_id="s1", outputs={"out": str(tmp_path / "a.txt")})
    s2 = FakeStep(step_id="s2", outputs={"out": str(tmp_path / "a.txt")})
    with pytest.raises(ABIError, match="Duplicate"):
        infer_dag([s1, s2], project_root=tmp_path)
