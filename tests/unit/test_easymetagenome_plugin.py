from __future__ import annotations

import csv
import gzip
import json
import os
import sys
from pathlib import Path

import pytest

from abi.agent import ABIAgentInterface
from abi.executor import GenericABIExecutor
from abi.plugins import get_plugin
from abi.plugins.easymetagenome.adapters import (
    DatabaseChecker,
    DatabaseValidationError,
    ManifestValidationError,
    ManifestValidator,
    OutputChecker,
    OutputValidationError,
    ReportCollector,
    ResumeManager,
    SampleRecord,
    ToolAdapter,
    merge_bracken,
    taxonomy_diversity,
)
from abi.provenance import RunLogger
from abi.tables import StandardTableManager


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


def test_manifest_validator_accepts_csv_read_aliases(tmp_path):
    r1 = tmp_path / "R1.fastq.gz"
    r2 = tmp_path / "R2.fastq.gz"
    r1.write_bytes(b"reads")
    r2.write_bytes(b"reads")
    manifest = tmp_path / "samples.csv"
    manifest.write_text(
        "sample_id,read1,read2,group\nS1,R1.fastq.gz,R2.fastq.gz,case\n",
        encoding="utf-8",
    )

    records = ManifestValidator.validate(manifest)

    assert records == [SampleRecord("S1", str(r1), str(r2), "case")]


def test_output_contract_reports_missing_and_empty_artifacts(tmp_path):
    empty_file = tmp_path / "empty.txt"
    empty_file.touch()
    empty_dir = tmp_path / "empty_dir"
    empty_dir.mkdir()

    passed, failures = OutputChecker.check([tmp_path / "missing", empty_file, empty_dir])

    assert passed is False
    assert failures == [
        f"missing: {tmp_path / 'missing'}",
        f"empty file: {empty_file}",
        f"empty directory: {empty_dir}",
    ]
    with pytest.raises(OutputValidationError, match="Output checks failed"):
        OutputChecker.require([empty_file])


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
    with pytest.raises(DatabaseValidationError, match="Database files missing"):
        DatabaseChecker.require(registry)
    required.write_text("index\n", encoding="utf-8")
    assert DatabaseChecker.check(registry)["status"] == "pass"
    assert ResumeManager.should_skip([required]) is True
    assert ResumeManager.should_skip([required], resume=False) is False
    assert ResumeManager.should_skip([]) is False
    required.write_text("", encoding="utf-8")
    assert ResumeManager.should_skip([required]) is False


def test_tool_adapter_surfaces_missing_values_and_known_failures(monkeypatch):
    import abi.plugins.easymetagenome.adapters as adapters

    adapter = ToolAdapter(
        "fixture",
        "fixture-tool",
        "fixture-tool --input {input}",
        failure_patterns=(("out of memory", "request more memory"),),
    )
    monkeypatch.setattr(adapters.shutil, "which", lambda _name: None)

    assert adapter.version_check()["reason"] == "executable_not_found"
    with pytest.raises(ValueError, match="command missing value: input"):
        adapter.build_command({})
    assert adapter.diagnose("OUT OF MEMORY", 137) == "request more memory"
    assert "status 2" in adapter.diagnose("unknown", 2)


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


def test_humann4_preset_selects_functional_branch_without_taxonomy(tmp_path):
    plugin = get_plugin("easymetagenome")
    config = plugin.load_config(
        overrides={
            "workflow": {"preset": "p1_humann4"},
            "outdir": str(tmp_path / "results"),
            "log_dir": str(tmp_path / "logs"),
        }
    )
    plan = plugin.build_plan(config, check_files=False)

    assert "humann4" in plan.selected_tools
    assert "humann_regroup_table" in plan.selected_tools
    assert "kraken2" not in plan.selected_tools
    assert "bracken" not in plan.selected_tools
    join_step = next(step for step in plan.steps if step.step_id == "humann_join_genefamilies")
    assert join_step.params["_explicit_dependencies"]


