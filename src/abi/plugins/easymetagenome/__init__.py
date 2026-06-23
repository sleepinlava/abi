"""EasyMetagenome-inspired ABI-native P0 shotgun metagenomics plugin."""

from __future__ import annotations

import csv
import gzip
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional

from abi._shared import _execute_generic_dry_run, _parse_fastp, _resolve_path
from abi.config import PLUGIN_ROOT, PROJECT_ROOT, compact_overrides, deep_merge, load_yaml
from abi.report import write_plugin_report
from abi.schemas import ABIExecutionPlan, ABISample, ABISampleContext
from abi.tools import ToolRegistry

from .adapters import ManifestValidator
from .handlers import handlers as easymeta_handlers
from .workflow import P0Workflow

__all__ = ["EasyMetagenomePlugin", "ManifestValidator", "P0Workflow"]

_COMMON_NODES = [
    "validate_manifest",
    "seqkit_stat_raw",
    "fastp_qc",
    "kneaddata_host_removal",
    "fastp_summary",
    "kneaddata_summary",
]
_TAXONOMY_NODES = [
    "kraken2_classify",
    "bracken_phylum",
    "bracken_genus",
    "bracken_species",
    "bracken_merge",
    "taxonomy_filter",
    "taxonomy_diversity",
    "collect_report",
]
_FUNCTIONAL_NODES = [
    "concat_dehost_reads",
    "humann4_profile",
    "humann_join_genefamilies",
    "humann_renorm_genefamilies",
    "humann_regroup_ko",
    "humann_split_ko",
    "humann_join_pathabundance",
    "humann_renorm_pathabundance",
    "humann_split_pathabundance",
    "functional_report",
]
WORKFLOW_PRESETS = {
    "p0_taxonomy": _COMMON_NODES + _TAXONOMY_NODES,
    "p1_humann4": _COMMON_NODES + _FUNCTIONAL_NODES,
    "full_read_based": _COMMON_NODES + _TAXONOMY_NODES + _FUNCTIONAL_NODES,
}


