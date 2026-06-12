"""Public ABI error hierarchy."""

from __future__ import annotations

__all__ = [
    "ABIError",
    "ConfigError",
    "SampleSheetError",
    "ToolError",
]


class ABIError(RuntimeError):
    """Base class for ABI user-facing errors."""


class ConfigError(ABIError):
    """Raised when ABI configuration or registry metadata is invalid."""


class SampleSheetError(ABIError):
    """Raised when sample metadata cannot be parsed or validated."""


class ToolError(ABIError):
    """Raised when a registered tool cannot be planned or executed."""
