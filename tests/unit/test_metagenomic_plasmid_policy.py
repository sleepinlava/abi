"""Regression tests for the metagenomic-plasmid optimization policy."""

from __future__ import annotations

import csv
from pathlib import Path

import yaml

from abi.contracts.lint import validate_pipeline_template_params
from abi.plugins import get_plugin
from abi.plugins.metagenomic_plasmid import build_plan_from_dag
from abi.plugins.metagenomic_plasmid._engine.config import load_config
from abi.plugins.metagenomic_plasmid._engine.pipeline import (
    _assembly_paths_by_sample,
    _terminal_overlap_length,
)
from abi.plugins.metagenomic_plasmid._engine.report.markdown import write_markdown_report
from abi.plugins.metagenomic_plasmid._engine.resources import (
    check_resources,
    default_resource_specs,
)
from abi.plugins.metagenomic_plasmid._engine.standard_tables import (
    TABLE_SCHEMAS,
    ensure_standard_tables,
)
from abi.schemas import ExecutionPlan, PlanStep, SampleContext, SampleInput


def _config(tmp_path: Path, overrides=None):
    merged = {
        "input": {"sample_sheet": None},
        "outdir": str(tmp_path / "results"),
        "log_dir": str(tmp_path / "logs"),
    }
    if overrides:
        merged.update(overrides)
    return load_config(profile="dry_run", overrides=merged)


def _context(samples: list[SampleInput]) -> SampleContext:
    groups = {sample.group for sample in samples if sample.group}
    return SampleContext(
        samples=samples,
        multi_sample=len(samples) > 1,
        has_groups=len(groups) >= 2,
        enable_sample_analysis=len(samples) > 1,
        enable_differential_abundance=len(groups) >= 2,
    )


def test_default_illumina_route_matches_optimized_main_path(tmp_path):
    sample = SampleInput(
        sample_id="S1", platform="illumina", read1="R1.fastq.gz", read2="R2.fastq.gz"
    )

    plan = build_plan_from_dag(_config(tmp_path), _context([sample]), check_files=False)
    tools = [step.tool_id for step in plan.steps]

    for required in (
        "fastp",
        "multiqc",
        "megahit",
        "quast",
        "genomad",
        "mmseqs2",
        "bowtie2",
        "samtools",
        "coverm",
        "bakta",
        "amrfinderplus",
        "isescan",
        "integronfinder",
        "plasmidfinder",
        "mob_typer",
    ):
        assert required in tools

    forbidden = {
        "bwa",
        "kneaddata",
        "bandage",
        "pmlst",
        "hic_evidence",
        "abricate",
        "rgi",
        "eggnog_mapper",
        "blast",
        "mummer",
        "clinker",
        "metabat2",
        "maxbin2",
        "concoct",
        "semibin",
    }
    assert forbidden.isdisjoint(tools)
    fastp = next(step for step in plan.steps if step.tool_id == "fastp")
    assembly = next(step for step in plan.steps if step.tool_id == "megahit")
    assert assembly.inputs["read1"] == fastp.outputs["clean_read1"]
    assert assembly.inputs["read2"] == fastp.outputs["clean_read2"]


def test_pipeline_template_params_are_contract_linted() -> None:
    assert validate_pipeline_template_params(Path("plugins/metagenomic_plasmid")) == []


def test_multiqc_steps_include_project_outdir_template_param(tmp_path):
    sample = SampleInput(
        sample_id="S1", platform="illumina", read1="R1.fastq.gz", read2="R2.fastq.gz"
    )

    config = _config(tmp_path)
    plan = build_plan_from_dag(config, _context([sample]), check_files=False)
    multiqc_steps = [step for step in plan.steps if step.tool_id == "multiqc"]

    assert multiqc_steps
    for step in multiqc_steps:
        assert step.params["project_outdir"] == config["outdir"]


