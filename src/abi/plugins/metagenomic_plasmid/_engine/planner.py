"""Execution plan generation."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional

from abi.config import PLUGIN_ROOT
from abi.plugins.metagenomic_plasmid._engine.sample_sheet import (
    parse_sample_sheet,
    single_sample_context,
)
from abi.plugins.metagenomic_plasmid._engine.schemas import (
    VALID_PLATFORMS,
    ExecutionPlan,
    PlanStep,
    SampleContext,
    SampleInput,
)

STEP_DIRS = {
    "input_validation": "00_input_validation",
    "qc": "01_qc",
    "assembly": "02_assembly",
    "assembly_qc": "03_assembly_qc",
    "plasmid_detection": "04_plasmid_detection",
    "plasmid_binning": "05_plasmid_binning",
    "typing": "06_plasmid_typing",
    "host_prediction": "07_host_prediction",
    "annotation": "08_annotation",
    "comparative_genomics": "09_comparative_genomics",
    "abundance": "10_abundance",
    "diversity": "11_diversity",
    "network": "12_network",
    "visualization": "13_visualization",
    "report": "report",
}

DATA_PROFILE_BY_PLATFORM = {
    "illumina": "illumina_short",
    "ont": "ont_long",
    "pacbio_hifi": "pacbio_hifi",
    "hybrid": "hybrid_short_long",
    "assembly": "assembly_only",
}

ISOLATE_PROFILES = {"isolate_plasmid", "isolate"}


def context_from_config(config: Mapping[str, Any], check_files: bool = True) -> SampleContext:
    input_config = config.get("input") or {}
    sample_sheet = input_config.get("sample_sheet")
    if sample_sheet:
        return parse_sample_sheet(sample_sheet, check_files=check_files)

    single_input = input_config.get("single_input")
    platform = input_config.get("platform")
    if not single_input and not input_config.get("assembly"):
        raise ValueError("No sample_sheet or single_input/assembly is configured")
    if platform not in VALID_PLATFORMS:
        raise ValueError(f"Single-sample input requires platform in {sorted(VALID_PLATFORMS)}")

    read1 = single_input if platform == "illumina" else input_config.get("read1")
    long_reads = (
        single_input if platform in {"ont", "pacbio_hifi"} else input_config.get("long_reads")
    )
    assembly = single_input if platform == "assembly" else input_config.get("assembly")
    return single_sample_context(
        sample_id=str(input_config.get("sample_id") or "single_sample"),
        platform=str(platform),
        read1=read1,
        read2=input_config.get("read2"),
        long_reads=long_reads,
        assembly=assembly,
        group=input_config.get("group"),
        check_files=check_files,
    )


def build_plan(
    config: Mapping[str, Any],
    sample_context: Optional[SampleContext] = None,
    *,
    check_files: bool = True,
) -> ExecutionPlan:
    context = sample_context or context_from_config(config, check_files=check_files)
    outdir = str(config["outdir"])
    steps: List[PlanStep] = []
    skipped: List[PlanStep] = []
    for sample in context.samples:
        sample_steps, sample_skipped = _sample_steps(sample, config)
        steps.extend(sample_steps)
        skipped.extend(sample_skipped)

    if context.enable_sample_analysis and _enabled(config, "sample_analysis"):
        steps.extend(_multi_sample_steps(context, config))
    else:
        skipped.append(
            PlanStep(
                step_id="skip_sample_analysis",
                sample_id=None,
                step_name="sample_analysis",
                tool_id="internal",
                category="sample_analysis",
                reason="Single-sample input or sample_analysis disabled",
                skipped=True,
            )
        )

    steps.extend(_report_steps(config))
    selected_tools = sorted({step.tool_id for step in steps if step.tool_id != "internal"})
    return ExecutionPlan(
        project_name=str(config["project_name"]),
        mode=str(config["mode"]),
        threads=int(config["threads"]),
        outdir=outdir,
        log_dir=str(config["log_dir"]),
        samples=context.samples,
        sample_context=context,
        selected_tools=selected_tools,
        steps=steps,
        skipped_steps=skipped,
        provenance_dir=str(Path(outdir) / "provenance"),
    )


def _enabled(config: Mapping[str, Any], key: str) -> bool:
    block = config.get(key)
    if isinstance(block, Mapping):
        value = block.get("enable", True)
        return value in {True, "auto"}
    return bool(block)


def _config_block(config: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    block = config.get(key, {})
    return block if isinstance(block, Mapping) else {}


def _data_profile_for_sample(sample: SampleInput, config: Mapping[str, Any]) -> str:
    workflow = config.get("workflow", {})
    if isinstance(workflow, Mapping):
        configured = workflow.get("data_profile")
        if configured:
            return str(configured)
    input_config = config.get("input", {})
    if isinstance(input_config, Mapping):
        configured = input_config.get("data_profile")
        if configured:
            return str(configured)
    return DATA_PROFILE_BY_PLATFORM.get(sample.platform, sample.platform)


def _enable_state(config: Mapping[str, Any], key: str, default: Any = True) -> Any:
    block = config.get(key)
    if isinstance(block, Mapping):
        return block.get("enable", default)
    if block is None:
        return default
    return block


def _category_enabled(
    config: Mapping[str, Any],
    category: str,
    data_profile: str,
    sample: SampleInput,
) -> bool:
    state = _enable_state(config, category)
    if state in {False, "false", "False", "no", "0"}:
        return False
    if state == "auto":
        if category == "abundance":
            return sample.has_short_reads or sample.has_long_reads
        if category == "typing":
            return _is_isolate_profile(data_profile)
        if category == "host_prediction":
            return sample.has_short_reads or sample.has_long_reads
        if category in {"comparative_genomics", "plasmid_binning"}:
            return False
        return True
    return bool(state)


def _tools_for_category(
    config: Mapping[str, Any],
    category: str,
    data_profile: str,
) -> List[str]:
    block = config.get(category, {})
    default_tools = _default_tools_for_category(category, data_profile)
    if not isinstance(block, Mapping):
        return default_tools
    tools = block.get("tools", "auto")
    if tools == "auto" or tools is None:
        return default_tools
    if isinstance(tools, list):
        return [str(tool) for tool in tools if tool]
    return []


def _default_tools_for_category(category: str, data_profile: str) -> List[str]:
    if category == "plasmid_detection":
        return ["genomad"]
    if category == "plasmid_binning":
        return ["gplas2"]
    if category == "typing" and _is_isolate_profile(data_profile):
        return ["mob_typer", "plasmidfinder"]
    if category == "host_prediction":
        if data_profile in {"illumina_short", "ont_long", "pacbio_hifi", "hybrid_short_long"}:
            return ["metaphlan"]
        return ["plasmidhostfinder"]
    return []


def _annotation_tools(config: Mapping[str, Any], data_profile: str) -> List[str]:
    annotation = config.get("annotation", {})
    if not isinstance(annotation, Mapping):
        return []
    general = annotation.get("general_annotator", "bakta")
    tools = [] if general in {None, "", "none"} else [str(general)]
    tools.extend(str(tool) for tool in annotation.get("arg_tools", []) if tool)
    tools.extend(str(tool) for tool in annotation.get("vf_tools", []) if tool)
    tools.extend(str(tool) for tool in annotation.get("mobile_element_tools", []) if tool)
    if _is_isolate_profile(data_profile):
        tools.append("mob_suite")
    return tools


def _abundance_mappers(
    sample: SampleInput,
    config: Mapping[str, Any],
    route: Mapping[str, Any],
) -> List[str]:
    abundance = config.get("abundance", {})
    if not isinstance(abundance, Mapping):
        abundance = {}
    mappers: List[str] = []
    if sample.has_short_reads:
        mappers.append(str(abundance.get("mapper_short", "bowtie2")))
    if sample.has_long_reads:
        mappers.append(str(abundance.get("mapper_long", "minimap2")))
    if not mappers:
        mapper = route.get("mapping")
        if isinstance(mapper, list):
            mappers.extend(str(tool_id) for tool_id in mapper)
        elif mapper:
            mappers.append(str(mapper))
    return [tool_id for tool_id in _unique(mappers) if tool_id != "auto_if_abundance_enabled"]


def _is_isolate_profile(data_profile: str) -> bool:
    return data_profile in ISOLATE_PROFILES or data_profile.endswith("_isolate")


def _sample_steps(
    sample: SampleInput, config: Mapping[str, Any]
) -> tuple[List[PlanStep], List[PlanStep]]:
    steps: List[PlanStep] = []
    skipped: List[PlanStep] = []
    outdir = Path(str(config["outdir"]))
    threads = int(config["threads"])
    common = sample.to_dict()
    data_profile = _data_profile_for_sample(sample, config)
    common.update(
        {
            "threads": threads,
            "mode": config.get("mode", "auto"),
            "data_profile": data_profile,
        }
    )
    if sample.platform == "pacbio_hifi":
        common["minimap2_preset"] = "map-hifi"
    elif sample.platform in {"ont", "hybrid"}:
        common["minimap2_preset"] = "map-ont"

    steps.append(
        _step(
            sample,
            "input_validation",
            "internal",
            config,
            params={**common, "validation": "sample inputs already validated"},
        )
    )

    route = _route_for_platform(sample.platform, config)
    qc_enabled = sample.platform != "assembly" and _category_enabled(
        config, "qc", data_profile, sample
    )
    if sample.platform == "assembly":
        skipped.extend(
            [
                _skip(sample, "qc", "Assembly-only input skips read QC"),
                _skip(sample, "assembly", "Assembly-only input uses provided contigs"),
            ]
        )
    elif qc_enabled:
        for tool_id in route["qc"]:
            steps.append(_step(sample, "qc", tool_id, config, params=common))

    post_qc_common = dict(common)
    post_qc_common.update(_post_qc_input_params(sample, config, route, qc_enabled=qc_enabled))

    assembly_tool = route["assembly"]
    if sample.platform != "assembly" and _category_enabled(
        config, "assembly", data_profile, sample
    ):
        if assembly_tool:
            steps.append(_step(sample, "assembly", assembly_tool, config, params=post_qc_common))
    elif sample.platform != "assembly":
        skipped.append(_skip(sample, "assembly", "Assembly disabled by config"))

    assembly_path = sample.assembly or _assembly_output_path(outdir, sample, assembly_tool)
    params_with_assembly = {**post_qc_common, "assembly": assembly_path}

    if _config_block(config, "assembly").get("assembly_qc", True):
        steps.append(_step(sample, "assembly_qc", "quast", config, params=params_with_assembly))

    if _category_enabled(config, "plasmid_detection", data_profile, sample):
        for tool_id in _tools_for_category(config, "plasmid_detection", data_profile):
            steps.append(
                _step(
                    sample,
                    "plasmid_detection",
                    tool_id,
                    config,
                    params=params_with_assembly,
                )
            )

    plasmid_contigs = _plasmid_contigs_path(sample, config, assembly_path)
    plasmid_params = {
        **params_with_assembly,
        "plasmid_contigs": plasmid_contigs,
        **_abundance_artifact_params(sample, config),
    }

    for category, tool_ids in [
        ("plasmid_binning", _tools_for_category(config, "plasmid_binning", data_profile)),
        ("typing", _tools_for_category(config, "typing", data_profile)),
        ("host_prediction", _tools_for_category(config, "host_prediction", data_profile)),
    ]:
        if _category_enabled(config, category, data_profile, sample):
            for tool_id in tool_ids:
                steps.append(_step(sample, category, tool_id, config, params=plasmid_params))

    if _category_enabled(config, "annotation", data_profile, sample):
        tools = _annotation_tools(config, data_profile)
        for tool_id in _unique(tools):
            steps.append(_step(sample, "annotation", tool_id, config, params=plasmid_params))

    if _category_enabled(config, "comparative_genomics", data_profile, sample):
        for tool_id in _tools_for_category(config, "comparative_genomics", data_profile):
            steps.append(
                _step(
                    sample,
                    "comparative_genomics",
                    tool_id,
                    config,
                    params=plasmid_params,
                )
            )

    if _category_enabled(config, "abundance", data_profile, sample):
        mappers = [
            tool_id
            for tool_id in _abundance_mappers(sample, config, route)
            if tool_id != "auto_if_abundance_enabled"
        ]
        if sample.platform == "hybrid" and len(mappers) > 1:
            steps.extend(_hybrid_abundance_steps(sample, config, plasmid_params, mappers))
        else:
            for tool_id in mappers:
                steps.append(_step(sample, "abundance", tool_id, config, params=plasmid_params))
            if mappers:
                steps.append(_step(sample, "abundance", "samtools", config, params=plasmid_params))
            abundance_tool = _config_block(config, "abundance").get("calculator", "coverm")
            if mappers and abundance_tool:
                steps.append(
                    _step(sample, "abundance", abundance_tool, config, params=plasmid_params)
                )
        if not mappers:
            skipped.append(_skip(sample, "abundance", "Abundance requires read inputs"))

    return steps, skipped


def _hybrid_abundance_steps(
    sample: SampleInput,
    config: Mapping[str, Any],
    plasmid_params: Mapping[str, Any],
    mappers: Iterable[str],
) -> List[PlanStep]:
    steps: List[PlanStep] = []
    abundance_tool = _config_block(config, "abundance").get("calculator", "coverm")
    for tool_id in mappers:
        source = _abundance_source_for_mapper(tool_id)
        params = {
            **plasmid_params,
            **_abundance_artifact_params(sample, config, source=source),
        }
        steps.append(
            _step(
                sample,
                "abundance",
                tool_id,
                config,
                params=params,
                step_suffix=source,
                output_subdir=source,
            )
        )
        steps.append(
            _step(
                sample,
                "abundance",
                "samtools",
                config,
                params=params,
                step_suffix=source,
                output_subdir=source,
            )
        )
        if abundance_tool:
            steps.append(
                _step(
                    sample,
                    "abundance",
                    str(abundance_tool),
                    config,
                    params=params,
                    step_suffix=source,
                    output_subdir=source,
                )
            )
    return steps


def _abundance_source_for_mapper(tool_id: str) -> str:
    if tool_id in {"bowtie2", "bwa"}:
        return "short"
    if tool_id in {"minimap2"}:
        return "long"
    return tool_id.replace("-", "_")


def _multi_sample_steps(context: SampleContext, config: Mapping[str, Any]) -> List[PlanStep]:
    params = {
        "threads": int(config["threads"]),
        "mode": config.get("mode", "auto"),
        "sample_count": len(context.samples),
        "abundance_table": str(
            Path(str(config["outdir"])) / "10_abundance" / "plasmid_abundance_tpm.tsv"
        ),
    }
    steps = [
        PlanStep(
            step_id="multi_diversity",
            sample_id=None,
            step_name="diversity",
            tool_id="internal",
            category="diversity",
            outputs={"outdir": str(Path(str(config["outdir"])) / STEP_DIRS["diversity"])},
            params=params,
        )
    ]
    if _config_block(config, "sample_analysis").get("network", True):
        steps.append(
            PlanStep(
                step_id="multi_network_fastspar",
                sample_id=None,
                step_name="network",
                tool_id="fastspar",
                category="network",
                outputs={"outdir": str(Path(str(config["outdir"])) / STEP_DIRS["network"])},
                params=params,
            )
        )
    if context.enable_differential_abundance:
        steps.append(
            PlanStep(
                step_id="multi_differential_abundance",
                sample_id=None,
                step_name="differential_abundance",
                tool_id="internal",
                category="statistics",
                outputs={"outdir": str(Path(str(config["outdir"])) / STEP_DIRS["diversity"])},
                params={**params, "grouped": True},
            )
        )
    return steps


def _report_steps(config: Mapping[str, Any]) -> List[PlanStep]:
    outdir = Path(str(config["outdir"]))
    return [
        PlanStep(
            step_id="report_markdown",
            sample_id=None,
            step_name="report",
            tool_id="report_markdown",
            category="report",
            outputs={
                "report_md": str(outdir / "report" / "report.md"),
                "methods_md": str(outdir / "report" / "methods.md"),
            },
            params={
                "project_outdir": str(outdir),
                "output_dir": str(outdir / "report"),
                "threads": int(config["threads"]),
                "mode": config.get("mode", "auto"),
            },
        )
    ]


def _route_for_platform(platform: str, config: Mapping[str, Any]) -> Dict[str, Any]:
    assembly = _config_block(config, "assembly")
    qc = _config_block(config, "qc")
    abundance = _config_block(config, "abundance")
    if platform == "illumina":
        route = {
            "qc": [qc.get("short_read_tool", "fastp")],
            "assembly": assembly.get("short_read_assembler", "megahit"),
            "mapping": abundance.get("mapper_short", "bowtie2"),
        }
        if qc.get("run_fastqc", True):
            route["qc"].append("fastqc")
        if qc.get("run_multiqc", True):
            route["qc"].append("multiqc")
        return route
    if platform == "ont":
        qc_tools = ["nanoplot"]
        long_tool = qc.get("long_read_tool", "filtlong")
        if long_tool and long_tool != "none":
            qc_tools.append(str(long_tool))
        if qc.get("run_multiqc", True):
            qc_tools.append("multiqc")
        return {
            "qc": qc_tools,
            "assembly": assembly.get("long_read_assembler", "metaflye"),
            "mapping": abundance.get("mapper_long", "minimap2"),
        }
    if platform == "pacbio_hifi":
        qc_tools = ["hifiadapterfilt"]
        if qc.get("run_multiqc", True):
            qc_tools.append("multiqc")
        return {
            "qc": qc_tools,
            "assembly": assembly.get("pacbio_hifi_assembler", "hifiasm_meta"),
            "mapping": abundance.get("mapper_long", "minimap2"),
        }
    if platform == "hybrid":
        qc_tools = [qc.get("short_read_tool", "fastp")]
        if qc.get("run_fastqc", True):
            qc_tools.append("fastqc")
        qc_tools.append("nanoplot")
        long_tool = qc.get("long_read_tool", "filtlong")
        if long_tool and long_tool != "none":
            qc_tools.append(str(long_tool))
        if qc.get("run_multiqc", True):
            qc_tools.append("multiqc")
        return {
            "qc": qc_tools,
            "assembly": assembly.get("hybrid_assembler", "opera_ms"),
            "mapping": [
                abundance.get("mapper_short", "bowtie2"),
                abundance.get("mapper_long", "minimap2"),
            ],
        }
    if platform == "assembly":
        return {"qc": [], "assembly": None, "mapping": "auto_if_abundance_enabled"}
    raise ValueError(f"Unsupported platform: {platform}")


def _post_qc_input_params(
    sample: SampleInput,
    config: Mapping[str, Any],
    route: Mapping[str, Any],
    *,
    qc_enabled: bool,
) -> Dict[str, str]:
    outdir = Path(str(config["outdir"])) / STEP_DIRS["qc"] / sample.sample_id
    params: Dict[str, str] = {}
    qc_tools = route.get("qc", [])
    if qc_enabled and sample.has_short_reads and "fastp" in qc_tools and sample.read2:
        params.update(
            {
                "read1": str(outdir / f"{sample.sample_id}_R1.clean.fastq.gz"),
                "read2": str(outdir / f"{sample.sample_id}_R2.clean.fastq.gz"),
            }
        )
    if qc_enabled and sample.has_long_reads:
        if "filtlong" in qc_tools:
            params["long_reads"] = str(outdir / f"{sample.sample_id}.filtlong.fastq")
        elif "fastplong" in qc_tools:
            params["long_reads"] = str(outdir / f"{sample.sample_id}.long.clean.fastq.gz")
        elif "hifiadapterfilt" in qc_tools:
            params["long_reads"] = str(outdir / f"{sample.sample_id}.hifiadapterfilt.fastq.gz")
    return params


def _assembly_output_path(
    outdir: Path,
    sample: SampleInput,
    assembly_tool: Any,
) -> str:
    sample_outdir = outdir / STEP_DIRS["assembly"] / sample.sample_id
    if assembly_tool == "megahit":
        return str(sample_outdir / "final.contigs.fa")
    if assembly_tool in {"metaspades", "spades"}:
        return str(sample_outdir / "contigs.fasta")
    if assembly_tool in {"metaflye", "flye"}:
        return str(sample_outdir / "assembly.fasta")
    if assembly_tool == "hifiasm_meta":
        return str(sample_outdir / f"{sample.sample_id}.hifiasm.fasta")
    if assembly_tool == "opera_ms":
        return str(sample_outdir / "contigs.fasta")
    return str(sample_outdir / "contigs.fasta")


def _abundance_artifact_params(
    sample: SampleInput,
    config: Mapping[str, Any],
    *,
    source: str | None = None,
) -> Dict[str, str]:
    outdir = Path(str(config["outdir"])) / STEP_DIRS["abundance"] / sample.sample_id
    label = f".{source}" if source else ""
    if source:
        outdir = outdir / source
    return {
        "abundance_source": source or "all",
        "abundance_label": label,
        "alignment": str(outdir / f"{sample.sample_id}{label}.sam"),
        "bam": str(outdir / f"{sample.sample_id}{label}.bam"),
        "abundance": str(outdir / f"{sample.sample_id}{label}.coverm.tsv"),
    }


def _step(
    sample: SampleInput,
    category: str,
    tool_id: str,
    config: Mapping[str, Any],
    *,
    params: Mapping[str, Any],
    step_suffix: str | None = None,
    output_subdir: str | None = None,
) -> PlanStep:
    outdir = Path(str(config["outdir"])) / STEP_DIRS[category] / sample.sample_id
    if output_subdir:
        outdir = outdir / output_subdir
    step_id = f"{sample.sample_id}_{category}_{tool_id}"
    if step_suffix:
        step_id = f"{step_id}_{step_suffix}"
    outputs = {"output_dir": str(outdir)}
    step_params = dict(params)
    step_params.update({"output_dir": str(outdir), "sample_id": sample.sample_id})
    if tool_id == "metaphlan":
        step_params.update(_metaphlan_params(step_params))
    step_params.update(_tool_runtime_params(config, tool_id))
    return PlanStep(
        step_id=step_id,
        sample_id=sample.sample_id,
        step_name=category,
        tool_id=tool_id,
        category=category,
        inputs=sample.to_dict(),
        outputs=outputs,
        params=step_params,
    )


def _metaphlan_params(params: Mapping[str, Any]) -> Dict[str, str]:
    read1 = str(params.get("read1") or "")
    read2 = str(params.get("read2") or "")
    long_reads = str(params.get("long_reads") or "")
    if read1:
        metaphlan_input = f"{read1},{read2}" if read2 else read1
        return {"metaphlan_input": metaphlan_input, "metaphlan_long_reads_flag": ""}
    if long_reads:
        return {"metaphlan_input": long_reads, "metaphlan_long_reads_flag": "--long_reads"}
    return {"metaphlan_input": "", "metaphlan_long_reads_flag": ""}


def _tool_runtime_params(config: Mapping[str, Any], tool_id: str) -> Dict[str, Any]:
    params: Dict[str, Any] = {}
    for section in ("resources", "tool_params"):
        values = config.get(section, {})
        if isinstance(values, Mapping):
            tool_values = values.get(tool_id, {})
            if isinstance(tool_values, Mapping):
                params.update(tool_values)
    return _normalize_tool_runtime_params(tool_id, params)


def _normalize_tool_runtime_params(tool_id: str, params: Dict[str, Any]) -> Dict[str, Any]:
    if tool_id == "genomad" and params.get("database"):
        database = Path(str(params["database"]))
        nested_database = database / "genomad_db"
        if (nested_database / "version.txt").exists():
            params["database"] = str(nested_database)
    return params


def _plasmid_contigs_path(
    sample: SampleInput,
    config: Mapping[str, Any],
    assembly_path: str,
) -> str:
    workflow = config.get("workflow", {})
    source = workflow.get("plasmid_contigs_source") if isinstance(workflow, Mapping) else None
    if source == "assembly" or (source is None and sample.platform == "assembly"):
        return assembly_path
    return str(
        Path(str(config["outdir"]))
        / STEP_DIRS["plasmid_detection"]
        / sample.sample_id
        / "plasmid_contigs.fasta"
    )


def _skip(sample: SampleInput, category: str, reason: str) -> PlanStep:
    return PlanStep(
        step_id=f"{sample.sample_id}_{category}_skipped",
        sample_id=sample.sample_id,
        step_name=category,
        tool_id="internal",
        category=category,
        reason=reason,
        skipped=True,
    )


def _unique(values: Iterable[str]) -> List[str]:
    seen = set()
    unique_values = []
    for value in values:
        if value and value not in seen:
            unique_values.append(value)
            seen.add(value)
    return unique_values


# ═══════════════════════════════════════════════════════════════════════════
# DAG-Driven Planner (new — reads pipeline_dag.yaml as source of truth)
# ═══════════════════════════════════════════════════════════════════════════

# Categories whose nodes operate at the PROJECT level (not per-sample).
_PROJECT_LEVEL_CATEGORIES: frozenset[str] = frozenset(
    {"report", "diversity", "network", "statistics"}
)


def build_plan_from_dag(
    config: Mapping[str, Any],
    sample_context: SampleContext | None = None,
    *,
    check_files: bool = True,
) -> ExecutionPlan:
    """Build an execution plan from the canonical ``pipeline_dag.yaml`` spec.

    This replaces the hardcoded ``_route_for_platform()`` / ``_sample_steps()``
    logic.  The DAG spec is the single source of truth for which tools run on
    which platform in which order.  The planner only resolves *how* (paths and
    parameter values).

    Args:
        config: Fully-resolved pipeline configuration (from ``load_config()``).
        sample_context: Pre-parsed sample context.  If ``None``, it is derived
            from the config via ``context_from_config()``.
        check_files: When ``True``, validate that referenced input files exist.

    Returns:
        A fully-typed ``ExecutionPlan`` with topologically ordered steps.
    """
    from abi.dag_planner import UniversalDAG

    dag = UniversalDAG.from_yaml(PLUGIN_ROOT / "metagenomic_plasmid" / "pipeline_dag.yaml")
    context = sample_context or context_from_config(config, check_files=check_files)
    platform = _resolve_platform(context, config)
    outdir = Path(str(config["outdir"]))
    threads = int(config["threads"])

    # Resolve which nodes are active for this platform + config
    active_ids = dag.active_node_ids(platform, config)
    resolved_deps = dag.resolve_dependencies(active_ids, platform)
    order = dag.topological_order(resolved_deps)

    # Separate project-level from sample-level nodes
    project_node_ids = [nid for nid in order if dag.scope_for(nid) == "cross_sample"]
    sample_node_ids = [nid for nid in order if dag.scope_for(nid) == "per_sample"]

    steps: List[PlanStep] = []
    skipped: List[PlanStep] = []

    # Generate per-sample steps with upstream output tracking
    for sample in context.samples:
        sample_params = _dag_sample_base_params(sample, config, platform)
        upstream_outputs: Dict[str, Dict[str, Any]] = {}
        for node_id in sample_node_ids:
            node = dag.get_node(node_id)
            step = _dag_step_for_node(
                node_id=node_id,
                node=node,
                sample=sample,
                config=config,
                platform=platform,
                base_params=sample_params,
                resolved_deps=resolved_deps,
                upstream_outputs=upstream_outputs,
            )
            if step.skipped:
                skipped.append(step)
            else:
                steps.append(step)
                # Track this step's outputs for downstream nodes
                upstream_outputs[node_id] = dict(step.outputs)

    # Generate project-level steps (report, multi-sample analysis)
    project_params = {
        "threads": threads,
        "mode": config.get("mode", "auto"),
        "project_outdir": str(outdir),
        "output_dir": str(outdir / "report"),
        "sample_count": len(context.samples),
        "abundance_table": str(outdir / "10_abundance" / "plasmid_abundance_tpm.tsv"),
    }
    for node_id in project_node_ids:
        node = dag.get_node(node_id)
        step = _dag_project_step(
            node_id=node_id,
            node=node,
            config=config,
            platform=platform,
            params=project_params,
        )
        if step.skipped:
            skipped.append(step)
        else:
            steps.append(step)

    selected_tools = sorted({step.tool_id for step in steps if step.tool_id != "internal"})

    return ExecutionPlan(
        project_name=str(config["project_name"]),
        mode=str(config["mode"]),
        threads=threads,
        outdir=str(outdir),
        log_dir=str(config["log_dir"]),
        samples=context.samples,
        sample_context=context,
        selected_tools=selected_tools,
        steps=steps,
        skipped_steps=skipped,
        provenance_dir=str(outdir / "provenance"),
    )


def _resolve_platform(sample_context: SampleContext, config: Mapping[str, Any]) -> str:
    """Determine the active platform from the sample context or config."""
    if sample_context.samples:
        return sample_context.samples[0].platform
    input_config = config.get("input", {})
    if isinstance(input_config, Mapping):
        plat = input_config.get("platform")
        if plat:
            return str(plat)
    return "illumina"


def _dag_sample_base_params(
    sample: SampleInput,
    config: Mapping[str, Any],
    platform: str,
) -> Dict[str, Any]:
    """Build the base parameter dict shared by all sample-level nodes."""
    params: Dict[str, Any] = sample.to_dict()
    params.update(
        {
            "threads": int(config["threads"]),
            "mode": config.get("mode", "auto"),
            "platform": platform,
            "data_profile": _data_profile_dag(sample, config),
        }
    )
    if platform in {"pacbio_hifi"}:
        params["minimap2_preset"] = "map-hifi"
    elif platform in {"ont", "hybrid"}:
        params["minimap2_preset"] = "map-ont"
    return params


def _data_profile_dag(sample: SampleInput, config: Mapping[str, Any]) -> str:
    """Resolve the data profile label for DAG-driven planning."""
    workflow = config.get("workflow", {})
    if isinstance(workflow, Mapping) and workflow.get("data_profile"):
        return str(workflow["data_profile"])
    input_config = config.get("input", {})
    if isinstance(input_config, Mapping) and input_config.get("data_profile"):
        return str(input_config["data_profile"])
    return DATA_PROFILE_BY_PLATFORM.get(sample.platform, sample.platform)


def _resolve_output_path_template(
    template: str,
    config: Mapping[str, Any],
    sample: SampleInput | None,
    category: str,
) -> str:
    """Resolve a DAG output path template against sample and config context."""
    from abi.dag_planner import PathTemplateContext

    category_dir = STEP_DIRS.get(category, category)
    ctx = PathTemplateContext(
        config=config,
        sample=sample,
        category_dir=category_dir,
    )
    return template.format_map(ctx)


def _resolve_node_inputs(
    node: Mapping[str, Any],
    sample: SampleInput,
    config: Mapping[str, Any],
    upstream_outputs: Mapping[str, Mapping[str, Any]],
) -> Dict[str, Any]:
    """Resolve a DAG node's inputs by merging sample data with upstream outputs.

    For each input key in the node's ``inputs`` spec:
    1. If ``source: UPSTREAM_NODE.OUTPUT_KEY`` → use upstream output path.
    2. If ``fallback: UPSTREAM_NODE.OUTPUT_KEY`` → try fallback when source missing.
    3. Otherwise fall back to sample data or config defaults.
    """
    sample_dict = dict(sample.to_dict())
    resolved: Dict[str, Any] = dict(sample_dict)

    for key, spec in node.get("inputs", {}).items():
        if not isinstance(spec, Mapping):
            resolved.setdefault(key, spec)
            continue

        source = spec.get("source")
        if isinstance(source, str) and "." in source:
            parts = source.split(".", 1)
            upstream_id, upstream_key = parts[0], parts[1]

            # config.* sources: e.g. config.resources.genomad_database
            if upstream_id == "config":
                section: Any = config
                for segment in upstream_key.split("."):
                    if isinstance(section, Mapping) and segment in section:
                        section = section[segment]
                    else:
                        section = None
                        break
                if section is not None:
                    resolved[key] = str(section)
                    continue

            # Handle template source like "{active_assembly_node}.assembly"
            if upstream_id.startswith("{") and upstream_id.endswith("}"):
                # Template reference — try each upstream node
                for uid, uouts in upstream_outputs.items():
                    val = uouts.get(upstream_key)
                    if val:
                        resolved[key] = str(val)
                        break
            else:
                val = upstream_outputs.get(upstream_id, {}).get(upstream_key)
                if val is not None:
                    resolved[key] = str(val)
                    continue

        # Try fallback
        fallback = spec.get("fallback")
        if isinstance(fallback, str) and "." in fallback:
            parts = fallback.split(".", 1)
            fb_id, fb_key = parts[0], parts[1]
            val = upstream_outputs.get(fb_id, {}).get(fb_key)
            if val is not None and key not in resolved:
                resolved[key] = str(val)
                continue

    return resolved


def _dag_step_for_node(
    *,
    node_id: str,
    node: Mapping[str, Any],
    sample: SampleInput,
    config: Mapping[str, Any],
    platform: str,
    base_params: Dict[str, Any],
    resolved_deps: Mapping[str, List[str]],
    upstream_outputs: Mapping[str, Mapping[str, Any]] | None = None,
) -> PlanStep:
    """Build a single ``PlanStep`` for one sample-level DAG node.

    Resolves inputs by merging raw sample data with upstream node outputs
    (following DAG ``source`` references), then falling back to config values.
    """
    tool_id = str(node.get("tool_id", "internal"))
    category = str(node.get("category", ""))
    outdir = Path(str(config["outdir"])) / STEP_DIRS.get(category, category) / sample.sample_id
    step_id = f"{sample.sample_id}_{node_id}"

    # ── Resolve inputs first (outputs may reference them for internal nodes) ──
    resolved_inputs = _resolve_node_inputs(node, sample, config, upstream_outputs or {})

    # Merge node outputs with computed output_dir.
    outputs: Dict[str, Any] = {"output_dir": str(outdir)}
    for key, spec in node.get("outputs", {}).items():
        if isinstance(spec, Mapping) and key != "output_dir":
            path_template = spec.get("path")
            if path_template:
                outputs[key] = _resolve_output_path_template(
                    path_template, config, sample, category
                )
            elif tool_id == "internal" and key in resolved_inputs:
                # Internal nodes pass through their resolved inputs as outputs
                outputs[key] = str(resolved_inputs[key])
            else:
                outputs[key] = str(outdir / f"{sample.sample_id}.{tool_id}.{key}")
    # Ensure output_dir is present in params
    resolved_inputs["output_dir"] = str(outdir)

    # Build params: base + resolved inputs + tool-specific overrides
    step_params: Dict[str, Any] = dict(base_params)
    step_params.update(resolved_inputs)
    step_params["output_dir"] = str(outdir)
    step_params["sample_id"] = sample.sample_id

    # Resolve tool parameters from config
    tool_params = _tool_runtime_params(config, tool_id)
    step_params.update(tool_params)

    # Record which upstream nodes feed into this step (for provenance)
    deps = list(resolved_deps.get(node_id, []))
    if deps:
        step_params["_upstream_nodes"] = deps

    # Embed the step contract from the DAG spec
    step_params["_contract"] = {
        "outputs": node.get("outputs", {}),
        "assertions": node.get("assertions", []),
        "node_id": node_id,
    }

    return PlanStep(
        step_id=step_id,
        sample_id=sample.sample_id,
        step_name=node.get("name", category),
        tool_id=tool_id,
        category=category,
        inputs=resolved_inputs,
        outputs=outputs,
        params=step_params,
    )


def _dag_project_step(
    *,
    node_id: str,
    node: Mapping[str, Any],
    config: Mapping[str, Any],
    platform: str,
    params: Dict[str, Any],
) -> PlanStep:
    """Build a single ``PlanStep`` for one project-level DAG node."""
    tool_id = str(node.get("tool_id", "internal"))
    category = str(node.get("category", ""))
    outdir = Path(str(config["outdir"])) / STEP_DIRS.get(category, category)

    outputs: Dict[str, Any] = {"outdir": str(outdir)}
    for key, spec in node.get("outputs", {}).items():
        if isinstance(spec, Mapping) and key != "outdir":
            path_template = spec.get("path")
            if path_template:
                outputs[key] = _resolve_output_path_template(path_template, config, None, category)
            else:
                outputs[key] = str(outdir / key)

    step_params = dict(params)
    step_params["output_dir"] = str(outdir)

    return PlanStep(
        step_id=node_id,
        sample_id=None,
        step_name=node.get("name", category),
        tool_id=tool_id,
        category=category,
        inputs={},
        outputs=outputs,
        params=step_params,
    )