class EasyMetagenomePlugin:
    plugin_id = "easymetagenome"
    display_name = "EasyMetagenome-style P0"
    description = "ABI-native fastp, KneadData, Kraken2, Bracken, diversity, and reporting DAG."
    report_title = "EasyMetagenome-style P0 ABI Report"

    @property
    def root(self) -> Path:
        return PLUGIN_ROOT / self.plugin_id

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
        workflow = dict(config.get("workflow", {}))
        preset = str(workflow.get("preset", "p0_taxonomy"))
        if preset not in WORKFLOW_PRESETS:
            raise ValueError(
                f"Unknown easymetagenome workflow preset {preset!r}; "
                f"choose one of {sorted(WORKFLOW_PRESETS)}"
            )
        workflow.setdefault("include_nodes", list(WORKFLOW_PRESETS[preset]))
        workflow["functional_enabled"] = preset in {"p1_humann4", "full_read_based"}
        workflow["taxonomy_enabled"] = preset in {"p0_taxonomy", "full_read_based"}
        config["workflow"] = workflow
        raw_input_config = config.get("input", {})
        if not isinstance(raw_input_config, Mapping) or not raw_input_config.get("sample_sheet"):
            raise ValueError("easymetagenome requires input.sample_sheet")
        input_config = dict(raw_input_config)
        input_config["sample_sheet"] = str(
            _resolve_path(input_config["sample_sheet"], base_dirs=[PROJECT_ROOT])
        )
        config["input"] = input_config
        if int(config.get("threads", 0)) < 1:
            raise ValueError("threads must be at least 1")
        config["humann_samples_dir"] = str(Path(str(config["outdir"])) / "04_function/sample")
        return config

    def build_sample_context(
        self, config: Mapping[str, Any], *, check_files: bool = True
    ) -> ABISampleContext:
        path = config["input"]["sample_sheet"]
        try:
            records = ManifestValidator.validate(path, check_files=check_files)
        except (FileNotFoundError, ValueError):
            if check_files:
                raise
            records = []
        if not records:
            samples = [
                ABISample(
                    sample_id="SAMPLE_NOT_CONFIGURED",
                    platform="illumina",
                    read1="READ1_NOT_CONFIGURED",
                    read2="READ2_NOT_CONFIGURED",
                )
            ]
        else:
            samples = [
                ABISample(
                    sample_id=record.sample_id,
                    platform="illumina",
                    read1=record.r1,
                    read2=record.r2,
                    group=record.group or None,
                )
                for record in records
            ]
        groups = {sample.group for sample in samples if sample.group}
        return ABISampleContext(
            samples=samples,
            multi_sample=len(samples) > 1,
            has_groups=len(groups) >= 2,
            enable_sample_analysis=len(samples) > 1,
        )

    def build_plan(
        self, config: Mapping[str, Any], *, check_files: bool = True
    ) -> ABIExecutionPlan:
        from abi.dag_planner import build_plan_from_dag

        return build_plan_from_dag(
            self.root / "pipeline_dag.yaml",
            config,
            self.build_sample_context(config, check_files=check_files),
        )

    def preflight(
        self,
        config: Mapping[str, Any],
        *,
        engine: str,
        check_runtime: bool = True,
    ) -> Mapping[str, Any]:
        del engine
        checks: list[dict[str, Any]] = []
        try:
            samples = ManifestValidator.validate(config["input"]["sample_sheet"])
            checks.append({"name": "manifest", "status": "pass", "sample_count": len(samples)})
        except (FileNotFoundError, ValueError) as exc:
            checks.append({"name": "manifest", "status": "fail", "message": str(exc)})
        resources = config.get("resources", {})
        workflow = config.get("workflow", {})
        taxonomy_enabled = (
            bool(workflow.get("taxonomy_enabled")) if isinstance(workflow, Mapping) else True
        )
        functional_enabled = (
            bool(workflow.get("functional_enabled")) if isinstance(workflow, Mapping) else False
        )
        required_resources = ["host_db"]
        if taxonomy_enabled:
            required_resources.append("kraken2_db")
        if functional_enabled:
            required_resources.extend(["humann_nucleotide_db", "humann_protein_db", "metaphlan_db"])
        for name in required_resources:
            value = resources.get(name) if isinstance(resources, Mapping) else None
            path = Path(str(value or ""))
            valid = bool(value) and "NOT_CONFIGURED" not in str(value) and path.exists()
            checks.append(
                {
                    "name": name,
                    "status": "pass" if valid else "fail",
                    "path": str(path),
                }
            )
        if check_runtime:
            taxonomy_tools = {"seqkit", "fastp", "kneaddata", "kraken2", "bracken"}
            functional_tools = {
                "seqkit",
                "fastp",
                "kneaddata",
                "humann4",
                "humann_join_tables",
                "humann_renorm_table",
                "humann_regroup_table",
                "humann_split_stratified_table",
            }
            selected_tools = (taxonomy_tools if taxonomy_enabled else set()) | (
                functional_tools if functional_enabled else set()
            )
            for result in self.registry().check_tools(config=config):
                if str(result.get("tool_id")) not in selected_tools:
                    continue
                installed = bool(result.get("installed"))
                resource_status = str(result.get("resource_status", "ok"))
                checks.append(
                    {
                        "name": str(result.get("tool_id", "tool")),
                        "status": (
                            "pass"
                            if installed and resource_status in {"ok", "not_required"}
                            else "fail"
                        ),
                        "details": result,
                    }
                )
        failures = [item for item in checks if item["status"] == "fail"]
        return {
            "plugin": self.plugin_id,
            "status": "fail" if failures else "pass",
            "checks": checks,
            "recommendations": [f"Fix failed preflight check: {item['name']}" for item in failures],
        }

    def internal_handlers(self):
        return easymeta_handlers()

    def registry(self) -> ToolRegistry:
        return ToolRegistry.from_path(self.root / "tool_registry.yaml")

    def execute_dry_run(self, plan: Any, config: Mapping[str, Any]) -> Dict[str, Path]:
        return _execute_generic_dry_run(self, plan, config)

    def table_schemas(self) -> Mapping[str, Iterable[str]]:
        return load_yaml(self.root / "standard_tables.yaml").get("tables", {})

    def parse_outputs(
        self, tool_id: str, output_dir: str | Path, sample_id: str
    ) -> Mapping[str, Iterable[Mapping[str, Any]]]:
        root = Path(output_dir)
        if tool_id == "seqkit":
            return {"qc_summary": _parse_seqkit(root, sample_id)}
        if tool_id == "fastp":
            return {"qc_summary": _parse_fastp(root, sample_id)}
        if tool_id == "kneaddata":
            return {"host_removal_summary": _parse_kneaddata(root, sample_id)}
        if tool_id == "kraken2":
            return {"taxonomy_abundance": _parse_kraken2(root, sample_id)}
        if tool_id == "bracken":
            return {"taxonomy_abundance": _parse_bracken(root, sample_id)}
        if tool_id in {
            "humann4",
            "humann_join_tables",
            "humann_renorm_table",
            "humann_regroup_table",
            "humann_split_stratified_table",
        }:
            return {"functional_abundance": _parse_humann(root, tool_id, sample_id)}
        return {}

    def write_report(self, plan: Any, result_dir: str | Path) -> Dict[str, Path]:
        return write_plugin_report(self, plan, result_dir)

    def documented_workflow(self) -> P0Workflow:
        return P0Workflow.from_yaml(self.root / "workflows" / "preprocessing_kraken2_bracken.yaml")


