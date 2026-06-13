"""HTML report generation."""

from __future__ import annotations

from html import escape
from pathlib import Path
from typing import Mapping, Sequence

from abi.autoplasm.schemas import ExecutionPlan
from abi.autoplasm.standard_tables import read_standard_table, summarize_standard_tables


def write_html_report(
    plan: ExecutionPlan,
    report_dir: str | Path,
    *,
    tables_dir: str | Path | None = None,
    provenance_dir: str | Path | None = None,
    dry_run: bool = False,
) -> Path:
    report_path = Path(report_dir)
    report_path.mkdir(parents=True, exist_ok=True)
    html = report_path / "report.html"
    items = "\n".join(f"<li>{escape(tool)}</li>" for tool in plan.selected_tools)
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
    assembly_beta = _assembly_beta_html(plan)
    ont_beta = _ont_beta_html(plan)
    hifi_beta = _pacbio_hifi_beta_html(plan)
    hybrid_beta = _hybrid_beta_html(plan)
    warnings_html = _consensus_warnings_html(consensus)
    assembly_qc_html = _assembly_qc_html(assembly_summary)
    html.write_text(
        f"""<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>AutoPlasm Report</title></head>
<body>
<h1>AutoPlasm Report: {escape(plan.project_name)}</h1>
<p>Samples: {len(plan.samples)}. Planned steps: {len(plan.steps)}. Dry-run: {dry_run}.</p>
{assembly_beta}
{ont_beta}
{hifi_beta}
{hybrid_beta}
<h2>Selected Tools</h2>
<ul>{items}</ul>
<h2>Standard Tables</h2>
{_table_summary_html(table_summary)}
<h2>Core Result Summary</h2>
<ul>
<li>Total contigs: {contig_summary["total_contigs"]}</li>
<li>Predicted plasmid contigs: {contig_summary["predicted_plasmids"]}</li>
<li>Uncertain contigs: {contig_summary["uncertain_contigs"]}</li>
<li>Non-plasmid contigs: {contig_summary["non_plasmid_contigs"]}</li>
<li>Consensus plasmid calls: {_true_count(consensus, "final_plasmid_call")}</li>
<li>Annotation records: {len(annotations)}</li>
<li>Host prediction records: {len(hosts)}</li>
<li>Abundance records: {len(abundance)}</li>
<li>Diversity records: {len(diversity)}</li>
<li>Differential abundance records: {len(differential)}</li>
<li>Network edges/nodes: {len(network_edges)}/{len(network_nodes)}</li>
</ul>
{assembly_qc_html}
{warnings_html}
<h2>Provenance</h2>
<p>{escape(str(provenance_dir or ""))}</p>
<h2>Interpretation Notes</h2>
<p>Dry-run proves planning only. Assembly-only Beta starts from provided contigs and
skips read-dependent QC, assembly, abundance, differential, diversity and network
analysis unless matching inputs and modules are enabled. geNomad is primary plasmid
evidence; PlasmidFinder and MOB-suite are supporting evidence. Supporting-tool
absence is not evidence of non-plasmid origin. Host predictions are evidence labels,
not definitive host assignments. Plasmid clusters are not taxonomic species, and
network correlations are not causal evidence.</p>
</body>
</html>
""",
        encoding="utf-8",
    )
    return html


def _table_summary_html(table_summary: Mapping[str, Mapping[str, object]]) -> str:
    if not table_summary:
        return "<p>No standard tables were provided.</p>"
    rows = []
    for table_name, metadata in sorted(table_summary.items()):
        rows.append(
            "<tr><td>{name}</td><td>{count}</td><td><code>{path}</code></td></tr>".format(
                name=escape(f"{table_name}.tsv"),
                count=escape(str(metadata.get("rows", 0))),
                path=escape(str(metadata.get("path", ""))),
            )
        )
    return (
        "<table><thead><tr><th>Table</th><th>Rows</th><th>Path</th></tr></thead>"
        "<tbody>{}</tbody></table>"
    ).format("".join(rows))


def _assembly_beta_html(plan: ExecutionPlan) -> str:
    assembly_samples = [sample for sample in plan.samples if sample.platform == "assembly"]
    if not assembly_samples:
        return ""
    skipped = _skipped_category_counts(plan)
    skipped_text = ", ".join(
        f"{escape(category)}={count}" for category, count in sorted(skipped.items())
    )
    skipped_item = (
        f"<li>Skipped categories recorded in plan: {skipped_text}</li>" if skipped_text else ""
    )
    return (
        "<h2>Assembly-only Beta Scope</h2>"
        "<ul>"
        f"<li>Assembly samples: {len(assembly_samples)}</li>"
        "<li>Input mode: provided contig FASTA; read QC and read assembly are not rerun.</li>"
        f"{skipped_item}"
        "<li>Output FASTA sets are operational classifications from parsed consensus evidence.</li>"
        "</ul>"
    )


