"""Unit tests for the metagenomic_plasmid run logger (_engine/logger.py)."""

from __future__ import annotations

import json

from abi.plugins.metagenomic_plasmid._engine.logger import (
    RunLogger,
    write_commands_tsv,
    write_resolved_inputs_tsv,
    write_tool_versions,
)
from abi.plugins.metagenomic_plasmid._engine.schemas import PlanStep


# ---------------------------------------------------------------------------
# Helper — create a minimal PlanStep
# ---------------------------------------------------------------------------
def _make_step(**overrides) -> PlanStep:
    """Build a minimal PlanStep for test purposes."""
    defaults = {
        "step_id": "step_001",
        "step_name": "Quality Control",
        "tool_id": "fastqc",
        "category": "qc",
        "sample_id": "sample1",
        "inputs": {"reads": "reads.fq"},
        "outputs": {"report": "qc.html"},
        "params": {"threads": 4},
        "reason": "standard QC",
        "skipped": False,
    }
    defaults.update(overrides)
    return PlanStep(**defaults)


# ---------------------------------------------------------------------------
# RunLogger
# ---------------------------------------------------------------------------
class TestRunLogger:
    def test_creates_log_dir_and_log_file(self, tmp_path):
        log_dir = tmp_path / "logs"
        logger = RunLogger(log_dir)
        assert log_dir.is_dir()
        assert logger.log_file.parent == log_dir
        assert logger.log_file.name.startswith("log_autoanlyplam_")
        assert logger.log_file.name.endswith(".log")

    def test_log_event_writes_json_line(self, tmp_path):
        logger = RunLogger(tmp_path / "logs")
        logger.log_event("test_event", {"key": "value", "num": 42})
        lines = logger.log_file.read_text().strip().split("\n")
        assert len(lines) == 1
        record = json.loads(lines[0])
        assert record["event"] == "test_event"
        assert record["payload"] == {"key": "value", "num": 42}
        assert "timestamp" in record

    def test_log_event_multiple_entries(self, tmp_path):
        logger = RunLogger(tmp_path / "logs")
        logger.log_event("e1", {"a": 1})
        logger.log_event("e2", {"b": 2})
        lines = logger.log_file.read_text().strip().split("\n")
        assert len(lines) == 2
        assert json.loads(lines[0])["event"] == "e1"
        assert json.loads(lines[1])["event"] == "e2"

    def test_log_step_writes_step_event(self, tmp_path):
        logger = RunLogger(tmp_path / "logs")
        step = _make_step()
        logger.log_step(step, command=["fastqc", "-t", "4"], status="success")
        lines = logger.log_file.read_text().strip().split("\n")
        assert len(lines) == 1
        record = json.loads(lines[0])
        assert record["event"] == "pipeline_step"
        payload = record["payload"]
        assert payload["sample_id"] == "sample1"
        assert payload["step_name"] == "Quality Control"
        assert payload["tool_name"] == "fastqc"
        assert payload["status"] == "success"
        assert "fastqc" in payload["command"]

    def test_log_step_with_string_command(self, tmp_path):
        logger = RunLogger(tmp_path / "logs")
        step = _make_step()
        logger.log_step(step, command="fastqc reads.fq", status="running")
        lines = logger.log_file.read_text().strip().split("\n")
        assert len(lines) == 1
        record = json.loads(lines[0])
        assert record["payload"]["command"] == "fastqc reads.fq"

    def test_log_step_with_error_message(self, tmp_path):
        logger = RunLogger(tmp_path / "logs")
        step = _make_step()
        logger.log_step(
            step,
            command=["fastqc", "reads.fq"],
            status="failed",
            error_message="out of memory",
        )
        lines = logger.log_file.read_text().strip().split("\n")
        record = json.loads(lines[0])
        assert record["payload"]["status"] == "failed"
        assert record["payload"]["error_message"] == "out of memory"

    def test_log_step_none_error_message(self, tmp_path):
        logger = RunLogger(tmp_path / "logs")
        step = _make_step()
        logger.log_step(step, command="ls", status="success")
        lines = logger.log_file.read_text().strip().split("\n")
        record = json.loads(lines[0])
        assert record["payload"]["error_message"] is None

    def test_log_step_includes_inputs_outputs_params(self, tmp_path):
        logger = RunLogger(tmp_path / "logs")
        step = _make_step(
            inputs={"reads": "sample1_R1.fq"},
            outputs={"qc_report": "qc.html"},
            params={"threads": 8, "env_name": "qc_env"},
        )
        logger.log_step(step, command=["fastqc"], status="done")
        lines = logger.log_file.read_text().strip().split("\n")
        payload = json.loads(lines[0])["payload"]
        assert payload["input_files"] == {"reads": "sample1_R1.fq"}
        assert payload["output_files"] == {"qc_report": "qc.html"}
        assert payload["parameters"]["threads"] == 8
        assert payload["environment"] == "qc_env"


