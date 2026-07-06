"""Plasmid-specific context resolver for DAG-based planning.

Ports ``_resolve_context_conditions`` from ``planner.py`` into the
``PluginContextResolver`` hook interface so the universal DAG planner
can resolve auto/conditional pipeline settings.
"""

from __future__ import annotations

from collections import Counter
from typing import Any, Mapping

from abi.dag_planner import EligibilityResult, PluginContextResolver


class PlasmidContextResolver(PluginContextResolver):
    """Resolve auto/conditional plasmid pipeline settings from sample metadata.

    Replaces ``_engine/planner.py:_resolve_context_conditions()``.  Call
    ``resolve()`` to compute enabled/disabled flags for diversity analysis,
    differential abundance, network inference, and host-plasmid co-abundance
    linking, then call ``eligibility()`` to retrieve the per-feature
    eligibility report.
    """

    def resolve(self) -> dict[str, Any]:
        """Resolve auto/conditional settings in-place.

        Updates ``config.sample_analysis``, ``config.network``, and
        ``config.host_plasmid_linking`` with boolean enable flags
        derived from actual sample metadata (counts, groups, platforms).
        """
        config = dict(self._config)
        context = self._context
        sample_count = len(context.samples)
        abundance_samples = [s for s in context.samples if s.platform != "assembly"]
        abundance_sample_count = len(abundance_samples)
        group_counts = Counter(s.group for s in abundance_samples if s.group)
        has_read_inputs = abundance_sample_count > 0

        # ── sample_analysis ──────────────────────────────────────────────
        sample_analysis = config.setdefault("sample_analysis", {})
        if not isinstance(sample_analysis, dict):
            sample_analysis = {}
            config["sample_analysis"] = sample_analysis
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

        # ── network ─────────────────────────────────────────────────────
        network = config.setdefault("network", {})
        if not isinstance(network, dict):
            network = {}
            config["network"] = network
        network_requested = _requested(network.get("enable", "auto"))
        min_network = int(network.get("min_samples", 20))
        run_network = (
            network_requested and has_read_inputs and abundance_sample_count >= min_network
        )
        network["enable"] = run_network
        network["run_network"] = run_network

        # ── host_plasmid_linking ─────────────────────────────────────────
        host_linking = config.setdefault("host_plasmid_linking", {})
        if not isinstance(host_linking, dict):
            host_linking = {}
            config["host_plasmid_linking"] = host_linking
        methods = host_linking.get("methods", [])
        host_linking_enabled = _requested(host_linking.get("enable", False))
        coabundance_requested = (
            host_linking_enabled and isinstance(methods, list) and "co_abundance" in methods
        )
        host_prediction = config.get("host_prediction", {})
        host_profile_enabled = isinstance(host_prediction, Mapping) and _requested(
            host_prediction.get("enable", False)
        )
        run_coabundance = (
            coabundance_requested
            and host_profile_enabled
            and abundance_sample_count >= min_diversity
        )
        host_linking["enable"] = host_linking_enabled
        host_linking["run_coabundance"] = run_coabundance

        self._config = config
        return config

    def eligibility(self) -> dict[str, EligibilityResult]:
        """Return eligibility results for all evaluated features."""
        config = self._config
        context = self._context
        sample_count = len(context.samples)
        abundance_samples = [s for s in context.samples if s.platform != "assembly"]
        abundance_sample_count = len(abundance_samples)
        group_counts = Counter(s.group for s in abundance_samples if s.group)

        sample_analysis = config.get("sample_analysis", {})
        if not isinstance(sample_analysis, dict):
            sample_analysis = {}
        min_diversity = int(sample_analysis.get("min_diversity_samples", 3))
        min_replicates = int(sample_analysis.get("min_group_replicates", 3))
        run_diversity = bool(sample_analysis.get("run_diversity", False))
        run_differential = bool(sample_analysis.get("run_differential", False))

        network = config.get("network", {})
        if not isinstance(network, dict):
            network = {}
        min_network = int(network.get("min_samples", 20))
        run_network = bool(network.get("run_network", False))

        host_linking = config.get("host_plasmid_linking", {})
        if not isinstance(host_linking, dict):
            host_linking = {}
        run_coabundance = bool(host_linking.get("run_coabundance", False))

        return {
            "diversity": EligibilityResult(
                run=run_diversity,
                sample_count=sample_count,
                eligible_sample_count=abundance_sample_count,
                threshold=min_diversity,
                reason=(
                    "eligible"
                    if run_diversity
                    else (
                        f"requires at least {min_diversity} samples with "
                        "read-based abundance"
                    )
                ),
            ),
            "differential_abundance": EligibilityResult(
                run=run_differential,
                sample_count=sample_count,
                eligible_sample_count=abundance_sample_count,
                threshold=min_replicates,
                reason=(
                    "eligible"
                    if run_differential
                    else (
                        "requires at least two groups and "
                        f"{min_replicates} biological replicates per group"
                    )
                ),
            ),
            "network": EligibilityResult(
                run=run_network,
                sample_count=sample_count,
                eligible_sample_count=abundance_sample_count,
                threshold=min_network,
                reason=(
                    "eligible"
                    if run_network
                    else (
                        f"requires at least {min_network} samples with "
                        "read-based abundance"
                    )
                ),
            ),
            "host_plasmid_coabundance": EligibilityResult(
                run=run_coabundance,
                sample_count=sample_count,
                eligible_sample_count=abundance_sample_count,
                threshold=min_diversity,
                reason=(
                    "eligible"
                    if run_coabundance
                    else (
                        "requires host profiling and at least "
                        f"{min_diversity} samples with read-based abundance"
                    )
                ),
            ),
        }


