"""Install and diagnose ABI integrations for supported agent platforms."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import tomlkit
from tomlkit.exceptions import ParseError

from abi.schemas import ABIError

__all__ = [
    "doctor_agent_integration",
    "install_agent_integration",
    "resolve_agent_integrations_source",
]

SUPPORTED_AGENT_SCOPES = ("user", "project")
CLAUDE_MCP_ENTRY = {
    "type": "stdio",
    "command": "abi-mcp",
    "args": ["--profile", "safe"],
    "env": {},
}
OPENCODE_MCP_ENTRY = {
    "type": "local",
    "command": ["abi-mcp", "--profile", "safe"],
    "enabled": True,
    "timeout": 10000,
}
CODEX_MCP_ENTRY = {"command": "abi-mcp", "args": ["--profile", "safe"]}


@dataclass(frozen=True)
class _IntegrationLayout:
    source: str
    user_target: tuple[str, ...]
    project_target: tuple[str, ...]
    skill: tuple[str, ...]
    user_config: tuple[str, ...]
    project_config: tuple[str, ...]
    json_mcp_key: str | None = None


@dataclass(frozen=True)
class _IntegrationTarget:
    target: Path
    skill: Path
    config: Path


_INTEGRATION_LAYOUTS = {
    "claude-code": _IntegrationLayout(
        source="claude-code/abi/skills/abi",
        user_target=(".claude", "skills", "abi"),
        project_target=(".claude", "skills", "abi"),
        skill=("SKILL.md",),
        user_config=(".claude.json",),
        project_config=(".mcp.json",),
        json_mcp_key="mcpServers",
    ),
    "opencode": _IntegrationLayout(
        source="opencode/skills/abi",
        user_target=(".config", "opencode", "skills", "abi"),
        project_target=(".opencode", "skills", "abi"),
        skill=("SKILL.md",),
        user_config=(".config", "opencode", "opencode.json"),
        project_config=("opencode.json",),
        json_mcp_key="mcp",
    ),
    "codex": _IntegrationLayout(
        source="codex/abi/skills/abi",
        user_target=(".agents", "skills", "abi"),
        project_target=(".agents", "skills", "abi"),
        skill=("SKILL.md",),
        user_config=(".codex", "config.toml"),
        project_config=(".codex", "config.toml"),
    ),
}
SUPPORTED_AGENT_PLATFORMS = tuple(_INTEGRATION_LAYOUTS)
_MCP_ENTRIES: dict[str, dict[str, Any]] = {
    "claude-code": CLAUDE_MCP_ENTRY,
    "opencode": OPENCODE_MCP_ENTRY,
    "codex": CODEX_MCP_ENTRY,
}


def resolve_agent_integrations_source() -> Path:
    """Resolve integration assets in wheels and editable source checkouts."""
    try:
        from importlib.resources import files

        packaged = files("abi") / "integrations"
        if packaged.is_dir():
            return Path(str(packaged))
    except Exception:
        pass

    source_tree = Path(__file__).resolve().parents[2] / "integrations"
    if source_tree.is_dir():
        return source_tree
    raise ABIError("ABI agent integration assets were not found")


def install_agent_integration(
    *,
    platform: str,
    scope: str = "user",
    project_dir: str | Path | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Install one platform integration without changing ABI execution behavior."""
    _validate_target(platform=platform, scope=scope)
    root = Path(project_dir).resolve() if project_dir else Path.cwd().resolve()
    assets = resolve_agent_integrations_source()
    layout = _INTEGRATION_LAYOUTS[platform]
    paths = _resolve_integration_target(layout=layout, scope=scope, root=root)
    source = assets / layout.source

    config_text: str | None = None
    config_json: dict[str, Any] | None = None
    if platform == "codex":
        config_text, config_changed = _prepare_codex_config(paths.config, force=force)
    else:
        initial = {"$schema": "https://opencode.ai/config.json"} if platform == "opencode" else {}
        config_json, config_changed = _prepare_json_mcp_config(
            paths.config,
            mcp_key=layout.json_mcp_key or "mcpServers",
            entry=_MCP_ENTRIES[platform],
            initial=initial,
            platform_label="OpenCode" if platform == "opencode" else "Claude Code",
            force=force,
        )

    copied, unchanged = _copy_tree(source, paths.target, force=force)
    if config_changed and config_text is not None:
        _write_text_atomic(paths.config, config_text)
    elif config_changed and config_json is not None:
        _write_json_atomic(paths.config, config_json)
    return {
        "platform": platform,
        "scope": scope,
        "source": str(source),
        "target": str(paths.target),
        "config": str(paths.config),
        "config_changed": config_changed,
        "copied": copied,
        "unchanged": unchanged,
    }


