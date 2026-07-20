"""Internal DAG handlers for the metagenomic plasmid plugin."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any, Mapping

from abi.internal import FunctionInternalHandler, InternalHandlerContext, InternalHandlerResult


def passthrough_assembly_handler(
    step: Any,
    config: Mapping[str, Any],
    context: InternalHandlerContext,
) -> InternalHandlerResult:
    """Pass-through handler: copy assembly input path to output."""
    del config, context
    assembly_path = step.inputs.get("assembly", "")
    step.outputs["assembly"] = assembly_path
    return InternalHandlerResult(message=f"Assembly passthrough: {assembly_path}")


def plasmid_consensus_handler(
    step: Any,
    config: Mapping[str, Any],
    context: InternalHandlerContext,
) -> InternalHandlerResult:
    """Build consensus plasmid contigs from detection tool outputs.

    For assembly-mode pipelines where detection tools agree the input is plasmid,
    the consensus output is the original assembly. In the assembly passthrough case,
    the genomad plasmid contigs (or the original assembly) are copied to the output path.
    """
    del config, context
    output_path = Path(step.outputs.get("plasmid_contigs", ""))

    # Try genomad plasmid contigs first (most common path)
    genomad_summary = step.inputs.get("genomad_summary", "")
    if genomad_summary:
        genomad_dir = Path(genomad_summary).parent
        genomad_contigs = genomad_dir / "contigs_plasmid.fna"
        if genomad_contigs.exists():
            output_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(genomad_contigs, output_path)
            return InternalHandlerResult(
                message=f"Consensus contigs from genomad: {genomad_contigs} -> {output_path}"
            )

    # Fallback: try parent directory for NC_*.plasmid.fasta
    genomad_summary_path = Path(genomad_summary) if genomad_summary else None
    if genomad_summary_path and genomad_summary_path.exists():
        step_dir = genomad_summary_path.parent
        for f in step_dir.glob("*.plasmid.fasta"):
            output_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, output_path)
            return InternalHandlerResult(
                message=f"Consensus contigs from genomad: {f} -> {output_path}"
            )

    return InternalHandlerResult(
        status="skipped",
        message="No plasmid contigs found from detection tools — consensus skipped",
    )


def plasmid_structure_handler(
    step: Any,
    config: Mapping[str, Any],
    context: InternalHandlerContext,
) -> InternalHandlerResult:
    """Detect header-declared circularity and exact terminal sequence overlap."""
    del config, context
    from ._engine.pipeline import _read_fasta_records, _terminal_overlap_length

    source_value = step.inputs.get("plasmid_contigs") or step.params.get("plasmid_contigs")
    source = Path(str(source_value or ""))
    rows = []
    if source.is_file():
        for record in _read_fasta_records(source):
            sequence = record["sequence"].upper()
            overlap = _terminal_overlap_length(sequence)
            header_circular = any(
                marker in record["header"].lower()
                for marker in ("circular=true", "topology=circular", "_circular")
            )
            rows.append(
                {
                    "sample_id": step.sample_id or "",
                    "plasmid_id": record["id"],
                    "length_bp": len(sequence),
                    "is_circular": str(bool(header_circular or overlap >= 20)).lower(),
                    "terminal_overlap_bp": overlap,
                    "method": "header_or_exact_terminal_overlap",
                    "warnings": (
                        "Sequence-based circularity is predictive and should be confirmed from "
                        "the assembly graph or read support."
                    ),
                    "source_file": str(source),
                }
            )
    return InternalHandlerResult(
        message=f"Plasmid structure detection: {len(rows)} sequence(s) evaluated",
        tables={"plasmid_structure": rows},
    )


def plasmid_catalog_prepare_handler(
    step: Any,
    config: Mapping[str, Any],
    context: InternalHandlerContext,
) -> InternalHandlerResult:
    """Prepare non-redundant plasmid catalog for cross-sample comparison.

    Gathers all per-sample plasmid contigs files and concatenates them
    into a single FASTA catalog file.
    """
    del config
    output_path = Path(step.outputs.get("combined_plasmids", ""))
    outdir = context.outdir
    contig_files = sorted(outdir.glob("04_plasmid_detection/*/plasmid_contigs.fasta"))

    if not contig_files:
        return InternalHandlerResult(
            status="skipped",
            message="No plasmid contigs found for catalog preparation",
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w") as out:
        for f in contig_files:
            out.write(f.read_text())

    return InternalHandlerResult(
        message=f"Plasmid catalog prepared from {len(contig_files)} samples: {output_path}"
    )


def handlers() -> dict[str, FunctionInternalHandler]:
    return {
        "metagenomic_plasmid.passthrough_assembly": FunctionInternalHandler(
            "metagenomic_plasmid.passthrough_assembly",
            passthrough_assembly_handler,
        ),
        "metagenomic_plasmid.plasmid_consensus": FunctionInternalHandler(
            "metagenomic_plasmid.plasmid_consensus",
            plasmid_consensus_handler,
        ),
        "metagenomic_plasmid.plasmid_structure": FunctionInternalHandler(
            "metagenomic_plasmid.plasmid_structure",
            plasmid_structure_handler,
        ),
        "metagenomic_plasmid.plasmid_catalog_prepare": FunctionInternalHandler(
            "metagenomic_plasmid.plasmid_catalog_prepare",
            plasmid_catalog_prepare_handler,
        ),
    }
