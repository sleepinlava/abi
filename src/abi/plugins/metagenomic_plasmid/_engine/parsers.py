"""Parse core tool outputs into AutoPlasm standard tables."""

from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Mapping

from abi.plugins.metagenomic_plasmid._engine.json_utils import load_json_object

StandardRows = Dict[str, List[Dict[str, Any]]]
Parser = Callable[[Path, str], StandardRows]


def supports_standard_parsing(tool_id: str) -> bool:
    return tool_id in PARSERS


def parse_standard_outputs(tool_id: str, output_dir: str | Path, sample_id: str) -> StandardRows:
    parser = PARSERS.get(tool_id)
    if parser is None:
        return {}
    return parser(Path(output_dir), sample_id)


def parse_genomad(output_dir: Path, sample_id: str) -> StandardRows:
    rows = []
    for path in _candidate_files(
        output_dir,
        # Read ONLY the aggregated contigs_summary/contigs_plasmid_summary.tsv.
        # geNomad also produces per-contig summaries under
        #   {contig_id}_summary/{contig_id}_plasmid_summary.tsv,
        # which contain the same data as the aggregated file. Reading both
        # produces duplicate rows. Restrict to the contigs_summary/ directory
        # to avoid picking up the per-contig ones.
        ("contigs_summary/*plasmid*summary*.tsv",),
    ):
        for row in _read_table(path):
            contig = _get(
                row,
                "seq_name",
                "sequence_name",
                "seq_id",
                "contig",
                "contig_id",
                "sequence",
                "name",
            )
            if not contig:
                continue
            score = _get(
                row,
                "plasmid_score",
                "score",
                "probability",
                "plasmid_probability",
                "marker_enrichment",
            )
            length = _get(row, "length", "sequence_length", "contig_length", "seq_length")
            topology = _get(row, "topology", "circularity", "circular")
            rows.append(
                {
                    "sample_id": sample_id,
                    "contig_id": contig,
                    "tool": "genomad",
                    "evidence_level": "primary",
                    "score": _score_or_blank(score),
                    "confidence": _confidence(score),
                    "contig_length": length,
                    "circularity": topology,
                    "evidence": _evidence(row, ["plasmid_score", "score", "topology"]),
                    "warnings": "Virus/plasmid boundaries can be ambiguous.",
                    "source_file": str(path),
                }
            )
    return {"plasmid_predictions": rows}


def parse_plasmidfinder(output_dir: Path, sample_id: str) -> StandardRows:
    prediction_rows = []
    annotation_rows = []
    typing_rows = []
    for path in _candidate_files(output_dir, ("*result*.tsv", "*tab*.tsv", "*.tsv", "*.txt")):
        for row in _read_table(path):
            contig = _get(
                row,
                "contig",
                "sequence",
                "contig_id",
                "contig_name",
                "query",
                "query_id",
            )
            replicon = _get(row, "plasmid", "replicon", "gene", "template", "template_name")
            if not contig and not replicon:
                continue
            identity = _get(row, "identity", "perc_identity", "percent_identity")
            coverage = _get(row, "coverage", "perc_coverage", "percent_coverage")
            score = _fraction_score(identity)
            prediction_rows.append(
                {
                    "sample_id": sample_id,
                    "contig_id": contig,
                    "tool": "plasmidfinder",
                    "evidence_level": "supporting",
                    "score": score,
                    "confidence": _confidence(score),
                    "contig_length": "",
                    "circularity": "",
                    "evidence": _join_evidence({"replicon": replicon, "identity": identity}),
                    "warnings": (
                        "Replicon hits support plasmid evidence; no hit does not exclude plasmids."
                    ),
                    "source_file": str(path),
                }
            )
            annotation_rows.append(
                {
                    "sample_id": sample_id,
                    "contig_id": contig,
                    "start": _get(row, "position_in_contig", "start"),
                    "end": _get(row, "end"),
                    "strand": "",
                    "gene": replicon,
                    "product": "plasmid replicon",
                    "category": "replicon",
                    "tool": "plasmidfinder",
                    "evidence": _join_evidence({"identity": identity, "coverage": coverage}),
                    "identity": identity,
                    "coverage": coverage,
                    "source_file": str(path),
                }
            )
            typing_rows.append(
                {
                    "sample_id": sample_id,
                    "contig_id": contig,
                    "typing_scheme": "PlasmidFinder",
                    "type_id": replicon,
                    "mobility": "",
                    "confidence": _confidence(score),
                    "tool": "plasmidfinder",
                    "evidence": _join_evidence({"identity": identity, "coverage": coverage}),
                    "source_file": str(path),
                }
            )
    return {
        "plasmid_predictions": prediction_rows,
        "annotations": annotation_rows,
        "plasmid_typing": typing_rows,
    }


def parse_mob_suite(output_dir: Path, sample_id: str) -> StandardRows:
    prediction_rows = []
    annotation_rows = []
    host_rows = []
    typing_rows = []
    for path in _candidate_files(
        output_dir,
        ("contig_report.txt", "mobtyper_results.txt", "*.tsv", "*.txt"),
    ):
        for row in _read_table(path):
            contig = _get(row, "contig_id", "contig", "sample_id")
            if not contig:
                continue
            # MOB-typer restores the complete FASTA header in ``sample_id``;
            # standard ABI tables use the first whitespace-delimited sequence ID.
            contig = contig.split(maxsplit=1)[0]
            molecule_type = _get(row, "molecule_type", "type")
            size = _get(row, "size", "length", "contig_length")
            score = "1.0" if "plasmid" in molecule_type.lower() else ""
            replicon_type = _get(row, "replicon_type", "rep_type_s", "rep_type")
            relaxase_type = _get(row, "relaxase_type", "relaxase_type_s")
            mpf_type = _get(row, "mpf_type")
            orit_type = _get(row, "orit_type", "orit_type_s")
            mobility = _get(row, "predicted_mobility", "mobility")
            prediction_rows.append(
                {
                    "sample_id": sample_id,
                    "contig_id": contig,
                    "tool": "mob_suite",
                    "evidence_level": "supporting",
                    "score": score,
                    "confidence": _confidence(score or "0.7"),
                    "contig_length": size,
                    "circularity": _get(row, "circularity", "circular"),
                    "evidence": _evidence(row, ["molecule_type", "primary_cluster_id"]),
                    "warnings": "MOB-suite evidence is strongest for isolate-like plasmids.",
                    "source_file": str(path),
                }
            )
            for value, product, category in [
                (replicon_type, "replicon_type", "replicon"),
                (relaxase_type, "relaxase_type", "MOB"),
                (mpf_type, "mpf_type", "MPF"),
                (orit_type, "orit_type", "oriT"),
                (mobility, "predicted_mobility", "mobility"),
            ]:
                if value:
                    annotation_rows.append(
                        {
                            "sample_id": sample_id,
                            "contig_id": contig,
                            "start": "",
                            "end": "",
                            "strand": "",
                            "gene": value,
                            "product": product,
                            "category": category,
                            "tool": "mob_suite",
                            "evidence": _evidence(row, ["primary_cluster_id"]),
                            "identity": "",
                            "coverage": "",
                            "source_file": str(path),
                        }
                    )
            # ── plasmon typing rows ──
            if replicon_type:
                typing_rows.append(
                    {
                        "sample_id": sample_id,
                        "contig_id": contig,
                        "typing_scheme": "MOB-typer",
                        "type_id": replicon_type,
                        "mobility": mobility or "",
                        "confidence": _confidence(score or "0.7"),
                        "tool": "mob_suite",
                        "evidence": _evidence(row, ["primary_cluster_id"]),
                        "source_file": str(path),
                    }
                )
            if relaxase_type:
                typing_rows.append(
                    {
                        "sample_id": sample_id,
                        "contig_id": contig,
                        "typing_scheme": "MOB-typer",
                        "type_id": f"relaxase:{relaxase_type}",
                        "mobility": mobility or "",
                        "confidence": _confidence(score or "0.7"),
                        "tool": "mob_suite",
                        "evidence": _evidence(row, ["primary_cluster_id"]),
                        "source_file": str(path),
                    }
                )
            if mpf_type:
                typing_rows.append(
                    {
                        "sample_id": sample_id,
                        "contig_id": contig,
                        "typing_scheme": "MOB-typer",
                        "type_id": f"MPF:{mpf_type}",
                        "mobility": mobility or "",
                        "confidence": _confidence(score or "0.7"),
                        "tool": "mob_suite",
                        "evidence": _evidence(row, ["primary_cluster_id"]),
                        "source_file": str(path),
                    }
                )
            host = _get(
                row,
                "host_range",
                "predicted_host",
                "predicted_host_range_overall_name",
                "observed_host_range_ncbi_name",
                "reported_host_range_lit_name",
                "host",
            )
            if host:
                host_rows.append(
                    {
                        "sample_id": sample_id,
                        "contig_id": contig,
                        "host_taxon": host,
                        "method": "mob_suite",
                        "confidence": _get(row, "host_score", "confidence") or "unknown",
                        "evidence": _evidence(row, ["mash_nearest_neighbor", "primary_cluster_id"]),
                        "tool": "mob_suite",
                        "source_file": str(path),
                    }
                )
            if not any((replicon_type, relaxase_type, mpf_type)):
                typing_rows.append(
                    {
                        "sample_id": sample_id,
                        "contig_id": contig,
                        "typing_scheme": "MOB-typer",
                        "type_id": _get(row, "primary_cluster_id"),
                        "mobility": mobility or orit_type,
                        "confidence": _get(row, "confidence") or "supporting",
                        "tool": "mob_typer",
                        "evidence": _join_evidence(
                            {
                                "orit_type": orit_type,
                                "primary_cluster_id": _get(row, "primary_cluster_id"),
                            }
                        ),
                        "source_file": str(path),
                    }
                )
    return {
        "plasmid_predictions": prediction_rows,
        "annotations": annotation_rows,
        "host_predictions": host_rows,
        "plasmid_typing": typing_rows,
    }


