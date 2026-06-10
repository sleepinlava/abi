"""Tests for ABI schemas."""

from __future__ import annotations

from abi.schemas import (
    ABIError,
    ABIExecutionPlan,
    ABIPlanStep,
    ABISample,
    ABISampleContext,
)


def test_abi_error_is_runtime_error():
    assert issubclass(ABIError, RuntimeError)


def test_abi_sample_to_dict():
    sample = ABISample(sample_id="S1", platform="illumina", read1="R1.fq", read2="R2.fq")
    d = sample.to_dict()
    assert d["sample_id"] == "S1"
    assert d["platform"] == "illumina"
    assert d["read1"] == "R1.fq"
    assert d["attributes"] == {}


def test_abi_sample_context_to_dict():
    sample = ABISample(sample_id="S1")
    ctx = ABISampleContext(samples=[sample], multi_sample=False, has_groups=False)
    d = ctx.to_dict()
    assert d["multi_sample"] is False
    assert len(d["samples"]) == 1


def test_abi_plan_step_to_dict():
    step = ABIPlanStep(
        step_id="step_1", sample_id="S1", step_name="qc", tool_id="fastp", category="qc"
    )
    d = step.to_dict()
    assert d["step_id"] == "step_1"
    assert d["skipped"] is False


def test_abi_execution_plan_to_dict():
    sample = ABISample(sample_id="S1")
    ctx = ABISampleContext(samples=[sample], multi_sample=False, has_groups=False)
    step = ABIPlanStep(
        step_id="step_1", sample_id="S1", step_name="qc", tool_id="fastp", category="qc"
    )
    plan = ABIExecutionPlan(
        project_name="test",
        analysis_type="metatranscriptomics",
        mode="auto",
        threads=4,
        outdir="/tmp/out",
        log_dir="/tmp/log",
        samples=[sample],
        steps=[step],
        sample_context=ctx,
        selected_tools=["fastp"],
    )
    d = plan.to_dict()
    assert d["project_name"] == "test"
    assert d["analysis_type"] == "metatranscriptomics"
    assert len(d["steps"]) == 1
