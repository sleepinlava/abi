from __future__ import annotations

from pathlib import Path

import pytest

from abi.plugins import get_plugin
from abi.plugins.viral_viwrap.artifact_mapper import collect_artifacts
from abi.plugins.viral_viwrap.checker import (
    REQUIRED_CONDA_ENVS,
    REQUIRED_DB_DIRS,
    check_environment,
)
from abi.plugins.viral_viwrap.command_builder import build_viwrap_command
from abi.plugins.viral_viwrap.errors import ViWrapConfigError
from abi.plugins.viral_viwrap.parser import parse_viwrap_outputs
from abi.plugins.viral_viwrap.runner import run_viwrap


def _config(tmp_path: Path) -> dict[str, object]:
    fasta = tmp_path / "assembly.fa"
    r1 = tmp_path / "R1.fastq.gz"
    r2 = tmp_path / "R2.fastq.gz"
    fasta.write_text(">contig_1\nACGT\n", encoding="utf-8")
    r1.write_bytes(b"reads")
    r2.write_bytes(b"reads")
    envs = tmp_path / "envs"
    db = tmp_path / "db"
    for name in REQUIRED_CONDA_ENVS:
        (envs / name).mkdir(parents=True)
    for name in REQUIRED_DB_DIRS:
        (db / name).mkdir(parents=True)
        (db / name / "ready").write_text("ok\n", encoding="utf-8")
    return {
        "input_metagenome": str(fasta),
        "input_reads": [str(r1), str(r2)],
        "out_dir": str(tmp_path / "viwrap-output"),
        "db_dir": str(db),
        "conda_env_dir": str(envs),
        "identify_method": "genomad",
        "reads_type": "illumina",
        "threads": 1,
    }


def test_viwrap_command_includes_reads_and_uses_argv(tmp_path):
    config = _config(tmp_path)
    command = build_viwrap_command(config)

    assert command[:2] == ["ViWrap", "run"]
    assert command[command.index("--input_reads") + 1].count(",") == 1
    assert "--input_cov" not in command


def test_viwrap_rejects_reads_and_coverage_together(tmp_path):
    config = _config(tmp_path)
    config["input_cov"] = str(tmp_path / "coverage.tsv")

    with pytest.raises(ViWrapConfigError, match="mutually exclusive"):
        build_viwrap_command(config)


def test_viwrap_preflight_can_validate_fixture_without_runtime(tmp_path):
    report = check_environment(_config(tmp_path), check_runtime=False)

    assert report["status"] in {"pass", "warn"}
    assert report["summary"]["can_run"] is True


def test_viwrap_managed_dry_run_returns_complete_command(tmp_path):
    config = _config(tmp_path)
    config.update({"dry_run": True, "skip_runtime_check": True})

    result = run_viwrap(config)

    assert result["mode"] == "dry_run"
    assert "--input_reads" in result["command"]


def test_viwrap_parser_and_artifact_manifest(tmp_path):
    summary = tmp_path / "08_ViWrap_summary_outdir"
    summary.mkdir()
    (summary / "Virus_summary_info.txt").write_text(
        "virus_id\tlength\nvirus_1\t5000\n", encoding="utf-8"
    )

    parsed = parse_viwrap_outputs(tmp_path)
    artifacts = collect_artifacts(tmp_path)

    assert parsed["table_rows"]["virus_summary"][0]["virus_id"] == "virus_1"
    assert artifacts["artifact_count"] == 1
    assert artifacts["artifacts"][0]["category"] == "summary"


def test_viwrap_is_registered_and_plannable_offline():
    plugin = get_plugin("viral_viwrap")
    config = plugin.load_config()
    plan = plugin.build_plan(config, check_files=False)

    assert plan.analysis_type == "viral_viwrap"
    assert plan.selected_tools == ["viwrap"]


def test_viwrap_plugin_reads_example_builds_complete_dry_run_command(tmp_path):
    plugin = get_plugin("viral_viwrap")
    source = _config(tmp_path)
    config_file = tmp_path / "viwrap.yaml"
    config_file.write_text(
        "\n".join(
            [
                f"input_metagenome: {source['input_metagenome']}",
                "input_reads:",
                *[f"  - {path}" for path in source["input_reads"]],
                f"out_dir: {source['out_dir']}",
                f"db_dir: {source['db_dir']}",
                f"conda_env_dir: {source['conda_env_dir']}",
                "identify_method: genomad",
                "reads_type: illumina",
                "threads: 1",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    config = plugin.load_config(config_file)
    plan = plugin.build_plan(config, check_files=False)
    step = next(step for step in plan.steps if step.tool_id == "viwrap")
    params = {**step.inputs, **step.outputs, **step.params}
    command = plugin.registry().create("viwrap", mock_tools=True).build_command(params)

    assert "--input_reads" in command
    assert "--input_cov" not in command
