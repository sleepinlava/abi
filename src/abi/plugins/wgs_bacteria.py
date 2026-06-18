"""WGS Bacterial Genome Analysis ABI Plugin.

Purpose / 目的
~~~~~~~~~~~~~~
Clinical/food/environmental bacterial isolate analysis pipeline:

    fastp → SPAdes → Prokka → MLST → AMRFinderPlus
    (QC)    (assembly)  (annotation)  (typing)  (AMR profiling)
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional

from abi._shared import _parse_fastp, _resolve_path
from abi.config import PLUGIN_ROOT, PROJECT_ROOT, compact_overrides, deep_merge, load_yaml
from abi.report import write_plugin_report
from abi.schemas import ABIExecutionPlan, ABIPlanStep, ABISample, ABISampleContext
from abi.timeouts import mapping_block
from abi.tools import ToolRegistry


class WGSBacteriaPlugin:
    """ABI plugin for bacterial isolate WGS analysis.

    Implements the ``ABIPlugin`` interface with a 5-tool chain:
    fastp → SPAdes → Prokka → MLST → AMRFinderPlus.
    """

    plugin_id = "wgs_bacteria"
    display_name = "WGS Bacterial Genome Analysis"
    description = (
        "Clinical/food/environmental bacterial isolate analysis: "
        "QC (fastp) → assembly (SPAdes) → annotation (Prokka) → MLST → AMR profiling."
    )
    report_title = "WGS Bacterial Genome ABI Report"

    @property
    def root(self) -> Path:
        return PLUGIN_ROOT / self.plugin_id

    def load_config(self, config_path=None, *, profile=None, overrides=None) -> Dict[str, Any]:
        del profile
        config = load_yaml(self.root / "config_default.yaml")
        if config_path:
            config = deep_merge(config, load_yaml(config_path))
        config = deep_merge(config, compact_overrides(overrides))
        _resolve_config_paths(config)
        self._validate_config(config)
        self._last_config = config
        return config

    def build_sample_context(
        self, config: Mapping[str, Any], *, check_files: bool = True
    ) -> ABISampleContext:
        input_config = config.get("input", {})
        sample_sheet = input_config.get("sample_sheet")
        if not sample_sheet:
            raise ValueError("wgs_bacteria requires input.sample_sheet")
        return _parse_sample_sheet(sample_sheet, check_files=check_files)

    def build_plan(
        self, config: Mapping[str, Any], *, check_files: bool = True
    ) -> ABIExecutionPlan:
        context = self.build_sample_context(config, check_files=check_files)
        outdir = Path(str(config["outdir"]))
        threads = int(config["threads"])
        annot_config = mapping_block(config, "annotation")
        genus = str(annot_config.get("genus", "Escherichia"))
        species = str(annot_config.get("species", "coli"))
        typing_config = mapping_block(config, "typing")
        mlst_scheme = str(typing_config.get("mlst_scheme", "auto"))

        steps: List[ABIPlanStep] = []
        for sample in context.samples:
            # Step 1: QC (fastp)
            qc_out = outdir / "01_qc" / sample.sample_id
            cr1 = qc_out / f"{sample.sample_id}_R1.clean.fastq.gz"
            cr2 = qc_out / f"{sample.sample_id}_R2.clean.fastq.gz"
            steps.append(
                ABIPlanStep(
                    step_id=f"{sample.sample_id}_qc_fastp",
                    sample_id=sample.sample_id,
                    step_name="read_qc",
                    tool_id="fastp",
                    category="qc",
                    inputs={"read1": sample.read1, "read2": sample.read2},
                    outputs={
                        "output_dir": str(qc_out),
                        "clean_read1": str(cr1),
                        "clean_read2": str(cr2),
                    },
                    params={
                        "sample_id": sample.sample_id,
                        "threads": threads,
                        "mode": config["mode"],
                    },
                )
            )

            # Step 2: Assembly (SPAdes)
            asm_out = outdir / "02_assembly" / sample.sample_id
            contigs = asm_out / "contigs.fasta"
            steps.append(
                ABIPlanStep(
                    step_id=f"{sample.sample_id}_assembly_spades",
                    sample_id=sample.sample_id,
                    step_name="genome_assembly",
                    tool_id="spades",
                    category="assembly",
                    inputs={"clean_read1": str(cr1), "clean_read2": str(cr2)},
                    outputs={"output_dir": str(asm_out), "contigs_fasta": str(contigs)},
                    params={
                        "sample_id": sample.sample_id,
                        "threads": threads,
                        "mode": config["mode"],
                    },
                )
            )

            # Step 3: Annotation (Prokka)
            ann_out = outdir / "03_annotation" / sample.sample_id
            faa = ann_out / f"{sample.sample_id}.faa"
            gff = ann_out / f"{sample.sample_id}.gff"
            steps.append(
                ABIPlanStep(
                    step_id=f"{sample.sample_id}_annotation_prokka",
                    sample_id=sample.sample_id,
                    step_name="genome_annotation",
                    tool_id="prokka",
                    category="annotation",
                    inputs={"assembly_fasta": str(contigs), "genus": genus, "species": species},
                    outputs={"output_dir": str(ann_out), "faa": str(faa), "gff": str(gff)},
                    params={
                        "sample_id": sample.sample_id,
                        "threads": threads,
                        "mode": config["mode"],
                    },
                )
            )

            # Step 4: MLST
            mlst_out = outdir / "04_mlst" / sample.sample_id
            steps.append(
                ABIPlanStep(
                    step_id=f"{sample.sample_id}_mlst",
                    sample_id=sample.sample_id,
                    step_name="mlst_typing",
                    tool_id="mlst",
                    category="typing",
                    inputs={"assembly_fasta": str(contigs), "scheme": mlst_scheme},
                    outputs={"output_dir": str(mlst_out)},
                    params={"sample_id": sample.sample_id, "mode": config["mode"]},
                )
            )

            # Step 5: AMR profiling
            amr_out = outdir / "05_amr" / sample.sample_id
            steps.append(
                ABIPlanStep(
                    step_id=f"{sample.sample_id}_amr",
                    sample_id=sample.sample_id,
                    step_name="amr_profiling",
                    tool_id="amrfinderplus",
                    category="amr",
                    inputs={"prokka_faa": str(faa), "prokka_gff": str(gff)},
                    outputs={"output_dir": str(amr_out)},
                    params={
                        "sample_id": sample.sample_id,
                        "threads": threads,
                        "mode": config["mode"],
                    },
                )
            )

        selected_tools = sorted({s.tool_id for s in steps if s.tool_id != "internal"})
        return ABIExecutionPlan(
            project_name=str(config["project_name"]),
            analysis_type=self.plugin_id,
            mode=str(config["mode"]),
            threads=threads,
            outdir=str(outdir),
            log_dir=str(config["log_dir"]),
            samples=context.samples,
            sample_context=context,
            selected_tools=selected_tools,
            steps=steps,
            provenance_dir=str(outdir / "provenance"),
        )

    def registry(self) -> ToolRegistry:
        return ToolRegistry.from_path(self.root / "tool_registry.yaml")

    def table_schemas(self) -> Mapping[str, Any]:
        data = load_yaml(self.root / "standard_tables.yaml")
        return data.get("tables", {})

    def parse_outputs(
        self, tool_id: str, output_dir: str | Path, sample_id: str
    ) -> Mapping[str, Iterable[Mapping[str, Any]]]:
        if tool_id == "fastp":
            return {"qc_summary": _parse_fastp(Path(output_dir), sample_id)}
        if tool_id == "spades":
            return {"genome_assembly_stats": _parse_spades(Path(output_dir), sample_id)}
        if tool_id == "prokka":
            return {"genome_annotation": _parse_prokka(Path(output_dir), sample_id)}
        if tool_id == "mlst":
            return {"mlst_profile": _parse_mlst(Path(output_dir), sample_id)}
        if tool_id == "amrfinderplus":
            return {"amr_profile": _parse_amrfinderplus(Path(output_dir), sample_id)}
        return {}

    def write_report(self, plan: Any, result_dir: str | Path) -> Dict[str, Path]:
        return write_plugin_report(self, plan, result_dir)

    def _validate_config(self, config: Mapping[str, Any]) -> None:
        required = ["project_name", "mode", "threads", "outdir", "log_dir", "input"]
        missing = [k for k in required if k not in config]
        if missing:
            raise ValueError(f"Missing wgs_bacteria config keys: {', '.join(missing)}")


# (shared helpers: _parse_sample_sheet, _resolve_config_paths, _resolve_path, _clean)
# These are near-identical across inline plugins. In production, import from abi._shared.


def _parse_sample_sheet(path: str | Path, *, check_files: bool) -> ABISampleContext:
    ss = _resolve_path(path, base_dirs=[PROJECT_ROOT])
    if check_files and not ss.exists():
        raise ValueError(f"Sample sheet does not exist: {ss}")
    with ss.open("r", encoding="utf-8", newline="") as h:
        r = csv.DictReader(h, delimiter="\t")
        if not r.fieldnames:
            raise ValueError(f"Sample sheet is empty: {ss}")
        required = {"sample_id", "read1", "read2"}
        if required - set(r.fieldnames):
            raise ValueError(
                f"Sample sheet missing columns: {sorted(required - set(r.fieldnames))}"
            )
        samples = []
        for i, row in enumerate(r, start=2):
            sid = str(row.get("sample_id", "")).strip()
            r1 = str(row.get("read1", "")).strip()
            r2 = str(row.get("read2", "")).strip()
            if not sid or not r1 or not r2:
                raise ValueError(f"Row {i}: sample_id, read1, read2 required")
            r1 = str(_resolve_path(r1, base_dirs=[ss.parent, PROJECT_ROOT]))
            r2 = str(_resolve_path(r2, base_dirs=[ss.parent, PROJECT_ROOT]))
            samples.append(
                ABISample(
                    sample_id=sid,
                    platform="illumina",
                    group=str(row.get("group", "")).strip() or None,
                    read1=r1,
                    read2=r2,
                    condition=str(row.get("condition", "")).strip() or None,
                )
            )
    groups = {s.group for s in samples if s.group}
    if check_files:
        missing_files = []
        for sample in samples:
            for field in ("read1", "read2"):
                value = getattr(sample, field)
                if value and not Path(str(value)).exists():
                    missing_files.append(f"{sample.sample_id}:{field}={value}")
        if missing_files:
            raise ValueError("Input files do not exist: " + "; ".join(missing_files))
    return ABISampleContext(
        samples=samples,
        multi_sample=len(samples) > 1,
        has_groups=len(groups) >= 2,
        enable_sample_analysis=len(samples) > 1,
        enable_differential_abundance=len(groups) >= 2,
    )


def _resolve_config_paths(config: Dict[str, Any]) -> None:
    ic = config.get("input", {})
    if isinstance(ic, dict) and ic.get("sample_sheet"):
        ic["sample_sheet"] = str(_resolve_path(ic["sample_sheet"], base_dirs=[PROJECT_ROOT]))


# (``_clean``, ``_resolve_path`` are imported from abi._shared)


def _parse_mlst(output_dir: Path, sample_id: str) -> List[Dict[str, Any]]:
    rows = []
    for path in sorted(output_dir.glob("mlst*.tsv")):
        with path.open() as h:
            for line in h:
                parts = line.strip().split("\t")
                if len(parts) < 3:
                    continue
                row = {
                    "sample_id": sample_id,
                    "scheme": parts[1],
                    "sequence_type": parts[2],
                    "tool": "mlst",
                    "source_file": str(path),
                }
                for j, allele in enumerate(parts[3:10], 1):
                    row[f"allele_{j}"] = allele
                row["clonal_complex"] = parts[3] if len(parts) > 3 else ""
                rows.append(row)
    return rows


def _parse_amrfinderplus(output_dir: Path, sample_id: str) -> List[Dict[str, Any]]:
    rows = []
    for path in sorted(output_dir.glob("*amr*.tsv")):
        with path.open() as h:
            r = csv.DictReader(h, delimiter="\t")
            if not r.fieldnames:
                continue
            for row in r:
                rows.append(
                    {
                        "sample_id": sample_id,
                        "gene_symbol": row.get("Gene symbol", ""),
                        "sequence_name": row.get("Sequence name", ""),
                        "scope": row.get("Scope", ""),
                        "element_type": row.get("Element type", ""),
                        "element_subtype": row.get("Element subtype", ""),
                        "target_class": row.get("Class", ""),
                        "target_subclass": row.get("Subclass", ""),
                        "method": row.get("Method", ""),
                        "coverage_pct": row.get("% Coverage of reference sequence", ""),
                        "identity_pct": row.get("% Identity to reference sequence", ""),
                        "tool": "amrfinderplus",
                        "source_file": str(path),
                    }
                )
    return rows


# ── SPAdes assembly parser ───────────────────────────────────────────────


def _parse_spades(output_dir: Path, sample_id: str) -> List[Dict[str, Any]]:
    """Parse SPAdes contigs FASTA → genome_assembly_stats rows.

    Computes standard assembly metrics: total length, contig count, N50,
    max contig length, and GC content from the contigs FASTA.
    """
    rows: List[Dict[str, Any]] = []
    for path in sorted(output_dir.glob("contigs.fasta")):
        lengths = _read_fasta_lengths(path)
        if not lengths:
            continue
        total = sum(lengths)
        n50 = _compute_n50(lengths)
        gc = _compute_gc_content(path)
        rows.append(
            {
                "sample_id": sample_id,
                "total_length": total,
                "num_contigs": len(lengths),
                "n50": n50,
                "max_contig_length": max(lengths),
                "gc_content": round(gc, 2) if gc is not None else "",
                "coverage": "",
                "tool": "spades",
                "source_file": str(path),
            }
        )
    return rows


# ── Prokka annotation parser ─────────────────────────────────────────────


def _parse_prokka(output_dir: Path, sample_id: str) -> List[Dict[str, Any]]:
    """Parse Prokka GFF3 output → genome_annotation rows.

    Each GFF feature row becomes one annotation entry.
    """
    rows: List[Dict[str, Any]] = []
    for path in sorted(output_dir.glob("*.gff")):
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split("\t")
                if len(parts) < 9:
                    continue
                attrs = _parse_gff_attributes(parts[8])
                rows.append(
                    {
                        "sample_id": sample_id,
                        "feature_id": attrs.get("ID", ""),
                        "feature_type": parts[2],
                        "start": parts[3],
                        "end": parts[4],
                        "strand": parts[6],
                        "product": attrs.get("product", ""),
                        "gene_name": attrs.get("gene", attrs.get("Name", "")),
                        "ec_number": attrs.get("eC_number", attrs.get("EC_number", "")),
                        "tool": "prokka",
                        "source_file": str(path),
                    }
                )
    return rows


# ── Shared helpers ───────────────────────────────────────────────────────


def _read_fasta_lengths(path: Path) -> List[int]:
    """Extract sequence lengths from a FASTA file."""
    lengths: List[int] = []
    current_len = 0
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line.startswith(">"):
                if current_len > 0:
                    lengths.append(current_len)
                current_len = 0
            else:
                current_len += len(line)
        if current_len > 0:
            lengths.append(current_len)
    return lengths


def _compute_n50(lengths: List[int]) -> int:
    """Compute N50 from a list of contig lengths."""
    if not lengths:
        return 0
    sorted_lengths = sorted(lengths, reverse=True)
    total = sum(sorted_lengths)
    cumulative = 0
    for length in sorted_lengths:
        cumulative += length
        if cumulative >= total / 2.0:
            return length
    return 0


def _compute_gc_content(path: Path) -> Optional[float]:
    """Compute GC content from a FASTA file."""
    gc = 0
    total = 0
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line.startswith(">"):
                continue
            for base in line.upper():
                if base in ("G", "C"):
                    gc += 1
                    total += 1
                elif base in ("A", "T", "U"):
                    total += 1
    if total == 0:
        return None
    return (gc / total) * 100.0


def _parse_gff_attributes(attr_string: str) -> Dict[str, str]:
    """Parse GFF3 column-9 attributes into a key→value dict."""
    result: Dict[str, str] = {}
    for pair in attr_string.split(";"):
        pair = pair.strip()
        if "=" in pair:
            key, _, value = pair.partition("=")
            result[key.strip()] = value.strip()
    return result
