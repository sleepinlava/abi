"""Tests for CompiledPlan — compilation, invariants, resource resolution."""

from __future__ import annotations

from pathlib import Path

import pytest

from abi.execution_policy import ExecutionPolicy, ResourceOverride
from abi.tool_catalog import ToolCatalog
from abi.tools import ResourceSpec
from abi.workflow.compiled_plan import (
    CompiledPlan,
    CompiledStep,
    CompilationWarning,
    ExecutionKind,
    _validate_invariants,
    compile_plan,
)
from abi.errors import PlanIntegrityError, UnsupportedExecutionError


# ── Test helpers ─────────────────────────────────────────────────────────────


def _plan_step(
    step_id: str,
    tool_id: str = "fastp",
    category: str = "qc",
    sample_id: str | None = "sample1",
    outputs: dict | None = None,
    params: dict | None = None,
    skipped: bool = False,
) -> "object":
    """Create a lightweight stub matching PlanStep's interface."""
    from types import SimpleNamespace

    return SimpleNamespace(
        step_id=step_id,
        tool_id=tool_id,
        category=category,
        sample_id=sample_id,
        inputs={},
        outputs=outputs or {"output_dir": f"/tmp/out/{category}/{sample_id}"},
        params=params or {},
        skipped=skipped,
        reason=None,
    )


def _exec_plan(
    steps: list,
    *,
    outdir: str = "/tmp/out",
    project_name: str = "test",
    mode: str = "auto",
    threads: int = 4,
    selected_tools: list | None = None,
    analysis_type: str = "metagenomic_plasmid",
) -> "object":
    """Create a lightweight stub matching ExecutionPlan's interface."""
    from types import SimpleNamespace

    return SimpleNamespace(
        project_name=project_name,
        mode=mode,
        threads=threads,
        outdir=outdir,
        steps=steps,
        selected_tools=selected_tools or ["fastp"],
        analysis_type=analysis_type,
        samples=None,
        log_dir="/tmp/out/logs",
    )


# ── ExecutionKind ────────────────────────────────────────────────────────────


class TestExecutionKind:
    def test_values(self) -> None:
        assert ExecutionKind.EXTERNAL.value == "external"
        assert ExecutionKind.INTERNAL_WORKER.value == "internal_worker"
        assert ExecutionKind.INTERNAL_DRIVER.value == "internal_driver"

    def test_is_string(self) -> None:
        assert ExecutionKind.EXTERNAL == "external"
        assert isinstance(ExecutionKind.EXTERNAL, str)


# ── CompiledStep ─────────────────────────────────────────────────────────────


class TestCompiledStep:
    def test_minimal(self) -> None:
        s = CompiledStep(
            step_id="s1",
            tool_id="fastp",
            category="qc",
            sample_id=None,
            execution_kind=ExecutionKind.EXTERNAL,
        )
        assert s.step_id == "s1"
        assert s.dependencies == []
        assert s.resources.cpu == 1
        assert s.env_name == ""

    def test_with_resources(self) -> None:
        s = CompiledStep(
            step_id="s1",
            tool_id="fastp",
            category="qc",
            sample_id=None,
            execution_kind=ExecutionKind.EXTERNAL,
            resources=ResourceSpec(cpu=8, memory="16GB"),
            env_name="autoplasm-qc",
        )
        assert s.resources.cpu == 8
        assert s.resources.memory == "16GB"
        assert s.env_name == "autoplasm-qc"


# ── CompiledPlan ─────────────────────────────────────────────────────────────


