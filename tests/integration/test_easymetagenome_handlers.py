from __future__ import annotations

import gzip
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from abi.plugins import get_plugin
from abi.plugins.easymetagenome.handlers import (
    bracken_merge_handler,
    report_handler,
    taxonomy_diversity_handler,
    taxonomy_filter_handler,
)
from abi.runtimes import RuntimeOptions
from abi.workflow import WorkflowCoordinator

_CANONICAL_REPORT_SCHEMA = (
    Path(__file__).parents[2] / "plugins/easymetagenome/schemas/abi_report_manifest.schema.json"
)


def _assert_json_schema(value, schema):
    if "const" in schema:
        assert value == schema["const"]
    if "enum" in schema:
        assert value in schema["enum"]
    schema_type = schema.get("type")
    if schema_type == "object":
        assert isinstance(value, dict)
        assert set(schema.get("required", ())) <= set(value)
        assert len(value) >= schema.get("minProperties", 0)
        properties = schema.get("properties", {})
        for name, item in value.items():
            if name in properties:
                _assert_json_schema(item, properties[name])
                continue
            additional = schema.get("additionalProperties", True)
            assert additional is not False
            if isinstance(additional, dict):
                _assert_json_schema(item, additional)
    elif schema_type == "integer":
        assert isinstance(value, int) and not isinstance(value, bool)
        assert value >= schema.get("minimum", value)
    elif schema_type == "string":
        assert isinstance(value, str)
        assert len(value) >= schema.get("minLength", 0)


def _assert_matches_canonical_report_schema(payload):
    schema = json.loads(_CANONICAL_REPORT_SCHEMA.read_text(encoding="utf-8"))
    _assert_json_schema(payload, schema)


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


