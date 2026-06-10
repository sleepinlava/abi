"""Generic runtime schemas for ABI plugins."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


class ABIError(RuntimeError):
    """Base class for ABI user-facing errors."""


@dataclass
class ABISample:
    sample_id: str
    platform: str = "generic"
    group: Optional[str] = None
    read1: Optional[str] = None
    read2: Optional[str] = None
    long_reads: Optional[str] = None
    assembly: Optional[str] = None
    condition: Optional[str] = None
    attributes: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ABISampleContext:
    samples: List[ABISample]
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
class ABIPlanStep:
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
class ABIExecutionPlan:
    project_name: str
    analysis_type: str
    mode: str
    threads: int
    outdir: str
    log_dir: str
    samples: List[ABISample]
    steps: List[ABIPlanStep]
    sample_context: ABISampleContext
    selected_tools: List[str]
    skipped_steps: List[ABIPlanStep] = field(default_factory=list)
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
