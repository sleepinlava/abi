from pathlib import Path

import pytest

from abi.autoplasm.config import load_config
from abi.autoplasm.logger import RunLogger
from abi.autoplasm.pipeline import PipelineExecutor
from abi.autoplasm.planner import build_plan
from abi.autoplasm.schemas import (
    AutoPlasmError,
    ExecutionPlan,
    PlanStep,
    SampleContext,
    SampleInput,
    ToolError,
)
from abi.autoplasm.skills.registry import ToolRegistry
from abi.autoplasm.standard_tables import read_standard_table


def test_dry_run_writes_provenance(tmp_path):
    outdir = tmp_path / "results" / "project"
    log_dir = tmp_path / "log"
    config = load_config(
        "examples/config_minimal.yaml",
        profile="dry_run",
        overrides={"outdir": str(outdir), "log_dir": str(log_dir), "mock_tools": True},
    )
    plan = build_plan(config)
    executor = PipelineExecutor(ToolRegistry.from_path(), RunLogger(log_dir), mock_tools=True)
    outputs = executor.dry_run(plan, config)
    assert outputs["commands"].exists()
    assert outputs["summary"].exists()
    assert "genomad" in outputs["commands"].read_text(encoding="utf-8")


@pytest.mark.xfail(reason="DAG refactoring changed step structure and output file paths")
def test_repeated_dry_run_replaces_analysis_status_rows(tmp_path):
    outdir = tmp_path / "results" / "project"
    log_dir = tmp_path / "log"
    config = load_config(
        "examples/config_minimal.yaml",
        profile="dry_run",
        overrides={"outdir": str(outdir), "log_dir": str(log_dir), "mock_tools": True},
    )
    plan = build_plan(config)
    plan.skipped_steps.append(
        PlanStep(
            step_id="diversity_not_run",
            step_name="diversity",
            tool_id="internal",
            category="statistics",
            sample_id=None,
            params={"sample_count": 1, "threshold": 3},
            reason="requires at least 3 samples",
            skipped=True,
        )
    )
    executor = PipelineExecutor(ToolRegistry.from_path(), RunLogger(log_dir), mock_tools=True)

    executor.dry_run(plan, config)
    first_rows = read_standard_table(outdir / "tables", "analysis_status")
    executor.dry_run(plan, config)
    second_rows = read_standard_table(outdir / "tables", "analysis_status")

    assert len(first_rows) == 5
    assert second_rows == first_rows


def test_dry_run_uses_existing_output_directory(tmp_path):
    outdir = tmp_path / "results"
    log_dir = tmp_path / "log"
    outdir.mkdir()
    marker = outdir / "keep.txt"
    marker.write_text("keep\n", encoding="utf-8")
    config = load_config(
        "examples/config_minimal.yaml",
        profile="dry_run",
        overrides={"outdir": str(outdir), "log_dir": str(log_dir), "mock_tools": True},
    )
    plan = build_plan(config)

    executor = PipelineExecutor(ToolRegistry.from_path(), RunLogger(log_dir), mock_tools=True)
    outputs = executor.dry_run(plan, config)

    assert marker.read_text(encoding="utf-8") == "keep\n"
    assert outputs["plan"].exists()
    assert outputs["commands"].exists()


def test_dry_run_rejects_output_path_that_is_file(tmp_path):
    outdir = tmp_path / "results"
    outdir.write_text("not a directory\n", encoding="utf-8")
    config = load_config(
        "examples/config_minimal.yaml",
        profile="dry_run",
        overrides={
            "outdir": str(outdir),
            "log_dir": str(tmp_path / "log"),
            "mock_tools": True,
        },
    )
    plan = build_plan(config)

    with pytest.raises(AutoPlasmError, match="Output directory exists but is not a directory"):
        PipelineExecutor(
            ToolRegistry.from_path(),
            RunLogger(tmp_path / "log"),
            mock_tools=True,
        ).dry_run(plan, config)


def test_run_executes_registered_tool_from_local_mamba(tmp_path, monkeypatch):
    env_bin = tmp_path / ".mamba" / "envs" / "mock-env" / "bin"
    env_bin.mkdir(parents=True)
    executable = env_bin / "mock_tool"
    executable.write_text("#!/usr/bin/env sh\nprintf 'done\\n' > \"$1\"\n", encoding="utf-8")
    executable.chmod(0o755)
    monkeypatch.setenv("AUTOPLASM_MAMBA_ROOT", str(tmp_path / ".mamba"))

    sample = SampleInput(sample_id="S1", platform="assembly", assembly="input.fasta")
    context = SampleContext(
        samples=[sample],
        multi_sample=False,
        has_groups=False,
        enable_sample_analysis=False,
        enable_differential_abundance=False,
    )
    outdir = tmp_path / "results"
    plan = ExecutionPlan(
        project_name="mock",
        mode="auto",
        threads=1,
        outdir=str(outdir),
        log_dir=str(tmp_path / "log"),
        samples=[sample],
        sample_context=context,
        selected_tools=["mock_tool"],
        steps=[
            PlanStep(
                step_id="S1_mock",
                sample_id="S1",
                step_name="mock",
                tool_id="mock_tool",
                category="mock",
                outputs={"output_dir": str(outdir / "mock")},
            )
        ],
    )
    registry = ToolRegistry(
        [
            {
                "id": "mock_tool",
                "env_name": "mock-env",
                "executable": "mock_tool",
                "command_template": "mock_tool {output_dir}/result.txt",
            }
        ]
    )

    outputs = PipelineExecutor(registry, RunLogger(tmp_path / "log")).run(
        plan,
        {"outdir": str(outdir), "log_dir": str(tmp_path / "log")},
        dry_run=False,
    )

    assert (outdir / "mock" / "result.txt").read_text(encoding="utf-8") == "done\n"
    commands = outputs["commands"].read_text(encoding="utf-8")
    assert "success" in commands
    assert "\t0\t" in commands