def _ont_beta_html(plan: ExecutionPlan) -> str:
    ont_samples = [sample for sample in plan.samples if sample.platform == "ont"]
    if not ont_samples:
        return ""
    return (
        "<h2>ONT Long-read Beta Scope</h2>"
        "<ul>"
        f"<li>ONT samples: {len(ont_samples)}</li>"
        "<li>Default route: NanoPlot/Filtlong QC, metaFlye assembly, geNomad primary "
        "plasmid evidence, minimap2/samtools/CoverM abundance.</li>"
        "<li>ONT reads have platform-specific error profiles; plasmid structure, "
        "circularity, and host evidence require cautious interpretation.</li>"
        "<li>Long-read abundance uses minimap2 and is not interchangeable with "
        "short-read bowtie2 abundance.</li>"
        "</ul>"
    )


def _pacbio_hifi_beta_html(plan: ExecutionPlan) -> str:
    hifi_samples = [sample for sample in plan.samples if sample.platform == "pacbio_hifi"]
    if not hifi_samples:
        return ""
    return (
        "<h2>PacBio HiFi Beta Scope</h2>"
        "<ul>"
        f"<li>PacBio HiFi samples: {len(hifi_samples)}</li>"
        "<li>Default route: HiFiAdapterFilt QC, hifiasm/hifiasm-meta assembly fallback, "
        "geNomad primary plasmid evidence, minimap2/samtools/CoverM abundance.</li>"
        "<li>HiFi reads use different quality and indel assumptions from ONT reads; "
        "planner steps set minimap2 <code>map-hifi</code> for PacBio abundance.</li>"
        "<li>hifiasm graph output is normalized to a FASTA contract before QUAST, "
        "geNomad, annotation and abundance steps consume the assembly.</li>"
        "</ul>"
    )


def _hybrid_beta_html(plan: ExecutionPlan) -> str:
    hybrid_samples = [sample for sample in plan.samples if sample.platform == "hybrid"]
    if not hybrid_samples:
        return ""
    return (
        "<h2>Hybrid Short+Long Beta Scope</h2>"
        "<ul>"
        f"<li>Hybrid samples: {len(hybrid_samples)}</li>"
        "<li>Default route: fastp/FastQC/MultiQC plus NanoPlot/Filtlong QC, "
        "OPERA-MS hybrid assembly, geNomad primary plasmid evidence, and separate "
        "bowtie2 and minimap2 abundance tracks.</li>"
        "<li>Short-read and long-read abundance are recorded as separate provenance "
        "steps and output files; they should not be merged without an explicit "
        "normalization policy.</li>"
        "<li>Hybrid assembly can improve continuity but may also combine conflicting "
        "signals in complex metagenomes; plasmid structure and host evidence remain "
        "candidate interpretations.</li>"
        "</ul>"
    )


def _consensus_warnings_html(consensus: Sequence[Mapping[str, str]]) -> str:
    warnings = []
    for row in consensus:
        warning = row.get("warnings", "")
        if warning and warning not in warnings:
            warnings.append(warning)
    if not warnings:
        return ""
    items = "".join(f"<li>{escape(warning)}</li>" for warning in warnings[:10])
    return f"<h3>Evidence Warnings</h3><ul>{items}</ul>"


def _skipped_category_counts(plan: ExecutionPlan) -> dict[str, int]:
    counts: dict[str, int] = {}
    for step in plan.skipped_steps:
        counts[step.category] = counts.get(step.category, 0) + 1
    return counts


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


def _assembly_qc_html(rows: Sequence[Mapping[str, str]]) -> str:
    if not rows:
        return "<h3>Assembly QC Summary</h3><p>No assembly QC records were parsed.</p>"
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
    items = []
    for row in selected[:12]:
        unit = row.get("unit", "")
        suffix = f" {unit}" if unit else ""
        items.append(
            "<li><code>{sample}</code> {metric}: {value}{suffix}</li>".format(
                sample=escape(row.get("sample_id", "")),
                metric=escape(row.get("metric", "")),
                value=escape(row.get("value", "")),
                suffix=escape(suffix),
            )
        )
    return f"<h3>Assembly QC Summary</h3><ul>{''.join(items)}</ul>"