def test_modern_annotation_fields_override_legacy_default_tool_list(tmp_path):
    sample = SampleInput(sample_id="ONT1", platform="ont", long_reads="reads.fastq.gz")
    config = _config(
        tmp_path,
        {
            "annotation": {
                "enable": True,
                "general_annotator": "bakta",
                "arg_tools": ["amrfinderplus", "abricate"],
                "vf_tools": [],
                "mobile_element_tools": [],
            },
            "host_prediction": {"enable": "auto", "tools": "auto"},
        },
    )

    plan = build_plan_from_dag(config, _context([sample]), check_files=False)
    tools = {step.tool_id for step in plan.steps}

    assert {"bakta", "amrfinderplus", "abricate", "metaphlan"} <= tools
    assert {"isescan", "integronfinder"}.isdisjoint(tools)


def test_auto_tool_policy_is_resolved_before_dag_filtering(tmp_path):
    sample = SampleInput(
        sample_id="S1", platform="illumina", read1="R1.fastq.gz", read2="R2.fastq.gz"
    )
    config = _config(
        tmp_path,
        {
            "workflow": {"data_profile": "isolate_plasmid"},
            "plasmid_binning": {"enable": True, "tools": "auto"},
            "typing": {"enable": "auto", "tools": "auto"},
            "host_prediction": {"enable": True, "tools": "auto"},
        },
    )

    plan = build_plan_from_dag(config, _context([sample]), check_files=False)
    tools = {step.tool_id for step in plan.steps}

    assert {"gplas2", "plasmidfinder", "mob_typer", "mob_suite"} <= tools


def test_hifi_route_does_not_run_ont_specific_nanoplot(tmp_path):
    sample = SampleInput(
        sample_id="HIFI1",
        platform="pacbio_hifi",
        long_reads="hifi.fastq.gz",
        technology="PacBio HiFi",
    )

    plan = build_plan_from_dag(_config(tmp_path), _context([sample]), check_files=False)
    tools = {step.tool_id for step in plan.steps}

    assert "hifiadapterfilt" in tools
    assert "nanoplot" not in tools


def test_assembly_input_remains_active_when_assembly_generation_is_disabled(tmp_path):
    sample = SampleInput(sample_id="ASM1", platform="assembly", assembly="assembly.fasta")
    config = _config(tmp_path, {"assembly": {"enable": False}})

    plan = build_plan_from_dag(config, _context([sample]), check_files=False)

    assert "ASM1_assembly_internal" in {step.step_id for step in plan.steps}


def test_candidate_fasta_export_uses_dag_input_assembly_path(tmp_path):
    assembly = tmp_path / "assembly.fasta"
    sample = SampleInput(sample_id="S1", platform="illumina")
    context = _context([sample])
    plan = ExecutionPlan(
        project_name="test",
        mode="auto",
        threads=1,
        outdir=str(tmp_path / "results"),
        log_dir=str(tmp_path / "logs"),
        samples=[sample],
        sample_context=context,
        selected_tools=["genomad"],
        steps=[
            PlanStep(
                step_id="S1_plasmid_detection_genomad",
                step_name="plasmid_detection",
                tool_id="genomad",
                category="plasmid_detection",
                sample_id="S1",
                inputs={"assembly": str(assembly)},
            )
        ],
    )

    assert _assembly_paths_by_sample(plan) == {"S1": str(assembly)}


def test_markdown_report_counts_dag_input_assembly_contigs(tmp_path):
    assembly = tmp_path / "assembly.fasta"
    assembly.write_text(">contig_1\nATGC\n>contig_2\nATGC\n>contig_3\nATGC\n", encoding="utf-8")
    tables_dir = tmp_path / "tables"
    ensure_standard_tables(tables_dir)
    sample = SampleInput(sample_id="S1", platform="illumina")
    plan = ExecutionPlan(
        project_name="test",
        mode="auto",
        threads=1,
        outdir=str(tmp_path / "results"),
        log_dir=str(tmp_path / "logs"),
        samples=[sample],
        sample_context=_context([sample]),
        selected_tools=["megahit"],
        steps=[
            PlanStep(
                step_id="S1_assembly_megahit",
                step_name="assembly",
                tool_id="megahit",
                category="assembly",
                sample_id="S1",
                inputs={"assembly": str(assembly)},
            )
        ],
    )

    report_path = write_markdown_report(plan, tmp_path / "report", tables_dir=tables_dir)

    assert "- Total contigs: 3" in report_path.read_text(encoding="utf-8")


