"""Unit tests for abi.provenance — RunLogger, PipelineProgressRecorder, TSV writers."""

from __future__ import annotations

import json
from pathlib import Path

from abi.provenance import (
    PipelineProgressRecorder,
    RunLogger,
    _tsv_value,
    reset_run_provenance,
    write_commands_tsv,
    write_methods_md,
    write_minimal_progress_artifacts,
    write_resolved_inputs_tsv,
    write_tool_versions,
)


def test_reset_run_provenance_removes_stale_attempt_artifacts(tmp_path: Path) -> None:
    provenance = tmp_path / "provenance"
    step_logs = provenance / "step_logs"
    step_logs.mkdir(parents=True)
    (step_logs / "old.stderr.log").write_text("old")
    for name in ("checksums.json", "progress.json", "progress.jsonl"):
        (provenance / name).write_text("old")
    (provenance / "commands.tsv").write_text("old")

    reset_run_provenance(provenance)

    assert not step_logs.exists()
    assert not (provenance / "checksums.json").exists()
    assert not (provenance / "progress.jsonl").exists()
    assert not (provenance / "commands.tsv").exists()


# ── _tsv_value ───────────────────────────────────────────────────────────


def test_tsv_value_none() -> None:
    """None → empty string (not the literal 'None')."""
    assert _tsv_value(None) == ""


def test_tsv_value_str() -> None:
    """String passes through unchanged."""
    assert _tsv_value("hello") == "hello"


def test_tsv_value_int() -> None:
    """Integer is stringified."""
    assert _tsv_value(42) == "42"


def test_tsv_value_tabs_replaced() -> None:
    """Embedded tabs are replaced with spaces."""
    assert "\t" not in _tsv_value("col1\tcol2")


def test_tsv_value_newlines_replaced() -> None:
    """Embedded newlines are replaced with ' | '."""
    result = _tsv_value("line1\nline2")
    assert "\n" not in result
    assert "|" in result


# ── RunLogger ────────────────────────────────────────────────────────────


def test_run_logger_creates_dir(tmp_path: Path) -> None:
    """RunLogger creates the log directory if it doesn't exist."""
    log_dir = tmp_path / "logs"
    logger = RunLogger(log_dir)
    assert log_dir.is_dir()
    assert logger.log_file.parent == log_dir


def test_run_logger_log_event(tmp_path: Path) -> None:
    """log_event appends a JSON line to the log file."""
    logger = RunLogger(tmp_path / "logs")
    logger.log_event("test_event", {"key": "value"})
    assert logger.log_file.exists()
    lines = logger.log_file.read_text().strip().split("\n")
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["event"] == "test_event"
    assert record["payload"]["key"] == "value"
    assert "timestamp" in record


def test_run_logger_log_step(tmp_path: Path) -> None:
    """log_step extracts fields from a step-like object and delegates to log_event."""
    logger = RunLogger(tmp_path / "logs")

    class Step:
        step_id = "S1_qc"
        sample_id = "S1"
        step_name = "qc"
        tool_id = "fastp"
        inputs = {"read1": "/data/R1.fq"}
        outputs = {"clean_read1": "/data/R1.clean.fq"}
        params = {"threads": 4}

    logger.log_step(Step(), command=["fastp", "-i", "R1.fq"], status="success")
    lines = logger.log_file.read_text().strip().split("\n")
    record = json.loads(lines[0])
    assert record["event"] == "pipeline_step"
    assert record["payload"]["sample_id"] == "S1"
    assert record["payload"]["tool_name"] == "fastp"
    assert record["payload"]["status"] == "success"


def test_run_logger_log_step_with_error(tmp_path: Path) -> None:
    """log_step records error_message for failed steps."""
    logger = RunLogger(tmp_path / "logs")

    class Step:
        step_id = "S2_fail"
        sample_id = "S2"
        step_name = "align"
        tool_id = "star"
        inputs = {}
        outputs = {}
        params = {}

    logger.log_step(
        Step(),
        command="STAR --genomeDir /ref",
        status="failed",
        error_message="OUT_OF_MEMORY",
    )
    lines = logger.log_file.read_text().strip().split("\n")
    record = json.loads(lines[0])
    assert record["payload"]["status"] == "failed"
    assert record["payload"]["error_message"] == "OUT_OF_MEMORY"


def test_run_logger_log_step_string_command(tmp_path: Path) -> None:
    """log_step accepts a string command directly."""
    logger = RunLogger(tmp_path / "logs")

    class Step:
        step_id = "S3"
        sample_id = "S3"
        step_name = "test"
        tool_id = "echo"
        inputs = {}
        outputs = {}
        params = {}

    logger.log_step(Step(), command="echo hello", status="success")
    lines = logger.log_file.read_text().strip().split("\n")
    record = json.loads(lines[0])
    assert "echo hello" in record["payload"]["command"]