def _parse_seqkit(root: Path, sample_id: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted(root.glob("*.seqkit.tsv")):
        try:
            with path.open("r", encoding="utf-8", errors="replace", newline="") as handle:
                for record in csv.DictReader(handle, delimiter="\t"):
                    for metric, value in record.items():
                        if metric == "file":
                            continue
                        rows.append(
                            {
                                "sample_id": sample_id,
                                "tool": "seqkit",
                                "metric": metric,
                                "value": value or "",
                                "unit": "",
                                "source_file": str(path),
                            }
                        )
        except (OSError, csv.Error):
            continue
    return rows


def _fastq_record_count(path: Path) -> int:
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8", errors="replace") as handle:
        return sum(1 for _ in handle) // 4


def _parse_kneaddata(root: Path, sample_id: str) -> list[dict[str, Any]]:
    candidates = sorted(root.glob("*paired_1.fastq*"))
    if not candidates:
        return []
    path = candidates[0]
    try:
        count = _fastq_record_count(path)
    except OSError:
        return []
    return [
        {
            "sample_id": sample_id,
            "dehost_read_pairs": count,
            "tool": "kneaddata",
            "source_file": str(path),
        }
    ]


def _parse_kraken2(root: Path, sample_id: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted(root.glob("*.kraken2.report")):
        try:
            with path.open("r", encoding="utf-8", errors="replace") as handle:
                for line in handle:
                    fields = line.rstrip("\n").split("\t")
                    if len(fields) < 6:
                        continue
                    rows.append(
                        {
                            "sample_id": sample_id,
                            "name": fields[5].strip(),
                            "taxonomy_id": fields[4].strip(),
                            "taxonomy_level": fields[3].strip(),
                            "fraction_total_reads": fields[0].strip(),
                            "fraction_classified_reads": "",
                            "new_est_reads": "",
                            "kraken_assigned_reads": fields[2].strip(),
                            "added_reads": "",
                            "tool": "kraken2",
                            "source_file": str(path),
                        }
                    )
        except OSError:
            continue
    return rows


def _parse_bracken(root: Path, sample_id: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted(root.glob("*.brk")):
        try:
            with path.open("r", encoding="utf-8", errors="replace", newline="") as handle:
                for record in csv.DictReader(handle, delimiter="\t"):
                    rows.append(
                        {
                            "sample_id": sample_id,
                            "name": record.get("name", ""),
                            "taxonomy_id": record.get("taxonomy_id", ""),
                            "taxonomy_level": record.get("taxonomy_lvl", ""),
                            "fraction_total_reads": record.get("fraction_total_reads", ""),
                            "fraction_classified_reads": record.get(
                                "fraction_classified_reads", ""
                            ),
                            "new_est_reads": record.get("new_est_reads", ""),
                            "kraken_assigned_reads": record.get("kraken_assigned_reads", ""),
                            "added_reads": record.get("added_reads", ""),
                            "tool": "bracken",
                            "source_file": str(path),
                        }
                    )
        except (OSError, csv.Error):
            continue
    return rows


def _parse_humann(root: Path, tool_id: str, fallback_sample_id: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*.tsv")):
        try:
            with path.open("r", encoding="utf-8", errors="replace", newline="") as handle:
                reader = csv.reader(handle, delimiter="\t")
                header: list[str] | None = None
                for values in reader:
                    if not values:
                        continue
                    if values[0].startswith("#"):
                        if len(values) > 1:
                            header = values
                        continue
                    if header is None:
                        continue
                    feature_id = values[0]
                    feature_type = _humann_feature_type(path)
                    for column, value in zip(header[1:], values[1:]):
                        sample_id = column.rsplit("-RPKs", 1)[0].lstrip("#")
                        rows.append(
                            {
                                "sample_id": sample_id or fallback_sample_id,
                                "feature_type": feature_type,
                                "feature_id": feature_id,
                                "value": value,
                                "stratified": "|" in feature_id,
                                "tool": tool_id,
                                "source_file": str(path),
                            }
                        )
        except (OSError, csv.Error):
            continue
    return rows


def _humann_feature_type(path: Path) -> str:
    name = path.name.lower()
    if "pathabundance" in name:
        return "pathway"
    if "pathcoverage" in name:
        return "pathway_coverage"
    if "ko" in name:
        return "ko"
    return "gene_family"
