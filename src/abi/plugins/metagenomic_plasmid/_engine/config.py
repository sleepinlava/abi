"""Configuration loading and validation."""

from __future__ import annotations

import os
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

import yaml

from abi.plugins.metagenomic_plasmid._engine.schemas import (
    VALID_MODES,
    VALID_PLASMID_STRATEGIES,
    ConfigError,
)
from abi.plugins.metagenomic_plasmid._engine.timeouts import parse_timeout_seconds


def _resolve_project_root() -> Path:
    current = Path(__file__).resolve()
    for candidate in (current.parents[3], current.parents[2], Path.cwd()):
        if (candidate / "config" / "default.yaml").exists():
            return candidate
    return current.parents[3]


PROJECT_ROOT = _resolve_project_root()
DEFAULT_CONFIG = PROJECT_ROOT / "config" / "default.yaml"


def load_yaml(path: str | Path) -> Dict[str, Any]:
    yaml_path = Path(path)
    if not yaml_path.exists():
        raise ConfigError(f"YAML file does not exist: {yaml_path}")
    with yaml_path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ConfigError(f"YAML file must contain a mapping at top level: {yaml_path}")
    return data


def write_yaml(data: Mapping[str, Any], path: str | Path) -> None:
    yaml_path = Path(path)
    yaml_path.parent.mkdir(parents=True, exist_ok=True)
    with yaml_path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(dict(data), handle, sort_keys=False, allow_unicode=True)


def deep_merge(base: Dict[str, Any], override: Mapping[str, Any]) -> Dict[str, Any]:
    result = deepcopy(base)
    for key, value in override.items():
        if value is None:
            continue
        if isinstance(value, Mapping) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result


