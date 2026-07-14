from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest
import yaml

from abi.executor import GenericABIExecutor
from abi.plugins import get_plugin
from abi.plugins.viral_viwrap.artifact_mapper import collect_artifacts
from abi.plugins.viral_viwrap.checker import (
    REQUIRED_CONDA_ENVS,
    REQUIRED_DB_DIRS,
    check_environment,
)
from abi.plugins.viral_viwrap.command_builder import build_viwrap_command
from abi.plugins.viral_viwrap.errors import (
    ViWrapConfigError,
)
from abi.plugins.viral_viwrap.parser import parse_viwrap_outputs
from abi.plugins.viral_viwrap.runner import run_viwrap
from abi.provenance import RunLogger
from abi.tables import StandardTableManager


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


def test_viwrap_command_supports_coverage_inputs_and_optional_flags(tmp_path):
    config = _config(tmp_path)
    config.pop("input_reads")
    coverage = tmp_path / "coverage.tsv"
    sample_info = tmp_path / "sample_to_reads.tsv"
    coverage.write_text("contig\tS1\nvirus_1\t2\n", encoding="utf-8")
    sample_info.write_text("sample\treads\nS1\t2\n", encoding="utf-8")
    config.update(
        {
            "input_cov": str(coverage),
            "input_sample2read_info": str(sample_info),
            "custom_MAGs_dir": str(tmp_path / "mags with spaces"),
            "virome": True,
        }
    )

    command = build_viwrap_command(config)

    assert "--input_reads" not in command
    assert command[command.index("--input_cov") + 1] == str(coverage)
    assert command[command.index("--custom_MAGs_dir") + 1] == str(tmp_path / "mags with spaces")
    assert command[-1] == "--virome"


def test_viwrap_preflight_can_validate_fixture_without_runtime(tmp_path):
    report = check_environment(_config(tmp_path), check_runtime=False)

    assert report["status"] in {"pass", "warn"}
    assert report["summary"]["can_run"] is True


def test_viwrap_compat_runner_preserves_typed_config_errors(tmp_path):
    config = _config(tmp_path)
    config.pop("out_dir")

    with pytest.raises(ViWrapConfigError, match="Missing required ViWrap settings: out_dir"):
        run_viwrap(config)


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


def test_viwrap_abi_tables_preserve_canonical_and_raw_columns(tmp_path):
    summary = tmp_path / "08_ViWrap_summary_outdir"
    summary.mkdir()
    (summary / "Virus_summary_info.txt").write_text(
        "Virus ID\tLength\tCheckV quality\tupstream_extra\nvirus_1\t5000\thigh-quality\tkept\n",
        encoding="utf-8",
    )
    plugin = get_plugin("viral_viwrap")

    row = plugin.parse_outputs("viwrap", tmp_path, "S1")["virus_summary"][0]

    assert row["virus_id"] == "virus_1"
    assert row["length"] == "5000"
    assert row["checkv_quality"] == "high-quality"
    assert '"upstream_extra": "kept"' in row["raw_record_json"]


def test_viwrap_is_registered_and_plannable_offline():
    plugin = get_plugin("viral_viwrap")
    config = plugin.load_config()
    plan = plugin.build_plan(config, check_files=False)

    assert plan.analysis_type == "viral_viwrap"
    assert plan.selected_tools == ["viwrap"]


def test_viwrap_compat_preset_is_explicit_and_rejects_unimplemented_native(tmp_path):
    plugin = get_plugin("viral_viwrap")

    config = plugin.load_config(overrides=_config(tmp_path))
    schema = json.loads((plugin.root / "schemas/input.schema.json").read_text(encoding="utf-8"))
    catalog = yaml.safe_load((plugin.root / "workflows/catalog.yaml").read_text(encoding="utf-8"))
    catalog_ids = [item["id"] for item in catalog["workflows"]]

    assert config["workflow"]["preset"] == "viwrap_compat"
    assert schema["properties"]["workflow"]["properties"]["preset"]["enum"] == catalog_ids
    native_dir = tmp_path / "native"
    native_dir.mkdir()
    with pytest.raises(ValueError, match="Unknown viral_viwrap workflow preset 'viral_native'"):
        plugin.load_config(
            overrides={**_config(native_dir), "workflow": {"preset": "viral_native"}}
        )
    typo_dir = tmp_path / "typo"
    typo_dir.mkdir()
    with pytest.raises(ValueError, match="Unknown viral_viwrap workflow field.*typo"):
        plugin.load_config(
            overrides={
                **_config(typo_dir),
                "workflow": {"preset": "viwrap_compat", "typo": 1},
            }
        )


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


def test_viwrap_dag_executes_end_to_end_with_fixture_tool(tmp_path, monkeypatch):
    config = _config(tmp_path)
    config.update(
        {
            "outdir": str(tmp_path / "abi-result"),
            "out_dir": str(tmp_path / "abi-result" / "viwrap-output"),
            "log_dir": str(tmp_path / "logs"),
            "skip_runtime_check": True,
        }
    )
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    executable = bin_dir / "ViWrap"
    executable.write_text(
        """#!/usr/bin/env python3
import pathlib
import sys
args = sys.argv[1:]
if '--version' in args or '-h' in args:
    print('ViWrap 1.3.1')
    raise SystemExit(0)
out = pathlib.Path(args[args.index('--out_dir') + 1]) / '08_ViWrap_summary_outdir'
out.mkdir(parents=True, exist_ok=True)
(out / 'Virus_summary_info.txt').write_text('virus_id\\tlength\\nvirus_1\\t5000\\n')
""",
        encoding="utf-8",
    )
    executable.chmod(0o755)
    shared_bin = Path(str(config["conda_env_dir"])) / "ViWrap/bin"
    shared_bin.mkdir(parents=True, exist_ok=True)
    (shared_bin / "ViWrap").symlink_to(executable)
    (bin_dir / "conda").symlink_to(executable)
    monkeypatch.setenv(
        "PATH",
        os.pathsep.join((str(bin_dir), str(Path(sys.executable).parent), os.environ["PATH"])),
    )

    plugin = get_plugin("viral_viwrap")
    loaded = plugin.load_config(overrides=config)
    plan = plugin.build_plan(loaded)
    executor = GenericABIExecutor(
        plugin.registry(),
        RunLogger(loaded["log_dir"]),
        table_manager=StandardTableManager(plugin.table_schemas()),
        parse_outputs=plugin.parse_outputs,
        internal_handlers=plugin.internal_handlers(),
    )

    outputs = executor.run(plan, loaded)

    summary = json.loads(outputs["summary"].read_text(encoding="utf-8"))
    assert summary["status"] == "success"
    virus_table = Path(loaded["outdir"]) / "tables/virus_summary.tsv"
    assert "virus_1" in virus_table.read_text(encoding="utf-8")
