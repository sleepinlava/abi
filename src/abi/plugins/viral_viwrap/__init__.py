"""ABI managed external-CLI plugin for ViWrap 1.3.1."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional, Sequence

from abi._shared import _execute_generic_dry_run, _resolve_path
from abi.config import PLUGIN_ROOT, PROJECT_ROOT, compact_overrides, deep_merge, load_yaml
from abi.report import write_plugin_report
from abi.schemas import ABIExecutionPlan, ABISample, ABISampleContext
from abi.tools import GenericCommandSkill, ToolRegistry
from abi.workflow import WorkflowCatalog

from .checker import check_environment
from .command_builder import build_viwrap_command
from .handlers import handlers as viwrap_handlers
from .parser import parse_table_for_abi
from .runner import run_viwrap

__all__ = [
    "ViralViWrapPlugin",
    "build_viwrap_command",
    "check_environment",
    "run_viwrap",
]


class _ViWrapToolSkill(GenericCommandSkill):
    """Use the typed builder so optional reads/coverage flags remain correct."""

    def build_command(self, params: Dict[str, Any]) -> list[str]:
        config = dict(params)
        config["out_dir"] = params.get("output_dir")
        conda_env_dir = Path(str(params.get("conda_env_dir", "")))
        shared_executable = conda_env_dir / "ViWrap" / "bin" / "ViWrap"
        config["executable"] = str(shared_executable) if conda_env_dir else self.executable
        return build_viwrap_command(config)


class _ViWrapToolRegistry(ToolRegistry):
    def create(self, tool_id: str, *, mock_tools: bool = False) -> GenericCommandSkill:
        if tool_id != "viwrap":
            return super().create(tool_id, mock_tools=mock_tools)
        metadata = dict(self.get(tool_id))
        metadata["mock_tools"] = mock_tools
        return _ViWrapToolSkill(metadata)


class ViralViWrapPlugin:
    """Expose ViWrap as one managed, transport-neutral ABI workflow."""

    plugin_id = "viral_viwrap"
    display_name = "ViWrap Viral Metagenomics"
    description = "Managed ViWrap viral identification, binning, taxonomy, QC, and hosts."
    report_title = "ViWrap Viral Metagenomics ABI Report"

    @property
    def root(self) -> Path:
        return PLUGIN_ROOT / self.plugin_id

    def load_config(
        self,
        config_path: str | Path | None = None,
        *,
        profile: str | None = None,
        db_profile: str | None = None,
        overrides: Optional[Mapping[str, Any]] = None,
    ) -> Dict[str, Any]:
        del profile
        del db_profile
        config = load_yaml(self.root / "config_default.yaml")
        if config_path:
            config = deep_merge(config, load_yaml(config_path))
        config = deep_merge(config, compact_overrides(overrides))
        raw_workflow = config.get("workflow", {})
        if not isinstance(raw_workflow, Mapping):
            raise ValueError("viral_viwrap workflow must be a mapping")
        workflow = dict(raw_workflow)
        unknown_workflow_keys = sorted(set(workflow) - {"preset"})
        if unknown_workflow_keys:
            raise ValueError(
                "Unknown viral_viwrap workflow field(s): " + ", ".join(unknown_workflow_keys)
            )
        preset = str(workflow.get("preset", "viwrap_compat"))
        WorkflowCatalog.for_plugin(self.plugin_id).resolve(preset)
        workflow["preset"] = preset
        config["workflow"] = workflow
        nested = config.get("input", {})
        if isinstance(nested, Mapping):
            for key in (
                "input_metagenome",
                "input_reads",
                "input_cov",
                "input_sample2read_info",
            ):
                if config.get(key) is None and nested.get(key) is not None:
                    config[key] = nested[key]
        for key in ("db_dir", "conda_env_dir"):
            resources = config.get("resources", {})
            if (
                config.get(key) is None
                and isinstance(resources, Mapping)
                and resources.get(key) is not None
            ):
                config[key] = resources[key]
        config["out_dir"] = config.get("out_dir") or config.get("outdir")
        config["input_metagenome"] = str(
            _resolve_path(config["input_metagenome"], base_dirs=[PROJECT_ROOT])
        )
        reads = config.get("input_reads") or []
        if isinstance(reads, (str, bytes)):
            reads = [reads]
        config["input_reads"] = [
            str(_resolve_path(path, base_dirs=[PROJECT_ROOT])) for path in reads
        ]
        if config["input_reads"]:
            for key in ("input_cov", "input_sample2read_info"):
                value = str(config.get(key) or "")
                if "NOT_CONFIGURED" in value:
                    config.pop(key, None)
        resolved_input = dict(config.get("input", {}))
        for key in (
            "input_metagenome",
            "input_reads",
            "input_cov",
            "input_sample2read_info",
        ):
            if key in config:
                resolved_input[key] = config[key]
            else:
                resolved_input.pop(key, None)
        config["input"] = resolved_input
        resolved_resources = dict(config.get("resources", {}))
        resolved_resources.update(
            {"db_dir": config["db_dir"], "conda_env_dir": config["conda_env_dir"]}
        )
        config["resources"] = resolved_resources
        config["executable"] = str(Path(str(config["conda_env_dir"])) / "ViWrap/bin/ViWrap")
        build_viwrap_command(config)
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
        from abi.resources import _setup_manual_resource_bundle

        return _setup_manual_resource_bundle(
            self.plugin_id,
            config,
            resource_ids=resource_ids,
            dry_run=dry_run,
            mock=mock,
        )

    def build_sample_context(
        self, config: Mapping[str, Any], *, check_files: bool = True
    ) -> ABISampleContext:
        assembly = Path(str(config["input_metagenome"]))
        if check_files and (not assembly.is_file() or assembly.stat().st_size == 0):
            raise ValueError(f"Input metagenome does not exist or is empty: {assembly}")
        sample_id = str(config.get("sample_id") or assembly.name.split(".")[0])
        sample = ABISample(sample_id=sample_id, platform="assembly", assembly=str(assembly))
        return ABISampleContext(samples=[sample], multi_sample=False, has_groups=False)

    def build_plan(
        self, config: Mapping[str, Any], *, check_files: bool = True
    ) -> ABIExecutionPlan:
        from abi.dag_planner import build_plan_from_dag

        plan = build_plan_from_dag(
            self.root / "pipeline_dag.yaml",
            config,
            self.build_sample_context(config, check_files=check_files),
        )
        viwrap_output = str(config["out_dir"])
        for step in plan.steps:
            if step.tool_id == "viwrap":
                step.outputs["output_dir"] = viwrap_output
                contract = step.params.get("_contract", {})
                contract_outputs = contract.get("outputs", {})
                if "output_dir" in contract_outputs:
                    contract_outputs["output_dir"]["path"] = viwrap_output
            elif step.step_name == "parse" and "output_dir" in step.inputs:
                step.inputs["output_dir"] = viwrap_output
        return plan

    def preflight(
        self,
        config: Mapping[str, Any],
        *,
        engine: str,
        check_runtime: bool = True,
    ) -> Mapping[str, Any]:
        del engine
        return check_environment(config, check_runtime=check_runtime)

    def internal_handlers(self):
        return viwrap_handlers()

    def registry(self) -> ToolRegistry:
        return _ViWrapToolRegistry.from_path(self.root / "tool_registry.yaml")

    def execute_dry_run(self, plan: Any, config: Mapping[str, Any]) -> Dict[str, Path]:
        return _execute_generic_dry_run(self, plan, config)

    def table_schemas(self) -> Mapping[str, Iterable[str]]:
        return load_yaml(self.root / "standard_tables.yaml").get("tables", {})

    def parse_outputs(
        self, tool_id: str, output_dir: str | Path, sample_id: str
    ) -> Mapping[str, Iterable[Mapping[str, Any]]]:
        if tool_id != "viwrap":
            return {}
        return {
            name: parse_table_for_abi(output_dir, name, sample_id)
            for name in (
                "virus_summary",
                "viral_taxonomy",
                "viral_hosts",
                "viral_abundance_normalized",
            )
        }

    def write_report(self, plan: Any, result_dir: str | Path) -> Dict[str, Path]:
        return write_plugin_report(self, plan, result_dir)
