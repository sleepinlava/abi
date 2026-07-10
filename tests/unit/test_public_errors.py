"""Tests for the public ABI error export surface."""

from __future__ import annotations

import abi.errors as errors


def test_all_public_error_types_are_exported() -> None:
    expected = {
        "ABIError",
        "ArtifactIntegrityError",
        "ConfigError",
        "InputPolicyError",
        "MissingTemplateParamError",
        "PackagingError",
        "PlanIntegrityError",
        "ResourcePolicyError",
        "SampleSheetError",
        "ToolError",
        "ToolResolutionError",
        "UnsupportedExecutionError",
    }

    assert set(errors.__all__) == expected
    assert all(
        issubclass(getattr(errors, name), errors.ABIError) for name in expected - {"ABIError"}
    )