def parse_mob_typer(output_dir: Path, sample_id: str) -> StandardRows:
    """Parse MOB-typer without treating post-detection typing as a new plasmid call."""
    rows = parse_mob_suite(output_dir, sample_id)
    rows.pop("plasmid_predictions", None)
    return rows


def parse_abricate(output_dir: Path, sample_id: str) -> StandardRows:
    rows = []
    for path in _candidate_files(output_dir, ("*.tsv", "*.tab", "*.txt")):
        for row in _read_table(path):
            contig = _get(row, "sequence", "contig", "contig_id")
            gene = _get(row, "gene", "resistance_gene", "accession")
            if not contig and not gene:
                continue
            database = _get(row, "database", "db")
            rows.append(
                {
                    "sample_id": sample_id,
                    "contig_id": contig,
                    "start": _get(row, "start"),
                    "end": _get(row, "end"),
                    "strand": _get(row, "strand"),
                    "gene": gene,
                    "product": _get(row, "product"),
                    "drug_class": _get(row, "resistance", "drug_class", "class"),
                    "category": _annotation_category(database),
                    "tool": "abricate",
                    "evidence": _join_evidence({"database": database}),
                    "identity": _get(row, "identity", "perc_identity", "percent_identity"),
                    "coverage": _get(row, "percent_coverage", "perc_coverage", "coverage"),
                    "source_file": str(path),
                }
            )
    return {"annotations": rows}


def parse_amrfinderplus(output_dir: Path, sample_id: str) -> StandardRows:
    rows = []
    for path in _candidate_files(output_dir, ("*.tsv", "*.txt")):
        for row in _read_table(path):
            contig = _get(row, "contig_id", "contig", "sequence_name")
            gene = _get(row, "gene_symbol", "element_symbol", "gene")
            if not contig and not gene:
                continue
            element_type = _get(row, "element_type", "type", "scope")
            rows.append(
                {
                    "sample_id": sample_id,
                    "contig_id": contig,
                    "start": _get(row, "start"),
                    "end": _get(row, "stop", "end"),
                    "strand": _get(row, "strand"),
                    "gene": gene,
                    "product": _get(row, "element_name", "sequence_name", "product"),
                    "drug_class": _get(row, "class", "subclass"),
                    "category": _annotation_category(element_type or "AMR"),
                    "tool": "amrfinderplus",
                    "evidence": _join_evidence({"element_type": element_type}),
                    "identity": _get(
                        row,
                        "identity_to_reference_sequence",
                        "percent_identity_to_reference_sequence",
                        "percent_identity_to_reference",
                        "identity_to_reference",
                        "identity",
                    ),
                    "coverage": _get(
                        row,
                        "coverage_of_reference_sequence",
                        "percent_coverage_of_reference_sequence",
                        "percent_coverage_of_reference",
                        "coverage_of_reference",
                        "coverage",
                    ),
                    "source_file": str(path),
                }
            )
    return {"annotations": rows}


def parse_bakta(output_dir: Path, sample_id: str) -> StandardRows:
    rows = []
    for path in _candidate_files(output_dir, ("*.tsv", "*.txt")):
        for row in _read_table(path):
            contig = _get(row, "sequence_id", "contig", "contig_id")
            feature_type = _get(row, "type", "feature")
            gene = _get(row, "gene", "locus_tag")
            product = _get(row, "product")
            if not contig and not gene and not product:
                continue
            rows.append(
                {
                    "sample_id": sample_id,
                    "contig_id": contig,
                    "start": _get(row, "start"),
                    "end": _get(row, "stop", "end"),
                    "strand": _get(row, "strand"),
                    "gene": gene,
                    "product": product,
                    "category": feature_type or "feature",
                    "tool": "bakta",
                    "evidence": _get(row, "dbxrefs", "inference"),
                    "identity": "",
                    "coverage": "",
                    "source_file": str(path),
                }
            )
    for path in _candidate_files(output_dir, ("*.gff3", "*.gff")):
        for row in _read_gff_features(path):
            contig = _get(row, "seqid")
            feature_type = _get(row, "type")
            gene = _get(row, "gene", "locus_tag", "id")
            product = _get(row, "product", "name")
            if not contig and not gene and not product:
                continue
            rows.append(
                {
                    "sample_id": sample_id,
                    "contig_id": contig,
                    "start": _get(row, "start"),
                    "end": _get(row, "end"),
                    "strand": _get(row, "strand"),
                    "gene": gene,
                    "product": product,
                    "category": feature_type or "feature",
                    "tool": "bakta",
                    "evidence": _get(row, "dbxref", "inference"),
                    "identity": "",
                    "coverage": "",
                    "source_file": str(path),
                }
            )
    return {"annotations": rows}


