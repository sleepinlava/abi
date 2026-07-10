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
    # Resource overrides (shared across all engines) / 资源覆盖（所有引擎共享）
    resource_profile: str | None = None
    cpu_override: int | None = None
    memory_override: str | None = None
    walltime_override: str | None = None
    accelerator_override: str | None = None
    disk_override: str | None = None
    # Container overrides (shared across all engines) / 容器覆盖（所有引擎共享）
    container_image: str | None = None
    container_runtime: str | None = None
    # HPC scheduler options / HPC 调度器选项
    scheduler: str | None = None
    partition: str | None = None
    account: str | None = None
    qos: str | None = None
    job_name: str | None = None
    array_size: int | None = None
    mail_type: str | None = None
    mail_user: str | None = None
    hpc_strategy: str | None = None
    poll_interval_seconds: float = 30.0


@dataclass
class RuntimeResult:
    status: str
    return_code: int | str
    outputs: Dict[str, Path] = field(default_factory=dict)


class ABIRuntime(Protocol):
    def check(self) -> None: ...

    def dry_run(self, plan: object, config: Mapping[str, object]) -> RuntimeResult: ...

    def run(self, plan: object, config: Mapping[str, object]) -> RuntimeResult: ...