# ── write_commands_tsv ───────────────────────────────────────────────────


def test_write_commands_tsv(tmp_path: Path) -> None:
    """Writes a TSV with the fixed header and one row."""
    path = tmp_path / "provenance" / "commands.tsv"
    rows = [
        {
            "step_id": "S1_qc",
            "sample_id": "S1",
            "step_name": "qc",
            "tool_id": "fastp",
            "category": "qc",
            "command": "fastp -i R1.fq",
            "status": "success",
            "return_code": 0,
            "remote_scheduler_job_id": "",
            "reason": "",
            "parsed_status": "ok",
            "standard_tables": "qc_summary",
        }
    ]
    result = write_commands_tsv(rows, path)
    assert result == path
    assert path.exists()
    content = path.read_text()
    assert "step_id\tsample_id" in content
    assert "S1_qc\tS1" in content


def test_write_commands_tsv_creates_parent_dirs(tmp_path: Path) -> None:
    """Parent directories are created automatically."""
    path = tmp_path / "deeply" / "nested" / "provenance" / "commands.tsv"
    write_commands_tsv([], path)
    assert path.exists()


def test_write_commands_tsv_empty(tmp_path: Path) -> None:
    """Writing zero rows produces a header-only file."""
    path = tmp_path / "commands.tsv"
    write_commands_tsv([], path)
    lines = path.read_text().strip().split("\n")
    assert len(lines) == 1  # header only
    assert "step_id" in lines[0]


# ── write_tool_versions ──────────────────────────────────────────────────


def test_write_tool_versions(tmp_path: Path) -> None:
    """Writes tool versions TSV with header and rows."""
    path = tmp_path / "provenance" / "tool_versions.tsv"
    rows = [
        {
            "tool_id": "fastp",
            "executable": "/usr/bin/fastp",
            "env_name": "rnaseq",
            "version": "0.23.4",
            "status": "ok",
        }
    ]
    write_tool_versions(rows, path)
    assert path.exists()
    content = path.read_text()
    assert "tool_id\texecutable\tenv_name\tversion\tstatus" in content
    assert "fastp\t/usr/bin/fastp\trnaseq\t0.23.4\tok" in content


# ── write_resolved_inputs_tsv ────────────────────────────────────────────


def test_write_resolved_inputs_tsv(tmp_path: Path) -> None:
    """Writes resolved inputs TSV with header and row including exists field."""
    path = tmp_path / "provenance" / "resolved_inputs.tsv"
    rows = [
        {
            "step_id": "S1_qc",
            "tool_id": "fastp",
            "sample_id": "S1",
            "input_name": "read1",
            "path": "/data/S1_R1.fq.gz",
            "exists": "true",
            "source": "sample_sheet",
        }
    ]
    write_resolved_inputs_tsv(rows, path)
    assert path.exists()
    content = path.read_text()
    assert "step_id\ttool_id\tsample_id\tinput_name\tpath\texists\tsource" in content
    assert "S1_qc\tfastp\tS1\tread1\t/data/S1_R1.fq.gz\ttrue\tsample_sheet" in content


# ── write_methods_md ─────────────────────────────────────────────────────


def test_write_methods_md_basic(tmp_path: Path) -> None:
    """Generates a markdown methods section with tool versions and commands."""
    command_rows = [
        {
            "step_id": "S1_qc",
            "tool_id": "fastp",
            "command": "fastp -i R1.fq -o R1.clean.fq",
            "status": "success",
        }
    ]
    tool_versions = [
        {
            "tool_id": "fastp",
            "executable": "fastp",
            "version": "0.23.4",
            "status": "ok",
        }
    ]
    md = write_methods_md(command_rows, tool_versions)
    assert "# Methods" in md
    assert "fastp" in md
    assert "0.23.4" in md
    assert "S1_qc" in md


def test_write_methods_md_with_resources(tmp_path: Path) -> None:
    """Includes reference databases section when resources are provided."""
    resource = {
        "name": "STAR Index",
        "version": "1.0",
        "source_url": "http://example.com",
        "path": "/ref/star",
    }
    md = write_methods_md([], [], resources=[resource])
    assert "## Reference Databases" in md
    assert "STAR Index" in md


def test_write_methods_md_missing_version(tmp_path: Path) -> None:
    """Marks missing version as 'not_captured'."""
    md = write_methods_md(
        [],
        [{"tool_id": "custom", "executable": "custom_tool", "version": "", "status": "ok"}],
    )
    assert "not_captured" in md


def test_write_methods_md_failed_version_capture(tmp_path: Path) -> None:
    """Marks failed version capture distinctly."""
    bad_tool = {
        "tool_id": "bad",
        "executable": "bad_tool",
        "version": "version_command_failed",
        "status": "error",
    }
    md = write_methods_md([], [bad_tool])
    assert "capture_failed" in md