class TestCompiledPlan:
    def test_empty(self) -> None:
        cp = CompiledPlan(
            project_name="test",
            mode="auto",
            threads=1,
            outdir=Path("/tmp"),
            steps=[],
        )
        assert len(cp.steps) == 0
        assert cp.step_ids == []

    def test_get(self) -> None:
        cs = CompiledStep(
            step_id="a",
            tool_id="x",
            category="qc",
            sample_id=None,
            execution_kind=ExecutionKind.EXTERNAL,
        )
        cp = CompiledPlan(
            project_name="test",
            mode="auto",
            threads=1,
            outdir=Path("/tmp"),
            steps=[cs],
        )
        assert cp.get("a") is cs
        with pytest.raises(KeyError):
            cp.get("b")

    def test_classification(self) -> None:
        steps = [
            CompiledStep("e", "fastp", "qc", None, ExecutionKind.EXTERNAL),
            CompiledStep("w", "internal", "merge", None, ExecutionKind.INTERNAL_WORKER),
            CompiledStep("d", "internal", "setup", None, ExecutionKind.INTERNAL_DRIVER),
        ]
        cp = CompiledPlan(
            project_name="test",
            mode="auto",
            threads=1,
            outdir=Path("/tmp"),
            steps=steps,
        )
        assert len(cp.external_steps) == 1
        assert len(cp.internal_worker_steps) == 1
        assert len(cp.internal_driver_steps) == 1


# ── compile_plan ─────────────────────────────────────────────────────────────


class TestCompilePlan:
    def test_smoke_external_step(self, tmp_path: Path) -> None:
        """Compile a trivial external-step plan."""
        outdir = tmp_path / "output"
        outdir.mkdir()
        step = _plan_step("sample1_qc_fastp", outputs={"output_dir": str(outdir / "qc" / "sample1")})
        plan = _exec_plan([step], outdir=str(outdir))
        compiled = compile_plan(plan, catalog=ToolCatalog(), outdir=outdir)
        assert len(compiled.steps) == 1
        cs = compiled.steps[0]
        assert cs.step_id == "sample1_qc_fastp"
        assert cs.execution_kind == ExecutionKind.EXTERNAL

    def test_skipped_steps_excluded(self, tmp_path: Path) -> None:
        outdir = tmp_path / "output"
        outdir.mkdir()
        steps = [
            _plan_step("s1", outputs={"output_dir": str(outdir / "qc" / "s1")}),
            _plan_step("s2", outputs={"output_dir": str(outdir / "qc" / "s2")}, skipped=True),
        ]
        plan = _exec_plan(steps, outdir=str(outdir))
        compiled = compile_plan(plan, catalog=ToolCatalog(), outdir=outdir)
        assert len(compiled.steps) == 1
        assert compiled.steps[0].step_id == "s1"

    def test_internal_worker(self, tmp_path: Path) -> None:
        outdir = tmp_path / "output"
        outdir.mkdir()
        handler = _make_handler("worker")
        step = _plan_step(
            "s1",
            tool_id="internal",
            outputs={"output_dir": str(outdir / "merge" / "sample1")},
            params={"_internal_handler": handler},
        )
        plan = _exec_plan([step], outdir=str(outdir))
        compiled = compile_plan(plan, catalog=ToolCatalog(), outdir=outdir)
        assert compiled.steps[0].execution_kind == ExecutionKind.INTERNAL_WORKER

    def test_internal_driver(self, tmp_path: Path) -> None:
        outdir = tmp_path / "output"
        outdir.mkdir()
        handler = _make_handler("driver")
        step = _plan_step(
            "driver_hdf5_build",
            tool_id="internal",
            outputs={"output_dir": str(outdir / "driver_output")},
            params={"_internal_handler": handler},
            sample_id=None,
        )
        plan = _exec_plan([step], outdir=str(outdir))
        compiled = compile_plan(plan, catalog=ToolCatalog(), outdir=outdir)
        assert compiled.steps[0].execution_kind == ExecutionKind.INTERNAL_DRIVER

    def test_path_escape_rejected(self, tmp_path: Path) -> None:
        outdir = tmp_path / "output"
        outdir.mkdir()
        step = _plan_step(
            "bad",
            outputs={"output_dir": "/etc/passwd"},
        )
        plan = _exec_plan([step], outdir=str(outdir))
        with pytest.raises(PlanIntegrityError, match="escapes"):
            compile_plan(plan, catalog=ToolCatalog(), outdir=outdir)

    def test_registry_tool_with_catalog(self, tmp_path: Path) -> None:
        """Compile with a catalog that knows about the tool."""
        from abi.tool_catalog import RuntimeToolDescriptor

        outdir = tmp_path / "output"
        outdir.mkdir()
        desc = RuntimeToolDescriptor(
            tool_id="fastp",
            name="FastP",
            env_name="autoplasm-qc",
            resources=ResourceSpec(cpu=4, memory="8GB"),
        )
        catalog = ToolCatalog([desc])
        step = _plan_step("sample1_qc_fastp", outputs={"output_dir": str(outdir / "qc" / "sample1")})
        plan = _exec_plan([step], outdir=str(outdir))
        compiled = compile_plan(plan, catalog=catalog, outdir=outdir)
        cs = compiled.steps[0]
        assert cs.resources.cpu == 4
        assert cs.env_name == "autoplasm-qc"

    def test_policy_applied(self, tmp_path: Path) -> None:
        """Policy invocation override wins over catalog."""
        from abi.tool_catalog import RuntimeToolDescriptor

        outdir = tmp_path / "output"
        outdir.mkdir()
        desc = RuntimeToolDescriptor(
            tool_id="fastp",
            resources=ResourceSpec(cpu=4, memory="8GB"),
        )
        catalog = ToolCatalog([desc])
        policy = ExecutionPolicy(
            invocation_overrides=ResourceOverride(cpu=2, memory="4GB"),
        )
        step = _plan_step("s1", outputs={"output_dir": str(outdir / "qc" / "s1")})
        plan = _exec_plan([step], outdir=str(outdir))
        compiled = compile_plan(plan, catalog=catalog, policy=policy, outdir=outdir)
        cs = compiled.steps[0]
        assert cs.resources.cpu == 2
        assert cs.resources.memory == "4GB"


