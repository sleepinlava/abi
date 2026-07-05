"""Execution plan generation."""
from __future__ import annotations




import os
from collections import Counter
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

from abi.config import PLUGIN_ROOT
from abi.dag_planner import build_sample_context
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

_LEGACY_BUILD_PLAN = os.environ.get("ABI_DAG_PLANNER_LEGACY", "") == "1"
STEP_DIRS = {
    "input_validation": "00_input_validation",
    "basecalling": "00_input_validation/basecalling",
    "qc": "01_qc",
    "host_removal": "01_qc/host_removal",
    "assembly": "02_assembly",
    "contig_coverage": "02_assembly/coverage",
    "assembly_qc": "03_assembly_qc",
    "plasmid_detection": "04_plasmid_detection",
    "plasmid_consensus": "04_plasmid_detection",
    "plasmid_binning": "05_plasmid_binning",
    "typing": "06_plasmid_typing",
    "host_prediction": "07_host_prediction",
    "host_plasmid_linking": "07_host_prediction",
    "mag_host_genomes": "07_host_prediction/mag",
    "annotation": "08_annotation",
    "comparative_genomics": "09_comparative_genomics",
    "abundance": "10_abundance",
    "diversity": "11_diversity",
    "statistics": "11_diversity",
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
    if not single_input and not any(
        input_config.get(key) for key in ("assembly", "long_reads", "pod5", "bam")
    ):
        raise ValueError(
            "No sample_sheet or single_input/assembly/long_reads/pod5/bam is configured"
        )
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
        pod5=input_config.get("pod5"),
        bam=input_config.get("bam"),
        assembly=assembly,
        group=input_config.get("group"),
        check_files=check_files,
    )


def _build_plan_legacy(
    config: Mapping[str, Any],
    sample_context: Optional[SampleContext] = None,
    *,
    check_files: bool = True,
) -> ExecutionPlan:
    """Compatibility entry point backed exclusively by the declarative DAG."""
    return build_plan_from_dag(
        config,
        sample_context=sample_context,
        check_files=check_files,
    )


def _build_plan_new(
    config: Mapping[str, Any],
    sample_context: Optional[SampleContext] = None,
    *,
    check_files: bool = True,
) -> ExecutionPlan:
    """New DAG planner path — calls dag_planner.build_plan_from_dag with hooks.

    Stages 1-4: Replaces context_from_config, _resolve_context_conditions,
    _config_for_sample, and _analysis_skip_steps with equivalent hooks.
    """
    from abi.dag_planner import build_plan_from_dag as dag_build
    from abi.dag_planner import build_sample_context

    if sample_context is None:
        sample_context = build_sample_context(config, check_files=check_files)

    # ── context_resolver hook (Stage 2) ───────────────────────────────
    # Wraps PlasmidContextResolver to match the ContextResolverHook signature.
    def _context_resolver_hook(cfg, ctx):
        from abi.plugins.metagenomic_plasmid._engine.context_resolver import (
            PlasmidContextResolver,
        )
        resolver = PlasmidContextResolver(cfg, ctx)
        resolved = resolver.resolve()
        eligibility = resolver.eligibility()
        return resolved, eligibility

    # ── skip_step_hook (Stage 4) ────────────────────────────────────
    # The DAG's enable_conditions (evaluated by active_node_ids) and
    # context_resolver already handle most conditional skipping.
    # assembly-only samples skip QC, which we handle here.
    def _skip_step_hook(node_id, tool_id, sample_config, sample):
        if sample.platform == "assembly" and node_id in (
            "qc_fastp", "qc_fastqc", "qc_multiqc",
            "qc_nanoplot", "qc_filtlong", "qc_porechop",
        ):
            return f"Assembly-only input skips {node_id}"
        return None

    # ── sample_config_hook (Stage 5) ────────────────────────────────────
    # Import from context_resolver to decouple from planner.py internals.
    from abi.plugins.metagenomic_plasmid._engine.context_resolver import (
        config_for_sample as _build_plan_sample_config,
    )

    dag_path = PLUGIN_ROOT / "metagenomic_plasmid" / "pipeline_dag.yaml"

    return dag_build(
        dag_spec_path=str(dag_path),
        config=config,
        sample_context=sample_context,
        context_resolver=_context_resolver_hook,
        sample_config_hook=_build_plan_sample_config,
        skip_step_hook=_skip_step_hook,
    )

def build_plan(
    config: Mapping[str, Any],
    sample_context: Optional[SampleContext] = None,
    *,
    check_files: bool = True,
) -> ExecutionPlan:
    """Entry point that dispatches based on ABI_DAG_PLANNER_LEGACY feature flag."""
    if _LEGACY_BUILD_PLAN:
        return _build_plan_legacy(
            config, sample_context=sample_context, check_files=check_files
        )
    else:
        return _build_plan_new(
            config, sample_context=sample_context, check_files=check_files
        )


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


