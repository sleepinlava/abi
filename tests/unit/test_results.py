from __future__ import annotations

from abi.plugins import get_plugin
from abi.results import (
    ABIResultWriter,
    completed_abi_result_outputs,
    validate_abi_result_dir,
)
from abi.schemas import ExecutionPlan, SampleContext, SampleInput
from abi.tools import ToolRegistry


def test_result_writer_produces_a_self_validating_bundle(tmp_path):
    plugin = get_plugin("metatranscriptomics")
    sample = SampleInput(sample_id="S1", platform="illumina")
    context = SampleContext(samples=[sample], multi_sample=False, has_groups=False)
    plan = ExecutionPlan(
        project_name="result-writer",
        analysis_type=plugin.plugin_id,
        mode="auto",
        threads=1,
        outdir=str(tmp_path),
        log_dir=str(tmp_path / "logs"),
        samples=[sample],
        steps=[],
        selected_tools=[],
        sample_context=context,
    )
    writer = ABIResultWriter(plugin, ToolRegistry([]))

    outputs = writer.write(
        plan=plan,
        config={"outdir": str(tmp_path)},
        command_rows=[],
        status="success",
        smoke=True,
        trace_rows=[{"task_id": "1", "status": "COMPLETED"}],
    )
    validation = validate_abi_result_dir(tmp_path)
    completed = completed_abi_result_outputs(tmp_path)

    assert outputs["progress_events"].exists()
    assert outputs["trace"].exists()
    assert validation["valid"] is True
    assert validation["analysis_type"] == "metatranscriptomics"
    assert completed is not None
    assert completed["plan"] == outputs["plan"]
    assert completed["report"] == outputs["report"]
    assert completed["trace"] == outputs["trace"]


def test_result_validation_reports_missing_and_malformed_artifacts(tmp_path):
    missing = validate_abi_result_dir(tmp_path / "missing")
    assert missing["status"] == "missing"

    tmp_path.mkdir(exist_ok=True)
    (tmp_path / "execution_plan.json").write_text("{bad", encoding="utf-8")
    malformed = validate_abi_result_dir(tmp_path)
    assert malformed["valid"] is False
    assert completed_abi_result_outputs(tmp_path) is None
    assert any("Invalid JSON" in error for error in malformed["errors"])
