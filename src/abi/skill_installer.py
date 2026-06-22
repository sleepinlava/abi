"""Transport-neutral installer for ABI's bundled agent skills."""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, Dict

from abi.schemas import ABIError

__all__ = ["install_bundled_skills", "resolve_skills_source"]


def resolve_skills_source() -> Path:
    """Resolve the packaged skills directory for editable and wheel installs."""
    try:
        from importlib.resources import files

        source = files("abi") / "skills"
        if source.is_dir():
            return Path(str(source))
    except Exception:
        pass

    import abi

    source = Path(abi.__file__).parent / "skills"
    if not source.is_dir():
        raise ABIError(f"ABI skills directory not found: {source}")
    return source


def install_bundled_skills(
    *, target: str | Path | None = None, force: bool = False
) -> Dict[str, Any]:
    """Install all SKILL.md files and the bundled README using atomic replaces."""
    source = resolve_skills_source()
    destination = Path(target).expanduser() if target else Path.home() / ".claude/skills/abi"
    destination.parent.mkdir(parents=True, exist_ok=True)

    source_files: list[tuple[Path, Path]] = []
    readme = source / "README.md"
    if readme.is_file():
        source_files.append((readme, Path("README.md")))
    for item in sorted(source.iterdir()):
        skill_file = item / "SKILL.md"
        if item.is_dir() and skill_file.is_file():
            source_files.append((skill_file, Path(item.name) / "SKILL.md"))

    copied: list[str] = []
    skipped: list[str] = []
    staging = Path(tempfile.mkdtemp(prefix=".abi-skills-", dir=destination.parent))
    try:
        for source_file, relative_path in source_files:
            final_path = destination / relative_path
            if final_path.exists() and not force:
                skipped.append(str(final_path))
                continue
            staged_path = staging / relative_path
            staged_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_file, staged_path)

        destination.mkdir(parents=True, exist_ok=True)
        for staged_path in sorted(path for path in staging.rglob("*") if path.is_file()):
            relative_path = staged_path.relative_to(staging)
            final_path = destination / relative_path
            final_path.parent.mkdir(parents=True, exist_ok=True)
            os.replace(staged_path, final_path)
            copied.append(str(final_path))
    finally:
        shutil.rmtree(staging, ignore_errors=True)

    return {
        "source": str(source),
        "target": str(destination),
        "copied": copied,
        "skipped": skipped,
        "count": len(copied),
    }
