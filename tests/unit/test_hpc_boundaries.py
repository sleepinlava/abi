from __future__ import annotations

import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from abi.dag import ABIDAG, StepBinding
from abi.runtimes import hpc
from abi.runtimes.base import RuntimeOptions, RuntimeResult
from abi.runtimes.hpc import HpcRuntime
from abi.schemas import ABIError, PlanStep
from abi.step_runner import StepExecutionResult


def _step(step_id: str, *, tool_id: str = "tool", params=None, outputs=None) -> PlanStep:
    return PlanStep(
        step_id=step_id,
        step_name=step_id,
        tool_id=tool_id,
        category="test",
        sample_id="S1",
        params=params or {},
        outputs=outputs or {},
    )


def _dag(first: PlanStep, second: PlanStep | None = None) -> ABIDAG:
    bindings = [StepBinding(first, first.step_id, [], {}, {})]
    edges = {first.step_id: []}
    order = [first.step_id]
    if second is not None:
        bindings.append(StepBinding(second, second.step_id, [first.step_id], {}, {}))
        edges[second.step_id] = [first.step_id]
        order.append(second.step_id)
    return ABIDAG(bindings, edges, [first.step_id], order)


def test_run_rejects_failed_preflight(monkeypatch) -> None:
    plugin = SimpleNamespace(plugin_id="test")
    runtime = HpcRuntime(plugin)
    monkeypatch.setattr(runtime, "check", lambda: None)
    monkeypatch.setattr(
        hpc,
        "run_plugin_preflight",
        lambda *args, **kwargs: {"status": "fail", "recommendations": ["configure db"]},
    )

    with pytest.raises(ABIError, match="configure db"):
        runtime.run(SimpleNamespace(steps=[]), {"outdir": "/tmp/not-used"})


def test_run_cancels_submitted_jobs_when_submission_fails(tmp_path: Path, monkeypatch) -> None:
    plugin = SimpleNamespace(plugin_id="test")
    runtime = HpcRuntime(plugin)
    cancelled = []
    monkeypatch.setattr(runtime, "check", lambda: None)
    monkeypatch.setattr(hpc, "run_plugin_preflight", lambda *args, **kwargs: {"status": "pass"})
    monkeypatch.setattr(runtime, "_run_driver_steps", lambda *args: None)
    monkeypatch.setattr(runtime, "_generate_all_scripts", lambda *args: [tmp_path / "step.sh"])

    def fail_submit(scripts):
        runtime._submitted_job_ids = {"step": "42"}
        raise ABIError("scheduler offline")

    monkeypatch.setattr(runtime, "_submit_jobs", fail_submit)
    monkeypatch.setattr(runtime, "_cancel_jobs", lambda ids: cancelled.extend(ids))

    with pytest.raises(ABIError, match="scheduler offline"):
        runtime.run(SimpleNamespace(steps=[]), {"outdir": str(tmp_path)})
    assert cancelled == ["42"]


def test_run_polls_and_collects_successful_submission(tmp_path: Path, monkeypatch) -> None:
    runtime = HpcRuntime(
        SimpleNamespace(plugin_id="test"),
        options=RuntimeOptions(engine="hpc", timeout_seconds=9),
    )
    expected = RuntimeResult("success", 0, {"summary": tmp_path / "summary.json"})
    monkeypatch.setattr(runtime, "check", lambda: None)
    monkeypatch.setattr(hpc, "run_plugin_preflight", lambda *args, **kwargs: {"status": "pass"})
    monkeypatch.setattr(runtime, "_run_driver_steps", lambda *args: None)
    monkeypatch.setattr(runtime, "_generate_all_scripts", lambda *args: [tmp_path / "step.sh"])
    monkeypatch.setattr(runtime, "_submit_jobs", lambda scripts: {"step": "42"})
    monkeypatch.setattr(
        runtime,
        "_poll_until_complete",
        lambda jobs, timeout: {"42": "COMPLETED"} if timeout == 9 else {},
    )
    monkeypatch.setattr(runtime, "_collect_results", lambda *args: expected)

    assert runtime.run(SimpleNamespace(steps=[]), {"outdir": str(tmp_path)}) is expected


