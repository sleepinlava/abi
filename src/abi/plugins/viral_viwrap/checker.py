"""Strict, side-effect-free ViWrap preflight checks."""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Mapping

from .command_builder import validate_run_config
from .errors import ViWrapConfigError

REQUIRED_DB_DIRS = (
    "VIBRANT_db",
    "CheckV_db",
    "DVF_db",
    "Tax_classification_db",
    "iPHoP_db",
    "VirSorter2_db",
    "GTDB_db",
    "genomad_db",
)
REQUIRED_CONDA_ENVS = (
    "ViWrap",
    "ViWrap-VIBRANT",
    "ViWrap-geNomad",
    "ViWrap-vRhyme",
    "ViWrap-vContact2",
    "ViWrap-CheckV",
    "ViWrap-dRep",
    "ViWrap-Tax",
    "ViWrap-iPHoP",
    "ViWrap-GTDBTk",
    "ViWrap-vs2",
    "ViWrap-Mapping",
    "ViWrap-DVF",
)


@dataclass(frozen=True)
class CheckResult:
    name: str
    status: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)


def _path_check(path: Any, name: str, *, directory: bool = False) -> CheckResult:
    target = Path(str(path))
    valid_type = target.is_dir() if directory else target.is_file()
    if not valid_type or (not directory and target.stat().st_size == 0):
        kind = "directory" if directory else "non-empty file"
        return CheckResult(name, "fail", f"Expected {kind}: {target}", {"path": str(target)})
    return CheckResult(name, "pass", f"Found {target}", {"path": str(target)})


def check_executables(executable: str = "ViWrap") -> CheckResult:
    required = ["conda", "wget", "tar", "gzip", executable]
    missing = [item for item in required if shutil.which(item) is None]
    if missing:
        return CheckResult(
            "executables", "fail", "Required executables are missing", {"missing": missing}
        )
    try:
        result = subprocess.run(
            [executable, "-h"], capture_output=True, text=True, timeout=30, check=False
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return CheckResult("executables", "fail", "ViWrap help check failed", {"error": str(exc)})
    if result.returncode != 0:
        output = ((result.stdout or "") + (result.stderr or ""))[:2000]
        return CheckResult(
            "executables", "fail", "`ViWrap -h` returned non-zero", {"output": output}
        )
    return CheckResult("executables", "pass", "Required executables are runnable")


def check_conda_envs(root: str | Path) -> CheckResult:
    path = Path(root)
    missing = [name for name in REQUIRED_CONDA_ENVS if not (path / name).is_dir()]
    status = "fail" if missing else "pass"
    return CheckResult(
        "conda_envs",
        status,
        "ViWrap environment set is incomplete" if missing else "ViWrap environments are present",
        {"root": str(path), "expected": len(REQUIRED_CONDA_ENVS), "missing": missing},
    )


def check_databases(root: str | Path) -> CheckResult:
    path = Path(root)
    missing: list[str] = []
    empty: list[str] = []
    for name in REQUIRED_DB_DIRS:
        candidate = path / name
        if not candidate.is_dir():
            missing.append(name)
        elif not any(candidate.iterdir()):
            empty.append(name)
    status = "fail" if missing or empty else "pass"
    return CheckResult(
        "databases",
        status,
        "ViWrap database set is incomplete" if status == "fail" else "ViWrap databases are present",
        {"root": str(path), "missing": missing, "empty": empty},
    )


def check_inputs(config: Mapping[str, Any]) -> list[CheckResult]:
    results = [_path_check(config["input_metagenome"], "input_metagenome")]
    fasta = Path(str(config["input_metagenome"]))
    if fasta.is_file() and fasta.stat().st_size:
        bad_headers: list[str] = []
        with fasta.open("r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                if line.startswith(">") and "__" in line:
                    bad_headers.append(line.rstrip()[:200])
                    if len(bad_headers) == 5:
                        break
        if bad_headers:
            results.append(
                CheckResult(
                    "fasta_headers",
                    "warn",
                    "FASTA headers contain '__', which ViWrap uses internally",
                    {"examples": bad_headers},
                )
            )
    reads = config.get("input_reads") or []
    if isinstance(reads, (str, bytes)):
        reads = [reads]
    for index, read in enumerate(reads):
        results.append(_path_check(read, f"input_reads[{index}]"))
    if reads and config.get("reads_type", "illumina") == "illumina" and len(reads) % 2:
        results.append(CheckResult("paired_reads", "fail", "Illumina read files must be paired"))
    if config.get("input_cov"):
        results.append(_path_check(config["input_cov"], "input_cov"))
        results.append(_path_check(config["input_sample2read_info"], "input_sample2read_info"))
    return results


def _check_output(config: Mapping[str, Any]) -> CheckResult:
    out_dir = Path(str(config["out_dir"]))
    if out_dir.exists():
        return CheckResult(
            "out_dir", "fail", "ViWrap requires out_dir not to exist", {"path": str(out_dir)}
        )
    parent = out_dir.parent
    if not parent.exists() or not os.access(parent, os.W_OK):
        return CheckResult(
            "out_dir", "fail", "Output parent is missing or not writable", {"path": str(parent)}
        )
    free_gb = shutil.disk_usage(parent).free / (1024**3)
    status = "warn" if free_gb < 100 else "pass"
    return CheckResult(
        "out_dir",
        status,
        "Low work disk space" if status == "warn" else "Output path is writable",
        {"free_gb": round(free_gb, 2)},
    )


def check_environment(config: Mapping[str, Any], *, check_runtime: bool = True) -> dict[str, Any]:
    """Return a schema-friendly report and never modify the configured paths."""
    try:
        validate_run_config(config)
    except (ViWrapConfigError, TypeError, ValueError) as exc:
        result = CheckResult("configuration", "fail", str(exc))
        return _report([result])

    results = [
        CheckResult(
            "system",
            "pass" if platform.system() == "Linux" else "fail",
            f"Detected {platform.system()}",
        )
    ]
    if check_runtime:
        results.append(check_executables(str(config.get("executable", "ViWrap"))))
    results.extend(
        [
            check_conda_envs(str(config["conda_env_dir"])),
            check_databases(str(config["db_dir"])),
            *check_inputs(config),
            _check_output(config),
        ]
    )
    cpu_count = os.cpu_count() or 1
    threads = int(config.get("threads", 20))
    if threads > cpu_count:
        results.append(
            CheckResult(
                "threads",
                "warn",
                "Requested threads exceed detected CPUs",
                {"requested": threads, "available": cpu_count},
            )
        )
    return _report(results)


def _report(results: list[CheckResult]) -> dict[str, Any]:
    failures = [item for item in results if item.status == "fail"]
    warnings = [item for item in results if item.status == "warn"]
    status = "fail" if failures else "warn" if warnings else "pass"
    return {
        "plugin": "viral_viwrap",
        "status": status,
        "summary": {
            "ready": not failures,
            "can_run": not failures,
            "requires_setup": bool(failures),
        },
        "checks": [asdict(item) for item in results],
        "recommendations": [item.message for item in failures + warnings],
    }
