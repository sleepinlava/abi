import json
import os
import subprocess
import sys

from abi.autoplasm.config import load_config
from abi.autoplasm.planner import build_plan


def test_build_plan_selects_expected_routes():
    config = load_config("examples/config_minimal.yaml", profile="dry_run")
    plan = build_plan(config)
    tool_ids = {step.tool_id for step in plan.steps}
    assert "fastp" in tool_ids
    assert "megahit" in tool_ids
    assert "genomad" in tool_ids
    # Optional categories disabled by default since Phase C
    assert "plasmaag" not in tool_ids
    assert "mob_suite" not in tool_ids
    assert "plasmidhostfinder" not in tool_ids
    assert plan.sample_context.enable_differential_abundance is True
    assert any(step.sample_id == "S2" and step.tool_id == "fastp" for step in plan.skipped_steps)
    assert "S2_host_prediction_metaphlan" not in {step.step_id for step in plan.steps}


def test_build_plan_treats_null_config_sections_as_defaults():
    config = load_config("examples/config_minimal.yaml", profile="dry_run")
    config["assembly"] = None
    config["abundance"] = None
    config["sample_analysis"] = None

    plan = build_plan(config)

    tool_ids = {step.tool_id for step in plan.steps}
    assert "quast" in tool_ids
    assert "bowtie2" in tool_ids
    assert "coverm" in tool_ids


def test_isolate_profile_enables_isolate_specific_typing_and_mob_suite():
    config = load_config(
        "examples/config_minimal.yaml",
        profile="dry_run",
        overrides={
            "workflow": {"data_profile": "isolate_plasmid"},
            "typing": {"enable": "auto", "tools": "auto"},
        },
    )
    plan = build_plan(config)
    tool_ids = {step.tool_id for step in plan.steps}

    assert "mob_typer" in tool_ids
    assert "plasmidfinder" in tool_ids
    assert "mob_suite" in tool_ids


def test_optional_auto_tools_require_explicit_enable():
    config = load_config(
        "examples/config_minimal.yaml",
        profile="dry_run",
        overrides={
            "plasmid_binning": {"enable": True, "tools": "auto"},
            "host_prediction": {"enable": True, "tools": "auto"},
        },
    )
    plan = build_plan(config)
    tool_ids = {step.tool_id for step in plan.steps}

    assert "gplas2" in tool_ids
    assert "metaphlan" in tool_ids
    assert "plasmidhostfinder" in tool_ids


def test_illumina_route_uses_cleaned_reads_and_megahit_contigs(tmp_path):
    config = load_config(
        "examples/config_minimal.yaml",
        profile="dry_run",
        overrides={"outdir": str(tmp_path / "results")},
    )
    plan = build_plan(config)
    steps = {step.step_id: step for step in plan.steps if step.sample_id == "S1"}

    megahit = steps["S1_assembly_megahit"]
    assert megahit.inputs["read1"].endswith("01_qc/S1/S1_R1.clean.fastq.gz")
    assert megahit.inputs["read2"].endswith("01_qc/S1/S1_R2.clean.fastq.gz")

    quast = steps["S1_assembly_qc_quast"]
    assert quast.inputs["assembly"].endswith("02_assembly/S1/final.contigs.fa")


def test_ont_route_uses_filtered_long_reads_and_metaflye_contigs(tmp_path):
    from abi.autoplasm.skills.registry import ToolRegistry

    config = load_config(
        "examples/config_ont_smoke.yaml",
        profile="dry_run",
        overrides={"outdir": str(tmp_path / "results")},
    )
    plan = build_plan(config)
    steps = {step.step_id: step for step in plan.steps if step.sample_id == "ONT1"}

    metaflye = steps["ONT1_assembly_metaflye"]
    assert metaflye.inputs["long_reads"].endswith("01_qc/ONT1/ONT1.filtlong.fastq")
    assert metaflye.params["threads"] == 2

    quast = steps["ONT1_assembly_qc_quast"]
    assert quast.inputs["assembly"].endswith("02_assembly/ONT1/assembly.fasta")

    minimap2 = steps["ONT1_abundance_minimap2"]
    assert minimap2.inputs["long_reads"].endswith("01_qc/ONT1/ONT1.filtlong.fastq")
    assert "bowtie2" not in {step.tool_id for step in plan.steps if step.sample_id == "ONT1"}

    metaphlan = steps["ONT1_host_prediction_metaphlan"]
    # Verify derived composite params by calling select_params
    registry = ToolRegistry.from_path()
    skill = registry.create("metaphlan", mock_tools=True)
    merged = dict(metaphlan.inputs)
    merged.update(metaphlan.params)
    selected = skill.select_params(merged)
    assert selected["metaphlan_input"].endswith("01_qc/ONT1/ONT1.filtlong.fastq")
    assert selected["metaphlan_long_reads_flag"] == "--long_reads"


