"""Configuration helpers for the ABI prototype."""

from __future__ import annotations

import os
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

import yaml

from abi.filesystem import ensure_parent


def _resolve_project_root() -> Path:
    current = Path(__file__).resolve()
    for candidate in (current.parents[2], current.parents[1], Path.cwd()):
        if (candidate / "plugins").exists():
            return candidate
    return current.parents[2]


PROJECT_ROOT = _resolve_project_root()
PLUGIN_ROOT = PROJECT_ROOT / "plugins"


class ABIConfigError(RuntimeError):
    """Raised when ABI configuration is invalid."""


def load_yaml(path: str | Path) -> Dict[str, Any]:
    yaml_path = Path(path)
    if not yaml_path.exists():
        raise ABIConfigError(f"YAML file does not exist: {yaml_path}")
    with yaml_path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ABIConfigError(f"YAML file must contain a mapping at top level: {yaml_path}")
    return data


def write_yaml(data: Mapping[str, Any], path: str | Path) -> Path:
    yaml_path = ensure_parent(path)
    with yaml_path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(dict(data), handle, sort_keys=False, allow_unicode=True)
    return yaml_path


def resolved_mamba_root() -> Path:
    """Return the local mamba root used by ABI-managed tool environments.

    Resolution order:
    1. ``ABI_MAMBA_ROOT`` env var (explicit override)
    2. ``AUTOPLASM_MAMBA_ROOT`` env var (legacy compat)
    3. ``PROJECT_ROOT / ".mamba"`` (default local install)
    4. ``PROJECT_ROOT.parent / "abi-envs"`` (sibling dir, common in dev/deploy)

    Env overrides that point at non-existent or empty directories fall through
    to default/sibling so one misconfigured export cannot silently break tool
    discovery.
    """
    for var in ("ABI_MAMBA_ROOT", "AUTOPLASM_MAMBA_ROOT"):
        env_override = os.environ.get(var)
        if env_override:
            candidate = Path(env_override)
            envs_dir = candidate / "envs"
            if envs_dir.is_dir() and any(envs_dir.iterdir()):
                return candidate
            # Fall through to default/sibling on empty/missing override.
    default = PROJECT_ROOT / ".mamba"
    if default.exists():
        return default
    sibling = PROJECT_ROOT.parent / "abi-envs"
    if sibling.exists():
        return sibling
    return default


def deep_merge(base: Dict[str, Any], override: Mapping[str, Any]) -> Dict[str, Any]:
    result = deepcopy(base)
    for key, value in override.items():
        if value is None:
            continue
        if isinstance(value, Mapping) and isinstance(result.get(key), Mapping):
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


def mapping_block(config: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    """Return a config section only when it is a mapping."""
    block = config.get(key, {})
    return block if isinstance(block, Mapping) else {}


def load_resource_profile(name: str) -> Dict[str, Any]:
    """Load a named resource profile from ``config/resource_profiles/``.

    Profiles are pre-defined resource presets (e.g. ``dev_small``,
    ``hpc_standard``, ``hpc_large``) that users can select via
    ``--resource-profile`` or ``ABI_RESOURCE_PROFILE``.

    Returns the profile data dict, or an empty dict if not found.
    / 返回 profile 数据字典，未找到则返回空字典。
    """
    profile_path = PROJECT_ROOT / "config" / "resource_profiles" / f"{name}.yaml"
    try:
        return load_yaml(str(profile_path))
    except ABIConfigError:
        return {}


def env_resource_overrides() -> Dict[str, Any]:
    """Build resource overrides from ``ABI_*`` environment variables.

    Reads ``ABI_DEFAULT_CPU``, ``ABI_DEFAULT_MEMORY``, ``ABI_DEFAULT_WALLTIME``,
    ``ABI_ACCELERATOR``, and ``ABI_RESOURCE_PROFILE`` from the environment.
    Returns a dict suitable for merging into resource configs.
    / 从环境变量构建资源覆盖字典。
    """
    overrides: Dict[str, Any] = {}
    cpu = os.environ.get("ABI_DEFAULT_CPU")
    if cpu:
        try:
            overrides["cpu"] = int(cpu)
        except ValueError:
            pass
    memory = os.environ.get("ABI_DEFAULT_MEMORY")
    if memory:
        overrides["memory"] = memory
    walltime = os.environ.get("ABI_DEFAULT_WALLTIME")
    if walltime:
        overrides["walltime"] = walltime
    accelerator = os.environ.get("ABI_ACCELERATOR")
    if accelerator:
        overrides["accelerator"] = accelerator
    # Container overrides
    container_image = os.environ.get("ABI_CONTAINER_IMAGE")
    if container_image:
        overrides["container_image"] = container_image
    container_runtime = os.environ.get("ABI_CONTAINER_RUNTIME")
    if container_runtime:
        overrides["container_runtime"] = container_runtime
    return overrides