def parse_isescan(output_dir: Path, sample_id: str) -> StandardRows:
    rows = []
    for path in _candidate_files(output_dir, ("*.gff3", "*.gff")):
        for row in _read_gff_features(path):
            rows.append(_mge_annotation_row(row, sample_id, "isescan", "IS", path))
    for path in _candidate_files(output_dir, ("*.tsv", "*.csv", "*.txt")):
        for row in _read_table(path):
            if _get(row, "contig", "contig_id", "seqid", "sequence"):
                rows.append(_mge_annotation_row(row, sample_id, "isescan", "IS", path))
    return {"annotations": rows}


def parse_integronfinder(output_dir: Path, sample_id: str) -> StandardRows:
    rows = []
    for path in _candidate_files(output_dir, ("*.gff3", "*.gff")):
        for row in _read_gff_features(path):
            rows.append(_mge_annotation_row(row, sample_id, "integronfinder", "integron", path))
    for path in _candidate_files(output_dir, ("*.integrons", "*.summary", "*.tsv", "*.txt")):
        for row in _read_table(path):
            if _get(row, "contig", "contig_id", "seqid", "replicon"):
                rows.append(_mge_annotation_row(row, sample_id, "integronfinder", "integron", path))
    return {"annotations": rows}


def parse_plasmidhostfinder(output_dir: Path, sample_id: str) -> StandardRows:
    rows = []
    for path in _candidate_files(output_dir, ("*.tsv", "*.txt")):
        for row in _read_table(path):
            contig = _get(row, "contig", "contig_id", "sequence")
            host = _get(row, "host", "host_taxon", "predicted_host")
            if not contig and not host:
                continue
            rows.append(
                {
                    "sample_id": sample_id,
                    "contig_id": contig,
                    "host_taxon": host,
                    "method": _get(row, "level", "method") or "plasmidhostfinder",
                    "confidence": _get(row, "score", "confidence") or "unknown",
                    "evidence": _evidence(row, ["match", "level"]),
                    "tool": "plasmidhostfinder",
                    "source_file": str(path),
                }
            )
    return {"host_predictions": rows}


def parse_metaphlan(output_dir: Path, sample_id: str) -> StandardRows:
    rows = []
    for path in _candidate_files(output_dir, ("*.metaphlan.tsv", "*metaphlan*.tsv", "*.tsv")):
        for row in _read_metaphlan_table(path):
            clade = _get(row, "clade_name", "clade")
            taxon = _metaphlan_species(clade)
            if not taxon:
                continue
            abundance = _get(row, "relative_abundance", "relative_abundance_percent")
            rows.append(
                {
                    "sample_id": sample_id,
                    "contig_id": "",
                    "host_taxon": taxon,
                    "method": "taxonomy_abundance",
                    "confidence": abundance or "unknown",
                    "evidence": _join_evidence(
                        {
                            "clade": clade,
                            "ncbi_tax_id": _get(row, "NCBI_tax_id", "tax_id"),
                            "relative_abundance": abundance,
                        }
                    ),
                    "tool": "metaphlan",
                    "source_file": str(path),
                }
            )
    return {"host_predictions": rows}


def parse_coverm(output_dir: Path, sample_id: str) -> StandardRows:
    rows = []
    for path in _candidate_files(output_dir, ("*.tsv", "*.txt")):
        for row in _read_table(path):
            contig = _get(row, "contig", "genome", "feature_id", "name")
            if not contig:
                continue
            # CoverM uses column names like "SRR2241213.samtools Mean"
            # which normalize to "srr2241213_samtools_mean" — the
            # standard _get() exact-match lookup fails because the
            # column prefix varies per sample.  Fall back to a
            # contains-match on the normalized key space.
            coverage = _get_contains(row, "mean", "coverage", "covered_fraction")
            tpm_val = _get_contains(row, "tpm")
            rpkm_val = _get_contains(row, "rpkm")
            mapped = _get_contains(row, "reads", "mapped_reads", "read_count")
            length_val = _get_contains(row, "length", "length_bp", "contig_length")
            rows.append(
                {
                    "sample_id": sample_id,
                    "feature_id": contig,
                    "contig_id": contig,
                    "coverage": coverage,
                    "tpm": tpm_val,
                    "rpkm": rpkm_val,
                    "mapped_reads": mapped,
                    "length_bp": length_val,
                    "tool": "coverm",
                    "source_file": str(path),
                }
            )
    return {"abundance": rows}


def parse_fastp(output_dir: Path, sample_id: str) -> StandardRows:
    rows = []
    for path in _candidate_files(output_dir, ("*.json",)):
        data = load_json_object(path)
        summary = data.get("summary", {}) if isinstance(data, dict) else {}
        before = summary.get("before_filtering", {})
        after = summary.get("after_filtering", {})
        for prefix, block in [("before_filtering", before), ("after_filtering", after)]:
            if isinstance(block, dict):
                for metric, value in block.items():
                    rows.append(
                        {
                            "sample_id": sample_id,
                            "tool": "fastp",
                            "metric": f"{prefix}.{metric}",
                            "value": value,
                            "unit": "",
                            "source_file": str(path),
                        }
                    )
    return {"qc_summary": rows}


