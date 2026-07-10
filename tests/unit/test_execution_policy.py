"""Tests for execution_policy — ResourceOverride, apply_resource_policy, ExecutionPolicy."""

from __future__ import annotations

from abi.execution_policy import (
    ExecutionPolicy,
    ResourceOverride,
    apply_resource_policy,
)
from abi.tools import ResourceSpec


class TestResourceOverride:
    def test_empty_override_is_empty(self) -> None:
        assert ResourceOverride().is_empty()

    def test_partial_override_is_not_empty(self) -> None:
        assert not ResourceOverride(cpu=4).is_empty()
        assert not ResourceOverride(memory="16GB").is_empty()

    def test_from_mapping_none_keys_become_none(self) -> None:
        ov = ResourceOverride.from_mapping({"cpu": None, "memory": "8GB"})
        assert ov.cpu is None
        assert ov.memory == "8GB"

    def test_from_mapping_missing_keys_become_none(self) -> None:
        ov = ResourceOverride.from_mapping({"cpu": 2})
        assert ov.memory is None
        assert ov.walltime is None

    def test_from_mapping_empty_dict_is_empty_override(self) -> None:
        assert ResourceOverride.from_mapping({}).is_empty()

    def test_explicit_default_is_still_set(self) -> None:
        """Explicit cpu=1 (same as ResourceSpec default) must be preserved."""
        ov = ResourceOverride.from_mapping({"cpu": 1})
        assert ov.cpu == 1  # set, even though it equals the default


class TestApplyResourcePolicy:
    def test_no_overrides_returns_base(self) -> None:
        base = ResourceSpec(cpu=8, memory="32GB", walltime="12:00:00")
        result = apply_resource_policy(base=base)
        assert result.cpu == 8
        assert result.memory == "32GB"
        assert result.walltime == "12:00:00"

    def test_single_layer_override(self) -> None:
        base = ResourceSpec(cpu=1, memory="4GB")
        result = apply_resource_policy(
            base=base, invocation=ResourceOverride(cpu=16)
        )
        assert result.cpu == 16
        assert result.memory == "4GB"  # unchanged

    def test_precedence_invocation_wins(self) -> None:
        base = ResourceSpec(cpu=1, memory="4GB")
        result = apply_resource_policy(
            base=base,
            catalog=ResourceOverride(cpu=4, memory="8GB"),
            workflow=ResourceOverride(cpu=8),
            invocation=ResourceOverride(cpu=32),
        )
        assert result.cpu == 32  # invocation wins
        assert result.memory == "8GB"  # catalog override carries through

    def test_explicit_default_overrides_catalog_default(self) -> None:
        """Invocation explicitly sets cpu=1 (the default) — it must win over
        a catalog recommendation of cpu=8."""
        base = ResourceSpec(cpu=1, memory="4GB")
        result = apply_resource_policy(
            base=base,
            catalog=ResourceOverride(cpu=8, memory="16GB"),
            invocation=ResourceOverride(cpu=1),  # explicit default!
        )
        assert result.cpu == 1  # explicit default wins
        assert result.memory == "16GB"  # catalog still applies for memory

    def test_empty_layers_are_skipped(self) -> None:
        base = ResourceSpec(cpu=4, memory="8GB")
        result = apply_resource_policy(
            base=base,
            catalog=ResourceOverride(),   # empty
            workflow=ResourceOverride(),  # empty
            invocation=ResourceOverride(cpu=64),
        )
        assert result.cpu == 64
        assert result.memory == "8GB"

    def test_all_layers_applied(self) -> None:
        base = ResourceSpec(cpu=1, memory="4GB", walltime="01:00:00")
        result = apply_resource_policy(
            base=base,
            catalog=ResourceOverride(cpu=4),
            workflow=ResourceOverride(memory="16GB"),
            invocation=ResourceOverride(walltime="24:00:00", accelerator="gpu:1"),
        )
        assert result.cpu == 4
        assert result.memory == "16GB"
        assert result.walltime == "24:00:00"
        assert result.accelerator == "gpu:1"
        assert result.disk is None  # never set


class TestExecutionPolicy:
    def test_default_policy(self) -> None:
        ep = ExecutionPolicy()
        assert ep.mode == "auto"
        assert ep.mamba_root is None
        assert ep.container_image is None
        assert ep.invocation_overrides is None

    def test_policy_with_overrides(self) -> None:
        ep = ExecutionPolicy(
            mode="conda",
            invocation_overrides=ResourceOverride(cpu=16, memory="64GB"),
        )
        assert ep.mode == "conda"
        assert ep.invocation_overrides is not None
        assert ep.invocation_overrides.cpu == 16