def compact_overrides(overrides: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    if not overrides:
        return {}
    compacted: Dict[str, Any] = {}
    for key, value in overrides.items():
        if value is None:
            continue
        if isinstance(value, Mapping):
            nested = compact_overrides(value)
            if nested:
                compacted[key] = nested
        else:
            compacted[key] = value
    return compacted


def _resolve_existing_path(path: str | Path) -> Path:
    raw_path = Path(path)
    if raw_path.is_absolute() or raw_path.exists():
        return raw_path
    project_path = PROJECT_ROOT / raw_path
    if project_path.exists():
        return project_path
    return raw_path


def _resolve_input_paths(config: Dict[str, Any], config_path: Path | None) -> None:
    input_config = config.get("input")
    if not isinstance(input_config, dict):
        return

    base_dirs = []
    if config_path is not None:
        base_dirs.append(config_path.parent)
    base_dirs.append(PROJECT_ROOT)

    for key in ("sample_sheet", "single_input", "read1", "read2", "long_reads", "assembly"):
        value = input_config.get(key)
        if not value:
            continue
        resolved = _resolve_input_path(value, base_dirs)
        input_config[key] = str(resolved)


def _resolve_input_path(value: str | Path, base_dirs: list[Path]) -> Path:
    raw_path = Path(value)
    if raw_path.is_absolute():
        return raw_path
    if raw_path.exists():
        return raw_path.resolve()
    for base_dir in base_dirs:
        candidate = base_dir / raw_path
        if candidate.exists():
            return candidate.resolve()
    return raw_path


def load_config(
    config_path: str | Path | None = None,
    profile: str | None = None,
    overrides: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    config = load_yaml(DEFAULT_CONFIG)

    selected_profile = profile or config.get("profile") or "local"
    profile_path = PROJECT_ROOT / "config" / "profiles" / f"{selected_profile}.yaml"
    if profile_path.exists():
        config = deep_merge(config, load_yaml(profile_path))

    resolved_config_path = _resolve_existing_path(config_path) if config_path else None
    if resolved_config_path:
        config = deep_merge(config, load_yaml(resolved_config_path))

    config = deep_merge(config, compact_overrides(overrides))
    _resolve_input_paths(config, resolved_config_path)
    config["profile"] = selected_profile
    validate_config(config)
    return config


def validate_config(config: Mapping[str, Any]) -> None:
    required = [
        "project_name",
        "mode",
        "threads",
        "outdir",
        "log_dir",
        "input",
        "qc",
        "assembly",
        "plasmid_detection",
    ]
    missing = [key for key in required if key not in config]
    if missing:
        raise ConfigError(f"Missing required config keys: {', '.join(missing)}")

    mode = str(config.get("mode"))
    if mode not in VALID_MODES:
        raise ConfigError(f"mode must be one of {sorted(VALID_MODES)}, got {mode!r}")

    threads = config.get("threads")
    if not isinstance(threads, int) or threads < 1:
        raise ConfigError(f"threads must be a positive integer, got {threads!r}")

    execution = config.get("execution", {})
    if execution is not None and not isinstance(execution, Mapping):
        raise ConfigError("execution must be a mapping")
    if isinstance(execution, Mapping):
        parallel = execution.get("parallel", False)
        if not isinstance(parallel, bool):
            raise ConfigError(f"execution.parallel must be a boolean, got {parallel!r}")
        workers = execution.get("workers", 1)
        if not isinstance(workers, int) or workers < 1:
            raise ConfigError(f"execution.workers must be a positive integer, got {workers!r}")
        progress = execution.get("progress", True)
        if not isinstance(progress, bool):
            raise ConfigError(f"execution.progress must be a boolean, got {progress!r}")
        for key in (
            "tool_timeout_seconds",
            "resource_timeout_seconds",
            "nextflow_timeout_seconds",
        ):
            try:
                parse_timeout_seconds(execution.get(key), default=None)
            except ValueError as exc:
                raise ConfigError(f"execution.{key} is invalid: {exc}") from exc
        dashboard = execution.get("dashboard", {})
        if dashboard is not None and not isinstance(dashboard, Mapping):
            raise ConfigError("execution.dashboard must be a mapping")
        if isinstance(dashboard, Mapping):
            enabled = dashboard.get("enable", False)
            if not isinstance(enabled, bool):
                raise ConfigError(f"execution.dashboard.enable must be a boolean, got {enabled!r}")
            host = dashboard.get("host", "127.0.0.1")
            if not isinstance(host, str) or not host:
                raise ConfigError(
                    f"execution.dashboard.host must be a non-empty string, got {host!r}"
                )
            port = dashboard.get("port", 18790)
            if not isinstance(port, int) or not 1 <= port <= 65535:
                raise ConfigError(
                    f"execution.dashboard.port must be an integer from 1 to 65535, got {port!r}"
                )
            open_browser = dashboard.get("open_browser", True)
            if not isinstance(open_browser, bool):
                raise ConfigError(
                    f"execution.dashboard.open_browser must be a boolean, got {open_browser!r}"
                )

    plasmid_detection = config.get("plasmid_detection") or {}
    tools = plasmid_detection.get("tools")
    if not isinstance(tools, list) or not tools:
        raise ConfigError("plasmid_detection.tools must be a non-empty list")

    strategy = plasmid_detection.get("strategy", "single_tool")
    if strategy not in VALID_PLASMID_STRATEGIES:
        raise ConfigError(
            "plasmid_detection.strategy must be one of "
            f"{sorted(VALID_PLASMID_STRATEGIES)}, got {strategy!r}"
        )
    if strategy == "single_tool" and len(tools) != 1:
        raise ConfigError("single_tool strategy requires exactly one plasmid detection tool")


def resolved_outdir(config: Mapping[str, Any]) -> Path:
    return Path(str(config["outdir"]))


def resolved_log_dir(config: Mapping[str, Any]) -> Path:
    return Path(str(config["log_dir"]))


def write_resolved_config(config: Mapping[str, Any]) -> Path:
    outdir = resolved_outdir(config)
    path = outdir / "provenance" / "config.resolved.yaml"
    write_yaml(config, path)
    return path


def resolved_mamba_root() -> Path:
    """Return the repository-local mamba root for ABI-bundled AutoPlasm tools."""
    return Path(
        os.environ.get("ABI_MAMBA_ROOT")
        or os.environ.get("AUTOPLASM_MAMBA_ROOT")
        or PROJECT_ROOT / ".mamba"
    )