# ---------------------------------------------------------------------------
# write_commands_tsv
# ---------------------------------------------------------------------------
class TestWriteCommandsTsv:
    def test_writes_header_and_rows(self, tmp_path):
        path = tmp_path / "commands.tsv"
        rows = [
            {
                "step_id": "step_001",
                "sample_id": "s1",
                "step_name": "QC",
                "tool_id": "fastqc",
                "category": "qc",
                "command": "fastqc reads.fq",
                "status": "success",
                "return_code": 0,
                "remote_scheduler_job_id": "",
                "reason": "default",
                "parsed_status": "",
                "standard_tables": "",
            },
        ]
        result = write_commands_tsv(rows, path)
        assert result == path
        content = path.read_text()
        lines = content.strip().split("\n")
        assert len(lines) == 2  # header + 1 row
        assert lines[0].startswith("step_id\t")
        assert "fastqc" in lines[1]

    def test_empty_rows_writes_header_only(self, tmp_path):
        path = tmp_path / "commands.tsv"
        result = write_commands_tsv([], path)
        content = path.read_text().strip()
        lines = content.split("\n")
        assert len(lines) == 1
        assert lines[0].startswith("step_id\t")
        assert result == path

    def test_none_values_converted_to_empty_string(self, tmp_path):
        path = tmp_path / "commands.tsv"
        rows = [
            {
                "step_id": "step_001",
                "sample_id": None,
                "step_name": "QC",
                "tool_id": None,
                "category": None,
                "command": None,
                "status": None,
                "return_code": None,
                "remote_scheduler_job_id": None,
                "reason": None,
                "parsed_status": None,
                "standard_tables": None,
            },
        ]
        write_commands_tsv(rows, path)
        content = path.read_text()
        # None values should be empty strings, never "None"
        assert "None" not in content
        assert "\t\t" in content  # consecutive tabs from empty fields


# ---------------------------------------------------------------------------
# write_tool_versions
# ---------------------------------------------------------------------------
class TestWriteToolVersions:
    def test_writes_header_and_rows(self, tmp_path):
        path = tmp_path / "versions.tsv"
        rows = [
            {
                "tool_id": "fastqc",
                "executable": "fastqc",
                "env_name": "qc",
                "version": "0.11.9",
                "status": "ok",
            },
        ]
        result = write_tool_versions(rows, path)
        assert result == path
        content = path.read_text()
        lines = content.strip().split("\n")
        assert len(lines) == 2
        assert lines[0].startswith("tool_id\t")
        assert "fastqc" in lines[1]
        assert "0.11.9" in lines[1]

    def test_empty_rows_writes_header_only(self, tmp_path):
        path = tmp_path / "versions.tsv"
        write_tool_versions([], path)
        lines = path.read_text().strip().split("\n")
        assert len(lines) == 1
        assert lines[0] == "tool_id\texecutable\tenv_name\tversion\tstatus"

    def test_none_values_become_empty(self, tmp_path):
        path = tmp_path / "versions.tsv"
        rows = [
            {"tool_id": "t", "executable": None, "env_name": None, "version": None, "status": None}
        ]
        write_tool_versions(rows, path)
        content = path.read_text()
        # None values should become empty strings, never appear as "None"
        assert "None" not in content
        assert "t\t\t\t\t\n" in content  # tool_id + 4 empty tabs + newline


# ---------------------------------------------------------------------------
# write_resolved_inputs_tsv
# ---------------------------------------------------------------------------
class TestWriteResolvedInputsTsv:
    def test_writes_header_and_rows(self, tmp_path):
        path = tmp_path / "inputs.tsv"
        rows = [
            {
                "step_id": "step_001",
                "tool_id": "fastqc",
                "sample_id": "s1",
                "input_name": "reads",
                "path": "/data/s1.fq",
                "exists": True,
                "source": "user",
            },
        ]
        result = write_resolved_inputs_tsv(rows, path)
        assert result == path
        content = path.read_text()
        lines = content.strip().split("\n")
        assert len(lines) == 2
        assert lines[0].startswith("step_id\t")
        assert "/data/s1.fq" in lines[1]

    def test_empty_rows_writes_header_only(self, tmp_path):
        path = tmp_path / "inputs.tsv"
        write_resolved_inputs_tsv([], path)
        lines = path.read_text().strip().split("\n")
        assert len(lines) == 1
        assert lines[0] == "step_id\ttool_id\tsample_id\tinput_name\tpath\texists\tsource"

    def test_none_values_become_empty(self, tmp_path):
        path = tmp_path / "inputs.tsv"
        rows = [
            {
                "step_id": "step_001",
                "tool_id": None,
                "sample_id": None,
                "input_name": None,
                "path": None,
                "exists": None,
                "source": None,
            },
        ]
        write_resolved_inputs_tsv(rows, path)
        content = path.read_text()
        # None values should become empty strings
        assert "None" not in content
        assert "step_001\t\t\t\t\t\t\n" in content  # step_id + 6 empty fields