# ── Invariant checks ─────────────────────────────────────────────────────────


class TestInvariants:
    def test_missing_dependency(self) -> None:
        cs = CompiledStep(
            step_id="s1",
            tool_id="fastp",
            category="qc",
            sample_id=None,
            execution_kind=ExecutionKind.EXTERNAL,
            dependencies=["nonexistent"],
        )
        cp = CompiledPlan(
            project_name="test",
            mode="auto",
            threads=1,
            outdir=Path("/tmp"),
            steps=[cs],
            enabled_steps=["s1"],
        )
        with pytest.raises(PlanIntegrityError, match="undefined step"):
            _validate_invariants(cp, {"s1"})

    def test_self_dependency(self) -> None:
        cs = CompiledStep(
            step_id="s1",
            tool_id="fastp",
            category="qc",
            sample_id=None,
            execution_kind=ExecutionKind.EXTERNAL,
            dependencies=["s1"],
        )
        cp = CompiledPlan(
            project_name="test",
            mode="auto",
            threads=1,
            outdir=Path("/tmp"),
            steps=[cs],
            enabled_steps=["s1"],
        )
        with pytest.raises(PlanIntegrityError, match="depends on itself"):
            _validate_invariants(cp, {"s1"})

    def test_cycle(self) -> None:
        a = CompiledStep(
            step_id="a", tool_id="x", category="c", sample_id=None,
            execution_kind=ExecutionKind.EXTERNAL, dependencies=["b"],
        )
        b = CompiledStep(
            step_id="b", tool_id="y", category="c", sample_id=None,
            execution_kind=ExecutionKind.EXTERNAL, dependencies=["a"],
        )
        cp = CompiledPlan(
            project_name="test",
            mode="auto",
            threads=1,
            outdir=Path("/tmp"),
            steps=[a, b],
            enabled_steps=["a", "b"],
        )
        with pytest.raises(PlanIntegrityError, match="Cycle"):
            _validate_invariants(cp, {"a", "b"})

    def test_mismatched_enabled(self) -> None:
        cs = CompiledStep(
            step_id="a", tool_id="x", category="qc", sample_id=None,
            execution_kind=ExecutionKind.EXTERNAL,
        )
        cp = CompiledPlan(
            project_name="test",
            mode="auto",
            threads=1,
            outdir=Path("/tmp"),
            steps=[cs],
            enabled_steps=["a", "b"],  # b not in steps
        )
        with pytest.raises(PlanIntegrityError, match="missing"):
            _validate_invariants(cp, {"a", "b"})


# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_handler(scope: str) -> "object":
    """Create a stub internal handler with execution_scope."""
    from types import SimpleNamespace

    return SimpleNamespace(handler_id="test_handler", execution_scope=scope)