def test_host_removal_is_resolved_per_sample(tmp_path):
    samples = [
        SampleInput(
            sample_id="hosted",
            platform="illumina",
            read1="R1.fastq.gz",
            read2="R2.fastq.gz",
            host_reference="host.fa",
        ),
        SampleInput(
            sample_id="environmental",
            platform="illumina",
            read1="R1.fastq.gz",
            read2="R2.fastq.gz",
        ),
    ]

    plan = build_plan_from_dag(_config(tmp_path), _context(samples), check_files=False)
    host_steps = [
        step
        for step in plan.steps
        if step.sample_id == "hosted" and step.tool_id == "bowtie2_host_removal"
    ]
    environmental_steps = [
        step
        for step in plan.steps
        if step.sample_id == "environmental" and "host_removal" in step.step_id
    ]

    assert len(host_steps) == 1
    assert host_steps[0].inputs["host_reference"] == "host.fa"
    assert environmental_steps == []


def test_alternative_assembler_replaces_default_instead_of_double_running(tmp_path):
    sample = SampleInput(
        sample_id="S1", platform="illumina", read1="R1.fastq.gz", read2="R2.fastq.gz"
    )
    config = _config(tmp_path, {"assembly": {"short_read_assembler": "metaspades"}})

    plan = build_plan_from_dag(config, _context([sample]), check_files=False)
    tools = [step.tool_id for step in plan.steps]

    assert "metaspades" in tools
    assert "megahit" not in tools


def test_medaka_is_opt_in_and_replaces_ont_assembly_for_downstream_inputs(tmp_path):
    sample = SampleInput(sample_id="ONT1", platform="ont", long_reads="reads.fastq.gz")
    config = _config(
        tmp_path,
        {"polishing": {"enable": True, "tools": ["medaka"]}},
    )

    plan = build_plan_from_dag(config, _context([sample]), check_files=False)
    medaka = next(step for step in plan.steps if step.tool_id == "medaka")
    genomad = next(step for step in plan.steps if step.tool_id == "genomad")

    assert medaka.outputs["assembly"].endswith("consensus.fasta")
    assert genomad.inputs["assembly"] == medaka.outputs["assembly"]


def test_platon_is_optional_consensus_evidence_after_genomad(tmp_path):
    sample = SampleInput(
        sample_id="S1", platform="illumina", read1="R1.fastq.gz", read2="R2.fastq.gz"
    )
    config = _config(
        tmp_path,
        {
            "plasmid_detection": {
                "tools": ["genomad", "platon"],
                "strategy": "weighted_vote",
            }
        },
    )

    plan = build_plan_from_dag(config, _context([sample]), check_files=False)
    platon = next(step for step in plan.steps if step.tool_id == "platon")
    consensus = next(
        step for step in plan.steps if step.step_id.endswith("plasmid_consensus_internal")
    )

    assert plan.steps.index(platon) < plan.steps.index(consensus)
    assert consensus.inputs["platon_predictions"] == platon.outputs["output_dir"]


def test_ont_pod5_is_basecalled_before_long_read_qc(tmp_path):
    sample = SampleInput(sample_id="ONT1", platform="ont", pod5="signals.pod5")

    plan = build_plan_from_dag(_config(tmp_path), _context([sample]), check_files=False)
    dorado = next(step for step in plan.steps if step.tool_id == "dorado")
    nanoplot = next(step for step in plan.steps if step.tool_id == "nanoplot")
    filtlong = next(step for step in plan.steps if step.tool_id == "filtlong")

    assert nanoplot.inputs["long_reads"] == dorado.outputs["long_reads"]
    assert filtlong.inputs["long_reads"] == dorado.outputs["long_reads"]


