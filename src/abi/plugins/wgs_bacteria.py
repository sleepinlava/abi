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
from typing import List

from abi.config import PLUGIN_ROOT, PROJECT_ROOT, compact_overrides, deep_merge, load_yaml
from abi.report import write_full_report
from abi.report.citations import load_citations
from abi.report.limitations import load_limitations
from abi.schemas import ABIExecutionPlan, ABIPlanStep, ABISample, ABISampleContext
from abi.tables import StandardTableManager
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

    def load_config(self, config_path=None, *, profile=None, overrides=None):
        del profile
        config = load_yaml(self.root / "config_default.yaml")
        if config_path:
            config = deep_merge(config, load_yaml(config_path))
        config = deep_merge(config, compact_overrides(overrides))
        _resolve_config_paths(config)
        self._validate_config(config)
        return config

    def build_sample_context(self, config, *, check_files=True):
        input_config = config.get("input", {})
        sample_sheet = input_config.get("sample_sheet")
        if not sample_sheet:
            raise ValueError("wgs_bacteria requires input.sample_sheet")
        return _parse_sample_sheet(sample_sheet, check_files=check_files)

    def build_plan(self, config, *, check_files=True):
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
            steps.append(ABIPlanStep(
                step_id=f"{sample.sample_id}_qc_fastp", sample_id=sample.sample_id,
                step_name="read_qc", tool_id="fastp", category="qc",
                inputs={"read1": sample.read1, "read2": sample.read2},
                outputs={
                    "output_dir": str(qc_out),
                    "clean_read1": str(cr1),
                    "clean_read2": str(cr2),
                },
                params={"sample_id": sample.sample_id, "threads": threads, "mode": config["mode"]},
            ))

            # Step 2: Assembly (SPAdes)
            asm_out = outdir / "02_assembly" / sample.sample_id
            contigs = asm_out / "contigs.fasta"
            steps.append(ABIPlanStep(
                step_id=f"{sample.sample_id}_assembly_spades", sample_id=sample.sample_id,
                step_name="genome_assembly", tool_id="spades", category="assembly",
                inputs={"clean_read1": str(cr1), "clean_read2": str(cr2)},
                outputs={"output_dir": str(asm_out), "contigs_fasta": str(contigs)},
                params={"sample_id": sample.sample_id, "threads": threads, "mode": config["mode"]},
            ))

            # Step 3: Annotation (Prokka)
            ann_out = outdir / "03_annotation" / sample.sample_id
            faa = ann_out / f"{sample.sample_id}.faa"
            gff = ann_out / f"{sample.sample_id}.gff"
            steps.append(ABIPlanStep(
                step_id=f"{sample.sample_id}_annotation_prokka", sample_id=sample.sample_id,
                step_name="genome_annotation", tool_id="prokka", category="annotation",
                inputs={"assembly_fasta": str(contigs), "genus": genus, "species": species},
                outputs={"output_dir": str(ann_out), "faa": str(faa), "gff": str(gff)},
                params={"sample_id": sample.sample_id, "threads": threads, "mode": config["mode"]},
            ))

            # Step 4: MLST
            mlst_out = outdir / "04_mlst" / sample.sample_id
            steps.append(ABIPlanStep(
                step_id=f"{sample.sample_id}_mlst", sample_id=sample.sample_id,
                step_name="mlst_typing", tool_id="mlst", category="typing",
                inputs={"assembly_fasta": str(contigs), "scheme": mlst_scheme},
                outputs={"output_dir": str(mlst_out)},
                params={"sample_id": sample.sample_id, "mode": config["mode"]},
            ))

            # Step 5: AMR profiling
            amr_out = outdir / "05_amr" / sample.sample_id
            steps.append(ABIPlanStep(
                step_id=f"{sample.sample_id}_amr", sample_id=sample.sample_id,
                step_name="amr_profiling", tool_id="amrfinderplus", category="amr",
                inputs={"prokka_faa": str(faa), "prokka_gff": str(gff)},
                outputs={"output_dir": str(amr_out)},
                params={"sample_id": sample.sample_id, "threads": threads, "mode": config["mode"]},
            ))

        selected_tools = sorted({s.tool_id for s in steps if s.tool_id != "internal"})
        return ABIExecutionPlan(
            project_name=str(config["project_name"]), analysis_type=self.plugin_id,
            mode=str(config["mode"]), threads=threads, outdir=str(outdir),
            log_dir=str(config["log_dir"]), samples=context.samples,
            sample_context=context, selected_tools=selected_tools, steps=steps,
            provenance_dir=str(outdir / "provenance"),
        )

    def registry(self):
        return ToolRegistry.from_path(self.root / "tool_registry.yaml")

    def table_schemas(self):
        data = load_yaml(self.root / "standard_tables.yaml")
        return data.get("tables", {})

    def parse_outputs(self, tool_id, output_dir, sample_id):
        if tool_id == "mlst":
            return {"mlst_profile": _parse_mlst(Path(output_dir), sample_id)}
        if tool_id == "amrfinderplus":
            return {"amr_profile": _parse_amrfinderplus(Path(output_dir), sample_id)}
        return {}

    def write_report(self, plan, result_dir):
        tm = StandardTableManager(self.table_schemas())
        summary = tm.summarize(Path(result_dir) / "tables")

        root = self.root
        citations = load_citations(root / "citation_registry.yaml") if (root / "citation_registry.yaml").exists() else []
        limitations = load_limitations(root / "limitations.yaml") if (root / "limitations.yaml").exists() else []

        return write_full_report(
            plan, result_dir,
            table_summary=summary,
            title=self.report_title,
            citations=citations,
            limitations=limitations,
        )

    def _validate_config(self, config):
        required = ["project_name", "mode", "threads", "outdir", "log_dir", "input"]
        missing = [k for k in required if k not in config]
        if missing:
            raise ValueError(f"Missing wgs_bacteria config keys: {', '.join(missing)}")


