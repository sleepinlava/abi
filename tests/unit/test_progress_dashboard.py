import json

from abi.autoplasm.dashboard import _handler_for, dashboard_state
from abi.autoplasm.progress import PipelineProgressRecorder
from abi.autoplasm.schemas import ExecutionPlan, PlanStep, SampleContext, SampleInput


def test_progress_recorder_writes_snapshot_and_events(tmp_path):
    sample = SampleInput(sample_id="S1", platform="assembly", assembly="input.fasta")
    context = SampleContext(
        samples=[sample],
        multi_sample=False,
        has_groups=False,
        enable_sample_analysis=False,
        enable_differential_abundance=False,
    )
    step = PlanStep(
        step_id="S1_mock",
        sample_id="S1",
        step_name="mock",
        tool_id="mock_tool",
        category="mock",
    )
    plan = ExecutionPlan(
        project_name="progress",
        mode="auto",
        threads=1,
        outdir=str(tmp_path / "results"),
        log_dir=str(tmp_path / "log"),
        samples=[sample],
        sample_context=context,
        selected_tools=["mock_tool"],
        steps=[step],
    )
    recorder = PipelineProgressRecorder(tmp_path / "results" / "provenance")

    recorder.start_run(plan, dry_run=False, parallel=True, workers=2)
    recorder.step_started(step)
    recorder.step_completed(step, status="success", return_code=0)
    recorder.finish_run(status="success")

    snapshot = json.loads(recorder.snapshot_path.read_text(encoding="utf-8"))
    assert snapshot["status"] == "success"
    assert snapshot["completed_step_count"] == 1
    assert snapshot["steps"][0]["status"] == "success"
    assert "step_completed" in recorder.events_path.read_text(encoding="utf-8")


def test_dashboard_state_reads_progress_snapshot(tmp_path):
    result_dir = tmp_path / "results"
    provenance = result_dir / "provenance"
    provenance.mkdir(parents=True)
    (provenance / "progress.json").write_text(
        json.dumps(
            {
                "project_name": "dashboard",
                "status": "running",
                "dry_run": False,
                "parallel": True,
                "workers": 2,
                "total_step_count": 1,
                "completed_step_count": 0,
                "failed_step_count": 0,
                "running_step_count": 1,
                "current_steps": ["S1_mock"],
                "samples": {},
                "steps": [],
                "last_event": {},
            }
        ),
        encoding="utf-8",
    )

    state = dashboard_state(result_dir)

    assert state["project_name"] == "dashboard"
    assert state["parallel"] is True
    assert state["result_dir"] == str(result_dir.resolve())


def test_dashboard_rejects_files_over_size_limit(tmp_path, monkeypatch):
    result_dir = tmp_path / "results"
    result_dir.mkdir()
    (result_dir / "large.txt").write_text("too large\n", encoding="utf-8")
    monkeypatch.setenv("AUTOPLASM_DASHBOARD_MAX_FILE_BYTES", "4")
    handler = object.__new__(_handler_for(result_dir.resolve()))
    errors = []
    handler.send_error = lambda code, message=None: errors.append((code, message))

    handler._send_file("large.txt")

    assert errors
    assert errors[0][0] == 413
