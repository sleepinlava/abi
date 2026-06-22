from __future__ import annotations

import csv
import gzip
import os
from pathlib import Path

import pytest

from abi.plugins import get_plugin
from abi.plugins.easymetagenome.adapters import (
    DatabaseChecker,
    ManifestValidationError,
    ManifestValidator,
    ReportCollector,
    ResumeManager,
    SampleRecord,
    merge_bracken,
    taxonomy_diversity,
)


def _manifest(tmp_path: Path) -> Path:
    r1 = tmp_path / "S1_R1.fastq.gz"
    r2 = tmp_path / "S1_R2.fastq.gz"
    r1.write_bytes(b"reads")
    r2.write_bytes(b"reads")
    manifest = tmp_path / "samples.tsv"
    manifest.write_text(
        "sample_id\tr1\tr2\tgroup\nS1\tS1_R1.fastq.gz\tS1_R2.fastq.gz\tcase\n",
        encoding="utf-8",
    )
    return manifest


def test_manifest_validator_writes_normalized_outputs(tmp_path):
    outputs = ManifestValidator.write_outputs(_manifest(tmp_path), tmp_path)

    assert outputs["normalized_manifest"].is_file()
    assert outputs["validation_report"].is_file()
    assert "S1" in outputs["normalized_manifest"].read_text(encoding="utf-8")


def test_manifest_validator_reports_missing_fastq(tmp_path):
    manifest = tmp_path / "samples.tsv"
    manifest.write_text("sample_id\tr1\tr2\nS1\tmissing_1.fq\tmissing_2.fq\n", encoding="utf-8")

    with pytest.raises(ManifestValidationError, match="missing or empty"):
        ManifestValidator.validate(manifest)


def test_document_workflow_expands_samples_and_taxonomic_levels(tmp_path):
    plugin = get_plugin("easymetagenome")
    workflow = plugin.documented_workflow()
    db_registry = tmp_path / "kraken.yaml"
    db_registry.write_text(
        f"path: {tmp_path / 'kraken'}\nhost_db: {tmp_path / 'host'}\nchecks: []\n",
        encoding="utf-8",
    )

    plan = workflow.dry_run(_manifest(tmp_path), tmp_path, db_registry=db_registry)
    bracken = [item for item in plan if item["node_id"] == "bracken_reestimate"]

    assert len(bracken) == 3
    assert {item["node"].rsplit(":", 1)[-1] for item in bracken} == {"P", "G", "S"}
    assert all("bracken -d" in item["command"] for item in bracken)


def test_database_checker_and_resume_require_nonempty_outputs(tmp_path, monkeypatch):
    database = tmp_path / "db"
    database.mkdir()
    required = database / "hash.k2d"
    registry = tmp_path / "db.yaml"
    registry.write_text(
        "database_id: test\nchecks:\n  - exists: ${TEST_DB}/hash.k2d\n", encoding="utf-8"
    )
    monkeypatch.setenv("TEST_DB", str(database))

    assert DatabaseChecker.check(registry)["status"] == "fail"
    required.write_text("index\n", encoding="utf-8")
    assert DatabaseChecker.check(registry)["status"] == "pass"
    assert ResumeManager.should_skip([required]) is True
    required.write_text("", encoding="utf-8")
    assert ResumeManager.should_skip([required]) is False


def test_bracken_merge_diversity_and_report(tmp_path):
    bracken_files = []
    for sample_id, counts in (("S1", (10, 0)), ("S2", (5, 5))):
        path = tmp_path / f"{sample_id}.S.brk"
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=["name", "taxonomy_id", "new_est_reads"],
                delimiter="\t",
            )
            writer.writeheader()
            writer.writerow({"name": "A", "taxonomy_id": "1", "new_est_reads": counts[0]})
            writer.writerow({"name": "B", "taxonomy_id": "2", "new_est_reads": counts[1]})
        bracken_files.append(path)
    merged = merge_bracken(bracken_files, tmp_path / "result/kraken2/bracken.S.txt")
    alpha, beta = taxonomy_diversity(
        merged, tmp_path / "result/kraken2/alpha.txt", tmp_path / "result/kraken2/beta.txt"
    )
    reports = ReportCollector.collect(
        tmp_path,
        [SampleRecord("S1", "r1", "r2"), SampleRecord("S2", "r1", "r2")],
    )

    assert alpha.stat().st_size > 0
    assert beta.stat().st_size > 0
    assert reports["markdown_report"].is_file()


