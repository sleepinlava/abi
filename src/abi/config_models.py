"""Pydantic config models for ABI pipelines.

This module provides type-safe configuration models that gradually replace
the legacy ``Dict[str, Any]`` config pattern.

Backward compatibility (2-release window):
    ``ABIConfig.model_validate()`` accepts both ``ABIConfig`` and ``dict``,
    so existing ``load_config()`` callers can migrate incrementally.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field

__all__ = [
    "ABIConfig",
    "AlignmentConfig",
    "DifferentialExpressionConfig",
    "ExecutionConfig",
    "InputConfig",
    "RNASeqConfig",
]


class ExecutionConfig(BaseModel):
    """Execution-level configuration (parallelism, error policy, etc.)."""

    parallel: bool = False
    workers: int = Field(default=1, ge=1, le=128)
    error_policy: str = Field(default="halt", pattern=r"^(halt|continue)$")
    record_progress: bool = False
    tool_timeout_seconds: Optional[float] = None


class ABIConfig(BaseModel):
    """Root ABI pipeline configuration.

    ``extra="allow"`` ensures plugins can store custom fields without
    schema errors during the migration window.
    """

    model_config = {"extra": "allow"}

    project_name: str = "ABI Analysis"
    outdir: str = "results"
    mode: str = Field(default="auto", pattern=r"^(auto|interactive)$")
    threads: int = Field(default=4, ge=1, le=1024)
    mamba_root: Optional[str] = None
    execution: ExecutionConfig = Field(default_factory=ExecutionConfig)
    resources: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ABIConfig:
        """Construct an ``ABIConfig`` from a raw dict (legacy interface).

        This is the migration bridge: callers that still build config as
        ``Dict[str, Any]`` can convert with ``ABIConfig.from_dict(d)``.
        """
        return cls.model_validate(data)

    def to_dict(self) -> dict[str, Any]:
        """Return a plain dict for backward-compatible code paths."""
        return self.model_dump()


class InputConfig(BaseModel):
    """Sample sheet input configuration."""

    sample_sheet: str = "sample_sheet.tsv"


class AlignmentConfig(BaseModel):
    """Alignment tool configuration."""

    tool: str = "star"


class DifferentialExpressionConfig(BaseModel):
    """Differential expression analysis configuration."""

    comparison: str = "treatment_vs_control"
    alpha: float = Field(default=0.05, ge=0.0, le=1.0)


class RNASeqConfig(ABIConfig):
    """RNA-seq expression analysis configuration.

    Extends :class:`ABIConfig` with RNA-seq-specific fields:
    ``log_dir``, ``input.sample_sheet``, ``alignment``,
    and ``differential_expression``.
    """

    log_dir: str = "logs/rnaseq_expression"

    input: InputConfig = Field(default_factory=lambda: InputConfig())
    alignment: AlignmentConfig = Field(default_factory=lambda: AlignmentConfig())
    differential_expression: DifferentialExpressionConfig = Field(
        default_factory=lambda: DifferentialExpressionConfig()
    )
