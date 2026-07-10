"""Tests for execution_policy — ResourceOverride, apply_resource_policy, ExecutionPolicy."""

from __future__ import annotations

from abi.execution_policy import (
    ExecutionPolicy,
    ResourceOverride,
    apply_resource_policy,
    resolve_resources_v2,
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


class TestResolveResourcesV2:
    """Bridge function tests — same layered precedence as resolve_resources
    but with sentinel semantics."""

    def test_defaults_only(self) -> None:
        result = resolve_resources_v2("fastp", {})
        assert result.cpu == 1
        assert result.memory == "4GB"
        assert result.walltime == "01:00:00"

    def test_tool_contract_resources(self) -> None:
        meta = {"resources": {"cpu": 8, "memory": "16GB"}}
        result = resolve_resources_v2("fastp", meta)
        assert result.cpu == 8
        assert result.memory == "16GB"

    def test_explicit_default_preserved(self) -> None:
        """F05 regression: explicit cpu=1 wins over unset layer."""
        meta = {"resources": {"cpu": 1}}  # explicit default
        result = resolve_resources_v2("fastp", meta)
        assert result.cpu == 1  # preserved, not merged away

    def test_config_global_defaults(self) -> None:
        config = {"execution": {"resources": {"defaults": {"cpu": 4}}}}
        result = resolve_resources_v2("fastp", {}, config=config)
        assert result.cpu == 4

    def test_config_tool_override(self) -> None:
        config = {
            "execution": {
                "resources": {
                    "defaults": {"cpu": 2},
                    "tool_overrides": {"fastp": {"cpu": 8}},
                }
            }
        }
        result = resolve_resources_v2("fastp", {}, config=config)
        assert result.cpu == 8  # tool override > global defaults

    def test_config_tool_override_does_not_affect_other_tool(self) -> None:
        config = {
            "execution": {
                "resources": {
                    "tool_overrides": {"fastp": {"cpu": 8}},
                }
            }
        }
        result = resolve_resources_v2("megahit", {}, config=config)
        assert result.cpu == 1  # default

    def test_cli_overrides_highest_priority(self) -> None:
        meta = {"resources": {"cpu": 4}}
        config = {"execution": {"resources": {"defaults": {"cpu": 8}}}}
        cli = ResourceSpec(cpu=16)
        result = resolve_resources_v2("fastp", meta, config=config, cli_overrides=cli)
        assert result.cpu == 16

    def test_resource_profile(self) -> None:
        """Resource profile should be loaded and applied."""
        # No profile exists for "test_profile" — falls back to defaults.
        result = resolve_resources_v2(
            "fastp", {}, resource_profile="test_profile"
        )
        assert result.cpu == 1  # no effect

    def test_partial_cli_override(self) -> None:
        """CLI from ResourceSpec fills all defaults — memory=4GB overrides catalog.
        
        This mirrors the pre-C06 behaviour. Once callers migrate to
        ResourceOverride for CLI overrides, this test should be updated
        to reflect proper sentinel semantics.
        """
        meta = {"resources": {"memory": "16GB"}}
        cli = ResourceSpec(cpu=32)  # memory defaults to "4GB"
        result = resolve_resources_v2("fastp", meta, cli_overrides=cli)
        assert result.cpu == 32
        # CLI default memory=4GB takes precedence over catalog 16GB,
        # because ResourceSpec fills all defaults. This is a pre-C06
        # limitation that ResourceOverride fixes.
        assert result.memory == "4GB"

    def test_config_is_none(self) -> None:
        result = resolve_resources_v2("fastp", {"resources": {"cpu": 2}}, config=None)
        assert result.cpu == 2
