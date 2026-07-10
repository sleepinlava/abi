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

from abi.errors import ResourcePolicyError
from abi.tools import ResourceSpec

__all__ = [
    "ExecutionPolicy",
    "ResourceOverride",
    "ResourcePolicyError",
    "apply_resource_policy",
    "resolve_resources_v2",
]


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
            getattr(self, f) is None for f in ("cpu", "memory", "walltime", "accelerator", "disk")
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


# ── Bridge: resolve_resources_v2 ───────────────────────────────────────────────


def resolve_resources_v2(
    tool_id: str,
    tool_metadata: Mapping[str, Any],
    *,
    config: Mapping[str, Any] | None = None,
    cli_overrides: ResourceSpec | ResourceOverride | None = None,
    resource_profile: str | None = None,
    resource_profiles_dir: str | Path | None = None,
) -> ResourceSpec:
    """Resolve resources using the C06 sentinel-based policy.

    Same layered precedence as ``resolve_resources()`` but uses
    ``apply_resource_policy()`` internally so that an explicit override
    that equals the default (e.g. ``cpu=1``) still wins.

    .. deprecated:: 2026-07
        Prefer building an ``ExecutionPolicy`` and using
        ``apply_resource_policy()`` directly.  This function exists as a
        drop-in migration bridge.
    """
    # Layer 1: hardcoded defaults
    base = ResourceSpec()

    # Layer 2: tool contract → catalog override
    tool_resources = tool_metadata.get("resources", {}) or {}
    catalog = (
        ResourceOverride.from_mapping(tool_resources)
        if isinstance(tool_resources, Mapping)
        else ResourceOverride()
    )

    # Layer 3: resource profile → workflow override
    workflow_data: dict[str, Any] = {}
    if resource_profile:
        profile_data = _load_resource_profile(resource_profile, resource_profiles_dir)
        if profile_data:
            workflow_data.update(profile_data)

    # Layers 4-5: user config overrides → also workflow
    if config:
        exec_cfg = config.get("execution", {})
        if isinstance(exec_cfg, Mapping):
            resources_cfg = exec_cfg.get("resources", {})
            if isinstance(resources_cfg, Mapping):
                defaults = resources_cfg.get("defaults")
                if isinstance(defaults, Mapping):
                    workflow_data.update(defaults)
                overrides = resources_cfg.get("tool_overrides", {})
                if isinstance(overrides, Mapping):
                    tool_override = overrides.get(tool_id)
                    if isinstance(tool_override, Mapping):
                        workflow_data.update(tool_override)

    workflow = ResourceOverride.from_mapping(workflow_data) if workflow_data else ResourceOverride()

    # Layer 6: CLI overrides → invocation override
    invocation = ResourceOverride()
    if isinstance(cli_overrides, ResourceOverride):
        invocation = cli_overrides
    elif cli_overrides:
        invocation = ResourceOverride(
            cpu=cli_overrides.cpu,
            memory=cli_overrides.memory,
            walltime=cli_overrides.walltime,
            accelerator=cli_overrides.accelerator,
            disk=cli_overrides.disk,
        )

    return apply_resource_policy(
        base=base,
        catalog=catalog,
        workflow=workflow,
        invocation=invocation,
    )


def _load_resource_profile(
    name: str,
    profiles_dir: str | Path | None = None,
) -> Mapping[str, Any] | None:
    """Load a named resource profile YAML file."""
    from abi.config import PROJECT_ROOT, load_yaml

    candidates = []
    if profiles_dir:
        candidates.append(Path(profiles_dir) / f"{name}.yaml")
    candidates.append(PROJECT_ROOT / "config" / "resource_profiles" / f"{name}.yaml")
    for candidate in candidates:
        if candidate.exists():
            return load_yaml(str(candidate))
    return None


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
