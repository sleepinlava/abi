"""Extended unit tests for Nextflow runtime and exporter edge/error paths."""

from __future__ import annotations

import shutil
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from abi.errors import ABIError, ToolError
from abi.exporters.nextflow import (
    NextflowExporter,
    _absolute_path,
    _command_text,
    _param_name,
    _tool_env_lines,
)
from abi.runtimes.nextflow import (
    _remote_scheduler_jobs,
    _status_from_trace,
    resolve_nextflow_bin,
)
from abi.tools import ToolRegistry


def test_resolve_nextflow_bin_from_env_var(tmp_path: Path, monkeypatch) -> None:
    fake_bin = tmp_path / "fake_nextflow"
    fake_bin.write_text("#!/bin/sh\necho nextflow")
    fake_bin.chmod(0o755)
    monkeypatch.setenv("ABI_NEXTFLOW_BIN", str(fake_bin))
    result = resolve_nextflow_bin(nextflow_bin=None, mamba_root=tmp_path)
    assert result == fake_bin.resolve()


def test_resolve_nextflow_bin_shutil_which_fallback(monkeypatch) -> None:
    monkeypatch.setattr(
        shutil, "which",
        lambda name: "/usr/local/bin/nextflow" if name == "nextflow" else None,
    )
    with (
        patch("pathlib.Path.exists", return_value=True),
        patch("os.access", return_value=True),
    ):
        result = resolve_nextflow_bin(nextflow_bin=None, mamba_root=Path("/tmp"))
        assert result.name == "nextflow"


def test_resolve_nextflow_bin_no_binary_found_raises(monkeypatch) -> None:
    monkeypatch.setattr(shutil, "which", lambda name: None)
    monkeypatch.delenv("ABI_NEXTFLOW_BIN", raising=False)
    with patch("pathlib.Path.exists", return_value=False):
        with pytest.raises(ABIError, match="Nextflow executable was not found"):
            resolve_nextflow_bin(nextflow_bin=None, mamba_root=Path("/tmp/nonexistent"))


def test_status_from_trace_empty_row_returns_fallback() -> None:
    assert _status_from_trace({}, fallback="dry_run") == "dry_run"


def test_status_from_trace_completed_status_returns_success() -> None:
    assert _status_from_trace({"status": "COMPLETED"}, fallback="failed") == "success"


def test_status_from_trace_cached_status_returns_success() -> None:
    assert _status_from_trace({"status": "CACHED"}, fallback="failed") == "success"


def test_status_from_trace_exit_zero_returns_success() -> None:
    assert _status_from_trace({"exit": "0"}, fallback="failed") == "success"


def test_status_from_trace_other_status_returns_failed() -> None:
    assert _status_from_trace({"status": "FAILED"}, fallback="success") == "failed"


def test_remote_scheduler_jobs_empty_scheduler_job_id_skips() -> None:
    rows: list[dict[str, str]] = [
        {"process": "task1", "status": "COMPLETED"},
        {"process": "task2", "status": "COMPLETED", "nativeId": "12345"},
        {"process": "task3", "status": "COMPLETED"},
    ]
    jobs = _remote_scheduler_jobs(rows)
    assert len(jobs) == 1
    assert jobs[0]["scheduler_job_id"] == "12345"


def test_resource_directive_lines_non_default_values() -> None:
    from abi.dag import StepBinding

    step = MagicMock()
    step.tool_id = "test_tool"
    registry = ToolRegistry([])
    exporter = NextflowExporter()
    binding = StepBinding(
        step=step,
        process_name="TEST_TOOL",
        dependencies=[],
        produced_paths={},
        consumed_paths={},
    )

    with (
        patch.object(registry, "get", return_value={
            "resources": {
                "memory": "16GB",
                "walltime": "04:00:00",
                "disk": "100GB",
            },
        }),
        patch.object(registry, "has", return_value=True),
    ):
        lines = exporter._resource_directive_lines(binding, registry)

    assert any("memory" in line for line in lines)
    assert any("time" in line for line in lines)
    assert any("disk" in line for line in lines)


def test_container_directive_line_with_image() -> None:
    from abi.dag import StepBinding

    step = MagicMock()
    step.tool_id = "test_tool"
    registry = ToolRegistry([])
    exporter = NextflowExporter()
    binding = StepBinding(
        step=step,
        process_name="TEST_TOOL",
        dependencies=[],
        produced_paths={},
        consumed_paths={},
    )

    with (
        patch.object(registry, "get", return_value={
            "container_image": "docker://biocontainers/fastp:0.23.2",
        }),
        patch.object(registry, "has", return_value=True),
        patch("abi.tools.resolve_container_image",
              return_value="docker://biocontainers/fastp:0.23.2"),
    ):
        result = exporter._container_directive_line(binding, registry)

    assert "container" in result
    assert "docker://biocontainers/fastp:0.23.2" in result


def test_container_directive_line_no_image_returns_none() -> None:
    from abi.dag import StepBinding

    step = MagicMock()
    step.tool_id = "test_tool"
    registry = ToolRegistry([])
    exporter = NextflowExporter()
    binding = StepBinding(
        step=step,
        process_name="TEST_TOOL",
        dependencies=[],
        produced_paths={},
        consumed_paths={},
    )

    with (
        patch.object(registry, "get", return_value={}),
        patch.object(registry, "has", return_value=True),
        patch("abi.tools.resolve_container_image", return_value=""),
    ):
        result = exporter._container_directive_line(binding, registry)

    assert result is None


def test_workflow_block_empty_dag_returns_placeholder_message() -> None:
    from abi.dag import ABIDAG

    dag = ABIDAG(bindings=[], edges={}, roots=[], topological_order=[])
    exporter = NextflowExporter()
    result = exporter._workflow_block(dag)
    assert "No exportable external steps" in result or "ABI plan has no exportable external steps" in result


def test_command_text_unknown_tool_id_raises_tool_error() -> None:
    step = MagicMock()
    step.tool_id = "nonexistent_tool"
    step.step_id = "step_1"
    registry = ToolRegistry([])
    with pytest.raises(ToolError, match="unknown tool"):
        _command_text(step, registry, project_root=Path("/tmp"))


def test_tool_env_lines_not_in_registry_returns_empty(tmp_path: Path) -> None:
    step = MagicMock()
    step.tool_id = "unknown_tool"
    registry = ToolRegistry([])
    result = _tool_env_lines(step, registry, mamba_root=tmp_path)
    assert result == []


def test_param_name_starts_with_digit_prefixed() -> None:
    assert _param_name("123abc") == "param_123abc"


def test_param_name_normal_name_unchanged() -> None:
    assert _param_name("threads") == "threads"


def test_param_name_special_chars_replaced() -> None:
    assert _param_name("foo-bar") == "foo_bar"


def test_absolute_path_escapes_project_root_raises_tool_error(tmp_path: Path) -> None:
    with pytest.raises(ToolError, match="escapes project root"):
        _absolute_path("../../../etc/passwd", tmp_path)
