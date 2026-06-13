"""Runtime protocol and shared runtime options."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Mapping, Protocol


@dataclass
class RuntimeOptions:
    engine: str = "local"
    smoke: bool = False
    nextflow_bin: Path | None = None
    work_dir: Path | None = None
    workflow: Path | None = None
    nxf_home: Path | None = None
    mamba_root: Path | None = None
    profile: str | None = None
    executor: str | None = None
    resume: bool = False
    timeout_seconds: float | None = None


@dataclass
class RuntimeResult:
    status: str
    return_code: int | str
    outputs: Dict[str, Path] = field(default_factory=dict)


class ABIRuntime(Protocol):
    def check(self) -> None: ...

    def dry_run(self, plan: object, config: Mapping[str, object]) -> RuntimeResult: ...

    def run(self, plan: object, config: Mapping[str, object]) -> RuntimeResult: ...