def test_driver_internal_steps_are_persisted_and_failure_blocks_submission(
    tmp_path: Path, monkeypatch
) -> None:
    step = _step(
        "normalize",
        tool_id="internal",
        params={"_internal_handler": {"handler_id": "normalize", "execution_scope": "driver"}},
    )
    runtime = HpcRuntime(object())
    success = StepExecutionResult(step.step_id, "internal", "success")
    monkeypatch.setattr(hpc, "execute_step", lambda *args, **kwargs: success)
    runtime._run_driver_steps(
        SimpleNamespace(steps=[_step("external"), step]), {"outdir": str(tmp_path)}
    )

    assert runtime._driver_results == {"normalize": success}
    assert (tmp_path / "provenance" / "step_results" / "normalize.json").is_file()

    failed = StepExecutionResult(step.step_id, "internal", "failed", reason="bad table")
    monkeypatch.setattr(hpc, "execute_step", lambda *args, **kwargs: failed)
    with pytest.raises(ABIError, match="bad table"):
        runtime._run_driver_steps(SimpleNamespace(steps=[step]), {"outdir": str(tmp_path)})


def test_submit_compatibility_path_ignores_unparseable_job_ids(tmp_path: Path, monkeypatch) -> None:
    runtime = HpcRuntime(object())
    responses = iter(
        [
            subprocess.CompletedProcess([], 0, "Submitted batch job 123\n", ""),
            subprocess.CompletedProcess([], 0, "scheduler unavailable\n", ""),
        ]
    )
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: next(responses))

    assert runtime._submit_jobs([tmp_path / "one.sh", tmp_path / "two.sh"]) == {"one.sh": "123"}


def test_submit_pbs_dependencies_and_submission_errors(tmp_path: Path, monkeypatch) -> None:
    first, second = _step("first"), _step("second")
    runtime = HpcRuntime(object(), options=RuntimeOptions(engine="hpc", scheduler="pbs"))
    runtime._dag = _dag(first, second)
    runtime._script_by_step = {"first": tmp_path / "first.sh", "second": tmp_path / "second.sh"}
    responses = iter(
        [
            subprocess.CompletedProcess([], 0, "101.server\n", ""),
            subprocess.CompletedProcess([], 0, "102.server\n", ""),
        ]
    )
    calls = []

    def submit(command, **kwargs):
        calls.append(command)
        return next(responses)

    monkeypatch.setattr(subprocess, "run", submit)
    assert runtime._submit_jobs(list(runtime._script_by_step.values())) == {
        "first": "101",
        "second": "102",
    }
    assert calls[1][1:3] == ["-W", "depend=afterok:101"]

    runtime._dag = _dag(first)
    runtime._script_by_step = {"first": tmp_path / "first.sh"}
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess([], 2, "", "denied"),
    )
    with pytest.raises(ABIError, match="denied"):
        runtime._submit_jobs([tmp_path / "first.sh"])

    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess([], 0, "no id", ""),
    )
    with pytest.raises(ABIError, match="did not return a job ID"):
        runtime._submit_jobs([tmp_path / "first.sh"])


def test_polling_handles_terminal_unknown_and_timeout_states(monkeypatch) -> None:
    runtime = HpcRuntime(object())
    monkeypatch.setattr(runtime, "_poll_slurm", lambda ids: {"1": "COMPLETED"})
    assert runtime._poll_until_complete({"step": "1"}, 1) == {"1": "COMPLETED"}

    monkeypatch.setattr(runtime, "_poll_slurm", lambda ids: {})
    monkeypatch.setattr(hpc.time, "sleep", lambda delay: None)
    assert runtime._poll_until_complete({"step": "2"}, 1)["2"] == "UNKNOWN"

    times = iter([0.0, 2.0])
    monkeypatch.setattr(hpc.time, "time", lambda: next(times))
    cancelled = []
    monkeypatch.setattr(runtime, "_cancel_jobs", lambda ids: cancelled.extend(ids))
    assert runtime._poll_until_complete({"step": "3"}, 1) == {"3": "TIMEOUT"}
    assert cancelled == ["3"]


def test_scheduler_pollers_parse_outputs_and_tolerate_command_errors(monkeypatch) -> None:
    runtime = HpcRuntime(object())
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess([], 0, "42|RUNNING\n", ""),
    )
    assert runtime._poll_slurm(["42"]) == {"42": "RUNNING"}

    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("scheduler offline")),
    )
    assert runtime._poll_slurm(["42"]) == {}
    assert runtime._poll_pbs(["42"]) == {}

    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            [], 0, "Job Id: 42.server\n    job_state = F\n", ""
        ),
    )
    assert runtime._poll_pbs(["42"]) == {"42": "F"}


