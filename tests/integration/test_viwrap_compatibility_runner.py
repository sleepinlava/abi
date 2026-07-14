from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from abi.plugins.viral_viwrap import run_viwrap
from abi.plugins.viral_viwrap.checker import REQUIRED_CONDA_ENVS, REQUIRED_DB_DIRS
from abi.plugins.viral_viwrap.errors import (
    ViWrapEnvironmentError,
    ViWrapExecutionError,
    ViWrapParseError,
)


def _compat_config(
    tmp_path: Path,
    *,
    return_code: int = 0,
    write_summary: bool = True,
) -> dict[str, object]:
    assembly = tmp_path / "assembly.fa"
    read1 = tmp_path / "R1.fastq.gz"
    read2 = tmp_path / "R2.fastq.gz"
    assembly.write_text(">contig_1\nACGT\n", encoding="utf-8")
    read1.write_bytes(b"reads")
    read2.write_bytes(b"reads")

    envs = tmp_path / "envs"
    for name in REQUIRED_CONDA_ENVS:
        (envs / name).mkdir(parents=True)
    executable = envs / "ViWrap/bin/ViWrap"
    executable.parent.mkdir(parents=True, exist_ok=True)
    executable.write_text(
        f"""#!/usr/bin/env python3
import pathlib
import sys
args = sys.argv[1:]
if '-h' in args:
    raise SystemExit(0)
if {return_code}:
    raise SystemExit({return_code})
root = pathlib.Path(args[args.index('--out_dir') + 1])
root.mkdir(parents=True)
if {write_summary!r}:
    out = root / '08_ViWrap_summary_outdir'
    out.mkdir()
    (out / 'Virus_summary_info.txt').write_text('virus_id\\tlength\\nvirus_1\\t5000\\n')
""",
        encoding="utf-8",
    )
    executable.chmod(0o755)

    databases = tmp_path / "db"
    for name in REQUIRED_DB_DIRS:
        path = databases / name
        path.mkdir(parents=True)
        (path / "ready").write_text("ok\n", encoding="utf-8")

    out_dir = tmp_path / "viwrap-output"
    return {
        "input_metagenome": str(assembly),
        "input_reads": [str(read1), str(read2)],
        "out_dir": str(out_dir),
        "log_dir": str(tmp_path / "viwrap-output.abi_logs"),
        "db_dir": str(databases),
        "conda_env_dir": str(envs),
        "executable": str(executable),
        "identify_method": "genomad",
        "reads_type": "illumina",
        "threads": 1,
        "skip_runtime_check": True,
    }


def test_compat_runner_preserves_legacy_result_and_writes_standard_abi_bundle(tmp_path):
    config = _compat_config(tmp_path)

    result = run_viwrap(config)

    assert (result["plugin"], result["mode"], result["status"]) == (
        "viral_viwrap",
        "run",
        "success",
    )
    assert Path(result["tables"]["virus_summary"]).is_file()
    assert Path(result["out_dir"]) == Path(str(config["out_dir"]))

    abi_result_dir = Path(result["abi_result_dir"])
    abi_outputs = {name: Path(path) for name, path in result["abi_outputs"].items()}
    summary = json.loads(abi_outputs["summary"].read_text(encoding="utf-8"))
    plan = json.loads(abi_outputs["plan"].read_text(encoding="utf-8"))
    with abi_outputs["commands"].open(encoding="utf-8", newline="") as handle:
        commands = list(csv.DictReader(handle, delimiter="\t"))

    assert abi_result_dir == Path(str(config["log_dir"]))
    assert summary["analysis_type"] == "viral_viwrap"
    assert summary["status"] == "success"
    assert plan["managed_output_roots"] == [str(config["out_dir"])]
    assert {row["step_name"] for row in commands} >= {
        "input_validation",
        "viral_analysis",
        "report",
    }
    assert "virus_1" in (abi_result_dir / "tables/virus_summary.tsv").read_text(encoding="utf-8")
    with (abi_result_dir / "tables/virus_summary.tsv").open(encoding="utf-8", newline="") as handle:
        virus_rows = list(csv.DictReader(handle, delimiter="\t"))
    assert [(row["sample_id"], row["virus_id"], row["length"]) for row in virus_rows] == [
        ("viral_sample", "virus_1", "5000")
    ]


