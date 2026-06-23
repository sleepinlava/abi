"""WGS Bacterial Genome Analysis ABI Plugin.

Purpose / 目的
~~~~~~~~~~~~~~
Clinical/food/environmental bacterial isolate analysis pipeline:

    fastp → SPAdes → Prokka → MLST → AMRFinderPlus
    (QC)    (assembly)  (annotation)  (typing)  (AMR profiling)
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

from abi._shared import (
    _execute_generic_dry_run,
    _offline_sample_context,
    _parse_fastp,
    _parse_sample_sheet_tabular,
    _resolve_path,
)
from abi.config import PLUGIN_ROOT, PROJECT_ROOT, compact_overrides, deep_merge, load_yaml
from abi.report import write_plugin_report
from abi.schemas import ABIExecutionPlan, ABISample, ABISampleContext
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

    @property
    def _tsv_mapper(self):
        if not hasattr(self, "_tsv_mapper_cache"):
            from abi.tsv_mapping import TSVMapper

            self._tsv_mapper_cache = TSVMapper.from_yaml(self.root / "parsers.yaml")
        return self._tsv_mapper_cache

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

    def check_resources(
        self,
        config: Mapping[str, Any],
        *,
        resource_ids: Optional[Sequence[str]] = None,
    ) -> list[dict[str, Any]]:
        from abi.resources import _check_generic_resources

        return _check_generic_resources(self.plugin_id, config, resource_ids=resource_ids)

    def setup_resources(
        self,
        config: Mapping[str, Any],
        *,
        resource_ids: Optional[Sequence[str]] = None,
        dry_run: bool = False,
        mock: bool = False,
    ) -> list[dict[str, Any]]:
        from abi.resources import _setup_wgs_bacteria

        return _setup_wgs_bacteria(
            config,
            resource_ids=resource_ids,
            dry_run=dry_run,
            mock=mock,
        )

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
        from abi.dag_planner import build_plan_from_dag

        return build_plan_from_dag(self.root / "pipeline_dag.yaml", config, context)

    def registry(self) -> ToolRegistry:
        return ToolRegistry.from_path(self.root / "tool_registry.yaml")

    def execute_dry_run(self, plan: Any, config: Mapping[str, Any]) -> Dict[str, Path]:
        return _execute_generic_dry_run(self, plan, config)

    def table_schemas(self) -> Mapping[str, Any]:
        data = load_yaml(self.root / "standard_tables.yaml")
        return data.get("tables", {})

    def parse_outputs(
        self, tool_id: str, output_dir: str | Path, sample_id: str
    ) -> Mapping[str, Iterable[Mapping[str, Any]]]:
        # Try declarative TSV mapper first
        if self._tsv_mapper.has_parser(tool_id):
            rows = self._tsv_mapper.parse(tool_id, output_dir, sample_id=sample_id)
            if rows:
                target = self._tsv_mapper.get_target_table(tool_id)
                return {target: rows} if target else {}
        # Fall back to hand-written parsers
        if tool_id == "fastp":
            return {"qc_summary": _parse_fastp(Path(output_dir), sample_id)}
        if tool_id == "spades":
            return {"genome_assembly_stats": _parse_spades(Path(output_dir), sample_id)}
        if tool_id == "prokka":
            return {"genome_annotation": _parse_prokka(Path(output_dir), sample_id)}
        # mlst and amrfinderplus are handled by TSVMapper above
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
    if not ss.exists():
        if check_files:
            raise ValueError(f"Sample sheet does not exist: {ss}")
        return _offline_sample_context()
    rows = _parse_sample_sheet_tabular(
        ss,
        check_files=check_files,
        base_dirs=[PROJECT_ROOT],
    )
    samples = [
        ABISample(
            sample_id=str(row["sample_id"]),
            platform=str(row.get("platform") or "illumina"),
            group=row.get("group"),
            read1=str(row["read1"]),
            read2=str(row["read2"]),
            condition=row.get("condition"),
        )
        for row in rows
    ]
    groups = {s.group for s in samples if s.group}
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
        coverage = _compute_spades_coverage(path)
        rows.append(
            {
                "sample_id": sample_id,
                "total_length": total,
                "num_contigs": len(lengths),
                "n50": n50,
                "max_contig_length": max(lengths),
                "gc_content": round(gc, 2) if gc is not None else "",
                "coverage": round(coverage, 2) if coverage is not None else "",
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


def _compute_spades_coverage(path: Path) -> Optional[float]:
    """Return length-weighted coverage encoded in SPAdes FASTA headers."""
    weighted_coverage = 0.0
    total_length = 0
    current_coverage: float | None = None
    current_length = 0

    def add_record() -> None:
        nonlocal weighted_coverage, total_length
        if current_coverage is not None and current_length > 0:
            weighted_coverage += current_coverage * current_length
            total_length += current_length

    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line.startswith(">"):
                add_record()
                match = re.search(r"(?:^|_)cov_([0-9]+(?:\.[0-9]+)?)", line)
                current_coverage = float(match.group(1)) if match else None
                current_length = 0
            else:
                current_length += len(line)
    add_record()
    return weighted_coverage / total_length if total_length else None


def _parse_gff_attributes(attr_string: str) -> Dict[str, str]:
    """Parse GFF3 column-9 attributes into a key→value dict."""
    result: Dict[str, str] = {}
    for pair in attr_string.split(";"):
        pair = pair.strip()
        if "=" in pair:
            key, _, value = pair.partition("=")
            result[key.strip()] = value.strip()
    return result
