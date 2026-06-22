"""Managed ViWrap execution with mandatory preflight and provenance logs."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any, Mapping

from .artifact_mapper import collect_artifacts
from .checker import check_environment
from .command_builder import build_viwrap_command, render_command
from .errors import ViWrapEnvironmentError, ViWrapExecutionError
from .parser import parse_viwrap_outputs


def run_viwrap(config: Mapping[str, Any]) -> dict[str, Any]:
    """Dry-run or execute ViWrap without a shell."""
    command = build_viwrap_command(config)
    report = check_environment(config, check_runtime=not bool(config.get("skip_runtime_check")))
    result: dict[str, Any] = {
        "plugin": "viral_viwrap",
        "command": command,
        "command_text": render_command(command),
        "env_report": report,
    }
    if config.get("dry_run"):
        result.update(
            {"mode": "dry_run", "status": "blocked" if report["status"] == "fail" else "ready"}
        )
        return result
    if report["status"] == "fail":
        raise ViWrapEnvironmentError("ViWrap preflight failed; inspect env_report")

    out_dir = Path(str(config["out_dir"]))
    log_dir = Path(str(config.get("log_dir") or out_dir.parent / f"{out_dir.name}.abi_logs"))
    log_dir.mkdir(parents=True, exist_ok=True)
    stdout_path = log_dir / "viwrap.stdout.log"
    stderr_path = log_dir / "viwrap.stderr.log"
    (log_dir / "viwrap.command.txt").write_text(result["command_text"] + "\n", encoding="utf-8")
    (log_dir / "viwrap.env_report.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    with (
        stdout_path.open("w", encoding="utf-8") as stdout,
        stderr_path.open("w", encoding="utf-8") as stderr,
    ):
        completed = subprocess.run(command, stdout=stdout, stderr=stderr, check=False)
    result.update(
        {
            "mode": "run",
            "status": "success" if completed.returncode == 0 else "failed",
            "returncode": completed.returncode,
            "out_dir": str(out_dir),
            "logs": {"stdout": str(stdout_path), "stderr": str(stderr_path)},
        }
    )
    if completed.returncode:
        raise ViWrapExecutionError(f"ViWrap exited with {completed.returncode}; see {stderr_path}")
    parsed = parse_viwrap_outputs(out_dir)
    artifact_manifest = log_dir / "artifact_manifest.json"
    artifacts = collect_artifacts(out_dir, artifact_manifest)
    result.update(
        {
            "tables": parsed["tables"],
            "artifacts": {
                "viral_genomes": artifacts["groups"]["primary_sequences"],
                "figures": artifacts["groups"]["primary_figures"],
                "amg_outputs": parsed["artifacts"]["amg_outputs"],
            },
            "logs": {
                "stdout": str(stdout_path),
                "stderr": str(stderr_path),
                "command": str(log_dir / "viwrap.command.txt"),
                "env_report": str(log_dir / "viwrap.env_report.json"),
                "artifact_manifest": str(artifact_manifest),
            },
            "warnings": parsed["warnings"],
        }
    )
    return result
