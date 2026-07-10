"""Integration tests for CLI commands not covered by test_cli.py or test_abi_cli.py.

Uses Typer's CliRunner to exercise the real CLI with real plugins on disk.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from abi.cli import app


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


# ── check ────────────────────────────────────────────────────────────────────


def test_check_no_check_runtime(runner: CliRunner) -> None:
    """check --no-check-runtime executes and returns structured JSON.

    Exit code 1 is expected because sample sheet / resources are not
    configured in the test environment.
    """
    result = runner.invoke(
        app,
        [
            "check",
            "--type",
            "rnaseq_expression",
            "--no-check-runtime",
        ],
    )
    # Exit 0 or 1 — assertion is on the shape of the output.
    assert result.exit_code in (0, 1), result.output
    # Non-JSON path: raw payload is a JSON object with plugin/status/checks.
    output = result.output.strip()
    if output.startswith("{"):
        data = json.loads(output)
        assert isinstance(data, dict)
        assert "plugin" in data or "status" in data


def test_check_output_json(runner: CliRunner) -> None:
    """check --output-json returns a valid agent envelope.

    The envelope.status is always "success" (command-level), even when
    the embedded check result has status "fail" because resources are
    not configured.  When the result fails the CLI exits with code 1.
    """
    result = runner.invoke(
        app,
        [
            "check",
            "--type",
            "rnaseq_expression",
            "--no-check-runtime",
            "--output-json",
        ],
    )
    # Exit 0 or 1 — envelope always present.
    assert result.exit_code in (0, 1), result.output
    data = json.loads(result.output.strip())
    assert data["status"] == "success"
    assert data["command"] == "check"


# ── contract-lint ────────────────────────────────────────────────────────────


def test_contract_lint(runner: CliRunner) -> None:
    """contract-lint validates DAG and tool contracts."""
    result = runner.invoke(
        app,
        [
            "contract-lint",
            "--type",
            "rnaseq_expression",
        ],
    )
    assert result.exit_code == 0, result.output
    data = json.loads(result.output.strip())
    assert data["passed"] is True
    assert data["error_count"] == 0
    assert data["warning_count"] == 0


# ── export-tools ─────────────────────────────────────────────────────────────


def test_export_tools_anthropic(runner: CliRunner) -> None:
    """export-tools --format anthropic returns a list of tool descriptors."""
    result = runner.invoke(
        app,
        [
            "export-tools",
            "--type",
            "rnaseq_expression",
            "--format",
            "anthropic",
        ],
    )
    assert result.exit_code == 0, result.output
    data = json.loads(result.output.strip())
    assert isinstance(data, list)
    assert len(data) > 0


def test_export_tools_gemini(runner: CliRunner) -> None:
    """export-tools --format gemini returns function_declarations dict."""
    result = runner.invoke(
        app,
        [
            "export-tools",
            "--type",
            "rnaseq_expression",
            "--format",
            "gemini",
        ],
    )
    assert result.exit_code == 0, result.output
    data = json.loads(result.output.strip())
    assert isinstance(data, dict)
    assert "function_declarations" in data
    assert isinstance(data["function_declarations"], list)
    assert len(data["function_declarations"]) > 0


# ── setup-resources --mock ───────────────────────────────────────────────────


def test_setup_resources_mock(runner: CliRunner, tmp_path: Path) -> None:
    """setup-resources --mock creates placeholder resource entries."""
    result = runner.invoke(
        app,
        [
            "setup-resources",
            "--type",
            "rnaseq_expression",
            "--outdir",
            str(tmp_path / "results"),
            "--mock",
            "--confirm",
        ],
    )
    assert result.exit_code == 0, result.output
    data = json.loads(result.output.strip())
    assert isinstance(data, list)
    assert len(data) > 0
    assert any(row.get("mock") is True for row in data)


# ── init --force ─────────────────────────────────────────────────────────────


def test_init_force(runner: CliRunner, tmp_path: Path) -> None:
    """init --force overwrites existing files without error."""
    outdir = tmp_path / "proj"

    # First init
    result1 = runner.invoke(
        app,
        [
            "init",
            "--type",
            "rnaseq_expression",
            "--outdir",
            str(outdir),
        ],
    )
    assert result1.exit_code == 0, result1.output
    assert (outdir / "config" / "rnaseq_expression.yaml").is_file()
    assert (outdir / "samples.tsv").is_file()

    # Second init with --force
    result2 = runner.invoke(
        app,
        [
            "init",
            "--type",
            "rnaseq_expression",
            "--outdir",
            str(outdir),
            "--force",
        ],
    )
    assert result2.exit_code == 0, result2.output


# ── Error: invalid analysis type ─────────────────────────────────────────────


def test_invalid_type_exit_code(runner: CliRunner) -> None:
    """Nonexistent analysis type -> exit code 1."""
    result = runner.invoke(
        app,
        [
            "query",
            "--type",
            "nonexistent_type_xyz",
            "--what",
            "stages",
        ],
    )
    assert result.exit_code == 1, result.output


# ── Error: missing required arg ──────────────────────────────────────────────


def test_missing_required_arg(runner: CliRunner) -> None:
    """plan without --type -> exit code 2 (Typer missing-option code)."""
    result = runner.invoke(app, ["plan"])
    assert result.exit_code == 2, result.output


# ── export-openai-tools --format apps-sdk ────────────────────────────────────


def test_export_openai_tools_apps_sdk(runner: CliRunner) -> None:
    """export-openai-tools --format apps-sdk returns valid JSON tool list."""
    result = runner.invoke(
        app,
        [
            "export-openai-tools",
            "--type",
            "rnaseq_expression",
            "--format",
            "apps-sdk",
        ],
    )
    assert result.exit_code == 0, result.output
    data = json.loads(result.output.strip())
    assert isinstance(data, list)
    assert len(data) > 0