def test_easymetagenome_is_registered_and_plannable_offline(tmp_path):
    plugin = get_plugin("easymetagenome")
    config = plugin.load_config(
        overrides={
            "outdir": str(tmp_path / "results"),
            "log_dir": str(tmp_path / "logs"),
        }
    )
    plan = plugin.build_plan(config, check_files=False)

    assert plan.analysis_type == "easymetagenome"
    assert set(plan.selected_tools) == {"seqkit", "fastp", "kneaddata", "kraken2", "bracken"}


def test_p0_runner_executes_chain_and_writes_report(tmp_path, monkeypatch):
    reads = [tmp_path / "S1_R1.fastq.gz", tmp_path / "S1_R2.fastq.gz"]
    for read in reads:
        with gzip.open(read, "wt", encoding="utf-8") as handle:
            handle.write("@r1\nACGT\n+\nIIII\n")
    manifest = tmp_path / "samples.tsv"
    manifest.write_text(
        f"sample_id\tr1\tr2\tgroup\nS1\t{reads[0]}\t{reads[1]}\tcase\n",
        encoding="utf-8",
    )
    database = tmp_path / "db"
    host = tmp_path / "host"
    database.mkdir()
    host.mkdir()
    registry = tmp_path / "db.yaml"
    registry.write_text(
        f"database_id: fixture\npath: {database}\nhost_db: {host}\nchecks: []\n",
        encoding="utf-8",
    )
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    tool_script = bin_dir / "fixture_tool.py"
    tool_script.write_text(
        """#!/usr/bin/env python3
import gzip
import json
import pathlib
import sys

name = pathlib.Path(sys.argv[0]).name
args = sys.argv[1:]
if '--version' in args or args == ['version']:
    print(name + ' 1.0')
    raise SystemExit(0)
def value(flag):
    return pathlib.Path(args[args.index(flag) + 1])
if name == 'seqkit':
    print('file\\tnum_seqs')
    print('fixture\\t1')
elif name == 'fastp':
    for flag in ('-o', '-O', '-h'):
        path = value(flag); path.parent.mkdir(parents=True, exist_ok=True); path.write_text('ok\\n')
    report = value('-j'); report.parent.mkdir(parents=True, exist_ok=True)
    data = {'summary': {
        'before_filtering': {'total_reads': 2},
        'after_filtering': {'total_reads': 2, 'q30_rate': 1.0},
    }}
    report.write_text(json.dumps(data))
elif name == 'kneaddata':
    out = value('-o'); out.mkdir(parents=True, exist_ok=True)
    for suffix in ('paired_1.fastq.gz', 'paired_2.fastq.gz'):
        with gzip.open(out / ('S1_1_kneaddata_' + suffix), 'wt') as handle:
            handle.write('@r1\\nACGT\\n+\\nIIII\\n')
elif name == 'kraken2':
    for flag in ('--report', '--output'):
        path = value(flag)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('classified\\n')
elif name == 'bracken':
    table = value('-o'); table.parent.mkdir(parents=True, exist_ok=True)
    table.write_text('name\\ttaxonomy_id\\tnew_est_reads\\nBacteria\\t2\\t10\\n')
    value('-w').write_text('report\\n')
""",
        encoding="utf-8",
    )
    tool_script.chmod(0o755)
    for name in ("seqkit", "fastp", "kneaddata", "kraken2", "bracken"):
        link = bin_dir / name
        link.symlink_to(tool_script)
    monkeypatch.setenv("PATH", str(bin_dir) + os.pathsep + os.environ["PATH"])

    workflow = get_plugin("easymetagenome").documented_workflow()
    result = workflow.run(manifest, tmp_path, db_registry=registry)

    assert result["status"] == "success"
    assert (tmp_path / "result/qc/fastp.txt").stat().st_size > 0
    assert (tmp_path / "result/qc/sum.txt").stat().st_size > 0
    assert (tmp_path / "result/kraken2/bracken.S.txt").stat().st_size > 0
    assert (tmp_path / "result/report.md").stat().st_size > 0
