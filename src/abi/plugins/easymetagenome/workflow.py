"""Loader and local P0 runner for the documented EasyMetagenome DAG format."""

from __future__ import annotations

import csv
import itertools
import json
import os
import shutil
import warnings
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Iterable, Mapping, Sequence

import yaml

from abi.results import completed_abi_result_outputs
from abi.runtimes.local import LocalRuntime

from .adapters import (
    DatabaseChecker,
    ManifestValidator,
    ReportCollector,
    SampleRecord,
)


class WorkflowDefinitionError(ValueError):
    """The workflow YAML is structurally invalid."""


def _namespace(value: Any) -> Any:
    if isinstance(value, Mapping):
        return SimpleNamespace(**{str(key): _namespace(item) for key, item in value.items()})
    if isinstance(value, list):
        return [_namespace(item) for item in value]
    return value


class _FormatContext(dict[str, Any]):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def _render(value: Any, context: Mapping[str, Any]) -> Any:
    if isinstance(value, str):
        return value.format_map(_FormatContext(context))
    if isinstance(value, list):
        return [_render(item, context) for item in value]
    if isinstance(value, Mapping):
        return {str(key): _render(item, context) for key, item in value.items()}
    return value


def _absolutize(value: Any, workdir: Path) -> Any:
    if not isinstance(value, str) or not value or value.startswith("{"):
        return value
    if value.startswith(("${", "~")) or "*" in value:
        return value
    path = Path(value)
    if path.is_absolute():
        return str(path)
    if value.startswith(("result/", "temp/", "seq/")):
        return str(workdir / path)
    return value