# (shared helpers: _parse_sample_sheet, _resolve_config_paths, _resolve_path, _clean)
# These are near-identical across inline plugins. In production, import from abi._shared.

def _parse_sample_sheet(path, *, check_files):
    ss = _resolve_path(path, base_dirs=[PROJECT_ROOT])
    if not ss.exists():
        raise ValueError(f"Sample sheet does not exist: {ss}")
    with ss.open("r", encoding="utf-8", newline="") as h:
        r = csv.DictReader(h, delimiter="\t")
        if not r.fieldnames:
            raise ValueError(f"Sample sheet is empty: {ss}")
        required = {"sample_id", "read1", "read2"}
        if required - set(r.fieldnames):
            raise ValueError(
                f"Sample sheet missing columns: "
                f"{sorted(required - set(r.fieldnames))}"
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
            samples.append(ABISample(sample_id=sid, platform="illumina",
                                     group=str(row.get("group", "")).strip() or None,
                                     read1=r1, read2=r2,
                                     condition=str(row.get("condition", "")).strip() or None))
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
    return ABISampleContext(samples=samples, multi_sample=len(samples) > 1,
                            has_groups=len(groups) >= 2,
                            enable_sample_analysis=len(samples) > 1,
                            enable_differential_abundance=len(groups) >= 2)


def _resolve_config_paths(config):
    ic = config.get("input", {})
    if isinstance(ic, dict) and ic.get("sample_sheet"):
        ic["sample_sheet"] = str(_resolve_path(ic["sample_sheet"], base_dirs=[PROJECT_ROOT]))


def _resolve_path(value, *, base_dirs):
    """Resolve *value* against *base_dirs*, rejecting paths that escape.

    Mirrors the path-traversal guard in the flagship plasmid plugin
    (``metagenomic_plasmid/_engine/sample_sheet.py``).  Absolute paths and
    paths that already exist are accepted only if they lie inside one of
    the *base_dirs*.
    """
    p = Path(value)
    # Absolute-or-existing fast path — but only if contained in a base dir.
    if p.is_absolute() or p.exists():
        for bd in base_dirs:
            try:
                p.resolve().relative_to(bd.resolve())
                return p
            except ValueError:
                continue
        # Fall through: could not validate containment; try base-relative lookup.
    for bd in base_dirs:
        c = (bd / p).resolve()
        try:
            c.relative_to(bd.resolve())
        except ValueError:
            # Path escapes the base directory — skip it.
            continue
        if c.exists():
            return c
    return p


def _parse_mlst(output_dir, sample_id):
    rows = []
    for path in sorted(output_dir.glob("mlst*.tsv")):
        with path.open() as h:
            for line in h:
                parts = line.strip().split("\t")
                if len(parts) < 3:
                    continue
                row = {"sample_id": sample_id, "scheme": parts[1], "sequence_type": parts[2],
                       "tool": "mlst", "source_file": str(path)}
                for j, allele in enumerate(parts[3:10], 1):
                    row[f"allele_{j}"] = allele
                row["clonal_complex"] = parts[3] if len(parts) > 3 else ""
                rows.append(row)
    return rows


def _parse_amrfinderplus(output_dir, sample_id):
    rows = []
    for path in sorted(output_dir.glob("amr*.tsv")):
        with path.open() as h:
            r = csv.DictReader(h, delimiter="\t")
            if not r.fieldnames:
                continue
            for row in r:
                rows.append({
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
                })
    return rows


def _clean(value):
    """Strip whitespace and return None for empty strings."""
    if value is None:
        return None
    value = str(value).strip()
    return value or None
