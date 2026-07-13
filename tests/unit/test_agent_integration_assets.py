import json
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
SHARED_SKILL = ROOT / "integrations/shared/skills/abi/SKILL.md"
CLAUDE_ROOT = ROOT / "integrations/claude-code/abi"
OPENCODE_ROOT = ROOT / "integrations/opencode"


def _frontmatter(path: Path) -> dict[str, object]:
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\n")
    block = text.split("---\n", 2)[1]
    parsed = yaml.safe_load(block)
    assert isinstance(parsed, dict)
    return parsed


def _project_version() -> str:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'^version = "([^"]+)"$', pyproject, flags=re.MULTILINE)
    assert match is not None
    return match.group(1)


def test_shared_abi_skill_is_agent_skills_compatible() -> None:
    metadata = _frontmatter(SHARED_SKILL)

    assert SHARED_SKILL.parent.name == metadata["name"] == "abi"
    assert isinstance(metadata["description"], str)
    assert "bioinformatics" in metadata["description"].lower()
    assert "abi_list_types" in SHARED_SKILL.read_text(encoding="utf-8")


def test_platform_skills_match_the_shared_source() -> None:
    expected = SHARED_SKILL.read_text(encoding="utf-8")

    assert (CLAUDE_ROOT / "skills/abi/SKILL.md").read_text(encoding="utf-8") == expected
    assert (OPENCODE_ROOT / "skills/abi/SKILL.md").read_text(encoding="utf-8") == expected


def test_claude_plugin_declares_safe_abi_mcp_server() -> None:
    manifest = json.loads((CLAUDE_ROOT / ".claude-plugin/plugin.json").read_text())
    mcp = json.loads((CLAUDE_ROOT / ".mcp.json").read_text())

    assert manifest["name"] == "abi"
    assert manifest["version"] == _project_version()
    assert mcp["mcpServers"]["abi"] == {
        "command": "abi-mcp",
        "args": ["--profile", "safe"],
    }


def test_opencode_example_declares_safe_abi_mcp_server() -> None:
    config = json.loads((OPENCODE_ROOT / "opencode.example.json").read_text())

    assert config["$schema"] == "https://opencode.ai/config.json"
    assert config["mcp"]["abi"] == {
        "type": "local",
        "command": ["abi-mcp", "--profile", "safe"],
        "enabled": True,
        "timeout": 10000,
    }


def test_agent_integration_assets_are_in_sdist_and_wheel() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")

    assert '"integrations" = "abi/integrations"' in pyproject
    assert re.search(r'^\s+"integrations",$', pyproject, flags=re.MULTILINE)