def test_write_methods_md_pipe_escape(tmp_path: Path) -> None:
    """Escapes pipe characters in commands for Markdown table safety."""
    grep_row = {
        "step_id": "S1",
        "tool_id": "grep",
        "command": "grep -E 'foo|bar' file.txt",
        "status": "success",
    }
    md = write_methods_md([grep_row], [])
    assert "foo\\|bar" in md


def test_write_methods_md_writes_to_file(tmp_path: Path) -> None:
    """Writes output to a file when path is given."""
    path = tmp_path / "methods.md"
    result = write_methods_md([], [], path=path)
    assert path.exists()
    assert result == path.read_text()


# ── PipelineProgressRecorder ─────────────────────────────────────────────


class _FakeStep:
    """Minimal step-like object for PipelineProgressRecorder tests."""

    def __init__(self, step_id, sample_id="S1", step_name="qc", tool_id="fastp", category="qc"):
        self.step_id = step_id
        self.sample_id = sample_id
        self.step_name = step_name
        self.tool_id = tool_id
        self.category = category
        self.reason = ""


class _FakePlan:
    """Minimal plan-like object for PipelineProgressRecorder tests."""

    def __init__(self, steps, samples=None):
        self.project_name = "test_project"
        self.steps = steps
        self.samples = samples or []


class _FakeSample:
    def __init__(self, sample_id="S1", platform="illumina"):
        self.sample_id = sample_id
        self.platform = platform


def test_recorder_start_run(tmp_path: Path) -> None:
    """start_run initializes snapshot and emits run_started event."""
    prov = tmp_path / "provenance"
    prov.mkdir()
    step = _FakeStep("S1_qc")
    plan = _FakePlan([step], [_FakeSample("S1")])
    recorder = PipelineProgressRecorder(prov)
    recorder.start_run(plan, dry_run=False, parallel=False, workers=1)
    assert recorder.events_path.exists()
    assert recorder.snapshot_path.exists()
    events = recorder.events_path.read_text().strip().split("\n")
    assert len(events) == 1
    record = json.loads(events[0])
    assert record["event"] == "run_started"
    snapshot = json.loads(recorder.snapshot_path.read_text())
    assert snapshot["status"] == "running"
    assert snapshot["total_step_count"] == 1


def test_recorder_step_started(tmp_path: Path) -> None:
    """step_started updates step and sample status to 'running'."""
    prov = tmp_path / "provenance"
    prov.mkdir()
    step = _FakeStep("S1_qc")
    plan = _FakePlan([step], [_FakeSample("S1")])
    recorder = PipelineProgressRecorder(prov)
    recorder.start_run(plan, dry_run=False, parallel=False, workers=1)
    recorder.step_started(step)
    snapshot = json.loads(recorder.snapshot_path.read_text())
    step_state = snapshot["steps"][0]
    assert step_state["status"] == "running"
    assert step_state["started_at"] != ""
    assert "S1_qc" in snapshot["current_steps"]


def test_recorder_step_completed_success(tmp_path: Path) -> None:
    """step_completed with success status updates counters."""
    prov = tmp_path / "provenance"
    prov.mkdir()
    step = _FakeStep("S1_qc")
    plan = _FakePlan([step], [_FakeSample("S1")])
    recorder = PipelineProgressRecorder(prov)
    recorder.start_run(plan, dry_run=False, parallel=False, workers=1)
    recorder.step_started(step)
    recorder.step_completed(step, status="success", return_code=0)
    snapshot = json.loads(recorder.snapshot_path.read_text())
    step_state = snapshot["steps"][0]
    assert step_state["status"] == "success"
    assert step_state["finished_at"] != ""
    assert snapshot["completed_step_count"] == 1
    assert snapshot["failed_step_count"] == 0


def test_recorder_step_completed_failed(tmp_path: Path) -> None:
    """step_completed with failed status increments failed counter."""
    prov = tmp_path / "provenance"
    prov.mkdir()
    step = _FakeStep("S2_bad")
    plan = _FakePlan([step], [_FakeSample("S2")])
    recorder = PipelineProgressRecorder(prov)
    recorder.start_run(plan, dry_run=False, parallel=False, workers=1)
    recorder.step_started(step)
    recorder.step_completed(step, status="failed", reason="tool crash", return_code=1)
    snapshot = json.loads(recorder.snapshot_path.read_text())
    assert snapshot["status"] == "failed"
    assert snapshot["failed_step_count"] == 1
    step_state = snapshot["steps"][0]
    assert step_state["reason"] == "tool crash"


