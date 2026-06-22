"""Build deterministic, shell-safe ViWrap command lines."""

from __future__ import annotations

import shlex
from typing import Any, Mapping

from .errors import ViWrapConfigError

IDENTIFY_METHODS = frozenset({"genomad", "vb", "vs", "dvf", "vb-vs", "vb-vs-dvf"})
READ_TYPES = frozenset({"illumina", "pacbio", "pacbio_hifi", "pacbio_asm20", "nanopore"})


def validate_run_config(config: Mapping[str, Any]) -> None:
    """Validate the mutually exclusive inputs and bounded options."""
    required = ("input_metagenome", "out_dir", "db_dir", "conda_env_dir")
    missing = [key for key in required if not config.get(key)]
    if missing:
        raise ViWrapConfigError(f"Missing required ViWrap settings: {', '.join(missing)}")

    reads = config.get("input_reads")
    coverage = config.get("input_cov")
    sample_info = config.get("input_sample2read_info")
    if reads and coverage:
        raise ViWrapConfigError("input_reads and input_cov are mutually exclusive")
    if not reads and not (coverage and sample_info):
        raise ViWrapConfigError("Provide input_reads, or both input_cov and input_sample2read_info")
    method = str(config.get("identify_method", "genomad"))
    if method not in IDENTIFY_METHODS:
        raise ViWrapConfigError(f"Unsupported identify_method: {method}")
    read_type = str(config.get("reads_type", "illumina"))
    if read_type not in READ_TYPES:
        raise ViWrapConfigError(f"Unsupported reads_type: {read_type}")
    if int(config.get("threads", 20)) < 1:
        raise ViWrapConfigError("threads must be at least 1")
    if int(config.get("input_length_limit", 5000)) < 2000:
        raise ViWrapConfigError("input_length_limit must be at least 2000")


def build_viwrap_command(config: Mapping[str, Any]) -> list[str]:
    """Return an argv list; no shell interpolation is used."""
    validate_run_config(config)
    command = [
        str(config.get("executable", "ViWrap")),
        "run",
        "--input_metagenome",
        str(config["input_metagenome"]),
        "--out_dir",
        str(config["out_dir"]),
        "--db_dir",
        str(config["db_dir"]),
        "--identify_method",
        str(config.get("identify_method", "genomad")),
        "--conda_env_dir",
        str(config["conda_env_dir"]),
        "--threads",
        str(config.get("threads", 20)),
        "--input_length_limit",
        str(config.get("input_length_limit", 5000)),
    ]
    reads = config.get("input_reads")
    if reads:
        if isinstance(reads, (str, bytes)):
            reads = [reads]
        command.extend(["--input_reads", ",".join(str(path) for path in reads)])
        command.extend(["--input_reads_type", str(config.get("reads_type", "illumina"))])
    else:
        command.extend(["--input_cov", str(config["input_cov"])])
        command.extend(["--input_sample2read_info", str(config["input_sample2read_info"])])

    for flag in ("custom_MAGs_dir", "iPHoP_db_custom", "iPHoP_db_custom_pre"):
        if config.get(flag):
            command.extend([f"--{flag}", str(config[flag])])
    if config.get("virome"):
        command.append("--virome")
    return command


def render_command(command: list[str]) -> str:
    """Render argv for logs without changing its execution semantics."""
    return shlex.join(command)