def test_compat_runner_dry_run_writes_abi_provenance_without_raw_output(tmp_path):
    config = _compat_config(tmp_path)
    config["dry_run"] = True

    result = run_viwrap(config)

    summary_path = Path(result["abi_outputs"]["summary"])
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert (result["mode"], result["status"], summary["dry_run"]) == (
        "dry_run",
        "ready",
        True,
    )
    assert not Path(str(config["out_dir"])).exists()


def test_compat_runner_stops_on_failed_preflight(tmp_path):
    config = _compat_config(tmp_path)
    config["db_dir"] = str(tmp_path / "missing-db")

    with pytest.raises(ViWrapEnvironmentError, match="preflight failed"):
        run_viwrap(config)


def test_false_string_does_not_skip_compat_runtime_check(tmp_path, monkeypatch):
    config = _compat_config(tmp_path)
    config["skip_runtime_check"] = "false"
    empty_path = tmp_path / "empty-path"
    empty_path.mkdir()
    monkeypatch.setenv("PATH", str(empty_path))

    with pytest.raises(ViWrapEnvironmentError, match="preflight failed"):
        run_viwrap(config)


def test_compat_runner_failure_keeps_standard_and_legacy_diagnostics(tmp_path):
    config = _compat_config(tmp_path, return_code=17)

    with pytest.raises(ViWrapExecutionError, match="exited with 17"):
        run_viwrap(config)

    abi_result_dir = Path(str(config["log_dir"]))
    summary = json.loads(
        (abi_result_dir / "provenance/run_summary.json").read_text(encoding="utf-8")
    )
    with (abi_result_dir / "provenance/commands.tsv").open(encoding="utf-8", newline="") as handle:
        commands = list(csv.DictReader(handle, delimiter="\t"))
    failed = next(row for row in commands if row["status"] == "failed")

    assert summary["status"] == "failed"
    assert (failed["tool_id"], failed["return_code"]) == ("viwrap", "17")
    assert (abi_result_dir / "viwrap.command.txt").is_file()
    assert (abi_result_dir / "viwrap.stderr.log").is_file()


def test_compat_runner_preserves_typed_parse_failure(tmp_path):
    config = _compat_config(tmp_path, write_summary=False)

    with pytest.raises(ViWrapParseError, match="summary directory not found"):
        run_viwrap(config)


def test_compat_runner_keeps_legacy_logs_separate_from_explicit_abi_outdir(tmp_path):
    config = _compat_config(tmp_path)
    abi_result_dir = tmp_path / "abi-result"
    config["outdir"] = str(abi_result_dir)

    result = run_viwrap(config)

    legacy_log_dir = Path(str(config["log_dir"]))
    assert Path(result["abi_result_dir"]) == abi_result_dir
    assert Path(result["abi_outputs"]["summary"]).is_relative_to(abi_result_dir)
    assert Path(result["logs"]["command"]) == legacy_log_dir / "viwrap.command.txt"
    assert (legacy_log_dir / "viwrap.stderr.log").is_file()
    assert not (abi_result_dir / "viwrap.command.txt").exists()


def test_compat_runner_executes_the_custom_executable_it_reports(tmp_path):
    config = _compat_config(tmp_path)
    shared_executable = Path(str(config["executable"]))
    custom_executable = tmp_path / "custom-bin/ViWrap"
    custom_executable.parent.mkdir()
    shared_executable.rename(custom_executable)
    config["executable"] = str(custom_executable)

    result = run_viwrap(config)

    commands_path = Path(result["abi_outputs"]["commands"])
    with commands_path.open(encoding="utf-8", newline="") as handle:
        commands = list(csv.DictReader(handle, delimiter="\t"))
    executed = next(row["command"] for row in commands if row["tool_id"] == "viwrap")
    assert result["command"][0] == str(custom_executable)
    assert executed == result["command_text"]