def parse_fastqc(output_dir: Path, sample_id: str) -> StandardRows:
    rows = []
    for path in _candidate_files(output_dir, ("fastqc_data.txt", "summary.txt")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line or line.startswith("#") or line.startswith(">>END_MODULE"):
                continue
            parts = line.split("\t")
            if path.name == "summary.txt" and len(parts) >= 2:
                rows.append(
                    {
                        "sample_id": sample_id,
                        "tool": "fastqc",
                        "metric": parts[1],
                        "value": parts[0],
                        "unit": "status",
                        "source_file": str(path),
                    }
                )
            elif (
                path.name == "fastqc_data.txt" and len(parts) >= 2 and not parts[0].startswith(">>")
            ):
                rows.append(
                    {
                        "sample_id": sample_id,
                        "tool": "fastqc",
                        "metric": parts[0],
                        "value": parts[1],
                        "unit": "",
                        "source_file": str(path),
                    }
                )
    return {"qc_summary": rows}


def parse_multiqc(output_dir: Path, sample_id: str) -> StandardRows:
    rows = []
    for path in _candidate_files(output_dir, ("multiqc_general_stats.txt",)):
        for row in _read_table(path):
            row_sample = _get(row, "sample", "sample_name", "name")
            if row_sample and sample_id and row_sample != sample_id:
                continue
            for metric, value in row.items():
                if metric in {"sample", "sample_name", "name"} or value == "":
                    continue
                rows.append(
                    {
                        "sample_id": sample_id or row_sample,
                        "tool": "multiqc",
                        "metric": f"multiqc.{metric}",
                        "value": value,
                        "unit": "",
                        "source_file": str(path),
                    }
                )
    return {"qc_summary": rows}


def parse_nanoplot(output_dir: Path, sample_id: str) -> StandardRows:
    rows = []
    for path in _candidate_files(output_dir, ("NanoStats.txt", "*nanostats*.txt", "*.tsv")):
        for row in _read_table(path):
            metric = _get(row, "metric", "name", "measure")
            value = _get(row, "value", "mean", "median")
            if metric and value:
                rows.append(
                    {
                        "sample_id": sample_id,
                        "tool": "nanoplot",
                        "metric": metric,
                        "value": value,
                        "unit": _get(row, "unit"),
                        "source_file": str(path),
                    }
                )
                continue
            for key, value in row.items():
                if value:
                    rows.append(
                        {
                            "sample_id": sample_id,
                            "tool": "nanoplot",
                            "metric": key,
                            "value": value,
                            "unit": "",
                            "source_file": str(path),
                        }
                    )
    return {"qc_summary": rows}


def parse_filtlong(output_dir: Path, sample_id: str) -> StandardRows:
    rows = []
    for path in _candidate_files(output_dir, ("*.log", "*.txt")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if ":" not in line:
                continue
            metric, value = line.split(":", 1)
            metric = metric.strip()
            value = value.strip()
            if not metric or not value:
                continue
            rows.append(
                {
                    "sample_id": sample_id,
                    "tool": "filtlong",
                    "metric": metric,
                    "value": value,
                    "unit": "",
                    "source_file": str(path),
                }
            )
    return {"qc_summary": rows}


def parse_hifiadapterfilt(output_dir: Path, sample_id: str) -> StandardRows:
    rows = []
    for path in _candidate_files(output_dir, ("*.log", "*.txt", "*.stats")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if ":" not in line:
                continue
            metric, value = line.split(":", 1)
            metric = metric.strip()
            value = value.strip()
            if not metric or not value:
                continue
            rows.append(
                {
                    "sample_id": sample_id,
                    "tool": "hifiadapterfilt",
                    "metric": metric,
                    "value": value,
                    "unit": "",
                    "source_file": str(path),
                }
            )
    return {"qc_summary": rows}


def parse_megahit(output_dir: Path, sample_id: str) -> StandardRows:
    rows = []
    for path in _candidate_files(output_dir, ("final.contigs.fa", "final.contigs.fasta")):
        lengths = _read_fasta_lengths(path)
        if not lengths:
            continue
        for metric, value, unit in [
            ("contig_count", len(lengths), "count"),
            ("total_length", sum(lengths), "bp"),
            ("max_contig_length", max(lengths), "bp"),
            ("n50", _n50(lengths), "bp"),
        ]:
            rows.append(
                {
                    "sample_id": sample_id,
                    "tool": "megahit",
                    "metric": metric,
                    "value": value,
                    "unit": unit,
                    "source_file": str(path),
                }
            )
    return {"assembly_summary": rows}


def parse_metaflye(output_dir: Path, sample_id: str) -> StandardRows:
    rows = []
    for path in _candidate_files(output_dir, ("assembly.fasta", "assembly.fa")):
        rows.extend(_assembly_fasta_summary_rows(path, sample_id, "metaflye"))
    return {"assembly_summary": rows}


def parse_hifiasm_meta(output_dir: Path, sample_id: str) -> StandardRows:
    rows = []
    for path in _candidate_files(
        output_dir,
        ("*.hifiasm.fasta", "*.hifiasm.fa", "*.p_ctg.fasta", "*.p_ctg.fa"),
    ):
        rows.extend(_assembly_fasta_summary_rows(path, sample_id, "hifiasm_meta"))
    return {"assembly_summary": rows}


def parse_opera_ms(output_dir: Path, sample_id: str) -> StandardRows:
    rows = []
    for path in _candidate_files(
        output_dir,
        (
            "contigs.fasta",
            "contigs.fa",
            "*contigs*.fasta",
            "*contigs*.fa",
            "*scaffolds*.fasta",
            "*scaffolds*.fa",
        ),
    ):
        rows.extend(_assembly_fasta_summary_rows(path, sample_id, "opera_ms"))
    return {"assembly_summary": rows}


def parse_quast(output_dir: Path, sample_id: str) -> StandardRows:
    rows = []
    for path in _candidate_files(output_dir, ("report.tsv", "transposed_report.tsv", "*.tsv")):
        for row in _read_table(path):
            if "assembly" in row:
                for metric, value in row.items():
                    if metric == "assembly":
                        continue
                    rows.append(
                        {
                            "sample_id": sample_id,
                            "tool": "quast",
                            "metric": metric,
                            "value": value,
                            "unit": "",
                            "source_file": str(path),
                        }
                    )
            else:
                metric = _get(row, "metric", "assembly")
                value = _get(row, "value", "contigs")
                if metric:
                    rows.append(
                        {
                            "sample_id": sample_id,
                            "tool": "quast",
                            "metric": metric,
                            "value": value,
                            "unit": "",
                            "source_file": str(path),
                        }
                    )
    return {"assembly_summary": rows}


def parse_plasme(output_dir: Path, sample_id: str) -> StandardRows:
    rows = []
    for path in _candidate_files(output_dir, ("*.tsv", "*.txt", "*.csv")):
        for row in _read_table(path):
            contig = _get(row, "contig", "contig_id", "sequence", "seq_id", "name")
            if not contig:
                continue
            score = _get(row, "score", "plasmid_score", "probability", "prediction")
            rows.append(_prediction_row(sample_id, contig, "plasme", score, row, path))
    return {"plasmid_predictions": rows}


def parse_plasx(output_dir: Path, sample_id: str) -> StandardRows:
    rows = []
    for path in _candidate_files(output_dir, ("*.plasx.tsv", "*.tsv", "*.csv", "*.txt")):
        for row in _read_table(path):
            contig = _get(row, "contig", "contig_id", "sequence", "seq_id", "name")
            if not contig:
                continue
            score = _get(row, "score", "plasmid_score", "probability", "plasx_score")
            rows.append(_prediction_row(sample_id, contig, "plasx", score, row, path))
    return {"plasmid_predictions": rows}


def parse_platon(output_dir: Path, sample_id: str) -> StandardRows:
    rows = []
    for path in _candidate_files(
        output_dir,
        ("*plasmid*.tsv", "*platon*.tsv", "*.tsv", "*.txt", "*.csv"),
    ):
        for row in _read_table(path):
            contig = _get(
                row,
                "id",
                "contig",
                "contig_id",
                "sequence",
                "seq_id",
                "name",
            )
            if not contig:
                continue
            score = _get(row, "rds", "score", "plasmid_score", "probability")
            rows.append(_prediction_row(sample_id, contig, "platon", score, row, path))
    return {"plasmid_predictions": rows}


def parse_copla(output_dir: Path, sample_id: str) -> StandardRows:
    rows = []
    for path in _candidate_files(output_dir, ("*.tsv", "*.txt", "*.csv")):
        for row in _read_table(path):
            contig = _get(row, "contig", "contig_id", "query", "sequence")
            type_id = _get(row, "ptu", "plasmid_taxonomic_unit", "type", "cluster", "replicon")
            if not contig and not type_id:
                continue
            rows.append(
                {
                    "sample_id": sample_id,
                    "contig_id": contig,
                    "typing_scheme": "COPLA",
                    "type_id": type_id,
                    "mobility": _get(row, "mobility", "predicted_mobility"),
                    "confidence": _get(row, "score", "confidence") or "unknown",
                    "tool": "copla",
                    "evidence": _evidence(row, ["identity", "coverage", "cluster"]),
                    "source_file": str(path),
                }
            )
    return {"plasmid_typing": rows}


def parse_gplas2(output_dir: Path, sample_id: str) -> StandardRows:
    return _parse_binning_tool(output_dir, sample_id, "gplas2")


def parse_plasmaag(output_dir: Path, sample_id: str) -> StandardRows:
    return _parse_binning_tool(output_dir, sample_id, "plasmaag")


def parse_kraken2(output_dir: Path, sample_id: str) -> StandardRows:
    rows = []
    for path in _candidate_files(output_dir, ("*.kraken2.report", "*report*", "*.tsv", "*.txt")):
        for row in _read_kraken_report(path):
            rank = _get(row, "rank_code", "rank")
            taxon = _get(row, "name", "taxon", "taxon_name")
            if not taxon or rank not in {"S", "G", "F", "species", "genus", "family"}:
                continue
            confidence = _get(row, "percent", "clade_percent")
            rows.append(
                {
                    "sample_id": sample_id,
                    "contig_id": "",
                    "host_taxon": taxon,
                    "method": "taxonomy_abundance",
                    "confidence": confidence or "unknown",
                    "evidence": _join_evidence(
                        {
                            "rank": rank,
                            "taxid": _get(row, "taxid", "ncbi_tax_id"),
                            "reads": _get(row, "clade_reads", "taxon_reads"),
                        }
                    ),
                    "tool": "kraken2",
                    "source_file": str(path),
                }
            )
    return {"host_predictions": rows}


def parse_blast(output_dir: Path, sample_id: str) -> StandardRows:
    return {"comparative_hits": _parse_tabular_hits(output_dir, sample_id, "blast")}


def parse_mmseqs2(output_dir: Path, sample_id: str) -> StandardRows:
    catalog_rows = []
    cluster_paths = _candidate_files(output_dir, ("*_cluster.tsv", "plasmid_catalog_cluster.tsv"))
    for path in cluster_paths:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                fields = line.rstrip("\n\r").split("\t")
                if len(fields) < 2:
                    continue
                representative, member = fields[0], fields[1]
                member_sample = member.split("|", 1)[0] if "|" in member else sample_id
                catalog_rows.append(
                    {
                        "cluster_id": representative,
                        "representative_id": representative,
                        "member_id": member,
                        "sample_id": member_sample,
                        "method": "mmseqs2_easy_cluster",
                        "source_file": str(path),
                    }
                )
    if catalog_rows:
        return {"plasmid_catalog": catalog_rows}
    return {"comparative_hits": _parse_tabular_hits(output_dir, sample_id, "mmseqs2")}


def parse_deseq2_plasmid(output_dir: Path, sample_id: str) -> StandardRows:
    del sample_id
    rows = []
    for path in _candidate_files(output_dir, ("differential_plasmids.tsv", "*.deseq2.tsv")):
        for row in _read_table(path):
            plasmid_id = _get(row, "plasmid_id", "feature_id", "contig_id")
            if not plasmid_id:
                continue
            rows.append(
                {
                    "plasmid_id": plasmid_id,
                    "group_a": _get(row, "group_a"),
                    "group_b": _get(row, "group_b"),
                    "log2_fold_change": _get(row, "log2_fold_change", "log2FoldChange"),
                    "p_value": _get(row, "p_value", "pvalue"),
                    "q_value": _get(row, "q_value", "padj"),
                    "method": _get(row, "method") or "DESeq2",
                    "warnings": _get(row, "warnings"),
                }
            )
    return {"differential_plasmids": rows}


def parse_mummer(output_dir: Path, sample_id: str) -> StandardRows:
    rows = []
    for path in _candidate_files(output_dir, ("*.coords", "*.tsv", "*.txt")):
        for row in _read_table(path):
            query = _get(row, "query", "query_id", "qry", "contig", "tag_2")
            subject = _get(row, "reference", "subject", "subject_id", "ref", "tag_1")
            if not query and not subject:
                continue
            rows.append(
                {
                    "sample_id": sample_id,
                    "query_id": query,
                    "subject_id": subject,
                    "identity": _get(row, "identity", "idy"),
                    "coverage": _get(row, "coverage", "cov"),
                    "e_value": "",
                    "bit_score": "",
                    "alignment_length": _get(row, "length", "len_1", "len_2"),
                    "tool": "mummer",
                    "evidence": _evidence(row, ["start_1", "end_1", "start_2", "end_2"]),
                    "source_file": str(path),
                }
            )
    return {"comparative_hits": rows}


def parse_clinker(output_dir: Path, sample_id: str) -> StandardRows:
    rows = []
    for path in _candidate_files(output_dir, ("*.html", "*.svg", "*.json")):
        rows.append(
            {
                "sample_id": sample_id,
                "output_type": path.suffix.lstrip(".") or "artifact",
                "path": str(path),
                "tool": "clinker",
                "description": "Gene cluster comparison visualization",
            }
        )
    return {"visualization_outputs": rows}


def parse_fastspar(output_dir: Path, sample_id: str) -> StandardRows:
    del sample_id
    correlations = _read_matrix(output_dir / "correlation.tsv")
    covariances = _read_matrix(output_dir / "covariance.tsv")
    edges = []
    degree: Dict[str, int] = {node: 0 for node in correlations}
    nodes = sorted(correlations)
    for index, source in enumerate(nodes):
        for target in nodes[index + 1 :]:
            correlation = correlations.get(source, {}).get(target, "")
            if correlation == "":
                continue
            covariance = covariances.get(source, {}).get(target, "")
            if _as_float(correlation) not in {None, 0.0}:
                degree[source] = degree.get(source, 0) + 1
                degree[target] = degree.get(target, 0) + 1
            edges.append(
                {
                    "source": source,
                    "target": target,
                    "correlation": correlation,
                    "covariance": covariance,
                    "p_value": "",
                    "q_value": "",
                    "method": "fastspar",
                    "evidence": "correlation_matrix",
                    "warnings": "FastSpar correlations are associations, not causal evidence.",
                    "source_file": str(output_dir / "correlation.tsv"),
                }
            )
    node_rows = [
        {
            "node_id": node,
            "node_type": "plasmid_feature",
            "sample_count": "",
            "mean_abundance": "",
            "degree": degree.get(node, 0),
            "evidence": "fastspar_matrix",
            "source_file": str(output_dir / "correlation.tsv"),
        }
        for node in nodes
    ]
    return {"network_edges": edges, "network_nodes": node_rows}


def parse_alignment(output_dir: Path, sample_id: str, tool: str) -> StandardRows:
    """Describe SAM/BAM artifacts and count SAM alignment records."""
    rows = []
    for path in _candidate_files(output_dir, ("*.sam", "*.bam", "*.cram")):
        record_count: int | str = ""
        mapped_records: int | str = ""
        unmapped_records: int | str = ""
        if path.suffix.lower() == ".sam":
            record_count = 0
            mapped_records = 0
            unmapped_records = 0
            try:
                with path.open("r", encoding="utf-8", errors="replace") as handle:
                    for line in handle:
                        if not line or line.startswith("@"):
                            continue
                        fields = line.rstrip("\n").split("\t")
                        if len(fields) < 2:
                            continue
                        try:
                            flag = int(fields[1])
                        except ValueError:
                            continue
                        record_count += 1
                        if flag & 4:
                            unmapped_records += 1
                        else:
                            mapped_records += 1
            except OSError:
                continue
        rows.append(
            {
                "sample_id": sample_id,
                "tool": tool,
                "artifact_type": path.suffix.lower().lstrip("."),
                "record_count": record_count,
                "mapped_records": mapped_records,
                "unmapped_records": unmapped_records,
                "size_bytes": path.stat().st_size,
                "source_file": str(path),
            }
        )
    return {"alignment_summary": rows}


def parse_fastq_artifacts(output_dir: Path, sample_id: str, tool: str) -> StandardRows:
    rows = []
    for path in _candidate_files(
        output_dir,
        ("*.fastq", "*.fq", "*.fastq.gz", "*.fq.gz"),
    ):
        rows.append(
            {
                "sample_id": sample_id,
                "tool": tool,
                "metric": "output_size_bytes",
                "value": path.stat().st_size,
                "unit": "bytes",
                "source_file": str(path),
            }
        )
    return {"qc_summary": rows}


def parse_assembly_fasta(output_dir: Path, sample_id: str, tool: str) -> StandardRows:
    rows = []
    for path in _candidate_files(
        output_dir,
        ("contigs.fasta", "contigs.fa", "assembly.fasta", "consensus.fasta", "*.fna"),
    ):
        rows.extend(_assembly_fasta_summary_rows(path, sample_id, tool))
    return {"assembly_summary": rows}


def parse_generic_annotations(output_dir: Path, sample_id: str, tool: str) -> StandardRows:
    rows = []
    for path in _candidate_files(output_dir, ("*.gff", "*.gff3")):
        for row in _read_gff_features(path):
            rows.append(
                {
                    "sample_id": sample_id,
                    "contig_id": _get(row, "seqid", "contig", "contig_id"),
                    "start": _get(row, "start"),
                    "end": _get(row, "end"),
                    "strand": _get(row, "strand"),
                    "gene": _get(row, "gene", "name", "id"),
                    "product": _get(row, "product", "description"),
                    "category": _get(row, "type") or "feature",
                    "tool": tool,
                    "evidence": _get(row, "dbxref", "inference", "score"),
                    "identity": _get(row, "identity", "percent_identity"),
                    "coverage": _get(row, "coverage", "percent_coverage"),
                    "source_file": str(path),
                }
            )
    for path in _candidate_files(output_dir, ("*.tsv", "*.csv", "*.txt")):
        for row in _read_table(path):
            contig = _get(row, "contig", "contig_id", "sequence", "query", "seqid")
            gene = _get(row, "gene", "gene_id", "protein", "model", "hit")
            product = _get(row, "product", "description", "annotation", "function")
            if not contig and not gene and not product:
                continue
            rows.append(
                {
                    "sample_id": sample_id,
                    "contig_id": contig,
                    "start": _get(row, "start"),
                    "end": _get(row, "end", "stop"),
                    "strand": _get(row, "strand"),
                    "gene": gene,
                    "product": product,
                    "category": _get(row, "category", "type", "class") or "feature",
                    "tool": tool,
                    "evidence": _evidence(row, ["database", "score", "evalue"]),
                    "identity": _get(row, "identity", "percent_identity"),
                    "coverage": _get(row, "coverage", "percent_coverage"),
                    "source_file": str(path),
                }
            )
    return {"annotations": rows}


def parse_mag_quality(output_dir: Path, sample_id: str, tool: str) -> StandardRows:
    rows = []
    for path in _candidate_files(output_dir, ("*.tsv", "*.csv", "*.txt")):
        for row in _read_table(path):
            bin_id = _get(row, "bin_id", "bin", "name", "user_genome")
            completeness = _get(row, "completeness")
            contamination = _get(row, "contamination")
            taxonomy = _get(row, "taxonomy", "classification")
            if not any((bin_id, completeness, contamination, taxonomy)):
                continue
            rows.append(
                {
                    "sample_id": sample_id,
                    "bin_id": bin_id,
                    "completeness": completeness,
                    "contamination": contamination,
                    "taxonomy": taxonomy,
                    "tool": tool,
                    "source_file": str(path),
                }
            )
    return {"mag_quality": rows}


def parse_visualization_artifacts(output_dir: Path, sample_id: str, tool: str) -> StandardRows:
    rows = []
    for path in _candidate_files(output_dir, ("*.html", "*.svg", "*.png", "*.pdf")):
        rows.append(
            {
                "sample_id": sample_id,
                "output_type": path.suffix.lower().lstrip("."),
                "path": str(path),
                "tool": tool,
                "description": f"{tool} visualization artifact",
            }
        )
    return {"visualization_outputs": rows}


def parse_generic_artifacts(output_dir: Path, sample_id: str, tool: str) -> StandardRows:
    rows: List[Dict[str, Any]] = []
    if not output_dir.exists():
        return {"artifacts": rows}
    for path in sorted(item for item in output_dir.rglob("*") if item.is_file()):
        rows.append(
            {
                "sample_id": sample_id,
                "tool": tool,
                "artifact_type": path.suffix.lower().lstrip(".") or "file",
                "path": str(path),
                "size_bytes": path.stat().st_size,
                "description": f"Output artifact produced by {tool}",
            }
        )
    return {"artifacts": rows}


def _bind_parser(parser: Callable[[Path, str, str], StandardRows], tool: str) -> Parser:
    def bound(output_dir: Path, sample_id: str) -> StandardRows:
        return parser(output_dir, sample_id, tool)

    return bound


def _bind_binning_parser(tool: str) -> Parser:
    def bound(output_dir: Path, sample_id: str) -> StandardRows:
        return _parse_binning_tool(output_dir, sample_id, tool)

    return bound


PARSERS: Dict[str, Parser] = {
    "genomad": parse_genomad,
    "plasme": parse_plasme,
    "plasx": parse_plasx,
    "platon": parse_platon,
    "plasmidfinder": parse_plasmidfinder,
    "mob_suite": parse_mob_suite,
    "mob_typer": parse_mob_typer,
    "copla": parse_copla,
    "gplas2": parse_gplas2,
    "plasmaag": parse_plasmaag,
    "abricate": parse_abricate,
    "amrfinderplus": parse_amrfinderplus,
    "bakta": parse_bakta,
    "isescan": parse_isescan,
    "integronfinder": parse_integronfinder,
    "plasmidhostfinder": parse_plasmidhostfinder,
    "kraken2": parse_kraken2,
    "metaphlan": parse_metaphlan,
    "coverm": parse_coverm,
    "fastspar": parse_fastspar,
    "blast": parse_blast,
    "mmseqs2": parse_mmseqs2,
    "deseq2_plasmid": parse_deseq2_plasmid,
    "mummer": parse_mummer,
    "clinker": parse_clinker,
    "fastp": parse_fastp,
    "fastqc": parse_fastqc,
    "multiqc": parse_multiqc,
    "nanoplot": parse_nanoplot,
    "filtlong": parse_filtlong,
    "hifiadapterfilt": parse_hifiadapterfilt,
    "megahit": parse_megahit,
    "metaflye": parse_metaflye,
    "hifiasm_meta": parse_hifiasm_meta,
    "opera_ms": parse_opera_ms,
    "quast": parse_quast,
    "bowtie2": _bind_parser(parse_alignment, "bowtie2"),
    "minimap2": _bind_parser(parse_alignment, "minimap2"),
    "samtools": _bind_parser(parse_alignment, "samtools"),
    "bowtie2_host_removal": _bind_parser(parse_fastq_artifacts, "bowtie2_host_removal"),
    "minimap2_host_removal": _bind_parser(parse_fastq_artifacts, "minimap2_host_removal"),
    "samtools_fastq": _bind_parser(parse_fastq_artifacts, "samtools_fastq"),
    "dorado": _bind_parser(parse_fastq_artifacts, "dorado"),
    "metaspades": _bind_parser(parse_assembly_fasta, "metaspades"),
    "hybridspades": _bind_parser(parse_assembly_fasta, "hybridspades"),
    "medaka": _bind_parser(parse_assembly_fasta, "medaka"),
    "prodigal": _bind_parser(parse_generic_annotations, "prodigal"),
    "rgi": _bind_parser(parse_generic_annotations, "rgi"),
    "eggnog_mapper": _bind_parser(parse_generic_annotations, "eggnog_mapper"),
    "minced": _bind_parser(parse_generic_annotations, "minced"),
    "macsyfinder": _bind_parser(parse_generic_annotations, "macsyfinder"),
    "conjscan": _bind_parser(parse_generic_annotations, "conjscan"),
    "metabat2": _bind_binning_parser("metabat2"),
    "concoct": _bind_binning_parser("concoct"),
    "semibin": _bind_binning_parser("semibin"),
    "das_tool": _bind_binning_parser("das_tool"),
    "scapp": _bind_binning_parser("scapp"),
    "recycler": _bind_binning_parser("recycler"),
    "checkm2": _bind_parser(parse_mag_quality, "checkm2"),
    "gtdbtk": _bind_parser(parse_mag_quality, "gtdbtk"),
    "dna_features_viewer": _bind_parser(parse_visualization_artifacts, "dna_features_viewer"),
    "pycirclize": _bind_parser(parse_visualization_artifacts, "pycirclize"),
    "pyvis": _bind_parser(parse_visualization_artifacts, "pyvis"),
    "report_markdown": _bind_parser(parse_generic_artifacts, "report_markdown"),
}


def _prediction_row(
    sample_id: str,
    contig: str,
    tool: str,
    score: str,
    row: Mapping[str, str],
    path: Path,
) -> Dict[str, Any]:
    return {
        "sample_id": sample_id,
        "contig_id": contig,
        "tool": tool,
        "evidence_level": "supporting",
        "score": _score_or_blank(score),
        "confidence": _confidence(score),
        "contig_length": _get(row, "length", "contig_length", "sequence_length"),
        "circularity": _get(row, "circularity", "topology", "circular"),
        "evidence": _evidence(row, ["score", "probability", "prediction", "label"]),
        "warnings": f"{tool} evidence is supporting evidence and should be integrated.",
        "source_file": str(path),
    }


def _mge_annotation_row(
    row: Mapping[str, str],
    sample_id: str,
    tool: str,
    category: str,
    path: Path,
) -> Dict[str, Any]:
    return {
        "sample_id": sample_id,
        "contig_id": _get(row, "contig", "contig_id", "seqid", "sequence", "replicon"),
        "start": _get(row, "start", "begin"),
        "end": _get(row, "end", "stop"),
        "strand": _get(row, "strand"),
        "gene": _get(row, "gene", "name", "id", "locus_tag") or category,
        "product": _get(row, "product", "type", "description") or category,
        "category": category,
        "tool": tool,
        "evidence": _evidence(row, ["family", "type", "model", "calin", "complete"]),
        "identity": _get(row, "identity", "percent_identity"),
        "coverage": _get(row, "coverage", "percent_coverage"),
        "source_file": str(path),
    }


def _parse_binning_tool(output_dir: Path, sample_id: str, tool: str) -> StandardRows:
    bin_rows: List[Dict[str, Any]] = []
    membership_rows: List[Dict[str, Any]] = []
    for path in _candidate_files(output_dir, ("*.tsv", "*.csv", "*.txt")):
        for row in _read_table(path):
            bin_id = _get(row, "bin_id", "bin", "plasmid_bin", "cluster")
            contig = _get(row, "contig", "contig_id", "sequence", "seq_id")
            if not bin_id and not contig:
                continue
            if bin_id:
                bin_rows.append(
                    {
                        "sample_id": sample_id,
                        "bin_id": bin_id,
                        "method": tool,
                        "contig_count": _get(row, "contig_count", "n_contigs"),
                        "total_length_bp": _get(row, "total_length", "length", "length_bp"),
                        "confidence": _get(row, "confidence", "score") or "unknown",
                        "evidence": _evidence(row, ["score", "coverage", "depth"]),
                        "source_file": str(path),
                    }
                )
            if bin_id and contig:
                membership_rows.append(
                    {
                        "sample_id": sample_id,
                        "bin_id": bin_id,
                        "contig_id": contig,
                        "membership_score": _get(row, "score", "membership_score", "confidence"),
                        "tool": tool,
                        "source_file": str(path),
                    }
                )
    seen_bins = {str(row["bin_id"]) for row in bin_rows}
    for path in _candidate_files(output_dir, ("*.fa", "*.fasta", "*.fna")):
        members: list[tuple[str, int]] = []
        contig_id = ""
        length = 0
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                line = line.strip()
                if line.startswith(">"):
                    if contig_id:
                        members.append((contig_id, length))
                    contig_id = line[1:].split()[0]
                    length = 0
                elif line:
                    length += len(line)
        if contig_id:
            members.append((contig_id, length))
        if not members:
            continue
        bin_id = path.stem
        if bin_id not in seen_bins:
            bin_rows.append(
                {
                    "sample_id": sample_id,
                    "bin_id": bin_id,
                    "method": tool,
                    "contig_count": len(members),
                    "total_length_bp": sum(item[1] for item in members),
                    "confidence": "unknown",
                    "evidence": "bin_fasta",
                    "source_file": str(path),
                }
            )
        membership_rows.extend(
            {
                "sample_id": sample_id,
                "bin_id": bin_id,
                "contig_id": member_id,
                "membership_score": "",
                "tool": tool,
                "source_file": str(path),
            }
            for member_id, _ in members
        )
    return {"plasmid_bins": bin_rows, "bin_to_contig": membership_rows}


def _read_kraken_report(path: Path) -> List[Dict[str, str]]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        parts = line.rstrip("\n").split("\t")
        if len(parts) >= 6:
            rows.append(
                {
                    "percent": parts[0].strip(),
                    "clade_reads": parts[1].strip(),
                    "taxon_reads": parts[2].strip(),
                    "rank_code": parts[3].strip(),
                    "taxid": parts[4].strip(),
                    "name": parts[5].strip(),
                }
            )
            continue
        table_rows = _read_table(path)
        if table_rows:
            return table_rows
    return rows


def _parse_tabular_hits(output_dir: Path, sample_id: str, tool: str) -> List[Dict[str, Any]]:
    rows = []
    for path in _candidate_files(output_dir, ("*.tsv", "*.txt", "*.m8", "*.blast")):
        parsed_any = False
        for row in _read_table(path):
            query = _get(row, "query", "query_id", "qseqid", "contig")
            subject = _get(row, "subject", "subject_id", "sseqid", "target")
            if query and subject:
                parsed_any = True
                rows.append(_comparative_hit_row(sample_id, query, subject, row, tool, path))
        if parsed_any:
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip() or line.startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) < 2:
                continue
            row = {
                "query_id": parts[0],
                "subject_id": parts[1],
                "identity": parts[2] if len(parts) > 2 else "",
                "alignment_length": parts[3] if len(parts) > 3 else "",
                "e_value": parts[10] if len(parts) > 10 else "",
                "bit_score": parts[11] if len(parts) > 11 else "",
            }
            rows.append(_comparative_hit_row(sample_id, parts[0], parts[1], row, tool, path))
    return rows


def _comparative_hit_row(
    sample_id: str,
    query: str,
    subject: str,
    row: Mapping[str, str],
    tool: str,
    path: Path,
) -> Dict[str, Any]:
    return {
        "sample_id": sample_id,
        "query_id": query,
        "subject_id": subject,
        "identity": _get(row, "identity", "pident", "percent_identity"),
        "coverage": _get(row, "coverage", "qcov", "qcovs", "target_coverage"),
        "e_value": _get(row, "e_value", "evalue"),
        "bit_score": _get(row, "bit_score", "bitscore"),
        "alignment_length": _get(row, "alignment_length", "length"),
        "tool": tool,
        "evidence": _evidence(row, ["mismatch", "gapopen", "qstart", "qend", "sstart", "send"]),
        "source_file": str(path),
    }


def _read_matrix(path: Path) -> Dict[str, Dict[str, str]]:
    if not path.exists():
        return {}
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not lines:
        return {}
    header = lines[0].split("\t")
    columns = [column.strip() for column in header[1:]]
    matrix: Dict[str, Dict[str, str]] = {}
    for line in lines[1:]:
        parts = line.split("\t")
        if not parts:
            continue
        row_id = parts[0].strip()
        if not row_id:
            continue
        matrix[row_id] = {}
        for column, value in zip(columns, parts[1:]):
            matrix[row_id][column] = value.strip()
    return matrix


def _candidate_files(output_dir: Path, patterns: Iterable[str]) -> List[Path]:
    if not output_dir.exists():
        return []
    files: List[Path] = []
    for pattern in patterns:
        for path in sorted(output_dir.rglob(pattern)):
            if path.is_file() and path not in files:
                files.append(path)
    return files


def _read_table(path: Path) -> List[Dict[str, str]]:
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not lines:
        return []
    start = 0
    while start < len(lines) and lines[start].startswith("##"):
        start += 1
    if start >= len(lines):
        return []
    header = lines[start]
    delimiter = "\t" if "\t" in header else ","
    reader = csv.DictReader(lines[start:], delimiter=delimiter)
    rows = []
    for raw in reader:
        normalized = {}
        for key, value in raw.items():
            if key is None:
                continue
            normalized[_normalize_key(key)] = "" if value is None else str(value).strip()
        rows.append(normalized)
    return rows


def _read_metaphlan_table(path: Path) -> List[Dict[str, str]]:
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not lines:
        return []
    table_lines = []
    header_seen = False
    for line in lines:
        if line.startswith("#clade_name"):
            table_lines.append(line.lstrip("#"))
            header_seen = True
            continue
        if line.startswith("#"):
            continue
        if header_seen:
            table_lines.append(line)
    if not table_lines:
        return []
    return [
        {str(key): str(value) for key, value in row.items() if key is not None}
        for row in csv.DictReader(table_lines, delimiter="\t")
    ]


def _metaphlan_species(clade: str) -> str:
    if not clade:
        return ""
    for part in reversed(clade.split("|")):
        if part.startswith("s__") and len(part) > 3:
            return part[3:].replace("_", " ")
    return ""


def _read_gff_features(path: Path) -> List[Dict[str, str]]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) < 9:
            continue
        attributes = _parse_gff_attributes(parts[8])
        row = {
            "seqid": parts[0],
            "source": parts[1],
            "type": parts[2],
            "start": parts[3],
            "end": parts[4],
            "score": parts[5],
            "strand": parts[6],
            "phase": parts[7],
            **attributes,
        }
        rows.append({_normalize_key(key): value for key, value in row.items()})
    return rows


def _read_fasta_lengths(path: Path) -> List[int]:
    lengths = []
    current = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith(">"):
            if current:
                lengths.append(current)
            current = 0
        elif line.strip():
            current += len(line.strip())
    if current:
        lengths.append(current)
    return lengths


def _assembly_fasta_summary_rows(path: Path, sample_id: str, tool: str) -> List[Dict[str, Any]]:
    lengths = _read_fasta_lengths(path)
    if not lengths:
        return []
    rows = []
    for metric, value, unit in [
        ("contig_count", len(lengths), "count"),
        ("total_length", sum(lengths), "bp"),
        ("max_contig_length", max(lengths), "bp"),
        ("n50", _n50(lengths), "bp"),
    ]:
        rows.append(
            {
                "sample_id": sample_id,
                "tool": tool,
                "metric": metric,
                "value": value,
                "unit": unit,
                "source_file": str(path),
            }
        )
    return rows


def _n50(lengths: Iterable[int]) -> int:
    sorted_lengths = sorted(lengths, reverse=True)
    half = sum(sorted_lengths) / 2
    running = 0
    for length in sorted_lengths:
        running += length
        if running >= half:
            return length
    return 0


def _parse_gff_attributes(value: str) -> Dict[str, str]:
    attributes = {}
    for item in value.split(";"):
        if not item:
            continue
        if "=" in item:
            key, raw_value = item.split("=", 1)
        elif " " in item:
            key, raw_value = item.split(" ", 1)
        else:
            continue
        attributes[key.strip()] = raw_value.strip().replace("%20", " ")
    return attributes


def _normalize_key(value: str) -> str:
    value = value.strip().lstrip("#").replace("%", "percent_")
    return re.sub(r"[^0-9a-zA-Z]+", "_", value).strip("_").lower()


def _get(row: Mapping[str, str], *keys: str) -> str:
    for key in keys:
        value = row.get(_normalize_key(key), "")
        if value not in {"", "-", "NA", "N/A", "nan", "None"}:
            return value
    return ""


def _get_contains(row: Mapping[str, str], *keys: str) -> str:
    """Like ``_get``, but also matches when any *normalized* column name
    **contains** one of the requested keys.  This is necessary for tools
    like CoverM whose column names embed dynamic sample-name prefixes
    (e.g. ``SRR2241213.samtools Mean``), making an exact-match lookup
    impossible.

    Returns the first value whose normalized column name contains any of
    the given keys.  Excludes sentinel / missing values (empty, dash, NA).
    """
    for key in keys:
        nkey = _normalize_key(key)
        for col, value in row.items():
            if nkey in _normalize_key(col) and value not in {"", "-", "NA", "N/A", "nan", "None"}:
                return value
    return ""


def _score_or_blank(value: str) -> str:
    numeric = _as_float(value)
    return "" if numeric is None else str(round(numeric, 4))


def _fraction_score(value: str) -> str:
    numeric = _as_float(value)
    if numeric is None:
        return ""
    if numeric > 1:
        numeric = numeric / 100.0
    return str(round(numeric, 4))


def _confidence(value: str) -> str:
    numeric = _as_float(value)
    if numeric is None:
        return "unknown"
    if numeric > 1:
        numeric = numeric / 100.0
    if numeric >= 0.9:
        return "high"
    if numeric >= 0.7:
        return "medium"
    return "low"


def _as_float(value: str) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _evidence(row: Mapping[str, str], keys: Iterable[str]) -> str:
    return _join_evidence({key: _get(row, key) for key in keys})


def _join_evidence(items: Mapping[str, str]) -> str:
    return ";".join(f"{key}={value}" for key, value in items.items() if value)


def _annotation_category(value: str) -> str:
    lowered = value.lower()
    if any(token in lowered for token in ["card", "amr", "arg", "resfinder", "resistance"]):
        return "ARG"
    if any(token in lowered for token in ["vf", "virulence"]):
        return "VF"
    if any(token in lowered for token in ["integron", "tn", "transpos", "is", "mobile"]):
        return "mobile_element"
    return value or "feature"