def _is_isolate_profile(data_profile: str) -> bool:
    return data_profile in ISOLATE_PROFILES or data_profile.endswith("_isolate")


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
    resolved_config, eligibility = _resolve_context_conditions(config, context)
    outdir = Path(str(config["outdir"]))
    threads = int(config["threads"])

    steps: List[PlanStep] = []
    skipped: List[PlanStep] = _analysis_skip_steps(eligibility)
    project_node_ids: List[str] = []
    project_node_seen: set[str] = set()
    project_platform = "mixed"

    # Resolve platform and sample-dependent conditions independently.  A sample
    # sheet may legitimately mix Illumina, ONT, HiFi, hybrid, and assembly-only
    # inputs, and host removal is enabled only for rows with host_reference.
    for sample in context.samples:
        platform = sample.platform
        if platform == "assembly":
            skipped.append(
                PlanStep(
                    step_id=f"{sample.sample_id}_qc_not_run",
                    sample_id=sample.sample_id,
                    step_name="qc",
                    tool_id="internal",
                    category="qc",
                    reason="Assembly-only input skips read QC",
                    skipped=True,
                )
            )
        sample_config = _config_for_sample(resolved_config, sample)
        active_ids = dag.active_node_ids(platform, sample_config)
        resolved_deps = dag.resolve_dependencies(active_ids, platform)
        order = dag.topological_order(resolved_deps)
        sample_node_ids = [nid for nid in order if dag.scope_for(nid) == "per_sample"]
        for node_id in order:
            if dag.scope_for(node_id) == "cross_sample" and node_id not in project_node_seen:
                project_node_ids.append(node_id)
                project_node_seen.add(node_id)

        sample_params = _dag_sample_base_params(sample, sample_config, platform)
        upstream_outputs: Dict[str, Dict[str, Any]] = {}
        for node_id in sample_node_ids:
            node = dag.get_node(node_id)
            step = _dag_step_for_node(
                node_id=node_id,
                node=node,
                sample=sample,
                config=sample_config,
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

    # Order the union of cross-sample nodes deterministically across mixed
    # platforms.  Dependencies on per-sample nodes are deliberately omitted
    # here because their steps have already been emitted above.
    project_order = [
        node_id
        for node_id in dag.topological_order(project_node_ids)
        if node_id in project_node_ids
    ]
    project_params = {
        "threads": threads,
        "mode": resolved_config.get("mode", "auto"),
        "project_outdir": str(outdir),
        "output_dir": str(outdir / "report"),
        "sample_count": len(context.samples),
        "abundance_table": str(outdir / "tables" / "plasmid_abundance.tsv"),
    }
    project_outputs: Dict[str, Dict[str, Any]] = {}
    for node_id in project_order:
        node = dag.get_node(node_id)
        step = _dag_project_step(
            node_id=node_id,
            node=node,
            config=resolved_config,
            platform=project_platform,
            params=project_params,
            upstream_outputs=project_outputs,
        )
        if step.skipped:
            skipped.append(step)
        else:
            steps.append(step)
            project_outputs[node_id] = dict(step.outputs)

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


def _resolve_context_conditions(
    config: Mapping[str, Any], context: SampleContext
) -> tuple[Dict[str, Any], Dict[str, Dict[str, Any]]]:
    """Resolve auto/conditional downstream settings from actual sample metadata."""
    resolved = deepcopy(dict(config))
    sample_count = len(context.samples)
    abundance_samples = [sample for sample in context.samples if sample.platform != "assembly"]
    abundance_sample_count = len(abundance_samples)
    group_counts = Counter(sample.group for sample in abundance_samples if sample.group)
    has_read_inputs = abundance_sample_count > 0

    sample_analysis = resolved.setdefault("sample_analysis", {})
    if not isinstance(sample_analysis, dict):
        sample_analysis = {}
        resolved["sample_analysis"] = sample_analysis
    analysis_requested = _requested(sample_analysis.get("enable", "auto"))
    min_diversity = int(sample_analysis.get("min_diversity_samples", 3))
    min_replicates = int(sample_analysis.get("min_group_replicates", 3))
    run_diversity = (
        analysis_requested and has_read_inputs and abundance_sample_count >= min_diversity
    )
    differential_requested = analysis_requested and _requested(
        sample_analysis.get("differential_abundance", "auto")
    )
    run_differential = (
        differential_requested
        and has_read_inputs
        and len(group_counts) >= 2
        and all(count >= min_replicates for count in group_counts.values())
    )
    sample_analysis["enable"] = run_diversity
    sample_analysis["run_diversity"] = run_diversity
    sample_analysis["differential_abundance"] = run_differential
    sample_analysis["run_differential"] = run_differential
    differential_method = str(sample_analysis.get("differential_method", "deseq2"))
    sample_analysis["run_differential_deseq2"] = (
        run_differential and differential_method == "deseq2"
    )
    sample_analysis["run_differential_internal"] = (
        run_differential and differential_method == "internal_effect_size"
    )

    network = resolved.setdefault("network", {})
    if not isinstance(network, dict):
        network = {}
        resolved["network"] = network
    network_requested = _requested(network.get("enable", "auto"))
    min_network = int(network.get("min_samples", 20))
    run_network = network_requested and has_read_inputs and abundance_sample_count >= min_network
    network["enable"] = run_network
    network["run_network"] = run_network

    host_linking = resolved.setdefault("host_plasmid_linking", {})
    if not isinstance(host_linking, dict):
        host_linking = {}
        resolved["host_plasmid_linking"] = host_linking
    methods = host_linking.get("methods", [])
    host_linking_enabled = _requested(host_linking.get("enable", False))
    coabundance_requested = (
        host_linking_enabled and isinstance(methods, list) and "co_abundance" in methods
    )
    host_prediction = resolved.get("host_prediction", {})
    host_profile_enabled = isinstance(host_prediction, Mapping) and _requested(
        host_prediction.get("enable", False)
    )
    run_coabundance = (
        coabundance_requested and host_profile_enabled and abundance_sample_count >= min_diversity
    )
    host_linking["enable"] = host_linking_enabled
    host_linking["run_coabundance"] = run_coabundance

    eligibility = {
        "diversity": {
            "run": run_diversity,
            "sample_count": sample_count,
            "eligible_sample_count": abundance_sample_count,
            "threshold": min_diversity,
            "reason": (
                "eligible"
                if run_diversity
                else f"requires at least {min_diversity} samples with read-based abundance"
            ),
        },
        "differential_abundance": {
            "run": run_differential,
            "sample_count": sample_count,
            "eligible_sample_count": abundance_sample_count,
            "group_counts": dict(sorted(group_counts.items())),
            "threshold": min_replicates,
            "reason": (
                "eligible"
                if run_differential
                else (
                    "requires at least two groups and "
                    f"{min_replicates} biological replicates per group"
                )
            ),
        },
        "network": {
            "run": run_network,
            "sample_count": sample_count,
            "eligible_sample_count": abundance_sample_count,
            "threshold": min_network,
            "reason": (
                "eligible"
                if run_network
                else f"requires at least {min_network} samples with read-based abundance"
            ),
        },
        "host_plasmid_coabundance": {
            "run": run_coabundance,
            "report_skip": coabundance_requested,
            "sample_count": sample_count,
            "eligible_sample_count": abundance_sample_count,
            "threshold": min_diversity,
            "reason": (
                "eligible"
                if run_coabundance
                else (
                    "requires host profiling and at least "
                    f"{min_diversity} samples with read-based abundance"
                )
            ),
        },
    }
    return resolved, eligibility


def _requested(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() not in {"false", "no", "0", "off", "disabled"}
    return value is not False


def _config_for_sample(config: Mapping[str, Any], sample: SampleInput) -> Dict[str, Any]:
    resolved = deepcopy(dict(config))
    input_config = resolved.setdefault("input", {})
    if not isinstance(input_config, dict):
        input_config = {}
        resolved["input"] = input_config
    input_config.update(
        {
            "long_reads": sample.long_reads,
            "pod5": sample.pod5,
            "bam": sample.bam,
        }
    )
    host_removal = resolved.setdefault("host_removal", {})
    if not isinstance(host_removal, dict):
        host_removal = {}
        resolved["host_removal"] = host_removal
    host_removal["host_reference"] = sample.host_reference or host_removal.get("host_reference")

    data_profile = _data_profile_dag(sample, resolved)
    assembly = resolved.get("assembly")
    if not isinstance(assembly, dict):
        assembly = {}
        resolved["assembly"] = assembly
    assembly.setdefault("short_read_assembler", "megahit")
    assembly.setdefault("long_read_assembler", "metaflye")
    assembly.setdefault("pacbio_hifi_assembler", "hifiasm_meta")
    assembly.setdefault("hybrid_assembler", "opera_ms")
    if sample.platform == "assembly":
        assembly["enable"] = True

    for category in ("plasmid_binning", "typing", "host_prediction"):
        block = resolved.get(category)
        if not isinstance(block, dict):
            block = {}
            resolved[category] = block
        enabled = block.get("enable", False)
        if enabled == "auto":
            block["enable"] = _category_enabled(resolved, category, data_profile, sample)
        configured_tools = block.get("tools", "auto")
        if block.get("enable") and (configured_tools == "auto" or configured_tools is None):
            block["tools"] = _default_tools_for_category(category, data_profile)

    annotation = resolved.get("annotation")
    if isinstance(annotation, dict) and (
        _is_isolate_profile(data_profile)
        or any(
            key in annotation
            for key in ("general_annotator", "arg_tools", "vf_tools", "mobile_element_tools")
        )
    ):
        annotation["tools"] = _annotation_tools(resolved, data_profile)
    return resolved


def _analysis_skip_steps(
    eligibility: Mapping[str, Mapping[str, Any]],
) -> List[PlanStep]:
    skipped: List[PlanStep] = []
    for module, status in eligibility.items():
        if status.get("run") or status.get("report_skip") is False:
            continue
        reason = str(status.get("reason", "eligibility requirements were not met"))
        skipped.append(
            PlanStep(
                step_id=f"{module}_not_run",
                sample_id=None,
                step_name=module,
                tool_id="internal",
                category="network" if module == "network" else "statistics",
                params=dict(status),
                reason=reason,
                skipped=True,
            )
        )
    return skipped


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
                val = None
                for uid, uouts in reversed(list(upstream_outputs.items())):
                    val = uouts.get(upstream_key)
                    if val:
                        resolved[key] = str(val)
                        break
                if val:
                    continue
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
            if val is not None:
                resolved[key] = str(val)
                continue

        if spec.get("default") is not None and not resolved.get(key):
            resolved[key] = spec["default"]

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
    output_specs = node.get("outputs", {})
    declared_output_dir = (
        output_specs.get("output_dir") if isinstance(output_specs, Mapping) else None
    )
    if isinstance(declared_output_dir, Mapping) and declared_output_dir.get("path"):
        outdir = Path(
            _resolve_output_path_template(
                str(declared_output_dir["path"]),
                config,
                sample,
                category,
            )
        )
    step_id = f"{sample.sample_id}_{node_id}"

    # ── Resolve inputs first (outputs may reference them for internal nodes) ──
    resolved_inputs = _resolve_node_inputs(node, sample, config, upstream_outputs or {})

    # Merge node outputs with computed output_dir.
    outputs: Dict[str, Any] = {"output_dir": str(outdir)}
    for key, spec in output_specs.items():
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
    if tool_id == "metaphlan":
        step_params.update(_metaphlan_params(step_params))

    # Resolve tool parameters from config
    tool_params = _tool_runtime_params(config, tool_id)
    step_params.update(tool_params)

    # Record which upstream nodes feed into this step (for provenance)
    deps = list(resolved_deps.get(node_id, []))
    if deps:
        step_params["_upstream_nodes"] = deps

    # Embed the step contract from the DAG spec
    step_params["_contract"] = {
        "inputs": node.get("inputs", {}),
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
        reason=f"active DAG node {node_id!r} for platform {platform!r}",
    )


def _dag_project_step(
    *,
    node_id: str,
    node: Mapping[str, Any],
    config: Mapping[str, Any],
    platform: str,
    params: Dict[str, Any],
    upstream_outputs: Mapping[str, Mapping[str, Any]] | None = None,
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

    resolved_inputs: Dict[str, Any] = {}
    for key, spec in node.get("inputs", {}).items():
        if not isinstance(spec, Mapping):
            resolved_inputs[key] = spec
            continue
        source = spec.get("source")
        if source == "sample_sheet":
            input_config = config.get("input", {})
            if isinstance(input_config, Mapping):
                resolved_inputs[key] = input_config.get("sample_sheet", "")
        elif isinstance(source, str) and "." in source:
            source_node, source_key = source.split(".", 1)
            if source_node == "config":
                value: Any = config
                for segment in source_key.split("."):
                    value = value.get(segment) if isinstance(value, Mapping) else None
                if value is not None:
                    resolved_inputs[key] = value
            else:
                value = (upstream_outputs or {}).get(source_node, {}).get(source_key)
                if value is not None:
                    resolved_inputs[key] = value
        if key not in resolved_inputs and spec.get("default") is not None:
            resolved_inputs[key] = spec["default"]

    step_params = dict(params)
    step_params.update(resolved_inputs)
    step_params["output_dir"] = str(outdir)
    step_params["_contract"] = {
        "inputs": node.get("inputs", {}),
        "outputs": node.get("outputs", {}),
        "assertions": node.get("assertions", []),
        "node_id": node_id,
    }

    return PlanStep(
        step_id=node_id,
        sample_id=None,
        step_name=node.get("name", category),
        tool_id=tool_id,
        category=category,
        inputs=resolved_inputs,
        outputs=outputs,
        params=step_params,
        reason=f"active cross-sample DAG node {node_id!r}",
    )