def test_taxonomy_internal_handlers_merge_filter_diversity_and_report(tmp_path):
    inputs = {}
    outputs = {}
    for level, name in (("P", "phylum"), ("G", "genus"), ("S", "species")):
        table = tmp_path / f"S1.{level}.brk"
        table.write_text(
            "name\ttaxonomy_id\tnew_est_reads\nA\t1\t10\nB\t2\t0\n",
            encoding="utf-8",
        )
        inputs[f"{name}_tables"] = [str(table)]
        outputs[f"{name}_table"] = str(tmp_path / "merged" / f"{name}.tsv")

    result = bracken_merge_handler(SimpleNamespace(inputs=inputs, outputs=outputs), {}, None)

    assert result.message == "Merged Bracken P/G/S tables"
    assert all(Path(path).is_file() for path in outputs.values())

    filter_outputs = {
        f"filtered_{name}": str(tmp_path / "filtered" / f"{name}.tsv")
        for name in ("phylum", "genus", "species")
    }
    taxonomy_filter_handler(
        SimpleNamespace(
            inputs={
                f"{name}_table": outputs[f"{name}_table"] for name in ("phylum", "genus", "species")
            },
            outputs=filter_outputs,
            params={"prevalence": 1.0},
        ),
        {},
        None,
    )

    species_rows = Path(filter_outputs["filtered_species"]).read_text(encoding="utf-8")
    assert "A\t1\t10" in species_rows
    assert "B\t2\t0" not in species_rows

    diversity = taxonomy_diversity_handler(
        SimpleNamespace(
            inputs={"species_table": outputs["species_table"]},
            outputs={
                "alpha_table": str(tmp_path / "diversity" / "alpha.tsv"),
                "beta_table": str(tmp_path / "diversity" / "beta.tsv"),
            },
        ),
        {},
        None,
    )
    assert Path(diversity.artifacts["alpha"]).is_file()
    assert Path(diversity.artifacts["beta"]).is_file()

    tables_dir = tmp_path / "tables"
    tables_dir.mkdir()
    for name in ("qc_summary", "host_removal_summary", "taxonomy_abundance"):
        (tables_dir / f"{name}.tsv").write_text("id\tvalue\na\t1\nb\t2\n", encoding="utf-8")

    report = report_handler(
        SimpleNamespace(
            inputs={
                "species_table": outputs["species_table"],
                "ignored": ["not", "a", "path"],
            },
            outputs={
                "report_markdown": str(tmp_path / "report" / "report.md"),
                "report_manifest": str(tmp_path / "report" / "manifest.json"),
            },
        ),
        {"input": {"sample_sheet": str(_manifest(tmp_path))}},
        SimpleNamespace(tables_dir=tables_dir),
    )

    assert report.message == "EasyMetagenome report generated"
    manifest = json.loads(Path(report.artifacts["manifest"]).read_text(encoding="utf-8"))
    assert manifest["schema_version"] == "abi.report-manifest.v1"
    assert manifest["workflow"] == "p0_taxonomy"
    assert manifest["sample_count"] == 1
    assert set(manifest["artifacts"]) == {"species_table"}
    assert manifest["consistency"] == {
        "standard_table_count": 3,
        "standard_row_count": 6,
    }


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
        "database_id: fixture\npath: ${EASY_KRAKEN_DB}\nhost_db: ${EASY_HOST_DB}\nchecks: []\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("EASY_KRAKEN_DB", str(database))
    monkeypatch.setenv("EASY_HOST_DB", str(host))
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
        (bin_dir / name).symlink_to(tool_script)
    monkeypatch.setenv(
        "PATH",
        os.pathsep.join((str(bin_dir), str(Path(sys.executable).parent), os.environ["PATH"])),
    )

    workflow = get_plugin("easymetagenome").documented_workflow()
    with pytest.warns(DeprecationWarning, match="use `abi run --type easymetagenome`"):
        result = workflow.run(manifest, tmp_path, db_registry=registry)

    assert result["status"] == "success"
    assert {"status", "nodes", "reports", "abi_outputs"} <= result.keys()
    assert all({"node", "command", "status"} <= row.keys() for row in result["nodes"])
    assert {row["status"] for row in result["nodes"]} == {"success", 0}
    assert {"fastp_qc:S1", "bracken_reestimate:S1:P", "collect_report"} <= {
        row["node"] for row in result["nodes"]
    }
    assert set(result["reports"]) == {"report_manifest", "markdown_report"}
    assert (tmp_path / "result/execution_plan.json").is_file()
    assert (tmp_path / "result/provenance/commands.tsv").is_file()
    legacy_paths = [
        "metadata.normalized.tsv",
        "input_validation.json",
        "qc/fastp.txt",
        "qc/sum.txt",
        "kraken2/bracken.P.txt",
        "kraken2/bracken.G.txt",
        "kraken2/bracken.S.txt",
        "kraken2/bracken.P.0.2.txt",
        "kraken2/bracken.G.0.2.txt",
        "kraken2/bracken.S.0.2.txt",
        "kraken2/alpha.txt",
        "kraken2/beta.txt",
        "report_manifest.json",
        "report.md",
    ]
    assert all((tmp_path / "result" / path).stat().st_size > 0 for path in legacy_paths)
    resolved_config = yaml.safe_load(
        (tmp_path / "result/provenance/config.resolved.yaml").read_text(encoding="utf-8")
    )
    assert resolved_config["resources"]["host_db"] == str(host)
    assert resolved_config["resources"]["kraken2_db"] == str(database)

    canonical_manifest_path = Path(result["abi_outputs"]["report_manifest"])
    canonical_report_path = Path(result["abi_outputs"]["report_markdown"])
    canonical_manifest = json.loads(canonical_manifest_path.read_text(encoding="utf-8"))
    _assert_matches_canonical_report_schema(canonical_manifest)
    assert canonical_manifest_path == tmp_path / "result/report/report_manifest.json"
    assert canonical_report_path == tmp_path / "result/report/easymetagenome_report.md"
    assert canonical_manifest["schema_version"] == "abi.report-manifest.v1"
    assert canonical_manifest["workflow"] == "p0_taxonomy"
    assert canonical_manifest["sample_count"] == 1
    assert canonical_manifest["standard_tables"]["taxonomy_abundance"] == {
        "path": str(tmp_path / "result/tables/taxonomy_abundance.tsv"),
        "rows": 3,
    }
    assert canonical_manifest["report"] == str(canonical_report_path)

    def fail_if_rerun(*_args, **_kwargs):
        raise AssertionError("resume=True must reuse a complete canonical ABI result")

    monkeypatch.setattr("abi.runtimes.local.LocalRuntime.run", fail_if_rerun)
    with pytest.warns(DeprecationWarning):
        resumed = workflow.run(manifest, tmp_path, db_registry=registry, resume=True)

    assert resumed["status"] == "success"
    assert {row["status"] for row in resumed["nodes"]} == {"resumed"}
    assert resumed["abi_outputs"]["report"] == result["abi_outputs"]["report"]
    assert resumed["abi_outputs"]["report_manifest"] == canonical_manifest_path
    assert resumed["abi_outputs"]["report_markdown"] == canonical_report_path

    canonical_manifest_text = canonical_manifest_path.read_text(encoding="utf-8")
    canonical_manifest_path.unlink()
    with (
        pytest.warns(DeprecationWarning),
        pytest.raises(AssertionError, match="resume=True must reuse"),
    ):
        workflow.run(manifest, tmp_path, db_registry=registry, resume=True)
    canonical_manifest_path.write_text(canonical_manifest_text, encoding="utf-8")

    corrupted_manifest = json.loads(canonical_manifest_text)
    corrupted_manifest["consistency"]["standard_row_count"] += 1
    canonical_manifest_path.write_text(json.dumps(corrupted_manifest), encoding="utf-8")
    with (
        pytest.warns(DeprecationWarning),
        pytest.raises(AssertionError, match="resume=True must reuse"),
    ):
        workflow.run(manifest, tmp_path, db_registry=registry, resume=True)
    canonical_manifest_path.write_text(canonical_manifest_text, encoding="utf-8")

    corrupted_manifest = json.loads(canonical_manifest_text)
    corrupted_manifest["sample_count"] = 999
    canonical_manifest_path.write_text(json.dumps(corrupted_manifest), encoding="utf-8")
    with (
        pytest.warns(DeprecationWarning),
        pytest.raises(AssertionError, match="resume=True must reuse"),
    ):
        workflow.run(manifest, tmp_path, db_registry=registry, resume=True)
    canonical_manifest_path.write_text(canonical_manifest_text, encoding="utf-8")

    corrupted_manifest = json.loads(canonical_manifest_text)
    corrupted_manifest["artifacts"]["species_table"] = str(tmp_path / "missing.tsv")
    canonical_manifest_path.write_text(json.dumps(corrupted_manifest), encoding="utf-8")
    with (
        pytest.warns(DeprecationWarning),
        pytest.raises(AssertionError, match="resume=True must reuse"),
    ):
        workflow.run(manifest, tmp_path, db_registry=registry, resume=True)
    canonical_manifest_path.write_text(canonical_manifest_text, encoding="utf-8")

    corrupted_manifest = json.loads(canonical_manifest_text)
    taxonomy_entry = corrupted_manifest["standard_tables"]["taxonomy_abundance"]
    qc_entry = corrupted_manifest["standard_tables"]["qc_summary"]
    taxonomy_entry.update(qc_entry)
    corrupted_manifest["consistency"]["standard_row_count"] = sum(
        entry["rows"] for entry in corrupted_manifest["standard_tables"].values()
    )
    canonical_manifest_path.write_text(json.dumps(corrupted_manifest), encoding="utf-8")
    with (
        pytest.warns(DeprecationWarning),
        pytest.raises(AssertionError, match="resume=True must reuse"),
    ):
        workflow.run(manifest, tmp_path, db_registry=registry, resume=True)
    canonical_manifest_path.write_text(canonical_manifest_text, encoding="utf-8")

    with (
        pytest.warns(DeprecationWarning),
        pytest.raises(AssertionError, match="resume=True must reuse"),
    ):
        workflow.run(manifest, tmp_path, db_registry=registry, threads=8, resume=True)

    (tmp_path / "result/provenance/config.resolved.yaml").unlink()
    with (
        pytest.warns(DeprecationWarning),
        pytest.raises(AssertionError, match="resume=True must reuse"),
    ):
        workflow.run(manifest, tmp_path, db_registry=registry, resume=True)


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

    coordinator = WorkflowCoordinator()
    prepared = coordinator.prepare(
        "easymetagenome",
        overrides={
            "input": {"sample_sheet": str(manifest)},
            "workflow": {"preset": "p1_humann4"},
            "resources": resources,
            "threads": 1,
            "outdir": str(tmp_path / "result"),
            "log_dir": str(tmp_path / "logs"),
        },
        options=RuntimeOptions(engine="local", check_runtime=False),
    )
    runtime_result = coordinator.run(prepared)
    outputs = runtime_result.outputs

    summary = json.loads(outputs["summary"].read_text(encoding="utf-8"))
    assert summary["status"] == "success"
    assert summary["completed_step_count"] == len(prepared.plan.steps)
    functional_table = Path(prepared.config["outdir"]) / "tables/functional_abundance.tsv"
    assert len(functional_table.read_text(encoding="utf-8").splitlines()) > 1
    assert outputs["report_markdown"] == (
        Path(prepared.config["outdir"]) / "report/easymetagenome_functional_report.md"
    )
    manifest_payload = json.loads(outputs["report_manifest"].read_text(encoding="utf-8"))
    _assert_matches_canonical_report_schema(manifest_payload)
    assert manifest_payload["schema_version"] == "abi.report-manifest.v1"
    assert manifest_payload["workflow"] == "p1_humann4"
    assert manifest_payload["standard_tables"]["functional_abundance"] == {
        "path": str(functional_table),
        "rows": 10,
    }
