"""Error hierarchy for ABI runtime.

Copied from autoplasm.schemas — only the error classes are kept here.
"""

from __future__ import annotations


class AutoPlasmError(RuntimeError):
    """Base class for clear user-facing errors."""


class ConfigError(AutoPlasmError):
    """Raised when configuration is invalid."""


class SampleSheetError(AutoPlasmError):
    """Raised when sample sheet validation fails."""


class ToolError(AutoPlasmError):
    """Raised when a tool wrapper cannot build or run a command."""