def doctor_agent_integration(
    *,
    platform: str,
    scope: str = "user",
    project_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Return read-only health checks for an installed platform integration."""
    _validate_target(platform=platform, scope=scope)
    root = Path(project_dir).resolve() if project_dir else Path.cwd().resolve()
    checks: list[dict[str, str]] = []
    layout = _INTEGRATION_LAYOUTS[platform]
    paths = _resolve_integration_target(layout=layout, scope=scope, root=root)

    executable = shutil.which("abi-mcp")
    checks.append(
        {
            "name": "abi_mcp_executable",
            "status": "passed" if executable else "failed",
            "message": executable or "abi-mcp was not found on PATH",
        }
    )

    expected_config = _MCP_ENTRIES[platform]

    checks.append(
        {
            "name": "skill",
            "status": "passed" if paths.skill.is_file() else "failed",
            "message": (
                str(paths.skill) if paths.skill.is_file() else f"Skill is missing: {paths.skill}"
            ),
        }
    )

    config_ok = False
    config_message = f"Platform config is missing: {paths.config}"
    if paths.config.is_file() and platform == "codex":
        try:
            config = tomlkit.parse(paths.config.read_text(encoding="utf-8")).unwrap()
            config_ok = _codex_mcp_entry(config) == expected_config
            config_message = (
                str(paths.config)
                if config_ok
                else f"ABI MCP entry is missing or differs: {paths.config}"
            )
        except (OSError, ParseError) as exc:
            config_message = f"Platform config could not be read: {paths.config}: {exc}"
    elif paths.config.is_file():
        try:
            config = json.loads(paths.config.read_text(encoding="utf-8"))
            mcp_key = layout.json_mcp_key
            mcp = config.get(mcp_key) if isinstance(config, dict) and mcp_key else None
            if isinstance(mcp, dict):
                config_ok = mcp.get("abi") == expected_config
            config_message = (
                str(paths.config)
                if config_ok
                else f"ABI MCP entry is missing or differs: {paths.config}"
            )
        except (json.JSONDecodeError, OSError) as exc:
            config_message = f"Platform config could not be read: {paths.config}: {exc}"
    checks.append(
        {
            "name": "platform_config",
            "status": "passed" if config_ok else "failed",
            "message": config_message,
        }
    )

    passed = all(check["status"] == "passed" for check in checks)
    return {
        "platform": platform,
        "scope": scope,
        "status": "healthy" if passed else "unhealthy",
        "passed": passed,
        "target": str(paths.target),
        "config": str(paths.config),
        "checks": checks,
    }


def _validate_target(*, platform: str, scope: str) -> None:
    if platform not in SUPPORTED_AGENT_PLATFORMS:
        expected = ", ".join(SUPPORTED_AGENT_PLATFORMS)
        raise ABIError(f"Unknown agent platform {platform!r}. Expected: {expected}")
    if scope not in SUPPORTED_AGENT_SCOPES:
        expected = ", ".join(SUPPORTED_AGENT_SCOPES)
        raise ABIError(f"Unknown agent scope {scope!r}. Expected: {expected}")


def _resolve_integration_target(
    *,
    layout: _IntegrationLayout,
    scope: str,
    root: Path,
) -> _IntegrationTarget:
    base = Path.home() if scope == "user" else root
    target_parts = layout.user_target if scope == "user" else layout.project_target
    config_parts = layout.user_config if scope == "user" else layout.project_config
    target = base.joinpath(*target_parts)
    return _IntegrationTarget(
        target=target,
        skill=target.joinpath(*layout.skill),
        config=base.joinpath(*config_parts),
    )


def _copy_tree(source: Path, target: Path, *, force: bool) -> tuple[list[str], list[str]]:
    if not source.is_dir():
        raise ABIError(f"Agent integration source is missing: {source}")

    source_files = sorted(path for path in source.rglob("*") if path.is_file())
    conflicts: list[Path] = []
    unchanged: list[str] = []
    pending: list[tuple[Path, Path]] = []
    for source_file in source_files:
        relative = source_file.relative_to(source)
        destination = target / relative
        if destination.is_file() and destination.read_bytes() == source_file.read_bytes():
            unchanged.append(str(destination))
        elif destination.exists() and not force:
            conflicts.append(destination)
        else:
            pending.append((source_file, relative))

    if conflicts:
        paths = ", ".join(str(path) for path in conflicts)
        raise ABIError(f"Agent integration files already exist; use --force to replace: {paths}")

    target.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".abi-agent-", dir=target.parent))
    copied: list[str] = []
    try:
        for source_file, relative in pending:
            staged = staging / relative
            staged.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_file, staged)

        for _, relative in pending:
            staged = staging / relative
            destination = target / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            os.replace(staged, destination)
            copied.append(str(destination))
    finally:
        shutil.rmtree(staging, ignore_errors=True)

    return copied, unchanged


def _prepare_json_mcp_config(
    path: Path,
    *,
    mcp_key: str,
    entry: dict[str, Any],
    initial: dict[str, Any],
    platform_label: str,
    force: bool,
) -> tuple[dict[str, Any], bool]:
    if path.is_file():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ABIError(
                f"{platform_label} config is not strict JSON and was not modified: {path}"
            ) from exc
        if not isinstance(loaded, dict):
            raise ABIError(f"{platform_label} config must contain a JSON object: {path}")
        config: dict[str, Any] = dict(loaded)
    else:
        config = dict(initial)

    existing_mcp = config.get(mcp_key, {})
    if not isinstance(existing_mcp, dict):
        raise ABIError(f"{platform_label} config field {mcp_key!r} must be a JSON object: {path}")
    mcp = dict(existing_mcp)
    existing_abi = mcp.get("abi")
    if existing_abi == entry:
        return config, False
    if existing_abi is not None and not force:
        raise ABIError(
            f"{platform_label} MCP entry 'abi' already differs; use --force to replace it: {path}"
        )
    mcp["abi"] = dict(entry)
    config[mcp_key] = mcp
    return config, True


def _prepare_codex_config(path: Path, *, force: bool) -> tuple[str, bool]:
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    try:
        document = tomlkit.parse(text)
        config = document.unwrap()
    except ParseError as exc:
        raise ABIError(f"Codex config is invalid TOML and was not modified: {path}") from exc

    existing = _codex_mcp_entry(config)
    if existing == CODEX_MCP_ENTRY:
        return text, False
    if existing is not None and not force:
        raise ABIError(f"Codex MCP entry 'abi' already differs; use --force: {path}")

    servers = config.get("mcp_servers")
    if servers is not None and not isinstance(servers, dict):
        raise ABIError(f"Codex config field 'mcp_servers' must be a TOML table: {path}")

    desired = deepcopy(config)
    desired_servers = desired.setdefault("mcp_servers", {})
    desired_servers["abi"] = deepcopy(CODEX_MCP_ENTRY)

    if document.get("mcp_servers") is None:
        if text:
            document.add(tomlkit.nl())
        document.add(tomlkit.comment("ABI managed MCP server (safe profile)"))
        document["mcp_servers"] = {}
    document["mcp_servers"]["abi"] = deepcopy(CODEX_MCP_ENTRY)
    rendered = tomlkit.dumps(document)

    # tomlkit preserves comments and layout where possible. Some dotted-key
    # documents cannot be mutated in place without changing their meaning, so
    # fall back to a canonical rendering after verifying the parsed data.
    if tomlkit.parse(rendered).unwrap() != desired:
        rendered = tomlkit.dumps(desired)
    return rendered, True


def _codex_mcp_entry(config: dict[str, Any]) -> Any:
    servers = config.get("mcp_servers")
    return servers.get("abi") if isinstance(servers, dict) else None


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _write_text_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
