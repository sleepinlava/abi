"""Filesystem helpers for AutoPlasm runtime paths."""

from __future__ import annotations

from pathlib import Path

from abi.autoplasm.schemas import AutoPlasmError


def ensure_directory(path: str | Path, *, label: str = "Directory") -> Path:
    """Return an existing directory or create it when missing."""
    directory = Path(path)
    if directory.exists():
        if not directory.is_dir():
            raise AutoPlasmError(f"{label} exists but is not a directory: {directory}")
        return directory
    directory.mkdir(parents=True, exist_ok=True)
    return directory