def test_collect_results_merges_worker_data_and_reports_missing_result(
    tmp_path: Path, monkeypatch
) -> None:
    resumed = _step("resumed")
    completed = _step("completed")
    missing = _step("missing")
    plan = SimpleNamespace(steps=[resumed, completed, missing])
    plugin = SimpleNamespace(table_schemas=lambda: {}, registry=lambda: {})
    runtime = HpcRuntime(plugin)
    runtime._resumed_steps = {"resumed"}
    result_path = tmp_path / "provenance" / "step_results" / "completed.json"
    result_path.parent.mkdir(parents=True)
    result_path.write_text(
        json.dumps(
            StepExecutionResult(
                "completed",
                "tool",
                "success",
                command="tool --run",
                standard_tables={"summary": [{"value": 1}]},
                checksums={"result.tsv": "abc"},
            ).to_dict()
        ),
        encoding="utf-8",
    )
    runtime._result_by_step = {"completed": result_path}
    runtime._script_by_step = {
        "resumed": tmp_path / "resumed.sh",
        "completed": tmp_path / "completed.sh",
        "missing": tmp_path / "missing.sh",
    }
    appended = []

    class FakeTableManager:
        def __init__(self, schemas):
            pass

        def ensure_tables(self, path):
            Path(path).mkdir(parents=True, exist_ok=True)

        def append_rows(self, path, rows):
            appended.append(rows)

    class FakeWriter:
        def __init__(self, *args, **kwargs):
            pass

        def write(self, **kwargs):
            assert kwargs["status"] == "partial_failure"
            assert kwargs["return_code"] == 1
            return {"summary": tmp_path / "summary.json"}

    monkeypatch.setattr(hpc, "StandardTableManager", FakeTableManager)
    monkeypatch.setattr(hpc, "ABIResultWriter", FakeWriter)

    result = runtime._collect_results(
        plan,
        {"outdir": str(tmp_path)},
        {"completed": "42", "missing": "43"},
        {"42": "COMPLETED", "43": "FAILED"},
    )

    assert result.status == "partial_failure"
    assert appended == [{"summary": [{"value": 1}]}]
    assert json.loads((tmp_path / "provenance" / "checksums.json").read_text()) == {
        "result.tsv": "abc"
    }
    manifest = json.loads(result.outputs["hpc_manifest"].read_text())
    assert manifest["jobs"][2]["status"] == "FAILED"


def test_manifest_dependencies_step_results_and_resume_negative_cases(tmp_path: Path) -> None:
    first, second = _step("first"), _step("second")
    runtime = HpcRuntime(object())
    runtime._dag = _dag(first, second)
    runtime._script_by_step = {"first": tmp_path / "first.sh", "second": tmp_path / "second.sh"}
    runtime._resumed_steps = {"first"}
    manifest = runtime._write_hpc_manifest(
        {"first": "1", "second": "2"},
        {"1": "COMPLETED", "2": "RUNNING"},
        {"outdir": str(tmp_path)},
    )
    jobs = json.loads(manifest.read_text())["jobs"]
    assert jobs[1]["dependencies"] == ["first"]

    written = runtime._write_step_result(
        "unsafe step/id",
        StepExecutionResult("unsafe step/id", "tool", "success"),
        {"outdir": str(tmp_path)},
    )
    assert written.name == "unsafe_step_id.json"
    assert (
        runtime._step_is_resumable(
            _step("empty", outputs={"output_dir": str(tmp_path)}), {"outdir": str(tmp_path)}
        )
        is False
    )
    assert (
        runtime._step_is_resumable(
            _step("missing", outputs={"result": str(tmp_path / "missing.tsv")}),
            {"outdir": str(tmp_path)},
        )
        is False
    )


def test_command_row_and_state_normalization() -> None:
    step = _step("step")
    assert hpc._command_row(step, "success", 0, "", command="tool")["parsed_status"] == "parsed"
    assert hpc._command_row(step, "failed", 1, "bad")["parsed_status"] == ""
    assert hpc._normalize_slurm_state(" completed+ ") == "COMPLETED"
