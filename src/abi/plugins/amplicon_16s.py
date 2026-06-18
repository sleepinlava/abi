"""Amplicon 16S rRNA Community Analysis ABI Plugin.

Purpose / 目的
~~~~~~~~~~~~~~
Microbial community profiling pipeline demonstrating ABI portability
to the most widely used bioinformatics analysis type:

    cutadapt → vsearch merge → vsearch derep → UNOISE3 → SINTAX → diversity
    (primer)    (merge pairs)   (dereplicate)   (ASV)     (taxonomy) (metrics)

Tool chain / 工具链
~~~~~~~~~~~~~~~~~~~
- **cutadapt**: primer/adapter removal (Martin 2011)
- **vsearch --fastq_mergepairs**: merge paired-end reads into full-length sequences
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

from abi._shared import _clean, _resolve_path
from abi.config import PLUGIN_ROOT, PROJECT_ROOT, compact_overrides, deep_merge, load_yaml
from abi.report import write_plugin_report
from abi.schemas import ABIExecutionPlan, ABISample, ABISampleContext
from abi.tools import ToolRegistry


class Amplicon16SPlugin:
    """ABI plugin for 16S rRNA amplicon community analysis.

    Implements the ``ABIPlugin`` interface with a 7-tool chain:
    cutadapt → vsearch merge → vsearch derep → UNOISE3 denoise
    → SINTAX taxonomy → (optional OTU clustering) → diversity metrics.
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

    @property
    def _tsv_mapper(self):
        if not hasattr(self, "_tsv_mapper_cache"):
            from abi.tsv_mapping import TSVMapper

            self._tsv_mapper_cache = TSVMapper.from_yaml(self.root / "parsers.yaml")
        return self._tsv_mapper_cache

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
        self._last_config = config
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
        from abi.dag_planner import build_plan_from_dag

        return build_plan_from_dag(self.root / "pipeline_dag.yaml", config, context)

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
        # Try declarative TSV mapper first
        if self._tsv_mapper.has_parser(tool_id):
            rows = self._tsv_mapper.parse(tool_id, output_dir, sample_id=sample_id)
            if rows:
                target = self._tsv_mapper.get_target_table(tool_id)
                return {target: rows} if target else {}
        # Fall back to hand-written parsers
        if tool_id == "cutadapt":
            return {"primer_trim_summary": _parse_cutadapt(Path(output_dir), sample_id)}
        if tool_id == "vsearch_mergepairs":
            return {"merge_stats": _parse_vsearch_merge(Path(output_dir), sample_id)}
        if tool_id == "vsearch_derep":
            return {"denoising_stats": _parse_vsearch_derep(Path(output_dir), sample_id)}
        if tool_id == "vsearch_denoise":
            return {"denoising_stats": _parse_vsearch_denoise(Path(output_dir), sample_id)}
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
        return write_plugin_report(self, plan, result_dir)

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
        if check_files:
            raise ValueError(f"Sample sheet does not exist: {sample_sheet}")
        # Return a minimal synthetic context for dry-run / testing
        return ABISampleContext(
            samples=[
                ABISample(
                    sample_id="S1",
                    platform="illumina",
                    read1="/tmp/R1.fq",
                    read2="/tmp/R2.fq",
                    group="default",
                )
            ],
            multi_sample=False,
            has_groups=False,
            enable_sample_analysis=False,
            enable_differential_abundance=False,
        )
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


# (``_clean``, ``_resolve_path`` are imported from abi._shared)


def _count_fastq_records(path: Path) -> int:
    """Count the number of FASTQ records in a (possibly gzipped) file."""
    count = 0
    try:
        opener = open
        if path.suffix == ".gz":
            import gzip

            opener = gzip.open  # type: ignore[assignment]
        with opener(path, "rt", encoding="utf-8", errors="replace") as handle:  # type: ignore[operator]
            for line in handle:
                if line.startswith("@"):
                    count += 1
    except (OSError, EOFError):
        return 0
    return count


# ── cutadapt parser ─────────────────────────────────────────────────────


def _parse_cutadapt(output_dir: Path, sample_id: str) -> List[Dict[str, Any]]:
    """Parse cutadapt log output → primer_trim_summary rows.

    Reads cutadapt's log/report file and extracts trimming statistics.
    Falls back to counting trimmed FASTQ records if no log is present.
    """
    rows: List[Dict[str, Any]] = []
    # Try parsing a cutadapt log/report file first
    for path in sorted(output_dir.glob("*cutadapt*.log")):
        stats: Dict[str, int] = {}
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if ":" in line:
                    key, _, val = line.partition(":")
                    key = key.strip().lower().replace(" ", "_")
                    try:
                        stats[key] = int(val.strip().replace(",", ""))
                    except ValueError:
                        continue
        if stats:
            # Match cutadapt log keys with substring containment
            def _get(*substrings: str) -> int:
                for k, v in stats.items():
                    if all(s in k for s in substrings):
                        return v
                return 0

            rows.append(
                {
                    "sample_id": sample_id,
                    "total_reads": _get("total", "read", "pair") or _get("total", "read"),
                    "reads_trimmed": _get("read", "adapter") or _get("trimmed"),
                    "reads_too_short": _get("too_short"),
                    "reads_written": _get("written", "pass") or _get("written"),
                    "tool": "cutadapt",
                    "source_file": str(path),
                }
            )
    # Fallback: count trimmed FASTQ records
    if not rows:
        total = 0
        for path in sorted(output_dir.glob("*trimmed*.fastq*")):
            total += _count_fastq_records(path)
        if total > 0:
            rows.append(
                {
                    "sample_id": sample_id,
                    "total_reads": total,
                    "reads_trimmed": total,
                    "reads_too_short": 0,
                    "reads_written": total,
                    "tool": "cutadapt",
                    "source_file": str(output_dir),
                }
            )
    return rows


