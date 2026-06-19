"""RNA-seq Gene Expression Quantification ABI Plugin.

Purpose / 目的
~~~~~~~~~~~~~~
Standard RNA-seq differential expression pipeline demonstrating the ABI
cross-plugin portability pattern.  Covers the complete workflow:

    fastp ──→ STAR ──→ featureCounts ──→ DESeq2
    (QC)      (alignment)   (quantification)   (diff. expression)

Compared to ``metatranscriptomics`` (3-tool demo), this plugin adds
DESeq2 for differential expression analysis, making it a complete
gene-level RNA-seq solution suitable for real biological studies.

Tool chain / 工具链
~~~~~~~~~~~~~~~~~~~
- **fastp**: adapter trimming and quality filtering
- **STAR**: spliced alignment to reference genome
- **featureCounts**: gene-level read counting
- **DESeq2**: normalisation and differential expression testing

Standard tables / 标准表格
~~~~~~~~~~~~~~~~~~~~~~~~~~
- ``gene_expression``: per-gene raw counts (from featureCounts)
- ``differential_expression``: DESeq2 results with log2FC, p-value, padj

Architecture / 架构
~~~~~~~~~~~~~~~~~~~
Follows the same ``ABIPlugin`` pattern as metatranscriptomics:
inline implementation, no ``_engine/`` sub-package, intentionally
simple and auditable.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional

from abi._shared import _clean, _parse_fastp, _parse_star, _resolve_path
from abi.config import PLUGIN_ROOT, PROJECT_ROOT, compact_overrides, deep_merge, load_yaml
from abi.report import write_plugin_report
from abi.schemas import ABIExecutionPlan, ABISample, ABISampleContext
from abi.tools import ToolRegistry


class RNASeqExpressionPlugin:
    """ABI plugin for standard RNA-seq differential expression analysis.

    Implements the ``ABIPlugin`` interface with a 4-tool chain:
    fastp (QC) → STAR (alignment) → featureCounts (quantification)
    → DESeq2 (differential expression).
    """

    plugin_id = "rnaseq_expression"
    display_name = "RNA-seq Gene Expression Quantification"
    description = (
        "Standard RNA-seq pipeline: QC (fastp) → alignment (STAR) → "
        "quantification (featureCounts) → differential expression (DESeq2)."
    )
    report_title = "RNA-seq Gene Expression ABI Report"

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
        # Stash for write_report() — ABIPlugin.write_report doesn't receive config.
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
            raise ValueError("rnaseq_expression requires input.sample_sheet")
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
        if tool_id == "fastp":
            return {"qc_summary": _parse_fastp(Path(output_dir), sample_id)}
        if tool_id in ("star", "hisat2"):
            return {"alignment_summary": _parse_star(Path(output_dir), sample_id)}
        # featurecounts is handled by TSVMapper above
        if tool_id == "deseq2":
            return {
                "differential_expression": _parse_deseq2(Path(output_dir), sample_id),
                "normalized_expression": _parse_deseq2_normalized(Path(output_dir), sample_id),
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
            raise ValueError(f"Missing rnaseq_expression config keys: {', '.join(missing)}")
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
                    condition="untreated",
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
                    platform=_clean(row.get("platform")) or "illumina",
                    group=_clean(row.get("group")) or _clean(row.get("condition")),
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


# ── featureCounts parser ─────────────────────────────────────────────────


# ── DESeq2 parser ───────────────────────────────────────────────────────


def _parse_deseq2(output_dir: Path, sample_id: str) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for path in sorted(output_dir.glob("*deseq2*.tsv")):
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle, delimiter="\t")
            if not reader.fieldnames:
                continue
            for row in reader:
                gene_id = row.get("gene_id") or row.get("Geneid") or row.get("")
                if not gene_id:
                    continue
                rows.append(
                    {
                        "gene_id": gene_id,
                        "base_mean": row.get("baseMean", ""),
                        "log2_fold_change": row.get("log2FoldChange", ""),
                        "lfc_se": row.get("lfcSE", ""),
                        "stat": row.get("stat", ""),
                        "pvalue": row.get("pvalue", ""),
                        "padj": row.get("padj", ""),
                        "comparison": row.get("comparison", ""),
                        "tool": "deseq2",
                        "source_file": str(path),
                    }
                )
    return rows


# ── fastp parser ─────────────────────────────────────────────────────────


# ── STAR parser ──────────────────────────────────────────────────────────


# ── DESeq2 normalized expression parser ──────────────────────────────────


def _parse_deseq2_normalized(output_dir: Path, sample_id: str) -> List[Dict[str, Any]]:
    """Parse DESeq2 normalized expression TSV → normalized_expression rows.

    The TSV has ``gene_id`` as the first column, followed by per-sample
    normalized count columns.  Each cell becomes one row in long format.
    """
    rows: List[Dict[str, Any]] = []
    for path in sorted(output_dir.glob("*normalized_expression*.tsv")):
        try:
            with path.open("r", encoding="utf-8", newline="") as handle:
                reader = csv.DictReader(handle, delimiter="\t")
                if not reader.fieldnames or len(reader.fieldnames) < 2:
                    continue
                sample_columns = [col for col in reader.fieldnames if col != "gene_id"]
                for row in reader:
                    gene_id = row.get("gene_id")
                    if not gene_id:
                        continue
                    for scol in sample_columns:
                        val = row.get(scol, "")
                        rows.append(
                            {
                                "sample_id": scol,
                                "gene_id": gene_id,
                                "normalized_count": val,
                                "normalization_method": "DESeq2_median_of_ratios",
                                "tool": "deseq2",
                                "source_file": str(path),
                            }
                        )
        except (OSError, csv.Error):
            continue
    return rows


# (``_clean``, ``_resolve_path``, ``_parse_fastp`` are imported from abi._shared)
