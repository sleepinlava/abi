"""Tests for ABI CLI."""

from __future__ import annotations

import json
import re

from typer.testing import CliRunner

from abi.cli import app

runner = CliRunner()

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text)


def test_list_types():
    result = runner.invoke(app, ["list-types"])
    assert result.exit_code == 0
    assert "metatranscriptomics" in result.output


def test_help():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "Agent-Bioinformatics Interface" in result.output


def test_plan_requires_explicit_type(tmp_path):
    result = runner.invoke(app, ["plan", "--outdir", str(tmp_path)])
    assert result.exit_code != 0
    assert "--type" in _strip_ansi(result.output)


def test_export_openai_tools_requires_explicit_type():
    result = runner.invoke(app, ["export-openai-tools"])
    assert result.exit_code != 0
    assert "--type" in _strip_ansi(result.output)


def test_export_openai_tools_uses_abi_tool_names():
    result = runner.invoke(
        app,
        ["export-openai-tools", "--type", "metatranscriptomics", "--format", "responses"],
    )
    assert result.exit_code == 0
    tools = json.loads(result.output)
    names = {tool["name"] for tool in tools}
    assert names
    assert all(name.startswith("abi_") for name in names)


def test_install_skills_json_uses_agent_envelope_and_installs_readme(tmp_path):
    target = tmp_path / "skills"

    result = runner.invoke(
        app,
        ["install-skills", "--target", str(target), "--output-json"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["status"] == "success"
    assert payload["command"] == "install_skills"
    assert (target / "README.md").is_file()
    assert list(target.glob("*/SKILL.md"))