def test_recorder_finish_run(tmp_path: Path) -> None:
    """finish_run emits run_completed and finalizes the snapshot."""
    prov = tmp_path / "provenance"
    prov.mkdir()
    step = _FakeStep("S1_qc")
    plan = _FakePlan([step], [_FakeSample("S1")])
    recorder = PipelineProgressRecorder(prov)
    recorder.start_run(plan, dry_run=False, parallel=False, workers=1)
    recorder.finish_run(status="success")
    snapshot = json.loads(recorder.snapshot_path.read_text())
    assert snapshot["status"] == "success"
    assert snapshot["finished_at"] != ""
    assert snapshot["running_step_count"] == 0
    assert snapshot["current_steps"] == []


def test_recorder_paths_property(tmp_path: Path) -> None:
    """paths property returns both output file paths."""
    prov = tmp_path / "provenance"
    prov.mkdir()
    recorder = PipelineProgressRecorder(prov)
    paths = recorder.paths
    assert paths["events"] == recorder.events_path
    assert paths["snapshot"] == recorder.snapshot_path


def test_recorder_multiple_steps(tmp_path: Path) -> None:
    """Multiple steps tracked independently with correct sample-level state."""
    prov = tmp_path / "provenance"
    prov.mkdir()
    s1 = _FakeStep("S1_qc", sample_id="S1")
    s2 = _FakeStep("S2_qc", sample_id="S2")
    plan = _FakePlan([s1, s2], [_FakeSample("S1"), _FakeSample("S2")])
    recorder = PipelineProgressRecorder(prov)
    recorder.start_run(plan, dry_run=False, parallel=True, workers=2)
    recorder.step_started(s1)
    recorder.step_started(s2)
    recorder.step_completed(s1, status="success")
    recorder.step_completed(s2, status="success")
    recorder.finish_run(status="success")
    snapshot = json.loads(recorder.snapshot_path.read_text())
    assert snapshot["completed_step_count"] == 2
    assert snapshot["failed_step_count"] == 0
    # Sample-level state
    assert snapshot["samples"]["S1"]["completed_step_count"] == 1
    assert snapshot["samples"]["S2"]["completed_step_count"] == 1


# ── write_minimal_progress_artifacts ─────────────────────────────────────


def test_write_minimal_progress_artifacts(tmp_path: Path) -> None:
    """Generates progress.jsonl and progress.json with post-hoc status."""
    prov = tmp_path / "provenance"
    step = _FakeStep("S1_qc")
    plan = _FakePlan([step], [_FakeSample("S1")])
    command_rows = [
        {
            "step_id": "S1_qc",
            "sample_id": "S1",
            "status": "success",
            "return_code": 0,
        }
    ]
    result = write_minimal_progress_artifacts(
        prov,
        plan,
        dry_run=False,
        parallel=False,
        workers=1,
        status="success",
        command_rows=command_rows,
    )
    assert result["events"].exists()
    assert result["snapshot"].exists()
    events = result["events"].read_text().strip().split("\n")
    assert len(events) == 2  # run_started + run_completed
    snapshot = json.loads(result["snapshot"].read_text())
    assert snapshot["record_progress"] is False
    assert snapshot["status"] == "success"
    assert snapshot["total_step_count"] == 1
    assert snapshot["completed_step_count"] == 1


def test_write_minimal_progress_artifacts_with_failures(tmp_path: Path) -> None:
    """Correctly counts failed steps."""
    prov = tmp_path / "provenance"
    s1 = _FakeStep("S1_qc")
    s2 = _FakeStep("S2_bad")
    plan = _FakePlan([s1, s2], [_FakeSample("S1"), _FakeSample("S2")])
    command_rows = [
        {"step_id": "S1_qc", "sample_id": "S1", "status": "success"},
        {"step_id": "S2_bad", "sample_id": "S2", "status": "failed"},
    ]
    result = write_minimal_progress_artifacts(
        prov,
        plan,
        dry_run=False,
        parallel=False,
        workers=1,
        status="partial_failure",
        command_rows=command_rows,
    )
    snapshot = json.loads(result["snapshot"].read_text())
    assert snapshot["failed_step_count"] == 1
    assert snapshot["completed_step_count"] == 2
    assert snapshot["samples"]["S2"]["status"] == "failed"


def test_write_minimal_progress_artifacts_empty_steps(tmp_path: Path) -> None:
    """Works with zero steps (edge case)."""
    prov = tmp_path / "provenance"
    plan = _FakePlan([])
    result = write_minimal_progress_artifacts(
        prov,
        plan,
        dry_run=True,
        parallel=False,
        workers=1,
        status="success",
        command_rows=[],
    )
    snapshot = json.loads(result["snapshot"].read_text())
    assert snapshot["total_step_count"] == 0
    assert snapshot["completed_step_count"] == 0
