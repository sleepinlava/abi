"""EasyMetagenome-inspired ABI-native P0 shotgun metagenomics plugin."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional

from abi._shared import _execute_generic_dry_run, _parse_fastp, _resolve_path
from abi.config import PLUGIN_ROOT, PROJECT_ROOT, compact_overrides, deep_merge, load_yaml
from abi.report import write_plugin_report
from abi.schemas import ABIExecutionPlan, ABISample, ABISampleContext
from abi.tools import ToolRegistry

from .adapters import ManifestValidator
from .workflow import P0Workflow

__all__ = ["EasyMetagenomePlugin", "ManifestValidator", "P0Workflow"]


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
        if tool_id == "fastp":
            return {"qc_summary": _parse_fastp(root, sample_id)}
        if tool_id == "kneaddata":
            return {"host_removal_summary": _read_tabular(root, "*.log", sample_id)}
        if tool_id == "bracken":
            return {"taxonomy_abundance": _read_tabular(root, "*.brk", sample_id)}
        return {}

    def write_report(self, plan: Any, result_dir: str | Path) -> Dict[str, Path]:
        return write_plugin_report(self, plan, result_dir)

    def documented_workflow(self) -> P0Workflow:
        return P0Workflow.from_yaml(self.root / "workflows" / "preprocessing_kraken2_bracken.yaml")


def _read_tabular(root: Path, pattern: str, sample_id: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for path in root.glob(pattern):
        try:
            with path.open("r", encoding="utf-8", errors="replace", newline="") as handle:
                for row in csv.DictReader(handle, delimiter="\t"):
                    rows.append(
                        {
                            "sample_id": sample_id,
                            **{str(key): str(value or "") for key, value in row.items()},
                        }
                    )
        except (OSError, csv.Error):
            continue
    return rows
