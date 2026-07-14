import json
from pathlib import Path

import pytest
import tomlkit

from abi.agent_integrations import doctor_agent_integration, install_agent_integration
from abi.schemas import ABIError


def test_install_claude_code_user_integration_is_idempotent(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))

    first = install_agent_integration(platform="claude-code", scope="user")
    target = tmp_path / ".claude/skills/abi"

    assert first["platform"] == "claude-code"
    assert first["scope"] == "user"
    assert Path(first["target"]) == target
    assert first["copied"]
    assert (target / "SKILL.md").is_file()
    assert json.loads((tmp_path / ".claude.json").read_text(encoding="utf-8"))["mcpServers"][
        "abi"
    ] == {
        "type": "stdio",
        "command": "abi-mcp",
        "args": ["--profile", "safe"],
        "env": {},
    }

    second = install_agent_integration(platform="claude-code", scope="user")

    assert second["copied"] == []
    assert second["unchanged"]
    assert second["config_changed"] is False


def test_install_opencode_project_preserves_config_and_adds_abi(tmp_path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    config_path = project / "opencode.json"
    config_path.write_text(
        json.dumps(
            {
                "$schema": "https://opencode.ai/config.json",
                "model": "anthropic/claude-sonnet-4-5",
                "mcp": {"existing": {"type": "remote", "url": "https://example.test"}},
            }
        ),
        encoding="utf-8",
    )

    result = install_agent_integration(
        platform="opencode",
        scope="project",
        project_dir=project,
    )
    config = json.loads(config_path.read_text(encoding="utf-8"))

    assert Path(result["target"]) == project / ".opencode/skills/abi"
    assert (project / ".opencode/skills/abi/SKILL.md").is_file()
    assert config["model"] == "anthropic/claude-sonnet-4-5"
    assert config["mcp"]["existing"]["url"] == "https://example.test"
    assert config["mcp"]["abi"] == {
        "type": "local",
        "command": ["abi-mcp", "--profile", "safe"],
        "enabled": True,
        "timeout": 10000,
    }
    assert result["config_changed"] is True


def test_install_claude_code_project_uses_discoverable_skill_and_root_mcp(tmp_path) -> None:
    config_path = tmp_path / ".mcp.json"
    config_path.write_text(
        json.dumps(
            {"mcpServers": {"existing": {"type": "http", "url": "https://example.test/mcp"}}}
        ),
        encoding="utf-8",
    )

    result = install_agent_integration(
        platform="claude-code",
        scope="project",
        project_dir=tmp_path,
    )
    config = json.loads(config_path.read_text(encoding="utf-8"))

    assert Path(result["target"]) == tmp_path / ".claude/skills/abi"
    assert (tmp_path / ".claude/skills/abi/SKILL.md").is_file()
    assert config["mcpServers"]["existing"]["url"] == "https://example.test/mcp"
    assert config["mcpServers"]["abi"] == {
        "type": "stdio",
        "command": "abi-mcp",
        "args": ["--profile", "safe"],
        "env": {},
    }


def test_doctor_reports_healthy_claude_code_install(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(
        "abi.agent_integrations.shutil.which",
        lambda command: "/venv/bin/abi-mcp" if command == "abi-mcp" else None,
    )
    monkeypatch.setattr(
        "abi.agent_integrations._mcp_runtime_status",
        lambda: (True, "Safe MCP server initialized: FastMCP"),
    )
    install_agent_integration(platform="claude-code", scope="user")

    report = doctor_agent_integration(platform="claude-code", scope="user")

    assert report["status"] == "healthy"
    assert report["passed"] is True
    assert {check["name"] for check in report["checks"]} == {
        "abi_mcp_executable",
        "abi_mcp_runtime",
        "skill",
        "platform_config",
    }
    assert all(check["status"] == "passed" for check in report["checks"])


def test_install_codex_project_preserves_config_and_adds_abi(tmp_path) -> None:
    project = tmp_path / "project"
    config_path = project / ".codex/config.toml"
    config_path.parent.mkdir(parents=True)
    config_path.write_text('model = "gpt-5.4"\n', encoding="utf-8")

    result = install_agent_integration(
        platform="codex",
        scope="project",
        project_dir=project,
    )

    assert Path(result["target"]) == project / ".agents/skills/abi"
    assert (project / ".agents/skills/abi/SKILL.md").is_file()
    config_text = config_path.read_text(encoding="utf-8")
    config = tomlkit.parse(config_text).unwrap()
    assert config["model"] == "gpt-5.4"
    assert config["mcp_servers"]["abi"] == {
        "command": "abi-mcp",
        "args": ["--profile", "safe"],
    }
    assert "# ABI managed MCP server (safe profile)" in config_text
    assert result["config_changed"] is True


def test_doctor_reports_healthy_codex_project_install(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        "abi.agent_integrations.shutil.which",
        lambda command: "/venv/bin/abi-mcp" if command == "abi-mcp" else None,
    )
    monkeypatch.setattr(
        "abi.agent_integrations._mcp_runtime_status",
        lambda: (True, "Safe MCP server initialized: FastMCP"),
    )
    install_agent_integration(platform="codex", scope="project", project_dir=tmp_path)

    report = doctor_agent_integration(
        platform="codex",
        scope="project",
        project_dir=tmp_path,
    )

    assert report["status"] == "healthy"
    assert report["passed"] is True


def test_doctor_reports_missing_mcp_runtime_as_unhealthy(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        "abi.agent_integrations.shutil.which",
        lambda command: "/venv/bin/abi-mcp" if command == "abi-mcp" else None,
    )
    monkeypatch.setattr(
        "abi.agent_integrations._mcp_runtime_status",
        lambda: (
            False,
            "Safe MCP server initialization failed: RuntimeError: install the MCP extra",
        ),
    )
    install_agent_integration(platform="codex", scope="project", project_dir=tmp_path)

    report = doctor_agent_integration(
        platform="codex",
        scope="project",
        project_dir=tmp_path,
    )

    runtime_check = next(check for check in report["checks"] if check["name"] == "abi_mcp_runtime")
    assert report["status"] == "unhealthy"
    assert report["passed"] is False
    assert runtime_check["status"] == "failed"
    assert "install the MCP extra" in runtime_check["message"]


def test_codex_install_refuses_conflicting_mcp_entry_without_force(tmp_path) -> None:
    config_path = tmp_path / ".codex/config.toml"
    config_path.parent.mkdir(parents=True)
    original = '[mcp_servers.abi]\ncommand = "other-server"\nargs = ["--unsafe"]\n'
    config_path.write_text(original, encoding="utf-8")

    with pytest.raises(ABIError, match="--force"):
        install_agent_integration(
            platform="codex",
            scope="project",
            project_dir=tmp_path,
        )

    assert config_path.read_text(encoding="utf-8") == original
    assert not (tmp_path / ".agents/skills/abi").exists()


def test_codex_force_replaces_only_abi_mcp_table(tmp_path) -> None:
    config_path = tmp_path / ".codex/config.toml"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(
        '[mcp_servers.abi]\ncommand = "other-server"\n\n'
        "[mcp_servers.existing]\n"
        'command = "keep-me"\n',
        encoding="utf-8",
    )

    install_agent_integration(
        platform="codex",
        scope="project",
        project_dir=tmp_path,
        force=True,
    )

    config = tomlkit.parse(config_path.read_text(encoding="utf-8")).unwrap()
    assert config["mcp_servers"]["existing"]["command"] == "keep-me"
    assert config["mcp_servers"]["abi"] == {
        "command": "abi-mcp",
        "args": ["--profile", "safe"],
    }


@pytest.mark.parametrize(
    "config_text",
    [
        ('[mcp_servers]\nabi = { command = "other-server" }\nexisting = { command = "keep-me" }\n'),
        (
            'mcp_servers = { abi = { command = "other-server" }, '
            'existing = { command = "keep-me" } }\n'
        ),
        (
            'mcp_servers.abi = { command = "other-server" }\n'
            'mcp_servers.existing = { command = "keep-me" }\n'
        ),
    ],
)
def test_codex_force_replaces_inline_and_dotted_mcp_entries(
    tmp_path,
    config_text,
) -> None:
    config_path = tmp_path / ".codex/config.toml"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(config_text, encoding="utf-8")

    install_agent_integration(
        platform="codex",
        scope="project",
        project_dir=tmp_path,
        force=True,
    )

    config = tomlkit.parse(config_path.read_text(encoding="utf-8")).unwrap()
    assert config["mcp_servers"]["existing"]["command"] == "keep-me"
    assert config["mcp_servers"]["abi"] == {
        "command": "abi-mcp",
        "args": ["--profile", "safe"],
    }
