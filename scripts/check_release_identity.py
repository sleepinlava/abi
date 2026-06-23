#!/usr/bin/env python3
"""Validate that source, installed package, changelog, and release tag agree."""

from __future__ import annotations

import argparse
import os
import re
import sys
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as distribution_version
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def project_version() -> str:
    content = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    project_match = re.search(
        r"(?ms)^\[project\]\s*$\n(?P<body>.*?)(?=^\[|\Z)",
        content,
    )
    version_match = (
        re.search(r'^version\s*=\s*["\'](?P<version>[^"\']+)["\']\s*$', project_match["body"], re.M)
        if project_match
        else None
    )
    if version_match is None:
        raise RuntimeError("pyproject.toml must define a non-empty project.version")
    return version_match["version"]


def release_tag_from_environment() -> str | None:
    if os.environ.get("GITHUB_REF_TYPE") == "tag":
        return os.environ.get("GITHUB_REF_NAME") or None
    return None


def validate_release_identity(tag: str | None = None) -> list[str]:
    expected = project_version()
    errors: list[str] = []

    try:
        installed = distribution_version("abi-agent")
    except PackageNotFoundError:
        errors.append("abi-agent distribution is not installed")
    else:
        if installed != expected:
            errors.append(f"installed distribution is {installed}, expected {expected}")

    import abi

    if abi.__version__ != expected:
        errors.append(f"abi.__version__ is {abi.__version__}, expected {expected}")

    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    if not re.search(rf"^## \[{re.escape(expected)}\](?:\s|$)", changelog, re.MULTILINE):
        errors.append(f"CHANGELOG.md has no release section for {expected}")

    if tag is not None and tag != f"v{expected}":
        errors.append(f"release tag is {tag}, expected v{expected}")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", default=release_tag_from_environment())
    args = parser.parse_args()
    errors = validate_release_identity(args.tag)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(f"Release identity verified: {project_version()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
