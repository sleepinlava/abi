"""Tests for ABI CLI."""

from __future__ import annotations

import json
import re
from pathlib import Path

import yaml
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


def test_lock_runtime_strict_rejects_incomplete_candidate(tmp_path):
    result = runner.invoke(
        app,
        [
            "lock-runtime",
            "--output-dir",
            str(tmp_path / "locks"),
            "--prefix",
            "candidate",
            "--mamba-root",
            str(tmp_path / "mamba"),
            "--resource-root",
            str(tmp_path / "resources"),
            "--type",
            "wgs_bacteria",
            "--strict",
        ],
    )

    assert result.exit_code == 1
    assert "Runtime lock is not release-ready" in result.output
    assert "Registered tool is unresolved" in result.output


def test_lock_runtime_strict_rejects_skipped_package_snapshots(tmp_path):
    result = runner.invoke(
        app,
        [
            "lock-runtime",
            "--output-dir",
            str(tmp_path / "locks"),
            "--skip-conda-packages",
            "--strict",
        ],
    )

    assert result.exit_code == 1
    assert "--strict cannot be combined with --skip-conda-packages" in result.output


def test_lock_runtime_uses_top_level_resource_environment_variable(tmp_path):
    runtime_root = tmp_path / "runtime-resources"
    legacy_database_root = tmp_path / "legacy-autoplasm"
    result = runner.invoke(
        app,
        [
            "lock-runtime",
            "--output-dir",
            str(tmp_path / "locks"),
            "--skip-conda-packages",
            "--type",
            "wgs_bacteria",
        ],
        env={
            "ABI_RUNTIME_RESOURCE_ROOT": str(runtime_root),
            "ABI_RESOURCE_ROOT": str(legacy_database_root),
        },
    )

    assert result.exit_code == 0, result.output
    paths = json.loads(result.output)
    resources_lock = yaml.safe_load(Path(paths["resources"]).read_text(encoding="utf-8"))
    assert resources_lock["resource_root"] == str(runtime_root.resolve())


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


def test_agent_install_and_doctor_opencode_project(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "abi.agent_integrations.shutil.which",
        lambda command: "/venv/bin/abi-mcp" if command == "abi-mcp" else None,
    )
    monkeypatch.setattr(
        "abi.agent_integrations._mcp_runtime_status",
        lambda: (True, "Safe MCP server initialized: FastMCP"),
    )

    installed = runner.invoke(
        app,
        [
            "agent",
            "install",
            "opencode",
            "--scope",
            "project",
            "--project-dir",
            str(tmp_path),
            "--output-json",
        ],
    )

    assert installed.exit_code == 0, installed.output
    install_payload = json.loads(installed.output)
    assert install_payload["platform"] == "opencode"
    assert (tmp_path / ".opencode/skills/abi/SKILL.md").is_file()
    assert (tmp_path / "opencode.json").is_file()

    diagnosed = runner.invoke(
        app,
        [
            "agent",
            "doctor",
            "opencode",
            "--scope",
            "project",
            "--project-dir",
            str(tmp_path),
            "--output-json",
        ],
    )

    assert diagnosed.exit_code == 0, diagnosed.output
    doctor_payload = json.loads(diagnosed.output)
    assert doctor_payload["status"] == "healthy"


def test_agent_install_and_doctor_codex_project(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "abi.agent_integrations.shutil.which",
        lambda command: "/venv/bin/abi-mcp" if command == "abi-mcp" else None,
    )
    monkeypatch.setattr(
        "abi.agent_integrations._mcp_runtime_status",
        lambda: (True, "Safe MCP server initialized: FastMCP"),
    )

    installed = runner.invoke(
        app,
        [
            "agent",
            "install",
            "codex",
            "--scope",
            "project",
            "--project-dir",
            str(tmp_path),
            "--output-json",
        ],
    )

    assert installed.exit_code == 0, installed.output
    install_payload = json.loads(installed.output)
    assert install_payload["platform"] == "codex"
    assert (tmp_path / ".agents/skills/abi/SKILL.md").is_file()
    assert (tmp_path / ".codex/config.toml").is_file()

    diagnosed = runner.invoke(
        app,
        [
            "agent",
            "doctor",
            "codex",
            "--scope",
            "project",
            "--project-dir",
            str(tmp_path),
            "--output-json",
        ],
    )

    assert diagnosed.exit_code == 0, diagnosed.output
    assert json.loads(diagnosed.output)["status"] == "healthy"