def test_pacbio_hifi_route_uses_filtered_reads_and_hifiasm_contigs(tmp_path):
    from abi.autoplasm.skills.registry import ToolRegistry

    config = load_config(
        "examples/config_hifi_smoke.yaml",
        profile="dry_run",
        overrides={"outdir": str(tmp_path / "results")},
    )
    plan = build_plan(config)
    steps = {step.step_id: step for step in plan.steps if step.sample_id == "HIFI1"}

    hifiasm = steps["HIFI1_assembly_hifiasm_meta"]
    assert hifiasm.inputs["long_reads"].endswith("01_qc/HIFI1/HIFI1.hifiadapterfilt.fastq.gz")

    quast = steps["HIFI1_assembly_qc_quast"]
    assert quast.inputs["assembly"].endswith("02_assembly/HIFI1/HIFI1.hifiasm.fasta")

    minimap2 = steps["HIFI1_abundance_minimap2"]
    assert minimap2.inputs["long_reads"].endswith("01_qc/HIFI1/HIFI1.hifiadapterfilt.fastq.gz")
    assert "bowtie2" not in {step.tool_id for step in plan.steps if step.sample_id == "HIFI1"}

    metaphlan = steps["HIFI1_host_prediction_metaphlan"]
    # Verify derived composite params by calling select_params
    registry = ToolRegistry.from_path()
    skill = registry.create("metaphlan", mock_tools=True)
    merged = dict(metaphlan.inputs)
    merged.update(metaphlan.params)
    selected = skill.select_params(merged)
    assert selected["metaphlan_input"].endswith("01_qc/HIFI1/HIFI1.hifiadapterfilt.fastq.gz")
    assert selected["metaphlan_long_reads_flag"] == "--long_reads"


def test_hybrid_route_uses_cleaned_reads_opera_ms_and_split_abundance(tmp_path):
    from abi.autoplasm.skills.registry import ToolRegistry

    config = load_config(
        "examples/config_hybrid_smoke.yaml",
        profile="dry_run",
        overrides={"outdir": str(tmp_path / "results")},
    )
    plan = build_plan(config)
    steps = {step.step_id: step for step in plan.steps if step.sample_id == "HYB1"}

    opera_ms = steps["HYB1_assembly_opera_ms"]
    assert opera_ms.inputs["read1"].endswith("01_qc/HYB1/HYB1_R1.clean.fastq.gz")
    assert opera_ms.inputs["read2"].endswith("01_qc/HYB1/HYB1_R2.clean.fastq.gz")
    assert opera_ms.inputs["long_reads"].endswith("01_qc/HYB1/HYB1.filtlong.fastq")

    quast = steps["HYB1_assembly_qc_quast"]
    assert quast.inputs["assembly"].endswith("02_assembly/HYB1/contigs.fasta")

    bowtie2 = steps["HYB1_abundance_bowtie2"]
    assert bowtie2.outputs["alignment"].endswith("10_abundance/HYB1/short/HYB1.short.sam")
    assert bowtie2.inputs["abundance_source"] == "short"

    minimap2 = steps["HYB1_abundance_minimap2"]
    assert minimap2.outputs["alignment"].endswith("10_abundance/HYB1/long/HYB1.long.sam")
    assert minimap2.inputs["long_reads"].endswith("01_qc/HYB1/HYB1.filtlong.fastq")

    metaphlan = steps["HYB1_host_prediction_metaphlan"]
    # Verify derived composite params by calling select_params
    registry = ToolRegistry.from_path()
    skill = registry.create("metaphlan", mock_tools=True)
    merged = dict(metaphlan.inputs)
    merged.update(metaphlan.params)
    selected = skill.select_params(merged)
    metaphlan_read1, metaphlan_read2 = selected["metaphlan_input"].split(",")
    assert metaphlan_read1.endswith("01_qc/HYB1/HYB1_R1.clean.fastq.gz")
    assert metaphlan_read2.endswith("01_qc/HYB1/HYB1_R2.clean.fastq.gz")
    assert selected["metaphlan_long_reads_flag"] == ""

    samtools_by_source = {
        step.inputs["abundance_source"]: step
        for step in steps.values()
        if step.tool_id == "samtools" and "abundance_source" in step.inputs
    }
    assert samtools_by_source["short"].outputs["bam"].endswith("HYB1.short.bam")
    assert samtools_by_source["long"].outputs["bam"].endswith("HYB1.long.bam")

    coverm_by_source = {
        step.inputs["abundance_source"]: step
        for step in steps.values()
        if step.tool_id == "coverm" and "abundance_source" in step.inputs
    }
    assert coverm_by_source["short"].outputs["abundance"].endswith("HYB1.short.coverm.tsv")
    assert coverm_by_source["long"].outputs["abundance"].endswith("HYB1.long.coverm.tsv")


def test_hybrid_step_ids_are_stable_across_hash_seeds():
    script = """
import json
from abi.autoplasm.config import load_config
from abi.autoplasm.planner import build_plan

config = load_config('examples/config_hybrid_smoke.yaml', profile='dry_run')
plan = build_plan(config)
print(json.dumps([
    step.step_id
    for step in plan.steps
    if step.sample_id == 'HYB1' and step.tool_id in {'samtools', 'coverm'}
]))
"""
    outputs = []
    for seed in ("1", "3"):
        env = os.environ.copy()
        env["PYTHONHASHSEED"] = seed
        result = subprocess.run(
            [sys.executable, "-c", script],
            check=True,
            capture_output=True,
            text=True,
            env=env,
        )
        outputs.append(json.loads(result.stdout))

    assert outputs[0] == outputs[1]
