"""Markdown report generation."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence

from abi.plugins.metagenomic_plasmid._engine.schemas import ExecutionPlan
from abi.plugins.metagenomic_plasmid._engine.standard_tables import read_standard_table, summarize_standard_tables


def write_markdown_report(
    plan: ExecutionPlan,
    report_dir: str | Path,
    *,
    tables_dir: str | Path | None = None,
    provenance_dir: str | Path | None = None,
    dry_run: bool = False,
) -> Path:
    report_path = Path(report_dir)
    report_path.mkdir(parents=True, exist_ok=True)
    md = report_path / "report.md"
    methods = report_path / "methods.md"
    table_summary = summarize_standard_tables(tables_dir) if tables_dir else {}
    consensus = read_standard_table(tables_dir, "plasmid_consensus") if tables_dir else []
    annotations = read_standard_table(tables_dir, "annotations") if tables_dir else []
    hosts = read_standard_table(tables_dir, "host_predictions") if tables_dir else []
    abundance = read_standard_table(tables_dir, "abundance") if tables_dir else []
    assembly_summary = read_standard_table(tables_dir, "assembly_summary") if tables_dir else []
    diversity = read_standard_table(tables_dir, "sample_diversity") if tables_dir else []
    differential = read_standard_table(tables_dir, "differential_abundance") if tables_dir else []
    network_edges = read_standard_table(tables_dir, "network_edges") if tables_dir else []
    network_nodes = read_standard_table(tables_dir, "network_nodes") if tables_dir else []
    contig_summary = _contig_summary(plan, consensus)

    lines = [
        f"# AutoPlasm Report: {plan.project_name}",
        "",
        "## Run Summary",
        "",
        f"- Samples: {len(plan.samples)}",
        f"- Planned steps: {len(plan.steps)}",
        f"- Mode: {plan.mode}",
        f"- Threads: {plan.threads}",
        f"- Dry-run: {dry_run}",
        "",
    ]
    lines.extend(_assembly_beta_section(plan))
    lines.extend(_ont_beta_section(plan))
    lines.extend(_pacbio_hifi_beta_section(plan))
    lines.extend(_hybrid_beta_section(plan))
    lines.extend(["", "## Selected Tools", ""])
    for tool_id in plan.selected_tools:
        lines.append(f"- `{tool_id}`")
    lines.extend(_standard_table_section(table_summary))
    lines.extend(
        [
            "",
            "## Core Result Summary",
            "",
            f"- Total contigs: {contig_summary['total_contigs']}",
            f"- Predicted plasmid contigs: {contig_summary['predicted_plasmids']}",
            f"- Uncertain contigs: {contig_summary['uncertain_contigs']}",
            f"- Non-plasmid contigs: {contig_summary['non_plasmid_contigs']}",
            f"- Consensus plasmid calls: {_true_count(consensus, 'final_plasmid_call')}",
            f"- Annotation records: {len(annotations)}",
            f"- Host prediction records: {len(hosts)}",
            f"- Abundance records: {len(abundance)}",
            f"- Diversity records: {len(diversity)}",
            f"- Differential abundance records: {len(differential)}",
            f"- Network edges/nodes: {len(network_edges)}/{len(network_nodes)}",
        ]
    )
    lines.extend(_assembly_qc_section(assembly_summary))
    if consensus:
        lines.extend(["", "### Consensus Plasmids", ""])
        for row in consensus[:10]:
            warning = row.get("warnings", "")
            line = (
                "- `{sample}` `{contig}` strategy=`{strategy}` support=`{support}` "
                "confidence=`{confidence}`".format(
                    sample=row.get("sample_id", ""),
                    contig=row.get("contig_id", ""),
                    strategy=row.get("decision_strategy", ""),
                    support=row.get("support_tools", ""),
                    confidence=row.get("confidence_score", ""),
                )
            )
            if warning:
                line += f" warnings={warning}"
            lines.append(line)
    lines.extend(_consensus_warning_section(consensus))
    lines.extend(
        [
            "",
            "## Provenance",
            "",
            f"- Provenance directory: `{provenance_dir or ''}`",
            "- Standard tables are written under `tables/` and should be treated as "
            "the stable interface for downstream interpretation.",
            "",
            "## Interpretation Notes",
            "",
            "- Dry-run proves planning and command rendering only.",
            "- Assembly-only Beta starts from provided contigs and skips read QC, read assembly, "
            "abundance, differential, diversity and network analysis unless reads and matching "
            "modules are explicitly enabled.",
            "- geNomad is treated as primary plasmid evidence; PlasmidFinder and MOB-suite are "
            "supporting evidence in the metagenome profile.",
            "- A supporting-tool hit strengthens a plasmid candidate, but no hit is not evidence "
            "that a contig is non-plasmid.",
            "- Host predictions are evidence labels, not definitive host assignments.",
            "- Plasmid clusters are operational groups, not taxonomic species.",
            "- Plasmid binning results are candidate reconstructions and may be incomplete.",
            "- Network correlations do not prove host assignment or causality.",
        ]
    )
    md.write_text("\n".join(lines) + "\n", encoding="utf-8")

    methods.write_text(
        "\n".join(
            [
                "# Methods",
                "",
                "AutoPlasm generated a platform-aware analysis plan and recorded all "
                "planned commands in the provenance directory.",
                "External bioinformatics tools are invoked through skill wrappers.",
                "Successful core tool steps are parsed into standard TSV tables before "
                "report generation.",
                "geNomad is the default plasmid detector unless the configuration "
                "selects another tool or multi-tool strategy.",
                "In assembly-only beta runs, AutoPlasm starts from provided contigs and "
                "records skipped read-dependent modules in the execution plan.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return md


def _assembly_beta_section(plan: ExecutionPlan) -> list[str]:
    assembly_samples = [sample for sample in plan.samples if sample.platform == "assembly"]
    if not assembly_samples:
        return []
    skipped = _skipped_category_counts(plan)
    skipped_text = ", ".join(f"{category}={count}" for category, count in sorted(skipped.items()))
    lines = [
        "",
        "## Assembly-only Beta Scope",
        "",
        f"- Assembly samples: {len(assembly_samples)}",
        "- Input mode: provided contig FASTA; read QC and read assembly are not rerun.",
    ]
    if skipped_text:
        lines.append(f"- Skipped categories recorded in plan: {skipped_text}")
    lines.append(
        "- Output FASTA sets are operational classifications from parsed consensus evidence."
    )
    return lines


def _ont_beta_section(plan: ExecutionPlan) -> list[str]:
    ont_samples = [sample for sample in plan.samples if sample.platform == "ont"]
    if not ont_samples:
        return []
    return [
        "",
        "## ONT Long-read Beta Scope",
        "",
        f"- ONT samples: {len(ont_samples)}",
        "- Default route: NanoPlot/Filtlong QC, metaFlye assembly, geNomad primary "
        "plasmid evidence, minimap2/samtools/CoverM abundance.",
        "- ONT reads have platform-specific error profiles; plasmid structure, circularity, "
        "and host evidence require cautious interpretation.",
        "- Long-read abundance uses minimap2 and is not interchangeable with short-read "
        "bowtie2 abundance.",
    ]


def _pacbio_hifi_beta_section(plan: ExecutionPlan) -> list[str]:
    hifi_samples = [sample for sample in plan.samples if sample.platform == "pacbio_hifi"]
    if not hifi_samples:
        return []
    return [
        "",
        "## PacBio HiFi Beta Scope",
        "",
        f"- PacBio HiFi samples: {len(hifi_samples)}",
        "- Default route: HiFiAdapterFilt QC, hifiasm/hifiasm-meta assembly fallback, "
        "geNomad primary plasmid evidence, minimap2/samtools/CoverM abundance.",
        "- HiFi reads use different quality and indel assumptions from ONT reads; "
        "planner steps set minimap2 `map-hifi` for PacBio abundance.",
        "- hifiasm graph output is normalized to a FASTA contract before QUAST, "
        "geNomad, annotation and abundance steps consume the assembly.",
    ]


def _hybrid_beta_section(plan: ExecutionPlan) -> list[str]:
    hybrid_samples = [sample for sample in plan.samples if sample.platform == "hybrid"]
    if not hybrid_samples:
        return []
    return [
        "",
        "## Hybrid Short+Long Beta Scope",
        "",
        f"- Hybrid samples: {len(hybrid_samples)}",
        "- Default route: fastp/FastQC/MultiQC plus NanoPlot/Filtlong QC, "
        "OPERA-MS hybrid assembly, geNomad primary plasmid evidence, and "
        "separate bowtie2 and minimap2 abundance tracks.",
        "- Short-read and long-read abundance are recorded as separate provenance "
        "steps and output files; they should not be merged without an explicit "
        "normalization policy.",
        "- Hybrid assembly can improve continuity but may also combine conflicting "
        "signals in complex metagenomes; plasmid structure and host evidence remain "
        "candidate interpretations.",
    ]


def _consensus_warning_section(consensus: Sequence[Mapping[str, str]]) -> list[str]:
    warnings = []
    for row in consensus:
        warning = row.get("warnings", "")
        if warning and warning not in warnings:
            warnings.append(warning)
    if not warnings:
        return []
    lines = ["", "### Evidence Warnings", ""]
    for warning in warnings[:10]:
        lines.append(f"- {warning}")
    return lines


def _skipped_category_counts(plan: ExecutionPlan) -> dict[str, int]:
    counts: dict[str, int] = {}
    for step in plan.skipped_steps:
        counts[step.category] = counts.get(step.category, 0) + 1
    return counts


def _standard_table_section(table_summary: Mapping[str, Mapping[str, Any]]) -> list[str]:
    if not table_summary:
        return []
    lines = ["", "## Standard Tables", ""]
    for table_name, metadata in sorted(table_summary.items()):
        lines.append(
            f"- `{table_name}.tsv`: {metadata.get('rows', 0)} rows (`{metadata.get('path', '')}`)"
        )
    return lines


def _true_count(rows: Sequence[Mapping[str, str]], field: str) -> int:
    return sum(1 for row in rows if str(row.get(field, "")).lower() == "true")


def _contig_summary(plan: ExecutionPlan, consensus: Sequence[Mapping[str, str]]) -> dict[str, int]:
    total_contigs = 0
    assembly_paths = _assembly_paths_by_sample(plan)
    for sample in plan.samples:
        assembly = sample.assembly or assembly_paths.get(sample.sample_id)
        if assembly:
            total_contigs += _count_fasta_records(Path(assembly))
    consensus_keys = {
        (row.get("sample_id", ""), row.get("contig_id", ""))
        for row in consensus
        if row.get("sample_id") and row.get("contig_id")
    }
    predicted = _true_count(consensus, "final_plasmid_call")
    uncertain = max(len(consensus_keys) - predicted, 0)
    non_plasmid = max(total_contigs - len(consensus_keys), 0)
    return {
        "total_contigs": total_contigs,
        "predicted_plasmids": predicted,
        "uncertain_contigs": uncertain,
        "non_plasmid_contigs": non_plasmid,
    }


def _count_fasta_records(path: Path) -> int:
    if not path.exists():
        return 0
    with path.open("r", encoding="utf-8") as handle:
        return sum(1 for line in handle if line.startswith(">"))


def _assembly_paths_by_sample(plan: ExecutionPlan) -> dict[str, str]:
    paths: dict[str, str] = {}
    for step in plan.steps:
        if step.sample_id and step.params.get("assembly") and step.sample_id not in paths:
            paths[step.sample_id] = str(step.params["assembly"])
    return paths


def _assembly_qc_section(rows: Sequence[Mapping[str, str]]) -> list[str]:
    if not rows:
        return ["", "### Assembly QC Summary", "", "- No assembly QC records were parsed."]
    preferred = {
        "# contigs",
        "Total length",
        "Largest contig",
        "N50",
        "GC (%)",
        "GC",
    }
    selected = [row for row in rows if row.get("metric", "") in preferred]
    if not selected:
        selected = list(rows[:8])
    lines = ["", "### Assembly QC Summary", ""]
    for row in selected[:12]:
        unit = row.get("unit", "")
        suffix = f" {unit}" if unit else ""
        lines.append(
            "- `{sample}` {metric}: {value}{suffix}".format(
                sample=row.get("sample_id", ""),
                metric=row.get("metric", ""),
                value=row.get("value", ""),
                suffix=suffix,
            )
        )
    return lines
