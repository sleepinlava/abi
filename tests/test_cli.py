"""Tests for ABI CLI."""

from __future__ import annotations

from typer.testing import CliRunner

from abi.cli import app

runner = CliRunner()


def test_list_types():
    result = runner.invoke(app, ["list-types"])
    assert result.exit_code == 0
    assert "metatranscriptomics" in result.output


def test_help():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "Agent-Bioinformatics Interface" in result.output
