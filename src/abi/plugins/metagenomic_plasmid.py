"""AutoPlasm adapter plugin for the ABI prototype.

This plugin requires the 'autoplasm' package to be installed.
Install with: pip install abi-agent[autoplasm]

All autoplasm imports are lazy (inside methods) so the module can be
imported without autoplasm installed.  The registry layer in
``abi.plugins.__init__`` also catches ``ImportError`` for extra safety.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Mapping, Optional, cast


class MetagenomicPlasmidPlugin:
    plugin_id = "metagenomic_plasmid"
    display_name = "Metagenomic Plasmid Analysis"
    description = "AutoPlasm adapter using the existing plasmid-analysis planner and executor."
    report_title = "AutoPlasm ABI Report"

    def load_config(
        self,
        config_path: str | Path | None = None,
        *,
        profile: str | None = None,
        overrides: Optional[Mapping[str, Any]] = None,
    ) -> Dict[str, Any]:
        from autoplasm.config import load_config as load_autoplasm_config

        return cast(
            Dict[str, Any],
            load_autoplasm_config(config_path, profile=profile or "dry_run", overrides=overrides),
        )

    def build_sample_context(self, config: Mapping[str, Any], *, check_files: bool = True) -> Any:
        del check_files
        return None

    def build_plan(self, config: Mapping[str, Any], *, check_files: bool = True) -> Any:
        from autoplasm.planner import build_plan

        return build_plan(config, check_files=check_files)

    def registry(self):
        from autoplasm.skills.registry import ToolRegistry

        return ToolRegistry.from_path()

    def table_schemas(self) -> Mapping[str, list[str]]:
        from autoplasm.standard_tables import TABLE_SCHEMAS

        return cast(Mapping[str, list[str]], TABLE_SCHEMAS)

    def parse_outputs(
        self,
        tool_id: str,
        output_dir: str | Path,
        sample_id: str,
    ) -> Mapping[str, Any]:
        from autoplasm.parsers import parse_standard_outputs

        return cast(Mapping[str, Any], parse_standard_outputs(tool_id, output_dir, sample_id))

    def execute_dry_run(self, plan: Any, config: Mapping[str, Any]) -> Dict[str, Path]:
        from autoplasm.logger import RunLogger
        from autoplasm.pipeline import PipelineExecutor

        logger = RunLogger(str(config["log_dir"]))
        executor = PipelineExecutor(self.registry(), logger, mock_tools=True)
        return cast(Dict[str, Path], executor.dry_run(plan, config))

    def write_report(self, plan: Any, result_dir: str | Path) -> Dict[str, Path]:
        from autoplasm.report.html import write_html_report
        from autoplasm.report.markdown import write_markdown_report
        from autoplasm.standard_tables import summarize_standard_tables

        if isinstance(plan, Mapping):
            plan = _plan_from_dict(plan)
        root = Path(result_dir)
        tables_dir = root / "tables"
        provenance_dir = root / "provenance"
        report_path = write_markdown_report(
            plan,
            root / "report",
            tables_dir=tables_dir,
            provenance_dir=provenance_dir,
            dry_run=False,
        )
        report_html_path = write_html_report(
            plan,
            root / "report",
            tables_dir=tables_dir,
            provenance_dir=provenance_dir,
            dry_run=False,
        )
        summarize_standard_tables(tables_dir)
        return {"report": report_path, "report_html": report_html_path}


def _plan_from_dict(data: Mapping[str, Any]) -> Any:
    from autoplasm.schemas import ExecutionPlan, PlanStep, SampleContext, SampleInput

    samples = [SampleInput(**sample) for sample in data.get("samples", [])]
    context_data = data.get("sample_context", {})
    if not isinstance(context_data, Mapping):
        context_data = {}
    sample_context = SampleContext(
        samples=samples,
        multi_sample=bool(context_data.get("multi_sample", len(samples) > 1)),
        has_groups=bool(context_data.get("has_groups", False)),
        enable_sample_analysis=bool(context_data.get("enable_sample_analysis", False)),
        enable_differential_abundance=bool(
            context_data.get("enable_differential_abundance", False)
        ),
    )
    return ExecutionPlan(
        project_name=str(data.get("project_name", "autoplasm_project")),
        mode=str(data.get("mode", "auto")),
        threads=int(data.get("threads", 1)),
        outdir=str(data.get("outdir", "")),
        log_dir=str(data.get("log_dir", "log")),
        samples=samples,
        steps=[PlanStep(**step) for step in data.get("steps", [])],
        sample_context=sample_context,
        selected_tools=[str(tool) for tool in data.get("selected_tools", [])],
        skipped_steps=[PlanStep(**step) for step in data.get("skipped_steps", [])],
        provenance_dir=data.get("provenance_dir"),
    )