def test_workflow_preset_preserves_explicit_node_selection(tmp_path):
    plugin = get_plugin("easymetagenome")
    config = plugin.load_config(
        overrides={
            "workflow": {
                "preset": "p1_humann4",
                "include_nodes": ["validate_manifest", "seqkit_stat_raw"],
            },
            "outdir": str(tmp_path / "results"),
        }
    )

    assert config["workflow"]["include_nodes"] == ["validate_manifest", "seqkit_stat_raw"]


def test_workflow_catalog_is_available_through_unified_query():
    payload = json.loads(
        ABIAgentInterface().query(analysis_type="easymetagenome", what="workflows")
    )

    assert payload["status"] == "success"
    assert {item["id"] for item in payload["result"]["workflows"]} == {
        "p0_taxonomy",
        "p1_humann4",
        "full_read_based",
    }


def test_humann4_preflight_requires_only_functional_databases(tmp_path):
    resource_dirs = {}
    for name in ("host_db", "humann_nucleotide_db", "humann_protein_db", "metaphlan_db"):
        path = tmp_path / name
        path.mkdir()
        resource_dirs[name] = str(path)
    plugin = get_plugin("easymetagenome")
    config = plugin.load_config(
        overrides={
            "input": {"sample_sheet": str(_manifest(tmp_path))},
            "workflow": {"preset": "p1_humann4"},
            "resources": resource_dirs,
            "outdir": str(tmp_path / "results"),
        }
    )

    report = plugin.preflight(config, engine="local", check_runtime=False)

    assert report["status"] == "pass"
    assert "kraken2_db" not in {check["name"] for check in report["checks"]}


def test_easymetagenome_parsers_cover_every_registered_tool(tmp_path):
    plugin = get_plugin("easymetagenome")

    (tmp_path / "S1.seqkit.tsv").write_text(
        "file\tnum_seqs\tsum_len\nreads.fastq.gz\t2\t300\n", encoding="utf-8"
    )
    (tmp_path / "S1.fastp.json").write_text(
        json.dumps(
            {
                "summary": {
                    "before_filtering": {"total_reads": 2},
                    "after_filtering": {"total_reads": 2, "q30_rate": 1.0},
                }
            }
        ),
        encoding="utf-8",
    )
    with gzip.open(tmp_path / "S1_1_kneaddata_paired_1.fastq.gz", "wt") as handle:
        handle.write("@r1\nACGT\n+\nIIII\n")
    (tmp_path / "S1.kraken2.report").write_text(
        "100.00\t10\t10\tS\t562\t  Escherichia coli\n", encoding="utf-8"
    )
    (tmp_path / "S1.S.brk").write_text(
        "name\ttaxonomy_id\ttaxonomy_lvl\tkraken_assigned_reads\t"
        "added_reads\tnew_est_reads\tfraction_total_reads\n"
        "Escherichia coli\t562\tS\t8\t2\t10\t1.0\n",
        encoding="utf-8",
    )
    (tmp_path / "S1_genefamilies.tsv").write_text(
        "# Gene Family\tS1-RPKs\nUniRef90_A\t4.5\n", encoding="utf-8"
    )

    assert plugin.parse_outputs("seqkit", tmp_path, "S1")["qc_summary"][0]["value"] == "2"
    assert (
        plugin.parse_outputs("kneaddata", tmp_path, "S1")["host_removal_summary"][0][
            "dehost_read_pairs"
        ]
        == 1
    )
    assert (
        plugin.parse_outputs("kraken2", tmp_path, "S1")["taxonomy_abundance"][0]["taxonomy_id"]
        == "562"
    )
    assert (
        plugin.parse_outputs("bracken", tmp_path, "S1")["taxonomy_abundance"][0]["new_est_reads"]
        == "10"
    )
    functional = plugin.parse_outputs("humann4", tmp_path, "S1")["functional_abundance"]
    assert functional[0]["feature_id"] == "UniRef90_A"
    assert functional[0]["value"] == "4.5"

    assert all(
        any(plugin.parse_outputs(tool_id, tmp_path, "S1").values())
        for tool_id in plugin.registry().ids()
    )