class P0Workflow:
    """Parse, expand, dry-run, and execute the document's list-style nodes."""

    required_node_fields = frozenset({"id", "tool", "stage", "inputs", "outputs", "checks"})

    def __init__(self, spec: Mapping[str, Any], source: Path | None = None) -> None:
        self.spec = dict(spec)
        self.source = source
        raw_nodes = self.spec.get("nodes")
        if isinstance(raw_nodes, Mapping):
            nodes = [{"id": node_id, **dict(data)} for node_id, data in raw_nodes.items()]
        elif isinstance(raw_nodes, list):
            nodes = [dict(item) for item in raw_nodes]
        else:
            raise WorkflowDefinitionError("Workflow requires a nodes list or mapping")
        self.nodes = nodes
        self._validate()

    @classmethod
    def from_yaml(cls, path: str | Path) -> "P0Workflow":
        source = Path(path)
        data = yaml.safe_load(source.read_text(encoding="utf-8")) or {}
        if not isinstance(data, Mapping):
            raise WorkflowDefinitionError("Workflow YAML must be a mapping")
        return cls(data, source)

    def _validate(self) -> None:
        ids: list[str] = []
        for node in self.nodes:
            # command_template is optional only for ABI internal nodes.
            required = self.required_node_fields - (
                {"checks"} if str(node.get("tool", "")).startswith("abi.internal.") else set()
            )
            missing = sorted(field for field in required if field not in node)
            if missing:
                raise WorkflowDefinitionError(
                    f"Node {node.get('id', '<unknown>')} is missing: {', '.join(missing)}"
                )
            ids.append(str(node["id"]))
        duplicates = sorted({item for item in ids if ids.count(item) > 1})
        if duplicates:
            raise WorkflowDefinitionError(f"Duplicate node ids: {', '.join(duplicates)}")
        known = set(ids)
        for node in self.nodes:
            unknown = set(node.get("depends_on", [])) - known
            if unknown:
                raise WorkflowDefinitionError(
                    f"Node {node['id']} has unknown dependencies: {sorted(unknown)}"
                )
        self.topological_nodes()  # cycle check

    def topological_nodes(self) -> list[dict[str, Any]]:
        remaining = {str(node["id"]): dict(node) for node in self.nodes}
        ordered: list[dict[str, Any]] = []
        completed: set[str] = set()
        while remaining:
            ready = [
                node_id
                for node_id, node in remaining.items()
                if set(node.get("depends_on", [])) <= completed
            ]
            if not ready:
                raise WorkflowDefinitionError(
                    f"Workflow contains a dependency cycle: {sorted(remaining)}"
                )
            for node_id in ready:
                ordered.append(remaining.pop(node_id))
                completed.add(node_id)
        return ordered

    @staticmethod
    def _iterations(
        node: Mapping[str, Any], samples: Sequence[SampleRecord]
    ) -> Iterable[dict[str, Any]]:
        mapping = node.get("map_over")
        if not mapping:
            yield {}
            return
        if mapping == "samples":
            for sample in samples:
                yield {"sample": sample.as_dict()}
            return
        if isinstance(mapping, Mapping):
            dimensions: list[tuple[str, Sequence[Any]]] = []
            for key, value in mapping.items():
                if value == "samples" or key == "samples":
                    dimensions.append(("sample", [sample.as_dict() for sample in samples]))
                else:
                    singular = str(key).removesuffix("s")
                    dimensions.append((singular, list(value)))
            for values in itertools.product(*(dimension[1] for dimension in dimensions)):
                yield {dimensions[index][0]: item for index, item in enumerate(values)}
            return
        raise WorkflowDefinitionError(f"Unsupported map_over in node {node['id']}")

    def plan(
        self,
        manifest: str | Path,
        workdir: str | Path,
        *,
        db_registry: str | Path | None = None,
        threads: int = 16,
        check_files: bool = True,
    ) -> list[dict[str, Any]]:
        samples = ManifestValidator.validate(manifest, check_files=check_files)
        root = Path(workdir).resolve()
        db_data: dict[str, Any] = {}
        if db_registry:
            db_data = yaml.safe_load(Path(db_registry).read_text(encoding="utf-8")) or {}
            path = str(db_data.get("path", ""))
            db_data = {"kraken2": {**db_data, "path": path}}
        records: list[dict[str, Any]] = []
        for node in self.topological_nodes():
            for iteration in self._iterations(node, samples):
                sample = iteration.get("sample")
                context: dict[str, Any] = {
                    "sample": _namespace(sample or {}),
                    "sample_id": (sample or {}).get("sample_id", "all"),
                    "tax_level": iteration.get("tax_level", ""),
                    "project": _namespace({"workdir": str(root)}),
                    "db": _namespace(db_data),
                    "inputs": _namespace(
                        {"manifest": str(Path(manifest).resolve()), "database_registry": db_data}
                    ),
                }
                inputs = _render(node.get("inputs", {}), context)
                outputs = _render(
                    node.get("outputs", {}), {**context, "inputs": _namespace(inputs)}
                )
                params = _render(
                    node.get("params", {}),
                    {**context, "inputs": _namespace(inputs), "outputs": _namespace(outputs)},
                )
                inputs = {key: _absolutize(value, root) for key, value in inputs.items()}
                outputs = {key: _absolutize(value, root) for key, value in outputs.items()}
                render_context = {
                    **context,
                    "inputs": _namespace(inputs),
                    "outputs": _namespace(outputs),
                    "params": _namespace({"threads": threads, **params}),
                }
                command_template = node.get("command_template")
                command = (
                    _render(command_template, render_context)
                    if command_template
                    else f"abi internal {node['id']}"
                )
                checks = []
                for item in node.get("checks", []):
                    if isinstance(item, Mapping) and item.get("exists"):
                        checks.append(_absolutize(_render(item["exists"], render_context), root))
                suffix = ""
                if sample:
                    suffix += f":{sample['sample_id']}"
                if iteration.get("tax_level"):
                    suffix += f":{iteration['tax_level']}"
                records.append(
                    {
                        "node": str(node["id"]) + suffix,
                        "node_id": str(node["id"]),
                        "tool": str(node["tool"]),
                        "command": str(command),
                        "inputs": inputs,
                        "outputs": outputs,
                        "checks": checks,
                        "depends_on": list(node.get("depends_on", [])),
                        "params": params,
                        "resources": dict(node.get("resources", {})),
                        "on_fail": dict(node.get("on_fail", {})),
                    }
                )
        return records

    def dry_run(self, *args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        kwargs.setdefault("check_files", True)
        return self.plan(*args, **kwargs)

    def run(
        self,
        manifest: str | Path,
        workdir: str | Path,
        *,
        db_registry: str | Path | None = None,
        threads: int = 16,
        resume: bool = True,
    ) -> dict[str, Any]:
        """Execute the documented P0 workflow through ABI's canonical runtime."""
        warnings.warn(
            "P0Workflow.run() is deprecated; use `abi run --type easymetagenome` instead",
            DeprecationWarning,
            stacklevel=2,
        )
        if db_registry is None:
            raise ValueError("db_registry is required for P0 execution")
        samples = ManifestValidator.validate(manifest)
        DatabaseChecker.require(db_registry)
        registry = yaml.safe_load(Path(db_registry).read_text(encoding="utf-8")) or {}
        root = Path(workdir).resolve()
        result_dir = root / "result"
        log_dir = root / "logs"

        from . import EasyMetagenomePlugin

        plugin = EasyMetagenomePlugin()
        config = plugin.load_config(
            overrides={
                "input": {"sample_sheet": str(Path(manifest).resolve())},
                "workflow": {"preset": "p0_taxonomy"},
                "resources": {
                    "host_db": _expand_registry_path(registry.get("host_db")),
                    "kraken2_db": _expand_registry_path(registry.get("path")),
                },
                "threads": threads,
                "outdir": str(result_dir),
                "log_dir": str(log_dir),
            }
        )
        plan = plugin.build_plan(config)
        outputs = (
            _matching_completed_outputs(result_dir, plan.to_dict(), config) if resume else None
        )
        resumed = outputs is not None
        if outputs is None:
            runtime_result = LocalRuntime(plugin).run(plan, config)
            outputs = runtime_result.outputs

        _write_legacy_output_aliases(result_dir)
        documented_plan = self.plan(
            manifest,
            root,
            db_registry=db_registry,
            threads=threads,
        )
        commands = _legacy_command_rows(
            Path(outputs["commands"]),
            documented_plan=documented_plan,
            resumed=resumed,
        )
        versions = _legacy_version_rows(Path(outputs["tool_versions"]))
        reports = ReportCollector.collect(root, samples, commands=commands, versions=versions)
        summary = json.loads(Path(outputs["summary"]).read_text(encoding="utf-8"))
        return {
            "status": summary["status"],
            "nodes": commands,
            "reports": reports,
            "abi_outputs": outputs,
        }


def _expand_registry_path(value: Any) -> str | None:
    if value in (None, ""):
        return None
    return str(Path(os.path.expandvars(str(value))).expanduser())


def _matching_completed_outputs(
    result_dir: Path,
    plan: Mapping[str, Any],
    config: Mapping[str, Any],
) -> dict[str, Path] | None:
    """Reuse a successful ABI result only when its resolved plan and config still match."""
    outputs = completed_abi_result_outputs(result_dir)
    if outputs is None:
        return None
    plan_path = outputs.get("plan")
    config_path = outputs.get("config")
    if plan_path is None or config_path is None:
        return None
    try:
        stored_plan = json.loads(plan_path.read_text(encoding="utf-8"))
        stored_config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except (OSError, json.JSONDecodeError, yaml.YAMLError):
        return None
    if stored_plan != dict(plan) or stored_config != dict(config):
        return None
    return outputs


def _legacy_command_rows(
    path: Path,
    *,
    documented_plan: Sequence[Mapping[str, Any]],
    resumed: bool,
) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    commands = []
    used_nodes: set[str] = set()
    for row in rows:
        command = dict(row)
        command["node"] = _documented_node_for_command(row, documented_plan, used_nodes)
        used_nodes.add(str(command["node"]))
        if resumed:
            command["status"] = "resumed"
        elif row.get("tool_id") != "internal":
            command["status"] = int(row.get("return_code") or 0)
        commands.append(command)
    return commands


def _documented_node_for_command(
    command: Mapping[str, str],
    documented_plan: Sequence[Mapping[str, Any]],
    used_nodes: set[str],
) -> str:
    step_id = str(command.get("step_id", ""))
    tool_id = str(command.get("tool_id", ""))
    if tool_id == "internal":
        for item in documented_plan:
            if item["node_id"] == step_id:
                return str(item["node"])
        return step_id

    candidates = [
        item
        for item in documented_plan
        if item["tool"] == tool_id and str(item["node"]) not in used_nodes
    ]
    sample_id = str(command.get("sample_id", ""))
    if sample_id:
        sample_candidates = [item for item in candidates if f":{sample_id}" in item["node"]]
        if sample_candidates:
            candidates = sample_candidates
    if tool_id == "bracken":
        rendered = str(command.get("command", ""))
        for level in ("P", "G", "S"):
            if f" -l {level} " in f" {rendered} ":
                level_candidates = [
                    item for item in candidates if item["node"].endswith(f":{level}")
                ]
                if level_candidates:
                    candidates = level_candidates
                break
    return str(candidates[0]["node"]) if candidates else step_id


def _legacy_version_rows(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    for row in rows:
        row["tool"] = row.get("tool_id", "")
    return rows


def _write_legacy_output_aliases(result_dir: Path) -> dict[str, Path]:
    """Preserve the documented P0 result paths during the ABI-runtime migration."""
    aliases = {
        result_dir / "00_input_validation/metadata.normalized.tsv": (
            result_dir / "metadata.normalized.tsv"
        ),
        result_dir / "00_input_validation/input_validation.json": (
            result_dir / "input_validation.json"
        ),
        result_dir / "04_summary/fastp_summary.tsv": result_dir / "qc/fastp.txt",
        result_dir / "04_summary/kneaddata_summary.tsv": result_dir / "qc/sum.txt",
        result_dir / "04_summary/bracken.P.tsv": result_dir / "kraken2/bracken.P.txt",
        result_dir / "04_summary/bracken.G.tsv": result_dir / "kraken2/bracken.G.txt",
        result_dir / "04_summary/bracken.S.tsv": result_dir / "kraken2/bracken.S.txt",
        result_dir / "04_summary/bracken.P.filtered.tsv": (
            result_dir / "kraken2/bracken.P.0.2.txt"
        ),
        result_dir / "04_summary/bracken.G.filtered.tsv": (
            result_dir / "kraken2/bracken.G.0.2.txt"
        ),
        result_dir / "04_summary/bracken.S.filtered.tsv": (
            result_dir / "kraken2/bracken.S.0.2.txt"
        ),
        result_dir / "05_statistics/alpha.tsv": result_dir / "kraken2/alpha.txt",
        result_dir / "05_statistics/beta.tsv": result_dir / "kraken2/beta.txt",
    }
    written: dict[str, Path] = {}
    for source, destination in aliases.items():
        if not source.is_file():
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        written[destination.name] = destination
    return written