# ── vsearch merge parser ─────────────────────────────────────────────────


def _parse_vsearch_merge(output_dir: Path, sample_id: str) -> List[Dict[str, Any]]:
    """Parse vsearch merge output → merge_stats rows.

    Counts merged reads from the FASTA output to determine merge success rate.
    """
    rows: List[Dict[str, Any]] = []
    merged_count = 0
    for path in sorted(output_dir.glob("*_merged.fasta")):
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if line.startswith(">"):
                    merged_count += 1
    if merged_count > 0:
        rows.append(
            {
                "sample_id": sample_id,
                "merged_reads": merged_count,
                "tool": "vsearch",
                "stage": "merge_pairs",
                "source_file": str(output_dir),
            }
        )
    return rows


# ── vsearch derep parser ────────────────────────────────────────────────


def _parse_vsearch_derep(output_dir: Path, sample_id: str) -> List[Dict[str, Any]]:
    """Parse vsearch derep output → denoising_stats rows.

    Counts unique sequences from the dereplicated FASTA to determine how
    many reads collapsed into unique sequences.
    """
    rows: List[Dict[str, Any]] = []
    seq_count = 0
    total_size = 0
    for path in sorted(output_dir.glob("derep.fasta")):
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if line.startswith(">"):
                    seq_count += 1
                    # vsearch annotates with ;size=N
                    if "size=" in line:
                        size_part = line.split("size=")[-1].split(";")[0]
                        try:
                            total_size += int(size_part)
                        except ValueError:
                            total_size += 1
                    else:
                        total_size += 1
    if seq_count > 0:
        rows.append(
            {
                "sample_id": sample_id,
                "stage": "dereplication",
                "input_reads": total_size,
                "output_reads": seq_count,
                "tool": "vsearch",
                "source_file": str(output_dir),
            }
        )
    return rows


# ── vsearch denoise parser ───────────────────────────────────────────────


def _parse_vsearch_denoise(output_dir: Path, sample_id: str) -> List[Dict[str, Any]]:
    """Parse vsearch UNOISE3 output → denoising_stats rows.

    Counts ASVs from the denoised FASTA.
    """
    rows: List[Dict[str, Any]] = []
    asv_count = 0
    for path in sorted(output_dir.glob("asvs.fasta")):
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if line.startswith(">"):
                    asv_count += 1
    if asv_count > 0:
        rows.append(
            {
                "sample_id": sample_id,
                "stage": "denoising",
                "input_reads": 0,
                "output_reads": asv_count,
                "tool": "vsearch",
                "source_file": str(output_dir),
            }
        )
    return rows


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
                rows.append(
                    {
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
                    }
                )
    return rows


# ── Diversity parsers ───────────────────────────────────────────────────


def _parse_alpha_diversity(output_dir: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for path in sorted(output_dir.glob("alpha*.tsv")):
        try:
            with path.open("r", encoding="utf-8", newline="") as handle:
                reader = csv.DictReader(handle, delimiter="\t")
                if not reader.fieldnames:
                    continue
                for row in reader:
                    rows.append(
                        {
                            "sample_id": row.get("sample_id", ""),
                            "observed_features": row.get(
                                "observed_features", row.get("observed_otus", "")
                            ),
                            "shannon_entropy": row.get("shannon", row.get("shannon_entropy", "")),
                            "simpson_index": row.get("simpson", ""),
                            "faith_pd": row.get("faith_pd", ""),
                            "chao1": row.get("chao1", ""),
                            "tool": "diversity_metrics",
                            "source_file": str(path),
                        }
                    )
        except (OSError, csv.Error):
            continue
    return rows


def _parse_beta_diversity(output_dir: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    paths = list(output_dir.glob("beta*.tsv")) + list(output_dir.glob("*distance*.tsv"))
    for path in sorted(paths):
        try:
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
                    rows.append(
                        {
                            "comparison": f"{sample_a}_vs_{sample_b}",
                            "distance_metric": metric,
                            "sample_a": sample_a,
                            "sample_b": sample_b,
                            "distance": row.get("distance", ""),
                            "tool": "diversity_metrics",
                            "source_file": str(path),
                        }
                    )
        except (OSError, csv.Error):
            continue
    return rows