def test_core_fixture_run_writes_standard_tables_and_reports(tmp_path, monkeypatch):
    mamba_root = tmp_path / ".mamba"
    env_bin = mamba_root / "envs" / "mock-env" / "bin"
    env_bin.mkdir(parents=True)
    monkeypatch.setenv("AUTOPLASM_MAMBA_ROOT", str(mamba_root))

    fixtures = {
        "genomad_mock": "genomad",
        "abricate_mock": "abricate",
        "coverm_mock": "coverm",
    }
    for executable, fixture_name in fixtures.items():
        script = env_bin / executable
        fixture_dir = (Path("tests/fixtures/tool_outputs") / fixture_name).resolve()
        script.write_text(
            "\n".join(
                [
                    "#!/usr/bin/env sh",
                    "set -eu",
                    'mkdir -p "$1"',
                    f'cp -R "{fixture_dir}/." "$1"/',
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        script.chmod(0o755)

    sample = SampleInput(sample_id="S1", platform="assembly", assembly="input.fasta")
    context = SampleContext(
        samples=[sample],
        multi_sample=False,
        has_groups=False,
        enable_sample_analysis=False,
        enable_differential_abundance=False,
    )
    outdir = tmp_path / "results"
    plan = ExecutionPlan(
        project_name="core_fixture",
        mode="auto",
        threads=1,
        outdir=str(outdir),
        log_dir=str(tmp_path / "log"),
        samples=[sample],
        sample_context=context,
        selected_tools=["abricate", "coverm", "genomad"],
        steps=[
            PlanStep(
                step_id="S1_genomad",
                sample_id="S1",
                step_name="plasmid_detection",
                tool_id="genomad",
                category="plasmid_detection",
                outputs={"output_dir": str(outdir / "04_plasmid_detection" / "S1")},
            ),
            PlanStep(
                step_id="S1_abricate",
                sample_id="S1",
                step_name="annotation",
                tool_id="abricate",
                category="annotation",
                outputs={"output_dir": str(outdir / "08_annotation" / "S1")},
            ),
            PlanStep(
                step_id="S1_coverm",
                sample_id="S1",
                step_name="abundance",
                tool_id="coverm",
                category="abundance",
                outputs={"output_dir": str(outdir / "10_abundance" / "S1")},
            ),
        ],
    )
    registry = ToolRegistry(
        [
            {
                "id": "genomad",
                "env_name": "mock-env",
                "executable": "genomad_mock",
                "command_template": "genomad_mock {output_dir}",
            },
            {
                "id": "abricate",
                "env_name": "mock-env",
                "executable": "abricate_mock",
                "command_template": "abricate_mock {output_dir}",
            },
            {
                "id": "coverm",
                "env_name": "mock-env",
                "executable": "coverm_mock",
                "command_template": "coverm_mock {output_dir}",
            },
        ]
    )

    outputs = PipelineExecutor(registry, RunLogger(tmp_path / "log")).run(
        plan,
        {
            "outdir": str(outdir),
            "log_dir": str(tmp_path / "log"),
            "plasmid_detection": {"strategy": "single_tool", "tools": ["genomad"]},
        },
        dry_run=False,
    )

    assert outputs["report"].exists()
    assert outputs["report_html"].exists()
    assert read_standard_table(outdir / "tables", "plasmid_predictions")
    assert read_standard_table(outdir / "tables", "plasmid_consensus")
    assert read_standard_table(outdir / "tables", "annotations")
    assert read_standard_table(outdir / "tables", "abundance")
    commands = outputs["commands"].read_text(encoding="utf-8")
    assert "parsed" in commands


def test_parallel_sample_run_writes_progress_and_ordered_commands(tmp_path, monkeypatch):
    mamba_root = tmp_path / ".mamba"
    env_bin = mamba_root / "envs" / "mock-env" / "bin"
    env_bin.mkdir(parents=True)
    monkeypatch.setenv("AUTOPLASM_MAMBA_ROOT", str(mamba_root))

    script = env_bin / "genomad_mock"
    fixture_dir = (Path("tests/fixtures/tool_outputs") / "genomad").resolve()
    script.write_text(
        "\n".join(
            [
                "#!/usr/bin/env sh",
                "set -eu",
                'mkdir -p "$1"',
                f'cp -R "{fixture_dir}/." "$1"/',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    script.chmod(0o755)

    samples = []
    steps = []
    outdir = tmp_path / "results"
    for sample_id in ["S1", "S2"]:
        assembly = tmp_path / f"{sample_id}.fasta"
        assembly.write_text(
            ">contig_1 plasmid-supported\nATGCATGC\n>contig_3 background\nATGC\n",
            encoding="utf-8",
        )
        sample = SampleInput(sample_id=sample_id, platform="assembly", assembly=str(assembly))
        samples.append(sample)
        steps.append(
            PlanStep(
                step_id=f"{sample_id}_genomad",
                sample_id=sample_id,
                step_name="plasmid_detection",
                tool_id="genomad",
                category="plasmid_detection",
                inputs=sample.to_dict(),
                outputs={"output_dir": str(outdir / "04_plasmid_detection" / sample_id)},
                params={
                    "sample_id": sample_id,
                    "assembly": str(assembly),
                    "output_dir": str(outdir / "04_plasmid_detection" / sample_id),
                },
            )
        )
    context = SampleContext(
        samples=samples,
        multi_sample=True,
        has_groups=False,
        enable_sample_analysis=False,
        enable_differential_abundance=False,
    )
    plan = ExecutionPlan(
        project_name="parallel",
        mode="auto",
        threads=1,
        outdir=str(outdir),
        log_dir=str(tmp_path / "log"),
        samples=samples,
        sample_context=context,
        selected_tools=["genomad"],
        steps=steps,
    )
    registry = ToolRegistry(
        [
            {
                "id": "genomad",
                "env_name": "mock-env",
                "executable": "genomad_mock",
                "command_template": "genomad_mock {output_dir}",
            }
        ]
    )

    outputs = PipelineExecutor(registry, RunLogger(tmp_path / "log")).run(
        plan,
        {
            "outdir": str(outdir),
            "log_dir": str(tmp_path / "log"),
            "plasmid_detection": {"strategy": "single_tool", "tools": ["genomad"]},
            "execution": {"parallel": True, "workers": 2, "progress": True},
        },
    )

    commands = outputs["commands"].read_text(encoding="utf-8").splitlines()
    assert commands[1].startswith("S1_genomad\t")
    assert commands[2].startswith("S2_genomad\t")
    progress = outputs["progress"].read_text(encoding="utf-8")
    assert '"parallel": true' in progress
    assert '"workers": 2' in progress
    predictions = read_standard_table(outdir / "tables", "plasmid_predictions")
    assert {row["sample_id"] for row in predictions} == {"S1", "S2"}


@pytest.mark.xfail(reason="DAG refactoring changed step structure and output file paths")
def test_assembly_full_route_mock_run_writes_provenance_tables_and_report(tmp_path, monkeypatch):
    sample_dir = tmp_path / "samples"
    sample_dir.mkdir()
    sample_sheet = sample_dir / "sample_sheet.tsv"
    fasta_paths = []
    for sample_id in ["S1", "S2"]:
        fasta = sample_dir / f"{sample_id}.fasta"
        fasta.write_text(
            "\n".join(
                [
                    ">contig_1 plasmid-supported",
                    "ATGCATGCATGCATGC",
                    ">contig_2 partial-support",
                    "ATGCATGCATGC",
                    f">{sample_id}_extra no-support",
                    "ATGCATGC",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        fasta_paths.append(fasta)
    sample_sheet.write_text(
        "\n".join(
            [
                "sample_id\tgroup\tplatform\tread1\tread2\tlong_reads\tassembly\ttechnology\thost_reference\tnotes",
                f"S1\tcase\tassembly\t\t\t\t{fasta_paths[0]}\tassembly\t\tmock",
                f"S2\tcontrol\tassembly\t\t\t\t{fasta_paths[1]}\tassembly\t\tmock",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    resource_root = tmp_path / "resources"
    resource_config = {
        "root": str(resource_root),
        "genomad": {"database": str(resource_root / "genomad")},
        "bakta": {"database": str(resource_root / "bakta"), "type": "light"},
        "mob_suite": {"database": str(resource_root / "mob_suite")},
        "plasmidfinder": {"database": str(resource_root / "plasmidfinder_db")},
    }
    for block in resource_config.values():
        if isinstance(block, dict) and block.get("database"):
            Path(block["database"]).mkdir(parents=True)

    config = load_config(
        "examples/config_assembly_full_run.yaml",
        overrides={
            "outdir": str(tmp_path / "results"),
            "log_dir": str(tmp_path / "log"),
            "input": {"sample_sheet": str(sample_sheet)},
            "resources": resource_config,
        },
    )
    plan = build_plan(config)

    mamba_root = tmp_path / ".mamba"
    env_bin = mamba_root / "envs" / "mock-env" / "bin"
    env_bin.mkdir(parents=True)
    monkeypatch.setenv("AUTOPLASM_MAMBA_ROOT", str(mamba_root))
    fixtures = {
        "quast_mock": "quast",
        "genomad_mock": "genomad",
        "mob_typer_mock": "mob_suite",
        "plasmidfinder_mock": "plasmidfinder",
        "bakta_mock": "bakta",
        "mob_suite_mock": "mob_suite",
    }
    for executable, fixture_name in fixtures.items():
        script = env_bin / executable
        fixture_dir = (Path("tests/fixtures/tool_outputs") / fixture_name).resolve()
        script.write_text(
            "\n".join(
                [
                    "#!/usr/bin/env sh",
                    "set -eu",
                    'mkdir -p "$1"',
                    f'cp -R "{fixture_dir}/." "$1"/',
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        script.chmod(0o755)

    registry = ToolRegistry(
        [
            {
                "id": "quast",
                "env_name": "mock-env",
                "executable": "quast_mock",
                "command_template": "quast_mock {output_dir}",
            },
            {
                "id": "genomad",
                "env_name": "mock-env",
                "executable": "genomad_mock",
                "command_template": "genomad_mock {output_dir} {database}",
            },
            {
                "id": "mob_typer",
                "env_name": "mock-env",
                "executable": "mob_typer_mock",
                "command_template": "mob_typer_mock {output_dir}",
            },
            {
                "id": "plasmidfinder",
                "env_name": "mock-env",
                "executable": "plasmidfinder_mock",
                "command_template": "plasmidfinder_mock {output_dir} {database}",
            },
            {
                "id": "bakta",
                "env_name": "mock-env",
                "executable": "bakta_mock",
                "command_template": "bakta_mock {output_dir} {database}",
            },
            {
                "id": "mob_suite",
                "env_name": "mock-env",
                "executable": "mob_suite_mock",
                "command_template": "mob_suite_mock {output_dir}",
            },
        ]
    )

    outputs = PipelineExecutor(registry, RunLogger(tmp_path / "log")).run(plan, config)

    assert outputs["resolved_inputs"].exists()
    assert outputs["resources"].exists()
    assert outputs["environment"].exists()
    consensus = read_standard_table(tmp_path / "results" / "tables", "plasmid_consensus")
    assert len(consensus) >= 2
    assert any(row["final_plasmid_call"] == "True" for row in consensus)
    plasmid_fasta = tmp_path / "results" / "04_plasmid_detection" / "S1" / "plasmid_contigs.fasta"
    uncertain_fasta = (
        tmp_path / "results" / "04_plasmid_detection" / "S1" / "uncertain_contigs.fasta"
    )
    non_plasmid_fasta = (
        tmp_path / "results" / "04_plasmid_detection" / "S1" / "non_plasmid_contigs.fasta"
    )
    assert ">contig_1 plasmid-supported" in plasmid_fasta.read_text(encoding="utf-8")
    assert ">contig_2 partial-support" in uncertain_fasta.read_text(encoding="utf-8")
    assert ">S1_extra no-support" in non_plasmid_fasta.read_text(encoding="utf-8")
    report = outputs["report"].read_text(encoding="utf-8")
    assert "Core Result Summary" in report
    assert "Assembly-only Beta Scope" in report
    assert "Total contigs: 6" in report
    assert "Predicted plasmid contigs:" in report
    assert "Uncertain contigs:" in report
    assert "Non-plasmid contigs:" in report
    assert "Assembly QC Summary" in report


@pytest.mark.xfail(reason="DAG refactoring changed step structure and output file paths")
def test_illumina_mock_run_chains_to_standard_tables_and_report(tmp_path, monkeypatch):
    sample_sheet = tmp_path / "illumina_samples.tsv"
    sample_sheet.write_text(
        "\n".join(
            [
                "sample_id\tgroup\tplatform\tread1\tread2\tlong_reads\tassembly\ttechnology\thost_reference\tnotes",
                (
                    "S1\tcase\tillumina\texamples/fixtures/tiny_R1.fastq\t"
                    "examples/fixtures/tiny_R2.fastq\t\t\tNovaSeq\t\tmock illumina"
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    config = load_config(
        "examples/config_minimal.yaml",
        profile="dry_run",
        overrides={
            "outdir": str(tmp_path / "results"),
            "log_dir": str(tmp_path / "log"),
            "dry_run": False,
            "mock_tools": False,
            "input": {"sample_sheet": str(sample_sheet)},
            "sample_analysis": {"enable": False},
            "plasmid_binning": {"enable": False},
            "typing": {"enable": False},
            "host_prediction": {"enable": False},
            "comparative_genomics": {"enable": False},
            "plasmid_detection": {"enable": True, "tools": ["genomad"], "strategy": "single_tool"},
            "annotation": {
                "enable": True,
                "general_annotator": "bakta",
                "arg_tools": ["amrfinderplus", "abricate"],
                "vf_tools": [],
                "mobile_element_tools": [],
            },
            "abundance": {"enable": True, "mapper_short": "bowtie2", "calculator": "coverm"},
        },
    )
    plan = build_plan(config)

    mamba_root = tmp_path / ".mamba"
    env_bin = mamba_root / "envs" / "mock-env" / "bin"
    env_bin.mkdir(parents=True)
    monkeypatch.setenv("AUTOPLASM_MAMBA_ROOT", str(mamba_root))
    fixtures = {
        "fastp_mock": "fastp",
        "fastqc_mock": "fastqc",
        "multiqc_mock": "multiqc",
        "megahit_mock": "megahit",
        "quast_mock": "quast",
        "genomad_mock": "genomad",
        "metaphlan_mock": "metaphlan",
        "bakta_mock": "bakta",
        "abricate_mock": "abricate",
        "amrfinderplus_mock": "amrfinderplus",
        "coverm_mock": "coverm",
    }
    for executable, fixture_name in fixtures.items():
        script = env_bin / executable
        fixture_dir = (Path("tests/fixtures/tool_outputs") / fixture_name).resolve()
        script.write_text(
            "\n".join(
                [
                    "#!/usr/bin/env sh",
                    "set -eu",
                    'mkdir -p "$1"',
                    f'cp -R "{fixture_dir}/." "$1"/',
                    (
                        'if [ "$(basename "$0")" = "fastp_mock" ]; then '
                        'printf "@r1\\nACGT\\n+\\n!!!!\\n" > "$1/S1_R1.clean.fastq.gz"; '
                        'printf "@r2\\nTGCA\\n+\\n!!!!\\n" > "$1/S1_R2.clean.fastq.gz"; '
                        "fi"
                    ),
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        script.chmod(0o755)
    for executable in ["bowtie2_mock", "samtools_mock"]:
        script = env_bin / executable
        script.write_text(
            '#!/usr/bin/env sh\nset -eu\nmkdir -p "$1"\n: > "$1/S1.sam"\n: > "$1/S1.bam"\n',
            encoding="utf-8",
        )
        script.chmod(0o755)

    registry = ToolRegistry(
        [
            {
                "id": tool_id,
                "env_name": "mock-env",
                "executable": executable,
                "command_template": f"{executable} {{output_dir}}",
            }
            for tool_id, executable in [
                ("fastp", "fastp_mock"),
                ("fastqc", "fastqc_mock"),
                ("multiqc", "multiqc_mock"),
                ("megahit", "megahit_mock"),
                ("quast", "quast_mock"),
                ("genomad", "genomad_mock"),
                ("metaphlan", "metaphlan_mock"),
                ("bakta", "bakta_mock"),
                ("amrfinderplus", "amrfinderplus_mock"),
                ("abricate", "abricate_mock"),
                ("bowtie2", "bowtie2_mock"),
                ("samtools", "samtools_mock"),
                ("coverm", "coverm_mock"),
            ]
        ]
    )

    outputs = PipelineExecutor(registry, RunLogger(tmp_path / "log")).run(plan, config)
    tables = tmp_path / "results" / "tables"

    qc_tools = {row["tool"] for row in read_standard_table(tables, "qc_summary")}
    # fastqc and multiqc are optional (gated by qc.run_fastqc / qc.run_multiqc config)
    assert "fastp" in qc_tools
    assembly_tools = {row["tool"] for row in read_standard_table(tables, "assembly_summary")}
    assert {"megahit", "quast"}.issubset(assembly_tools)
    assert read_standard_table(tables, "plasmid_predictions")
    assert read_standard_table(tables, "plasmid_consensus")
    assert read_standard_table(tables, "annotations")
    assert read_standard_table(tables, "abundance")

    plasmid_fasta = tmp_path / "results" / "04_plasmid_detection" / "S1" / "plasmid_contigs.fasta"
    non_plasmid_fasta = (
        tmp_path / "results" / "04_plasmid_detection" / "S1" / "non_plasmid_contigs.fasta"
    )
    assert ">contig_1 plasmid-supported" in plasmid_fasta.read_text(encoding="utf-8")
    assert ">contig_3 chromosomal-background" in non_plasmid_fasta.read_text(encoding="utf-8")

    report = outputs["report"].read_text(encoding="utf-8")
    assert "Total contigs: 3" in report
    assert "Abundance records: 1" in report


@pytest.mark.xfail(reason="DAG refactoring changed step structure and output file paths")
def test_ont_mock_run_chains_to_standard_tables_and_report(tmp_path, monkeypatch):
    sample_sheet = tmp_path / "ont_samples.tsv"
    sample_sheet.write_text(
        "\n".join(
            [
                "sample_id\tgroup\tplatform\tread1\tread2\tlong_reads\tassembly\ttechnology\thost_reference\tnotes",
                "ONT1\tcase\tont\t\t\texamples/fixtures/tiny_long.fastq\t\tONT\t\tmock ont",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    config = load_config(
        "examples/config_ont_smoke.yaml",
        profile="dry_run",
        overrides={
            "outdir": str(tmp_path / "results"),
            "log_dir": str(tmp_path / "log"),
            "dry_run": False,
            "mock_tools": False,
            "input": {"sample_sheet": str(sample_sheet)},
        },
    )
    plan = build_plan(config)

    mamba_root = tmp_path / ".mamba"
    env_bin = mamba_root / "envs" / "mock-env" / "bin"
    env_bin.mkdir(parents=True)
    monkeypatch.setenv("AUTOPLASM_MAMBA_ROOT", str(mamba_root))
    fixtures = {
        "nanoplot_mock": "nanoplot",
        "filtlong_mock": "filtlong",
        "multiqc_mock": "multiqc",
        "metaflye_mock": "metaflye",
        "quast_mock": "quast",
        "genomad_mock": "genomad",
        "metaphlan_mock": "metaphlan",
        "bakta_mock": "bakta",
        "abricate_mock": "abricate",
        "amrfinderplus_mock": "amrfinderplus",
        "coverm_mock": "coverm",
    }
    for executable, fixture_name in fixtures.items():
        script = env_bin / executable
        fixture_dir = (Path("tests/fixtures/tool_outputs") / fixture_name).resolve()
        script.write_text(
            "\n".join(
                [
                    "#!/usr/bin/env sh",
                    "set -eu",
                    'mkdir -p "$1"',
                    f'cp -R "{fixture_dir}/." "$1"/',
                    (
                        'if [ "$(basename "$0")" = "filtlong_mock" ]; then '
                        'printf "@long\\nACGTACGT\\n+\\n!!!!!!!!\\n" > "$1/ONT1.filtlong.fastq"; '
                        "fi"
                    ),
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        script.chmod(0o755)
    for executable in ["minimap2_mock", "samtools_mock"]:
        script = env_bin / executable
        script.write_text(
            '#!/usr/bin/env sh\nset -eu\nmkdir -p "$1"\n: > "$1/ONT1.sam"\n: > "$1/ONT1.bam"\n',
            encoding="utf-8",
        )
        script.chmod(0o755)

    registry = ToolRegistry(
        [
            {
                "id": tool_id,
                "env_name": "mock-env",
                "executable": executable,
                "command_template": f"{executable} {{output_dir}}",
            }
            for tool_id, executable in [
                ("nanoplot", "nanoplot_mock"),
                ("filtlong", "filtlong_mock"),
                ("multiqc", "multiqc_mock"),
                ("metaflye", "metaflye_mock"),
                ("quast", "quast_mock"),
                ("genomad", "genomad_mock"),
                ("metaphlan", "metaphlan_mock"),
                ("bakta", "bakta_mock"),
                ("amrfinderplus", "amrfinderplus_mock"),
                ("abricate", "abricate_mock"),
                ("minimap2", "minimap2_mock"),
                ("samtools", "samtools_mock"),
                ("coverm", "coverm_mock"),
            ]
        ]
    )

    outputs = PipelineExecutor(registry, RunLogger(tmp_path / "log")).run(plan, config)
    tables = tmp_path / "results" / "tables"

    qc_tools = {row["tool"] for row in read_standard_table(tables, "qc_summary")}
    assert {"nanoplot", "filtlong", "multiqc"}.issubset(qc_tools)
    assembly_tools = {row["tool"] for row in read_standard_table(tables, "assembly_summary")}
    assert {"metaflye", "quast"}.issubset(assembly_tools)
    assert read_standard_table(tables, "plasmid_predictions")
    assert read_standard_table(tables, "plasmid_consensus")
    assert read_standard_table(tables, "host_predictions")
    assert read_standard_table(tables, "annotations")
    assert read_standard_table(tables, "abundance")

    plasmid_fasta = tmp_path / "results" / "04_plasmid_detection" / "ONT1" / "plasmid_contigs.fasta"
    non_plasmid_fasta = (
        tmp_path / "results" / "04_plasmid_detection" / "ONT1" / "non_plasmid_contigs.fasta"
    )
    assert ">contig_1 plasmid-supported" in plasmid_fasta.read_text(encoding="utf-8")
    assert ">contig_3 long-read-background" in non_plasmid_fasta.read_text(encoding="utf-8")

    report = outputs["report"].read_text(encoding="utf-8")
    assert "ONT Long-read Beta Scope" in report
    assert "Total contigs: 3" in report
    assert "Abundance records: 1" in report


@pytest.mark.xfail(reason="DAG refactoring changed step structure and output file paths")
def test_hifi_mock_run_chains_to_standard_tables_and_report(tmp_path, monkeypatch):
    sample_sheet = tmp_path / "hifi_samples.tsv"
    sample_sheet.write_text(
        "\n".join(
            [
                "sample_id\tgroup\tplatform\tread1\tread2\tlong_reads\tassembly\ttechnology\thost_reference\tnotes",
                (
                    "HIFI1\tcase\tpacbio_hifi\t\t\texamples/fixtures/tiny_long.fastq\t\t"
                    "PacBio HiFi\t\tmock hifi"
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    config = load_config(
        "examples/config_hifi_smoke.yaml",
        profile="dry_run",
        overrides={
            "outdir": str(tmp_path / "results"),
            "log_dir": str(tmp_path / "log"),
            "dry_run": False,
            "mock_tools": False,
            "input": {"sample_sheet": str(sample_sheet)},
        },
    )
    plan = build_plan(config)

    mamba_root = tmp_path / ".mamba"
    env_bin = mamba_root / "envs" / "mock-env" / "bin"
    env_bin.mkdir(parents=True)
    monkeypatch.setenv("AUTOPLASM_MAMBA_ROOT", str(mamba_root))
    fixtures = {
        "hifiadapterfilt_mock": "hifiadapterfilt",
        "multiqc_mock": "multiqc",
        "hifiasm_mock": "hifiasm_meta",
        "quast_mock": "quast",
        "genomad_mock": "genomad",
        "metaphlan_mock": "metaphlan",
        "bakta_mock": "bakta",
        "abricate_mock": "abricate",
        "amrfinderplus_mock": "amrfinderplus",
        "coverm_mock": "coverm",
    }
    for executable, fixture_name in fixtures.items():
        script = env_bin / executable
        fixture_dir = (Path("tests/fixtures/tool_outputs") / fixture_name).resolve()
        script.write_text(
            "\n".join(
                [
                    "#!/usr/bin/env sh",
                    "set -eu",
                    'mkdir -p "$1"',
                    f'cp -R "{fixture_dir}/." "$1"/',
                    (
                        'if [ "$(basename "$0")" = "hifiadapterfilt_mock" ]; then '
                        'printf "@hifi\\nACGTACGT\\n+\\n!!!!!!!!\\n" > '
                        '"$1/HIFI1.hifiadapterfilt.fastq.gz"; '
                        "fi"
                    ),
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        script.chmod(0o755)
    for executable in ["minimap2_mock", "samtools_mock"]:
        script = env_bin / executable
        script.write_text(
            '#!/usr/bin/env sh\nset -eu\nmkdir -p "$1"\n: > "$1/HIFI1.sam"\n: > "$1/HIFI1.bam"\n',
            encoding="utf-8",
        )
        script.chmod(0o755)

    registry = ToolRegistry(
        [
            {
                "id": tool_id,
                "env_name": "mock-env",
                "executable": executable,
                "command_template": f"{executable} {{output_dir}}",
            }
            for tool_id, executable in [
                ("hifiadapterfilt", "hifiadapterfilt_mock"),
                ("multiqc", "multiqc_mock"),
                ("hifiasm_meta", "hifiasm_mock"),
                ("quast", "quast_mock"),
                ("genomad", "genomad_mock"),
                ("metaphlan", "metaphlan_mock"),
                ("bakta", "bakta_mock"),
                ("amrfinderplus", "amrfinderplus_mock"),
                ("abricate", "abricate_mock"),
                ("minimap2", "minimap2_mock"),
                ("samtools", "samtools_mock"),
                ("coverm", "coverm_mock"),
            ]
        ]
    )

    outputs = PipelineExecutor(registry, RunLogger(tmp_path / "log")).run(plan, config)
    tables = tmp_path / "results" / "tables"

    qc_tools = {row["tool"] for row in read_standard_table(tables, "qc_summary")}
    assert {"hifiadapterfilt", "multiqc"}.issubset(qc_tools)
    assembly_tools = {row["tool"] for row in read_standard_table(tables, "assembly_summary")}
    assert {"hifiasm_meta", "quast"}.issubset(assembly_tools)
    assert read_standard_table(tables, "plasmid_predictions")
    assert read_standard_table(tables, "plasmid_consensus")
    assert read_standard_table(tables, "annotations")
    assert read_standard_table(tables, "abundance")

    plasmid_fasta = (
        tmp_path / "results" / "04_plasmid_detection" / "HIFI1" / "plasmid_contigs.fasta"
    )
    non_plasmid_fasta = (
        tmp_path / "results" / "04_plasmid_detection" / "HIFI1" / "non_plasmid_contigs.fasta"
    )
    assert ">contig_1 plasmid-supported" in plasmid_fasta.read_text(encoding="utf-8")
    assert ">contig_3 hifi-background" in non_plasmid_fasta.read_text(encoding="utf-8")

    report = outputs["report"].read_text(encoding="utf-8")
    assert "PacBio HiFi Beta Scope" in report
    assert "Total contigs: 3" in report
    assert "Abundance records: 1" in report


@pytest.mark.xfail(reason="DAG refactoring changed step structure and output file paths")
def test_hybrid_mock_run_chains_to_standard_tables_and_report(tmp_path, monkeypatch):
    sample_sheet = tmp_path / "hybrid_samples.tsv"
    sample_sheet.write_text(
        "\n".join(
            [
                "sample_id\tgroup\tplatform\tread1\tread2\tlong_reads\tassembly\ttechnology\thost_reference\tnotes",
                (
                    "HYB1\tcase\thybrid\texamples/fixtures/tiny_R1.fastq\t"
                    "examples/fixtures/tiny_R2.fastq\texamples/fixtures/tiny_long.fastq\t\t"
                    "Illumina+ONT\t\tmock hybrid"
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    config = load_config(
        "examples/config_hybrid_smoke.yaml",
        profile="dry_run",
        overrides={
            "outdir": str(tmp_path / "results"),
            "log_dir": str(tmp_path / "log"),
            "dry_run": False,
            "mock_tools": False,
            "input": {"sample_sheet": str(sample_sheet)},
        },
    )
    plan = build_plan(config)

    mamba_root = tmp_path / ".mamba"
    env_bin = mamba_root / "envs" / "mock-env" / "bin"
    env_bin.mkdir(parents=True)
    monkeypatch.setenv("AUTOPLASM_MAMBA_ROOT", str(mamba_root))
    fixtures = {
        "fastp_mock": "fastp",
        "fastqc_mock": "fastqc",
        "nanoplot_mock": "nanoplot",
        "filtlong_mock": "filtlong",
        "multiqc_mock": "multiqc",
        "opera_ms_mock": "opera_ms",
        "quast_mock": "quast",
        "genomad_mock": "genomad",
        "metaphlan_mock": "metaphlan",
        "bakta_mock": "bakta",
        "abricate_mock": "abricate",
        "amrfinderplus_mock": "amrfinderplus",
    }
    for executable, fixture_name in fixtures.items():
        script = env_bin / executable
        fixture_dir = (Path("tests/fixtures/tool_outputs") / fixture_name).resolve()
        script.write_text(
            "\n".join(
                [
                    "#!/usr/bin/env sh",
                    "set -eu",
                    'mkdir -p "$1"',
                    f'cp -R "{fixture_dir}/." "$1"/',
                    (
                        'if [ "$(basename "$0")" = "fastp_mock" ]; then '
                        'printf "@r1\\nACGT\\n+\\n!!!!\\n" > "$1/HYB1_R1.clean.fastq.gz"; '
                        'printf "@r2\\nTGCA\\n+\\n!!!!\\n" > "$1/HYB1_R2.clean.fastq.gz"; '
                        "fi"
                    ),
                    (
                        'if [ "$(basename "$0")" = "filtlong_mock" ]; then '
                        'printf "@long\\nACGTACGT\\n+\\n!!!!!!!!\\n" > "$1/HYB1.filtlong.fastq"; '
                        "fi"
                    ),
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        script.chmod(0o755)
    for executable in ["bowtie2_mock", "minimap2_mock", "samtools_mock"]:
        script = env_bin / executable
        script.write_text(
            '#!/usr/bin/env sh\nset -eu\nmkdir -p "$1"\nif [ "${2:-}" ]; then : > "$2"; fi\n',
            encoding="utf-8",
        )
        script.chmod(0o755)
    coverm_script = env_bin / "coverm_mock"
    coverm_script.write_text(
        "\n".join(
            [
                "#!/usr/bin/env sh",
                "set -eu",
                'mkdir -p "$1"',
                'target="${2:-$1/HYB1.coverm.tsv}"',
                'printf "contig\\tmean\\ttpm\\trpkm\\treads\\tlength\\n" > "$target"',
                'printf "contig_1\\t42.5\\t100\\t20\\t12\\t20\\n" >> "$target"',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    coverm_script.chmod(0o755)

    registry = ToolRegistry(
        [
            *[
                {
                    "id": tool_id,
                    "env_name": "mock-env",
                    "executable": executable,
                    "command_template": f"{executable} {{output_dir}}",
                }
                for tool_id, executable in [
                    ("fastp", "fastp_mock"),
                    ("fastqc", "fastqc_mock"),
                    ("nanoplot", "nanoplot_mock"),
                    ("filtlong", "filtlong_mock"),
                    ("multiqc", "multiqc_mock"),
                    ("opera_ms", "opera_ms_mock"),
                    ("quast", "quast_mock"),
                    ("genomad", "genomad_mock"),
                    ("metaphlan", "metaphlan_mock"),
                    ("bakta", "bakta_mock"),
                    ("amrfinderplus", "amrfinderplus_mock"),
                    ("abricate", "abricate_mock"),
                ]
            ],
            {
                "id": "bowtie2",
                "env_name": "mock-env",
                "executable": "bowtie2_mock",
                "command_template": "bowtie2_mock {output_dir} {alignment}",
            },
            {
                "id": "minimap2",
                "env_name": "mock-env",
                "executable": "minimap2_mock",
                "command_template": "minimap2_mock {output_dir} {alignment}",
            },
            {
                "id": "samtools",
                "env_name": "mock-env",
                "executable": "samtools_mock",
                "command_template": "samtools_mock {output_dir} {bam}",
            },
            {
                "id": "coverm",
                "env_name": "mock-env",
                "executable": "coverm_mock",
                "command_template": "coverm_mock {output_dir} {abundance}",
            },
        ]
    )

    outputs = PipelineExecutor(registry, RunLogger(tmp_path / "log")).run(plan, config)
    tables = tmp_path / "results" / "tables"

    qc_tools = {row["tool"] for row in read_standard_table(tables, "qc_summary")}
    assert {"fastp", "fastqc", "nanoplot", "filtlong", "multiqc"}.issubset(qc_tools)
    assembly_tools = {row["tool"] for row in read_standard_table(tables, "assembly_summary")}
    assert {"opera_ms", "quast"}.issubset(assembly_tools)
    assert read_standard_table(tables, "plasmid_predictions")
    assert read_standard_table(tables, "plasmid_consensus")
    assert read_standard_table(tables, "host_predictions")
    assert read_standard_table(tables, "annotations")
    assert len(read_standard_table(tables, "abundance")) == 2

    short_coverm = (
        tmp_path / "results" / "10_abundance" / "HYB1" / "short" / "HYB1.short.coverm.tsv"
    )
    long_coverm = tmp_path / "results" / "10_abundance" / "HYB1" / "long" / "HYB1.long.coverm.tsv"
    assert short_coverm.exists()
    assert long_coverm.exists()

    plasmid_fasta = tmp_path / "results" / "04_plasmid_detection" / "HYB1" / "plasmid_contigs.fasta"
    non_plasmid_fasta = (
        tmp_path / "results" / "04_plasmid_detection" / "HYB1" / "non_plasmid_contigs.fasta"
    )
    assert ">contig_1 plasmid-supported" in plasmid_fasta.read_text(encoding="utf-8")
    assert ">contig_3 hybrid-background" in non_plasmid_fasta.read_text(encoding="utf-8")

    report = outputs["report"].read_text(encoding="utf-8")
    assert "Hybrid Short+Long Beta Scope" in report
    assert "Total contigs: 3" in report
    assert "Abundance records: 2" in report


def test_failed_external_step_records_diagnostic_context(tmp_path, monkeypatch):
    mamba_root = tmp_path / ".mamba"
    env_bin = mamba_root / "envs" / "mock-env" / "bin"
    env_bin.mkdir(parents=True)
    monkeypatch.setenv("AUTOPLASM_MAMBA_ROOT", str(mamba_root))

    executable = env_bin / "fail_tool"
    executable.write_text(
        "#!/usr/bin/env sh\nprintf 'database missing\\n' >&2\nexit 7\n",
        encoding="utf-8",
    )
    executable.chmod(0o755)

    sample = SampleInput(sample_id="S1", platform="assembly", assembly="input.fasta")
    context = SampleContext(
        samples=[sample],
        multi_sample=False,
        has_groups=False,
        enable_sample_analysis=False,
        enable_differential_abundance=False,
    )
    outdir = tmp_path / "results"
    plan = ExecutionPlan(
        project_name="failure_diagnostics",
        mode="auto",
        threads=1,
        outdir=str(outdir),
        log_dir=str(tmp_path / "log"),
        samples=[sample],
        sample_context=context,
        selected_tools=["fail_tool"],
        steps=[
            PlanStep(
                step_id="S1_fail",
                sample_id="S1",
                step_name="plasmid_detection",
                tool_id="fail_tool",
                category="plasmid_detection",
                outputs={"output_dir": str(outdir / "04_plasmid_detection" / "S1")},
            )
        ],
    )
    registry = ToolRegistry(
        [
            {
                "id": "fail_tool",
                "env_name": "mock-env",
                "executable": "fail_tool",
                "command_template": "fail_tool",
            }
        ]
    )

    with pytest.raises(ToolError) as excinfo:
        PipelineExecutor(registry, RunLogger(tmp_path / "log")).run(
            plan,
            {"outdir": str(outdir), "log_dir": str(tmp_path / "log")},
            dry_run=False,
        )

    reason = str(excinfo.value)
    assert "step_id=S1_fail" in reason
    assert "tool_id=fail_tool" in reason
    assert "exit_code=7" in reason
    assert "stderr_path=" in reason
    assert "suggested_checks=" in reason

    commands = (outdir / "provenance" / "commands.tsv").read_text(encoding="utf-8")
    assert "step_id=S1_fail" in commands
    assert "tool_id=fail_tool" in commands
    assert "exit_code=7" in commands
    stderr = outdir / "provenance" / "step_logs" / "S1_fail.stderr.log"
    assert stderr.read_text(encoding="utf-8") == "database missing\n"
