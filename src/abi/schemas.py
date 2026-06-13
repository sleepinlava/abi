"""Canonical runtime schemas for ABI plugins.

These types are shared across all ABI plugins and the ABI Core.
The ABI-prefixed names (ABIExecutionPlan, ABIPlanStep, ABISample,
ABISampleContext) are stable public aliases for the canonical types.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from abi.errors import ABIError, ConfigError, SampleSheetError, ToolError

__all__ = [
    "ABIError",
    "ABIExecutionPlan",
    "ABIPlanStep",
    "ABISample",
    "ABISampleContext",
    "ConfigError",
    "ExecutionPlan",
    "PlanStep",
    "SampleContext",
    "SampleInput",
    "SampleSheetError",
    "ToolError",
    "VALID_MODES",
    "VALID_PLATFORMS",
    "VALID_PLASMID_STRATEGIES",
]

VALID_PLATFORMS = {"illumina", "ont", "pacbio_hifi", "hybrid", "assembly"}
VALID_MODES = {"auto", "interactive"}
VALID_PLASMID_STRATEGIES = {
    "single_tool",
    "union",
    "intersection",
    "majority_vote",
    "weighted_vote",
}


@dataclass
class SampleInput:
    """Canonical sample descriptor (unified superset of autoplasm and ABI fields)."""

    sample_id: str
    platform: str = "generic"
    group: Optional[str] = None
    read1: Optional[str] = None
    read2: Optional[str] = None
    long_reads: Optional[str] = None
    assembly: Optional[str] = None
    technology: Optional[str] = None
    host_reference: Optional[str] = None
    condition: Optional[str] = None
    notes: Optional[str] = None
    attributes: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @property
    def has_short_reads(self) -> bool:
        return bool(self.read1 or self.read2)

    @property
    def has_long_reads(self) -> bool:
        return bool(self.long_reads)

    @property
    def has_assembly(self) -> bool:
        return bool(self.assembly)


@dataclass
class SampleContext:
    samples: List[SampleInput]
    multi_sample: bool
    has_groups: bool
    enable_sample_analysis: bool = False
    enable_differential_abundance: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "samples": [sample.to_dict() for sample in self.samples],
            "multi_sample": self.multi_sample,
            "has_groups": self.has_groups,
            "enable_sample_analysis": self.enable_sample_analysis,
            "enable_differential_abundance": self.enable_differential_abundance,
        }


@dataclass
class PlanStep:
    step_id: str
    sample_id: Optional[str]
    step_name: str
    tool_id: str
    category: str
    inputs: Dict[str, Any] = field(default_factory=dict)
    outputs: Dict[str, Any] = field(default_factory=dict)
    params: Dict[str, Any] = field(default_factory=dict)
    reason: Optional[str] = None
    skipped: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ExecutionPlan:
    project_name: str
    mode: str
    threads: int
    outdir: str
    log_dir: str
    samples: List[SampleInput]
    steps: List[PlanStep]
    sample_context: SampleContext
    selected_tools: List[str]
    analysis_type: str = "metagenomic_plasmid"
    skipped_steps: List[PlanStep] = field(default_factory=list)
    provenance_dir: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "project_name": self.project_name,
            "analysis_type": self.analysis_type,
            "mode": self.mode,
            "threads": self.threads,
            "outdir": self.outdir,
            "log_dir": self.log_dir,
            "samples": [sample.to_dict() for sample in self.samples],
            "sample_context": self.sample_context.to_dict(),
            "selected_tools": self.selected_tools,
            "steps": [step.to_dict() for step in self.steps],
            "skipped_steps": [step.to_dict() for step in self.skipped_steps],
            "provenance_dir": self.provenance_dir,
        }


# ── Stable ABI-prefixed aliases ────────────────────────────────────────

ABISample = SampleInput
ABISampleContext = SampleContext
ABIPlanStep = PlanStep
ABIExecutionPlan = ExecutionPlan


# ── Utility ─────────────────────────────────────────────────────────────


def ensure_parent(path: str | Path) -> Path:
    resolved = Path(path)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    return resolved
