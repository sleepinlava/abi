"""Amplicon 16S rRNA Community Analysis ABI Plugin.

Purpose / 目的
~~~~~~~~~~~~~~
Microbial community profiling pipeline demonstrating ABI portability
to the most widely used bioinformatics analysis type:

    cutadapt → vsearch derep → vsearch UNOISE3 → SINTAX taxonomy → diversity
    (primer)    (dereplicate)   (ASV denoise)     (classification)   (metrics)

Tool chain / 工具链
~~~~~~~~~~~~~~~~~~~
- **cutadapt**: primer/adapter removal (Martin 2011)
- **vsearch --derep_fulllength**: dereplicate with abundance annotation
- **vsearch --cluster_unoise**: UNOISE3 denoising into ASVs (Edgar 2016)
- **vsearch --cluster_size**: optional OTU clustering at 97% identity
- **vsearch --sintax**: SINTAX taxonomic classification (Edgar 2016)
- **diversity**: alpha + beta diversity metrics

Standard tables / 标准表格
~~~~~~~~~~~~~~~~~~~~~~~~~~
- ``asv_table``: ASV abundance per sample
- ``taxonomy``: kingdom→species classification with confidence scores
- ``alpha_diversity``: observed_features, Shannon, Simpson, Faith's PD, Chao1
- ``beta_diversity``: pairwise distances (Bray-Curtis, Jaccard, UniFrac)
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional

from abi.config import PLUGIN_ROOT, PROJECT_ROOT, compact_overrides, deep_merge, load_yaml
from abi.report import write_generic_report
from abi.schemas import ABIExecutionPlan, ABIPlanStep, ABISample, ABISampleContext
from abi.tables import StandardTableManager
from abi.timeouts import mapping_block
from abi.tools import ToolRegistry


class Amplicon16SPlugin:
    """ABI plugin for 16S rRNA amplicon community analysis.

    Implements the ``ABIPlugin`` interface with a 6-tool chain:
    cutadapt → vsearch derep → UNOISE3 denoise → SINTAX taxonomy
    → (optional OTU clustering) → diversity metrics.
    """

    plugin_id = "amplicon_16s"
    display_name = "Amplicon 16S rRNA Community Analysis"
    description = (
        "Microbial community profiling: primer trimming (cutadapt) → "
        "denoising/ASV (vsearch UNOISE3) → taxonomy (vsearch SINTAX) → "
        "diversity metrics."
    )
    report_title = "Amplicon 16S Community Analysis ABI Report"

    @property
    def root(self) -> Path:
        return PLUGIN_ROOT / self.plugin_id

    # ── Configuration ───────────────────────────────────────────────────

    def load_config(
        self,
        config_path: str | Path | None = None,
        *,
        profile: str | None = None,
        overrides: Optional[Mapping[str, Any]] = None,
    ) -> Dict[str, Any]:
        del profile
        config = load_yaml(self.root / "config_default.yaml")
        if config_path:
            config = deep_merge(config, load_yaml(config_path))
        config = deep_merge(config, compact_overrides(overrides))
        _resolve_config_paths(config)
        self._validate_config(config)
        return config

    # ── Sample context ───────────────────────────────────────────────────

    def build_sample_context(
        self,
        config: Mapping[str, Any],
        *,
        check_files: bool = True,
    ) -> ABISampleContext:
        input_config = config.get("input", {})
        if not isinstance(input_config, Mapping):
            raise ValueError("input must be a mapping")
        sample_sheet = input_config.get("sample_sheet")
        if not sample_sheet:
            raise ValueError("amplicon_16s requires input.sample_sheet")
        return _parse_sample_sheet(sample_sheet, check_files=check_files)

    # ── Plan construction ────────────────────────────────────────────────

    def build_plan(
        self,
        config: Mapping[str, Any],
        *,
        check_files: bool = True,
    ) -> ABIExecutionPlan:
        context = self.build_sample_context(config, check_files=check_files)
        outdir = Path(str(config["outdir"]))
        threads = int(config["threads"])
        primers = mapping_block(config, "primers")
        forward_primer = str(primers.get("forward", "GTGCCAGCMGCCGCGGTAA"))
        reverse_primer = str(primers.get("reverse", "GGACTACHVGGGTWTCTAAT"))
        resources = config.get("resources", {})
        if not isinstance(resources, Mapping):
            resources = {}
        taxonomy_db = str(resources.get("taxonomy_db", "TAXONOMY_DB_NOT_CONFIGURED"))
        diversity_script = str(resources.get("diversity_script", "DIVERSITY_SCRIPT_NOT_CONFIGURED"))
        phylogeny_tree = str(resources.get("phylogeny_tree", "PHYLOGENY_TREE_NOT_CONFIGURED"))
        do_otu = bool(mapping_block(config, "otu_clustering").get("enabled", False))

        steps: List[ABIPlanStep] = []

        for sample in context.samples:
            # ── Step 1: Primer trimming (cutadapt) ──
            trim_out = outdir / "01_trimmed" / sample.sample_id
            steps.append(
                ABIPlanStep(
                    step_id=f"{sample.sample_id}_trim_cutadapt",
                    sample_id=sample.sample_id,
                    step_name="primer_trimming",
                    tool_id="cutadapt",
                    category="qc",
                    inputs={"read1": sample.read1, "read2": sample.read2,
                            "forward_primer": forward_primer, "reverse_primer": reverse_primer},
                    outputs={"output_dir": str(trim_out)},
                    params={"sample_id": sample.sample_id, "threads": threads,
                            "mode": config["mode"]},
                )
            )

            # ── Step 2: Dereplicate (vsearch) ──
            derep_out = outdir / "02_derep" / sample.sample_id
            merged = trim_out / f"{sample.sample_id}_merged.fasta"
            steps.append(
                ABIPlanStep(
                    step_id=f"{sample.sample_id}_derep_vsearch",
                    sample_id=sample.sample_id,
                    step_name="dereplicate",
                    tool_id="vsearch_derep",
                    category="preprocessing",
                    inputs={"merged_fasta": str(merged)},
                    outputs={"output_dir": str(derep_out)},
                    params={"sample_id": sample.sample_id, "mode": config["mode"]},
                )
            )

            # ── Step 3: Denoise UNOISE3 (vsearch) ──
            denoise_out = outdir / "03_denoise" / sample.sample_id
            derep_fasta = derep_out / "derep.fasta"
            asv_fasta = denoise_out / "asvs.fasta"
            steps.append(
                ABIPlanStep(
                    step_id=f"{sample.sample_id}_denoise_unoise3",
                    sample_id=sample.sample_id,
                    step_name="asv_denoising",
                    tool_id="vsearch_denoise",
                    category="denoising",
                    inputs={"derep_fasta": str(derep_fasta)},
                    outputs={"output_dir": str(denoise_out), "asv_fasta": str(asv_fasta)},
                    params={"sample_id": sample.sample_id, "mode": config["mode"]},
                )
            )

            # ── Step 4 (optional): OTU clustering ──
            if do_otu:
                otu_out = outdir / "03b_otu" / sample.sample_id
                steps.append(
                    ABIPlanStep(
                        step_id=f"{sample.sample_id}_otu_cluster",
                        sample_id=sample.sample_id,
                        step_name="otu_clustering",
                        tool_id="vsearch_otu",
                        category="clustering",
                        inputs={"asv_fasta": str(asv_fasta)},
                        outputs={"output_dir": str(otu_out)},
                        params={"sample_id": sample.sample_id, "mode": config["mode"]},
                    )
                )

            # ── Step 5: SINTAX taxonomy (vsearch) ──
            tax_out = outdir / "04_taxonomy" / sample.sample_id
            steps.append(
                ABIPlanStep(
                    step_id=f"{sample.sample_id}_taxonomy_sintax",
                    sample_id=sample.sample_id,
                    step_name="taxonomic_classification",
                    tool_id="vsearch_taxonomy",
                    category="taxonomy",
                    inputs={"asv_fasta": str(asv_fasta), "taxonomy_db": taxonomy_db},
                    outputs={"output_dir": str(tax_out)},
                    params={"sample_id": sample.sample_id, "mode": config["mode"]},
                )
            )

        # ── Step 6: Diversity metrics (all samples) ──
        div_out = outdir / "05_diversity"
        asv_table = outdir / "merged_asv_table.tsv"
        steps.append(
            ABIPlanStep(
                step_id="diversity_metrics",
                sample_id="ALL",
                step_name="diversity_metrics",
                tool_id="diversity_metrics",
                category="diversity",
                inputs={
                    "asv_table": str(asv_table),
                    "diversity_script": diversity_script,
                    "phylogeny_tree": phylogeny_tree,
                },
                outputs={"output_dir": str(div_out)},
                params={"mode": config["mode"]},
            )
        )

        selected_tools = sorted({step.tool_id for step in steps if step.tool_id != "internal"})
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

    # ── Tool registry ────────────────────────────────────────────────────

    def registry(self) -> ToolRegistry:
        return ToolRegistry.from_path(self.root / "tool_registry.yaml")

    # ── Standard tables ──────────────────────────────────────────────────

    def table_schemas(self) -> Mapping[str, Iterable[str]]:
        data = load_yaml(self.root / "standard_tables.yaml")
        tables = data.get("tables", {})
        if not isinstance(tables, Mapping):
            raise ValueError("standard_tables.yaml must contain a tables mapping")
        return tables

    # ── Output parsing ───────────────────────────────────────────────────

    def parse_outputs(
        self,
        tool_id: str,
        output_dir: str | Path,
        sample_id: str,
    ) -> Mapping[str, List[Dict[str, Any]]]:
        if tool_id == "vsearch_taxonomy":
            return {"taxonomy": _parse_sintax(Path(output_dir), sample_id)}
        if tool_id == "diversity_metrics":
            return {
                "alpha_diversity": _parse_alpha_diversity(Path(output_dir)),
                "beta_diversity": _parse_beta_diversity(Path(output_dir)),
            }
        return {}

    # ── Report generation ────────────────────────────────────────────────

    def write_report(self, plan: Any, result_dir: str | Path) -> Dict[str, Path]:
        table_manager = StandardTableManager(self.table_schemas())
        return write_generic_report(
            plan,
            result_dir,
            table_summary=table_manager.summarize(Path(result_dir) / "tables"),
            title=self.report_title,
        )

    # ── Validation ───────────────────────────────────────────────────────

    def _validate_config(self, config: Mapping[str, Any]) -> None:
        required = ["project_name", "mode", "threads", "outdir", "log_dir", "input"]
        missing = [key for key in required if key not in config]
        if missing:
            raise ValueError(f"Missing amplicon_16s config keys: {', '.join(missing)}")
        threads = config.get("threads")
        try:
            threads = int(threads)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            raise ValueError("threads must be a positive integer") from None
        if threads < 1:
            raise ValueError("threads must be a positive integer")


# ── Sample sheet parser ──────────────────────────────────────────────────


def _parse_sample_sheet(path: str | Path, *, check_files: bool) -> ABISampleContext:
    sample_sheet = _resolve_path(path, base_dirs=[PROJECT_ROOT])
    if not sample_sheet.exists():
        raise ValueError(f"Sample sheet does not exist: {sample_sheet}")
    with sample_sheet.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if reader.fieldnames is None:
            raise ValueError(f"Sample sheet is empty: {sample_sheet}")
        columns = set(reader.fieldnames)
        required = {"sample_id", "read1", "read2"}
        missing = required - columns
        if missing:
            raise ValueError(f"Sample sheet missing required columns: {sorted(missing)}")
        samples = []
        for index, row in enumerate(reader, start=2):
            sample_id = _clean(row.get("sample_id"))
            read1 = _clean(row.get("read1"))
            read2 = _clean(row.get("read2"))
            if not sample_id or not read1 or not read2:
                raise ValueError(f"Row {index}: sample_id, read1, and read2 are required")
            read1 = str(_resolve_path(read1, base_dirs=[sample_sheet.parent, PROJECT_ROOT]))
            read2 = str(_resolve_path(read2, base_dirs=[sample_sheet.parent, PROJECT_ROOT]))
            samples.append(
                ABISample(
                    sample_id=sample_id,
                    platform="illumina",
                    group=_clean(row.get("group")),
                    read1=read1,
                    read2=read2,
                    condition=_clean(row.get("condition")),
                )
            )
    if not samples:
        raise ValueError("Sample sheet contains no sample rows")
    if check_files:
        missing_files = []
        for sample in samples:
            for field in ("read1", "read2"):
                value = getattr(sample, field)
                if value and not Path(str(value)).exists():
                    missing_files.append(f"{sample.sample_id}:{field}={value}")
        if missing_files:
            raise ValueError("Input files do not exist: " + "; ".join(missing_files))
    groups = {sample.group for sample in samples if sample.group}
    return ABISampleContext(
        samples=samples,
        multi_sample=len(samples) > 1,
        has_groups=len(groups) >= 2,
        enable_sample_analysis=len(samples) > 1,
        enable_differential_abundance=len(groups) >= 2,
    )


# ── Config path resolution ───────────────────────────────────────────────


def _resolve_config_paths(config: Dict[str, Any]) -> None:
    input_config = config.get("input", {})
    if not isinstance(input_config, dict):
        return
    sample_sheet = input_config.get("sample_sheet")
    if sample_sheet:
        input_config["sample_sheet"] = str(_resolve_path(sample_sheet, base_dirs=[PROJECT_ROOT]))


def _resolve_path(value: str | Path, *, base_dirs: Iterable[Path]) -> Path:
    path = Path(value)
    if path.is_absolute() or path.exists():
        return path
    for base_dir in base_dirs:
        candidate = base_dir / path
        if candidate.exists():
            return candidate
    return path


# ── SINTAX taxonomy parser ──────────────────────────────────────────────


def _parse_sintax(output_dir: Path, sample_id: str) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for path in sorted(output_dir.glob("taxonomy*.tsv")):
        with path.open("r", encoding="utf-8", newline="") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                parts = line.split("\t")
                if len(parts) < 2:
                    continue
                asv_id = parts[0]
                tax_str = parts[1]
                conf = parts[2] if len(parts) > 2 else ""
                ranks = tax_str.split(",")
                rank_map: Dict[str, str] = {}
                for rank_entry in ranks:
                    prefix = rank_entry[0] if rank_entry else ""
                    name = rank_entry[3:] if len(rank_entry) > 3 else rank_entry
                    if prefix == "d":
                        rank_map["kingdom"] = name
                    elif prefix == "p":
                        rank_map["phylum"] = name
                    elif prefix == "c":
                        rank_map["class"] = name
                    elif prefix == "o":
                        rank_map["order"] = name
                    elif prefix == "f":
                        rank_map["family"] = name
                    elif prefix == "g":
                        rank_map["genus"] = name
                    elif prefix == "s":
                        rank_map["species"] = name
                rows.append({
                    "asv_id": asv_id,
                    "kingdom": rank_map.get("kingdom", ""),
                    "phylum": rank_map.get("phylum", ""),
                    "class": rank_map.get("class", ""),
                    "order": rank_map.get("order", ""),
                    "family": rank_map.get("family", ""),
                    "genus": rank_map.get("genus", ""),
                    "species": rank_map.get("species", ""),
                    "confidence": conf.strip("()") if conf else "",
                    "tool": "vsearch_sintax",
                    "source_file": str(path),
                })
    return rows


# ── Diversity parsers ───────────────────────────────────────────────────


def _parse_alpha_diversity(output_dir: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for path in sorted(output_dir.glob("alpha*.tsv")):
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle, delimiter="\t")
            if not reader.fieldnames:
                continue
            for row in reader:
                rows.append({
                    "sample_id": row.get("sample_id", ""),
                    "observed_features": row.get("observed_features", row.get("observed_otus", "")),
                    "shannon_entropy": row.get("shannon", row.get("shannon_entropy", "")),
                    "simpson_index": row.get("simpson", ""),
                    "faith_pd": row.get("faith_pd", ""),
                    "chao1": row.get("chao1", ""),
                    "tool": "diversity_metrics",
                    "source_file": str(path),
                })
    return rows


def _parse_beta_diversity(output_dir: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for path in sorted(output_dir.glob("beta*.tsv") + output_dir.glob("*distance*.tsv")):
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle, delimiter="\t")
            if not reader.fieldnames:
                continue
            metric = path.stem
            for row in reader:
                sample_a = row.get("sample_a", row.get("sample1", ""))
                sample_b = row.get("sample_b", row.get("sample2", ""))
                if not sample_a or not sample_b:
                    continue
                rows.append({
                    "comparison": f"{sample_a}_vs_{sample_b}",
                    "distance_metric": metric,
                    "sample_a": sample_a,
                    "sample_b": sample_b,
                    "distance": row.get("distance", ""),
                    "tool": "diversity_metrics",
                    "source_file": str(path),
                })
    return rows


# ── String cleaning ─────────────────────────────────────────────────────


def _clean(value: Any) -> Optional[str]:
    if value is None:
        return None
    value = str(value).strip()
    return value or None