def _requested(value: Any) -> bool:
    """Interpret truthiness of a config value (auto → True)."""
    if isinstance(value, str):
        return value.strip().lower() not in {"false", "no", "0", "off", "disabled"}
    return value is not False

# ── Per-sample config helpers (Stage 5) ────────────────────────────────
# Ported from planner.py.  These are used by config_for_sample() which
# the new DAG planner calls as sample_config_hook.
# / 从 planner.py 移植。config_for_sample() 作为 sample_config_hook 使用。


DATA_PROFILE_BY_PLATFORM = {
    "illumina": "illumina_short",
    "ont": "ont_long",
    "pacbio_hifi": "pacbio_hifi",
    "hybrid": "hybrid_short_long",
    "assembly": "assembly_only",
}

ISOLATE_PROFILES = {"isolate_plasmid", "isolate"}


def _enable_state(config: Mapping[str, Any], key: str, default: Any = True) -> Any:
    block = config.get(key)
    if isinstance(block, Mapping):
        return block.get("enable", default)
    if block is None:
        return default
    return block


def _is_isolate_profile(data_profile: str) -> bool:
    return data_profile in ISOLATE_PROFILES or data_profile.endswith("_isolate")


def _category_enabled(
    config: Mapping[str, Any],
    category: str,
    data_profile: str,
    sample,  # SampleInput
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


def _default_tools_for_category(category: str, data_profile: str) -> list:
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


def _annotation_tools(config: Mapping[str, Any], data_profile: str) -> list:
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


def _data_profile_dag(sample, config: Mapping[str, Any]) -> str:
    """Resolve the data profile label for DAG-driven planning."""
    workflow = config.get("workflow", {})
    if isinstance(workflow, Mapping) and workflow.get("data_profile"):
        return str(workflow["data_profile"])
    input_config = config.get("input", {})
    if isinstance(input_config, Mapping) and input_config.get("data_profile"):
        return str(input_config["data_profile"])
    return DATA_PROFILE_BY_PLATFORM.get(sample.platform, sample.platform)


def config_for_sample(config: Mapping[str, Any], sample: Any) -> dict[str, Any]:
    """Generate a per-sample config with resolved auto/conditional settings.

    This is the sample_config_hook for the new DAG planner.  It deep‑copies
    the project config, then adjusts input paths, host_removal, assembly
    defaults, auto‑detected tool lists, and annotation tools for the given
    sample.

    Replaces ``planner.py:_config_for_sample()``.
    """
    from copy import deepcopy

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
    host_removal["host_reference"] = (
        sample.host_reference or host_removal.get("host_reference")
    )

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
            for key in (
                "general_annotator", "arg_tools", "vf_tools", "mobile_element_tools"
            )
        )
    ):
        annotation["tools"] = _annotation_tools(resolved, data_profile)
    return resolved
