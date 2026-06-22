"""Filesystem helpers used by ABI runtimes."""

from __future__ import annotations

from pathlib import Path

from abi.errors import ABIError

__all__ = ["ensure_directory", "ensure_parent"]


def ensure_directory(path: str | Path, *, label: str = "Directory") -> Path:
    """Return an existing directory or create it when missing."""
    directory = Path(path)
    if directory.exists():
        if not directory.is_dir():
            raise ABIError(f"{label} exists but is not a directory: {directory}")
        return directory
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def ensure_parent(path: str | Path) -> Path:
    """Create a path's parent directory and return the path unchanged."""
    resolved = Path(path)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    return resolved