def test_hifi_bam_is_converted_before_qc(tmp_path):
    sample = SampleInput(sample_id="HIFI1", platform="pacbio_hifi", bam="reads.bam")

    plan = build_plan_from_dag(_config(tmp_path), _context([sample]), check_files=False)
    conversion = next(step for step in plan.steps if step.tool_id == "samtools_fastq")
    qc = next(step for step in plan.steps if step.tool_id == "hifiadapterfilt")

    assert qc.inputs["long_reads"] == conversion.outputs["long_reads"]


def test_each_platform_uses_exactly_one_primary_assembly_route(tmp_path):
    cases = [
        (
            SampleInput(sample_id="ONT1", platform="ont", long_reads="ont.fastq.gz"),
            {"nanoplot", "filtlong", "metaflye"},
            "metaflye",
        ),
        (
            SampleInput(sample_id="HIFI1", platform="pacbio_hifi", long_reads="hifi.fastq.gz"),
            {"hifiadapterfilt", "hifiasm_meta"},
            "hifiasm_meta",
        ),
        (
            SampleInput(
                sample_id="HYBRID1",
                platform="hybrid",
                read1="R1.fastq.gz",
                read2="R2.fastq.gz",
                long_reads="long.fastq.gz",
            ),
            {"fastp", "nanoplot", "filtlong", "opera_ms"},
            "opera_ms",
        ),
    ]
    assemblers = {"megahit", "metaspades", "metaflye", "hifiasm_meta", "opera_ms"}

    for sample, required_tools, expected_assembler in cases:
        plan = build_plan_from_dag(_config(tmp_path), _context([sample]), check_files=False)
        tools = {step.tool_id for step in plan.steps}

        assert required_tools <= tools
        assert tools & assemblers == {expected_assembler}
        assert "genomad" in tools
        assert {"bakta", "amrfinderplus", "isescan", "integronfinder"} <= tools
        assert {"plasmidfinder", "mob_typer"} <= tools


def test_downstream_thresholds_activate_only_with_sufficient_metadata(tmp_path):
    samples = [
        SampleInput(
            sample_id=f"S{index:02d}",
            platform="illumina",
            read1="R1.fastq.gz",
            read2="R2.fastq.gz",
            group="case" if index < 10 else "control",
        )
        for index in range(20)
    ]

    plan = build_plan_from_dag(_config(tmp_path), _context(samples), check_files=False)
    step_ids = {step.step_id for step in plan.steps}

    assert "multisample_diversity" in step_ids
    assert "multisample_differential_deseq2" in step_ids
    assert "multisample_differential_abundance" not in step_ids
    assert "multisample_network_prepare" in step_ids
    assert "multisample_network_fastspar" in step_ids
    network_prepare = next(
        step for step in plan.steps if step.step_id == "multisample_network_prepare"
    )
    fastspar = next(step for step in plan.steps if step.step_id == "multisample_network_fastspar")
    assert fastspar.inputs["abundance_table"] == network_prepare.outputs["network_input"]
    assert not [step for step in plan.skipped_steps if step.step_id.endswith("_not_run")]


def test_ineligible_downstream_modules_record_reasons(tmp_path):
    sample = SampleInput(
        sample_id="S1", platform="illumina", read1="R1.fastq.gz", read2="R2.fastq.gz"
    )

    plan = build_plan_from_dag(_config(tmp_path), _context([sample]), check_files=False)
    reasons = {step.step_name: step.reason for step in plan.skipped_steps}

    assert (
        "no project platform or resolved configuration satisfied its activation conditions"
        in reasons["diversity"]
    )
    assert (
        "no project platform or resolved configuration satisfied its activation conditions"
        in reasons["statistics"]
    )
    assert (
        "no project platform or resolved configuration satisfied its activation conditions"
        in reasons["network"]
    )


