"""Path Policy — validate and contain sample-provided paths.

Security-critical module. All sample_id values and user-provided paths that
resolve within the output root must pass through this module. The policy is
intentionally small: two functions, one validator, one containment check.

Design doc ref: §4.1 Path Policy
"""

from __future__ import annotations

import os
import re
from functools import lru_cache
from pathlib import Path

from abi.errors import InputPolicyError

_MAX_SAMPLE_ID_LENGTH = 128
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f-\x9f]")


def validate_sample_id(value: str) -> str:
    """Validate a sample_id for safe use in file-system path construction.

    Rejects values that could escape the configured output root:
    absolute paths, path separators, ``.`` / ``..`` identifiers, NUL/control
    characters, traversal components, and excessive length.

    Returns the validated string unchanged on success.
    Raises :exc:`InputPolicyError` on rejection.
    """
    if not value or not value.strip():
        raise InputPolicyError("sample_id must not be empty or whitespace-only")

    stripped = value.strip()
    if stripped != value:
        raise InputPolicyError(f"sample_id must not have leading or trailing whitespace: {value!r}")

    # Reject absolute paths (Unix and Windows)
    if os.path.isabs(stripped):
        raise InputPolicyError(f"sample_id must not be an absolute path: {value!r}")

    # Reject both separator styles (catches embedded separators inside
    # otherwise-relative-looking strings)
    if "/" in stripped or "\\" in stripped:
        raise InputPolicyError(f"sample_id must not contain path separators: {value!r}")

    # Reject NUL and other control characters
    if _CONTROL_RE.search(stripped):
        raise InputPolicyError(f"sample_id must not contain control characters: {value!r}")

    # Reject dot and dot-dot as the entire value
    if stripped in (".", ".."):
        raise InputPolicyError(f"sample_id must not be '.' or '..': {value!r}")

    # Reject traversal components anywhere in the string (normalised check)
    components = stripped.replace("\\", "/").split("/")
    for component in components:
        c = component.strip()
        if c in (".", ".."):
            raise InputPolicyError(f"sample_id must not contain traversal components: {value!r}")

    # Reject excessive length (POSIX filename limit is 255, but sample_id is
    # embedded inside longer paths; 128 is conservative)
    if len(stripped.encode("utf-8")) > _MAX_SAMPLE_ID_LENGTH:
        raise InputPolicyError(
            f"sample_id must not exceed {_MAX_SAMPLE_ID_LENGTH} bytes: "
            f"{len(stripped.encode('utf-8'))} bytes"
        )

    return stripped


@lru_cache(maxsize=128)
def _resolve_root(root: str) -> Path:
    """Resolve stable output roots once across large multi-sample plans."""
    return Path(root).resolve()


def resolve_within(root: Path, candidate: str | Path, *, label: str = "path") -> Path:
    """Resolve *candidate* and verify it is strictly contained within *root*.

    The *label* is used in error messages to identify the path's purpose
    (e.g. ``"output_dir"``, ``"assembly"``).

    Rules enforced:
    - The resolved **real** path (symlinks followed) must start with the
      resolved real *root*.  This catches symlink escapes.
    - *root* itself must exist (or be creatable).  If *root* does not exist,
      containment is checked on the parent.

    Returns the resolved, real :class:`Path`.
    Raises :exc:`InputPolicyError` on escape.
    """
    root = _resolve_root(os.path.abspath(os.fspath(root)))

    # Reject NUL bytes before pathlib swallows the error with a different type.
    candidate_str = str(candidate)
    if "\x00" in candidate_str:
        raise InputPolicyError(f"{label} must not contain NUL bytes: {candidate_str!r}")

    candidate_path = Path(candidate)

    # If the candidate is absolute, resolve it directly.
    if candidate_path.is_absolute():
        resolved = candidate_path.resolve()
    else:
        resolved = (root / candidate_path).resolve()

    # Containment check: the resolved path must start with the resolved root.
    # Use os.path.commonpath for reliable prefix comparison.
    try:
        common = Path(os.path.commonpath([str(root), str(resolved)]))
    except ValueError:
        raise InputPolicyError(f"{label} escapes output root: candidate={candidate!s}, root={root}")

    if common != root:
        raise InputPolicyError(
            f"{label} escapes output root: candidate={candidate!s}, "
            f"resolved={resolved}, root={root}"
        )

    return resolved
