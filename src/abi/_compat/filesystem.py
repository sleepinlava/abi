"""Filesystem helpers.

Copied from autoplasm.filesystem with import path adjustments.
"""

from __future__ import annotations

from pathlib import Path

from abi._compat.errors import AutoPlasmError


def ensure_directory(path: str | Path, *, label: str = "Directory") -> Path:
    """Return an existing directory or create it when missing."""
    directory = Path(path)
    if directory.exists():
        if not directory.is_dir():
            raise AutoPlasmError(f"{label} exists but is not a directory: {directory}")
        return directory
    directory.mkdir(parents=True, exist_ok=True)
    return directory
