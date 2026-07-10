"""Execution policy — ResourceOverride, resolution chain, ExecutionPolicy.

Design doc ref: §6 Resource and execution policy, C06.

Separates partial overrides (``ResourceOverride``) from resolved values
(``ResourceSpec``).  ``None`` is the only unset representation — an explicit
value that equals a default is still honoured as an override and wins over
lower-priority layers.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from abi.errors import ToolError
from abi.tools import ResourceSpec

__all__ = [
    "ExecutionPolicy",
    "ResourceOverride",
    "ResourcePolicyError",
    "apply_resource_policy",
]


class ResourcePolicyError(ToolError):
    """Resource override violates a declared minimum or constraint."""


@dataclass(frozen=True)
class ResourceOverride:
    """Partial resource request override.

    Every field is ``Optional`` — ``None`` means *not set at this layer*.
    An explicit override that happens to equal a default is **still an
    override** and will carry forward through the resolution chain.

    See Also: :class:`abi.tools.ResourceSpec` for the resolved (all-fields-concrete) form.
    """

    cpu: int | None = None
    memory: str | None = None
    walltime: str | None = None
    accelerator: str | None = None
    disk: str | None = None

    @classmethod
    def from_mapping(cls, mapping: Mapping[str, Any]) -> ResourceOverride:
        """Build from a user-facing dict (config, CLI args, profile).

        Missing keys map to ``None`` (unset).  Keys with ``None`` values are
        also treated as unset so that ``{cpu: None}`` is equivalent to ``{}``.
        """
        _get = lambda k: mapping.get(k)  # noqa: E731
        return cls(
            cpu=_get("cpu"),
            memory=_get("memory"),
            walltime=_get("walltime"),
            accelerator=_get("accelerator"),
            disk=_get("disk"),
        )

    def is_empty(self) -> bool:
        """``True`` when every field is ``None``."""
        return all(
            getattr(self, f) is None
            for f in ("cpu", "memory", "walltime", "accelerator", "disk")
        )


# ── Resolution ───────────────────────────────────────────────────────────────


def _apply_value(current: Any, override: Any) -> Any:
    """Return *override* if not None, otherwise *current*."""
    return override if override is not None else current


def apply_resource_policy(
    *,
    base: ResourceSpec,
    catalog: ResourceOverride | None = None,
    workflow: ResourceOverride | None = None,
    invocation: ResourceOverride | None = None,
) -> ResourceSpec:
    """Resolve a ``ResourceSpec`` through the standard precedence chain.

    Priority (lowest → highest):

    1. **base**      — backend fallback or tool-contract defaults
    2. **catalog**   — per-tool recommendation from the tool catalog
    3. **workflow**  — step-level override in the DAG or user config
    4. **invocation** — CLI or agent invocation flags

    Returns a new ``ResourceSpec`` with all layers applied.  Input ``base``
    is never mutated.
    """
    spec = base

    for ov in (catalog, workflow, invocation):
        if ov is None or ov.is_empty():
            continue
        spec = ResourceSpec(
            cpu=_apply_value(spec.cpu, ov.cpu),
            memory=_apply_value(spec.memory, ov.memory),
            walltime=_apply_value(spec.walltime, ov.walltime),
            accelerator=_apply_value(spec.accelerator, ov.accelerator),
            disk=_apply_value(spec.disk, ov.disk),
        )

    return spec


# ── Execution policy ─────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ExecutionPolicy:
    """Immutable execution policy for a plan run.

    Captures the resolved execution mode, environment root, container
    settings, resource profile, and invocation-level resource overrides.
    Transport adapters (Local, HPC, Nextflow) consume this policy and
    must not resolve resources or environments independently.
    """

    mode: str = "auto"  # auto | native | conda | container
    mamba_root: Path | None = None
    container_image: str | None = None
    container_runtime: str | None = None  # docker | podman | singularity | apptainer
    resource_profile: str | None = None
    resource_profiles_dir: str | Path | None = None
    invocation_overrides: ResourceOverride | None = None
