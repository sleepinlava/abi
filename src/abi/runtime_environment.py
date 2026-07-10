"""Runtime environment resolution — discover mamba roots, find env prefixes, load assignments.

Centralizes environment logic that was scattered across ``config.py``,
``tools.py``, ``runtime_lock.py``, and the plasmid engine.  Design doc ref: §4.3.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from abi.config import PROJECT_ROOT, resolved_mamba_root


def resolve_environment_prefix(mamba_root: Path, env_name: str) -> Path:
    """Return the filesystem prefix for a named conda environment.

    Supports two layouts:
    1. **Direct**: ``{mamba_root}/{env_name}`` (``mamba env create -p ...``)
    2. **Managed**: ``{mamba_root}/envs/{env_name}`` (standard conda convention)

    The direct layout is checked first; the managed layout is the fallback.
    """
    direct = mamba_root / env_name
    if direct.exists():
        return direct
    return mamba_root / "envs" / env_name


def load_environment_assignments() -> Mapping[str, Any]:
    """Load ``environments.yaml`` from the ABI package data.

    Prefers ``importlib.resources`` (packaged wheel) and falls back to a
    direct filesystem read (development checkout).  Returns the full
    parsed YAML document.
    """
    import yaml

    # Try packaged path first (wheel installation).
    try:
        from importlib.resources import files

        data = files("abi.data").joinpath("environments.yaml")
        if data.is_file():
            return yaml.safe_load(data.read_bytes()) or {}
    except Exception:
        pass

    # Fallback: development checkout.
    dev_path = PROJECT_ROOT / "environments.yaml"
    if dev_path.exists():
        return yaml.safe_load(dev_path.read_bytes()) or {}

    raise FileNotFoundError(
        "environments.yaml not found in package data or project root. "
        "Rebuild the wheel or re-run from the project root."
    )


__all__ = [
    "load_environment_assignments",
    "resolve_environment_prefix",
    "resolved_mamba_root",
]