def test_humann4_dag_executes_end_to_end_with_fixture_tools(tmp_path, monkeypatch):
    manifest = _manifest(tmp_path)
    resources = {}
    for name in ("host_db", "humann_nucleotide_db", "humann_protein_db", "metaphlan_db"):
        path = tmp_path / name
        path.mkdir()
        resources[name] = str(path)

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fixture_tool = bin_dir / "fixture_humann_tool.py"
    fixture_tool.write_text(
        """#!/usr/bin/env python3
import gzip
import json
import pathlib
import shutil
import sys

name = pathlib.Path(sys.argv[0]).name
args = sys.argv[1:]
def value(flag):
    return pathlib.Path(args[args.index(flag) + 1])
def write_table(path, feature):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('# Feature\\tS1-RPKs\\n' + feature + '\\t4.5\\n')
if name == 'seqkit':
    print('file\\tnum_seqs\\tsum_len')
    print('reads.fastq.gz\\t1\\t4')
elif name == 'fastp':
    for flag in ('-o', '-O'):
        path = value(flag); path.parent.mkdir(parents=True, exist_ok=True)
        with gzip.open(path, 'wt') as handle: handle.write('@r1\\nACGT\\n+\\nIIII\\n')
    report = value('-j'); report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps({'summary': {
        'before_filtering': {'total_reads': 2},
        'after_filtering': {'total_reads': 2, 'q30_rate': 1.0},
    }}))
    value('-h').write_text('<html>fixture</html>\\n')
elif name == 'kneaddata':
    out = value('-o'); out.mkdir(parents=True, exist_ok=True)
    for suffix in ('paired_1.fastq.gz', 'paired_2.fastq.gz'):
        with gzip.open(out / ('S1_1_kneaddata_' + suffix), 'wt') as handle:
            handle.write('@r1\\nACGT\\n+\\nIIII\\n')
elif name == 'humann':
    out = value('--output'); sample = args[args.index('--output-basename') + 1]
    write_table(out / (sample + '_genefamilies.tsv'), 'UniRef90_A')
    write_table(out / (sample + '_pathabundance.tsv'), 'PWY-1')
    write_table(out / (sample + '_pathcoverage.tsv'), 'PWY-1')
elif name == 'humann_join_tables':
    write_table(value('--output'), 'UniRef90_A' if 'genefamilies' in args else 'PWY-1')
elif name in ('humann_renorm_table', 'humann_regroup_table'):
    source = value('--input')
    output_flag = '--output'
    destination = value(output_flag)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)
elif name == 'humann_split_stratified_table':
    out = value('--output'); out.mkdir(parents=True, exist_ok=True)
    write_table(out / 'unstratified.tsv', 'UniRef90_A')
""",
        encoding="utf-8",
    )
    fixture_tool.chmod(0o755)
    for name in (
        "seqkit",
        "fastp",
        "kneaddata",
        "humann",
        "humann_join_tables",
        "humann_renorm_table",
        "humann_regroup_table",
        "humann_split_stratified_table",
    ):
        (bin_dir / name).symlink_to(fixture_tool)
    monkeypatch.setenv(
        "PATH",
        os.pathsep.join((str(bin_dir), str(Path(sys.executable).parent), os.environ["PATH"])),
    )

    plugin = get_plugin("easymetagenome")
    config = plugin.load_config(
        overrides={
            "input": {"sample_sheet": str(manifest)},
            "workflow": {"preset": "p1_humann4"},
            "resources": resources,
            "threads": 1,
            "outdir": str(tmp_path / "result"),
            "log_dir": str(tmp_path / "logs"),
        }
    )
    plan = plugin.build_plan(config)
    executor = GenericABIExecutor(
        plugin.registry(),
        RunLogger(config["log_dir"]),
        table_manager=StandardTableManager(plugin.table_schemas()),
        parse_outputs=plugin.parse_outputs,
        internal_handlers=plugin.internal_handlers(),
    )

    outputs = executor.run(plan, config)

    summary = json.loads(outputs["summary"].read_text(encoding="utf-8"))
    assert summary["status"] == "success"
    assert summary["completed_step_count"] == len(plan.steps)
    functional_table = Path(config["outdir"]) / "tables/functional_abundance.tsv"
    assert len(functional_table.read_text(encoding="utf-8").splitlines()) > 1
    assert (Path(config["outdir"]) / "report/easymetagenome_functional_report.md").is_file()