def test_all_canonical_tables_are_created_with_headers(tmp_path):
    paths = ensure_standard_tables(tmp_path)
    required = {
        "sample_qc",
        "assembly_qc",
        "plasmid_predictions",
        "plasmid_catalog",
        "plasmid_structure",
        "plasmid_abundance",
        "plasmid_annotation",
        "amr_genes",
        "mge_elements",
        "plasmid_typing",
        "host_profile",
        "host_plasmid_links",
        "differential_plasmids",
        "network_edges",
        "network_nodes",
        "analysis_status",
    }

    assert required <= paths.keys()
    for table_name in required:
        with paths[table_name].open(encoding="utf-8", newline="") as handle:
            reader = csv.reader(handle, delimiter="\t")
            assert next(reader) == TABLE_SCHEMAS[table_name]
            assert list(reader) == []


def test_database_manifest_fields_include_fingerprint_and_date(tmp_path):
    database = tmp_path / "genomad"
    database.mkdir()
    (database / "version.txt").write_text("v1.11\n", encoding="utf-8")
    config = {
        "resources": {
            "root": str(tmp_path),
            "genomad": {
                "database": str(database),
                "version": "1.11",
                "date": "2026-06-22",
            },
        }
    }

    row = check_resources(config, resource_ids=["genomad"])[0]

    assert row["path"] == str(database)
    assert row["version"] == "1.11"
    assert row["checksum_sha256"]
    assert row["checksum_method"] == "sha256:directory-manifest-v1"
    assert row["date"] == "2026-06-22"


def test_required_database_manifest_entries_are_registered(tmp_path):
    resource_ids = {
        spec.resource_id for spec in default_resource_specs({"resources": {"root": str(tmp_path)}})
    }

    assert {
        "genomad",
        "bakta",
        "kraken2",
        "metaphlan",
        "card",
        "amrfinderplus",
        "eggnog_mapper",
        "abricate",
    } <= resource_ids


def test_standard_tables_yaml_is_runtime_schema_source_of_truth():
    plugin = get_plugin("metagenomic_plasmid")
    declared = yaml.safe_load((plugin.root / "standard_tables.yaml").read_text(encoding="utf-8"))[
        "tables"
    ]

    assert plugin.table_schemas() == declared


def test_dag_encodes_hard_tool_policy():
    repository = Path(__file__).parents[2]
    dag = yaml.safe_load(
        (repository / "plugins/metagenomic_plasmid/pipeline_dag.yaml").read_text(encoding="utf-8")
    )
    nodes = dag["nodes"]
    tool_nodes = {}
    for node_id, node in nodes.items():
        tool_nodes.setdefault(node["tool_id"], []).append((node_id, node))

    assert {"bwa", "kneaddata", "hic_evidence", "pmlst", "bandage"}.isdisjoint(tool_nodes)
    for tool_id in {
        "metaspades",
        "platon",
        "copla",
        "abricate",
        "rgi",
        "eggnog_mapper",
        "blast",
        "mummer",
        "clinker",
        "minced",
    }:
        assert tool_id in tool_nodes
        assert all(
            node["optional"] and "enable_condition" in node for _, node in tool_nodes[tool_id]
        )

    assert tool_nodes["genomad"][0][1]["optional"] is False
    assert "maxbin2" not in tool_nodes
    for tool_id in {"metabat2", "concoct", "semibin"}:
        assert all(node["category"] == "mag_host_genomes" for _, node in tool_nodes[tool_id])


def test_terminal_overlap_detection_is_bounded_and_exact():
    sequence = "A" * 25 + "CGTACGTA" + "A" * 25

    assert _terminal_overlap_length(sequence) == 25
    assert _terminal_overlap_length("ACGT" * 4) == 0
