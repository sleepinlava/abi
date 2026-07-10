"""Export ABI execution plans to Nextflow DSL2."""

from __future__ import annotations

import os
import re
import shlex
from pathlib import Path
from typing import Any, Dict, Mapping

from abi.config import PROJECT_ROOT
from abi.dag import ABIDAG, StepBinding, infer_dag
from abi.errors import ToolError
from abi.internal import internal_handler_spec
from abi.tools import ToolRegistry, _disk_to_nextflow, _memory_to_nextflow


class NextflowExporter:
    """Render an ABI execution plan as a Nextflow DSL2 workflow."""

    def export(
        self,
        plan: Any,
        config: Mapping[str, Any],
        registry: ToolRegistry,
        *,
        smoke: bool = False,
        project_root: str | Path | None = None,
        mamba_root: str | Path | None = None,
        dag: ABIDAG | None = None,
    ) -> str:
        """Generate a complete Nextflow DSL2 script."""
        root = Path(project_root or PROJECT_ROOT).resolve()
        mamba = Path(mamba_root or root / ".mamba").resolve()
        abi_dag = dag or infer_dag(
            getattr(plan, "steps", []),
            project_root=root,
            sequential_fallback=True,
        )
        # Fail-fast: internal steps with external downstream dependents
        # cannot be exported — Nextflow cannot execute Python handlers.
        # 快速失败：有外部下游依赖的内部步骤无法导出 —
        # Nextflow 无法执行 Python 处理器。
        self._check_internal_dependencies(abi_dag)
        sections = [
            self._header(plan, smoke=smoke),
            self._params_block(plan, config, project_root=root, mamba_root=mamba),
            self._process_definitions(
                abi_dag,
                registry,
                smoke=smoke,
                project_root=root,
                mamba_root=mamba,
            ),
            self._workflow_block(abi_dag),
        ]
        return "\n\n".join(section for section in sections if section).rstrip() + "\n"

    def write(
        self,
        plan: Any,
        config: Mapping[str, Any],
        registry: ToolRegistry,
        output_path: str | Path,
        *,
        smoke: bool = False,
        project_root: str | Path | None = None,
        mamba_root: str | Path | None = None,
        dag: ABIDAG | None = None,
    ) -> Path:
        """Write the generated Nextflow DSL2 script to disk."""
        path = Path(output_path)
        if path.exists():
            raise ToolError(
                f"Nextflow script already exists and would be overwritten: {path}. "
                f"Remove it manually or specify a different output path."
            )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            self.export(
                plan,
                config,
                registry,
                smoke=smoke,
                project_root=project_root,
                mamba_root=mamba_root,
                dag=dag,
            ),
            encoding="utf-8",
        )
        return path

    def command_for_step(
        self,
        step: Any,
        registry: ToolRegistry,
        *,
        smoke: bool = False,
        project_root: str | Path | None = None,
    ) -> str:
        """Return the displayed shell command for one ABI step."""
        if smoke:
            return f"abi-nextflow-smoke --step-id {shlex.quote(str(getattr(step, 'step_id', '')))}"
        root = Path(project_root or PROJECT_ROOT).resolve()
        return _command_text(step, registry, project_root=root)

    @staticmethod
    def _check_internal_dependencies(dag: ABIDAG) -> None:
        """Raise :exc:`ToolError` if any **driver**-scoped internal step would
        need a Nextflow process.

        Worker-scoped handlers are now supported by C09 — they generate
        Nextflow processes that call ``abi run-step``.  Driver-scoped
        handlers run on the control node before Nextflow starts; if a
        driver would be needed inside the workflow (e.g., it has upstream
        dependencies), the export is blocked.
        """
        # Build reverse dependency map: step_id → list of consumer step_ids
        reverse_deps: dict[str, list[str]] = {}
        for step_id, deps in dag.edges.items():
            for dep in deps:
                reverse_deps.setdefault(dep, []).append(step_id)

        affected: list[str] = []
        for binding in dag.bindings:
            tool_id = str(getattr(binding.step, "tool_id", ""))
            if tool_id != "internal":
                continue
            _handler_id, scope = internal_handler_spec(binding.step)
            if scope == "worker":
                # Supported — will generate a Nextflow process.
                continue
            # Driver-scoped handlers run before submission.  If they have
            # upstream dependencies, those dependencies must also be drivers
            # or pre-existing on disk — otherwise the export is unsupported.
            upstream = dag.edges.get(binding.step.step_id, [])
            if not upstream:
                # No upstream deps → driver runs fine before Nextflow.
                continue
            upstream_tool_ids = {
                uid: str(getattr(dag.binding_for(uid).step, "tool_id", "")) for uid in upstream
            }
            non_internal_upstream = {
                uid: tid for uid, tid in upstream_tool_ids.items() if tid != "internal"
            }
            if non_internal_upstream:
                step_id = str(getattr(binding.step, "step_id", "?"))
                handler_id = _handler_id or "?"
                affected.append(
                    f"  Driver-scoped handler {step_id} ({handler_id!r}) has "
                    f"non-internal upstream step(s) that cannot be satisfied "
                    f"before Nextflow starts: "
                    + ", ".join(f"{uid}({tid})" for uid, tid in non_internal_upstream.items())
                )

        if affected:
            raise ToolError(
                "Nextflow export blocked: driver-scoped internal handler steps "
                "with external upstream dependencies cannot be exported.\n"
                + "\n".join(affected)
                + "\n\nRun the workflow with the local (LSF/HPC) runtime "
                "or refactor the DAG to move these steps before Nextflow."
            )

    def _header(self, plan: Any, *, smoke: bool) -> str:
        analysis_type = getattr(plan, "analysis_type", "")
        project_name = getattr(plan, "project_name", "")
        mode = "smoke" if smoke else "real"
        return "\n".join(
            [
                "// Generated by ABI NextflowExporter.",
                f"// Project: {project_name}",
                f"// Analysis type: {analysis_type}",
                f"// Export mode: {mode}",
                "nextflow.enable.dsl=2",
            ]
        )

    def _params_block(
        self,
        plan: Any,
        config: Mapping[str, Any],
        *,
        project_root: Path,
        mamba_root: Path,
    ) -> str:
        params: Dict[str, Any] = {
            "project_name": getattr(plan, "project_name", ""),
            "analysis_type": getattr(plan, "analysis_type", ""),
            "threads": getattr(plan, "threads", 1),
            "outdir": getattr(plan, "outdir", ""),
            "log_dir": getattr(plan, "log_dir", ""),
            "project_root": str(project_root),
            "mamba_root": str(mamba_root),
        }
        for key, value in _flatten_scalars(config).items():
            params.setdefault(key, value)
        lines = [
            f"params.{key} = {_groovy_literal(value)}" for key, value in sorted(params.items())
        ]
        return "\n".join(lines)

    def _process_definitions(
        self,
        dag: ABIDAG,
        registry: ToolRegistry,
        *,
        smoke: bool,
        project_root: Path,
        mamba_root: Path,
    ) -> str:
        processes = []
        for step_id in dag.topological_order:
            binding = dag.binding_for(step_id)
            tool_id = str(getattr(binding.step, "tool_id", ""))
            if tool_id == "internal":
                _handler_id, scope = internal_handler_spec(binding.step)
                if scope == "driver":
                    # Driver handlers run on the control node before
                    # Nextflow starts — they have no process.
                    continue
                # Worker-scoped internal handler → generate a Nextflow
                # process that calls abi run-step (C09).
                processes.append(
                    self._internal_worker_process(
                        binding,
                        handler_id=_handler_id,
                        smoke=smoke,
                        project_root=project_root,
                        mamba_root=mamba_root,
                    )
                )
                continue
            processes.append(
                self._step_to_process(
                    binding,
                    registry,
                    smoke=smoke,
                    project_root=project_root,
                    mamba_root=mamba_root,
                )
            )
        return "\n\n".join(processes)

    def _step_to_process(
        self,
        binding: StepBinding,
        registry: ToolRegistry,
        *,
        smoke: bool,
        project_root: Path,
        mamba_root: Path,
    ) -> str:
        step = binding.step
        process_name = binding.process_name
        command = (
            _smoke_command_text(step, project_root=project_root)
            if smoke
            else _command_text(step, registry, project_root=project_root)
        )
        setup_lines = _output_setup_lines(getattr(step, "outputs", {}), project_root=project_root)
        env_lines = [] if smoke else _tool_env_lines(step, registry, mamba_root=mamba_root)
        marker = f"__ABI_STEP_DONE_{_shell_token(str(getattr(step, 'step_id', process_name)))}__"
        script_lines = [
            "set -euo pipefail",
            *env_lines,
            *setup_lines,
            command,
            f"echo {shlex.quote(marker)}",
        ]
        script = "\n".join(f"    {line}" for line in script_lines if line)
        # Resource and container directives / 资源和容器指令
        resource_dirs = self._resource_directive_lines(binding, registry)
        container_dir = self._container_directive_line(binding, registry)
        if container_dir:
            resource_dirs.append(container_dir)
        return f"""process {process_name} {{
    tag {_groovy_literal(str(getattr(step, "step_id", process_name)))}
    cpus params.threads
    errorStrategy 'terminate'
{chr(10).join(resource_dirs)}
    input:
    val abi_trigger

    output:
    stdout

    script:
    '''
{script}
    '''
}}"""

    def _internal_worker_process(
        self,
        binding: StepBinding,
        *,
        handler_id: str,
        smoke: bool,
        project_root: Path,
        mamba_root: Path,
    ) -> str:
        """Generate a Nextflow process for a worker-scoped internal handler.

        The process writes a step payload, invokes ``abi run-step``, and
        emits the result JSON as stdout.  This reuses the existing step
        runner and CLI path so there is exactly one execution path.
        """
        step = binding.step
        process_name = binding.process_name
        step_id = str(getattr(step, "step_id", process_name))
        outdir = getattr(step, "outputs", {}).get("output_dir", ".abi-work")

        if smoke:
            cmd = "abi-nextflow-smoke --step-id " + step_id
            payload_section = ""
        else:
            # Inline the payload as a heredoc so the worker can reconstruct
            # the step without relying on a shared filesystem.
            import json

            payload = {
                "handler_id": handler_id,
                "step_id": step_id,
                "category": str(getattr(step, "category", "")),
                "sample_id": getattr(step, "sample_id", None),
                "outdir": str(outdir),
                "provenance_dir": str(outdir) + "/provenance",
                "tables_dir": str(outdir) + "/tables",
            }
            payload_json = json.dumps(payload, indent=2)
            escaped = payload_json.replace("\\", "\\\\").replace("'", "\\'")
            payload_section = (
                f"echo '{escaped}' > .abi_payload.json\n"
            )
            cmd = "abi run-step --payload-file .abi_payload.json"

        marker = f"__ABI_STEP_DONE_{_shell_token(step_id)}__"
        script_lines = [
            "set -euo pipefail",
            f"mkdir -p {shlex.quote(str(outdir))}",
            f"mkdir -p {shlex.quote(str(outdir))}/provenance/step_logs",
            payload_section,
            cmd,
            f"echo {shlex.quote(marker)}",
        ]
        script = "\n".join(f"    {line}" for line in script_lines if line)

        return f"""process {process_name} {{
    tag {_groovy_literal(step_id)}
    cpus 1
    errorStrategy 'terminate'

    input:
    val abi_trigger

    output:
    stdout

    script:
    '''
{script}
    '''
}}"""

    def _resource_directive_lines(
        self,
        binding: StepBinding,
        registry: ToolRegistry,
    ) -> list[str]:
        """Render Nextflow process directive lines for resource requests.

        Uses the sentinel-based ``resolve_resources_v2`` (C06) so that
        explicit overrides (e.g. ``cpu=1``) are preserved even when they
        happen to equal the default value.
        / 从工具合同读取 resources 块并转为 Nextflow 指令。
        """
        from abi.execution_policy import resolve_resources_v2
        from abi.tools import ResourceSpec

        step = binding.step
        tool_id = getattr(step, "tool_id", "")
        meta = registry.get(tool_id) if tool_id else {}
        spec = resolve_resources_v2(tool_id, meta)

        # Only emit non-default values / 只输出非默认值
        lines: list[str] = []
        defaults = ResourceSpec()
        if spec.memory != defaults.memory:
            lines.append(f"    memory '{_memory_to_nextflow(spec.memory)}'")
        if spec.walltime != defaults.walltime:
            lines.append(f"    time '{spec.walltime}'")
        if spec.disk and spec.disk != defaults.disk:
            lines.append(f"    disk '{_disk_to_nextflow(spec.disk)}'")
        if spec.accelerator:
            lines.append(f"    accelerator {spec.accelerator}")
        return lines

    def _container_directive_line(
        self,
        binding: StepBinding,
        registry: ToolRegistry,
    ) -> str | None:
        """Render Nextflow ``container`` directive if a container image is set.

        Checks the tool's registry metadata for a ``container_image`` field.
        / 如果设置了容器镜像，渲染 Nextflow container 指令。
        """
        from abi.tools import resolve_container_image

        step = binding.step
        tool_id = getattr(step, "tool_id", "")
        meta = registry.get(tool_id) if tool_id else {}
        image = resolve_container_image(tool_id, meta)
        if image:
            return f"    container '{image}'"
        return None

    def _workflow_block(self, dag: ABIDAG) -> str:
        if not dag.topological_order:
            return "\n".join(
                [
                    "workflow {",
                    "    Channel.of('ABI plan has no exportable external steps').view()",
                    "}",
                ]
            )
        lines = ["workflow {", "    abi_root = Channel.value('abi_nextflow_start')"]
        channel_by_step: Dict[str, str] = {}
        for step_id in dag.topological_order:
            binding = dag.binding_for(step_id)
            # Internal steps have no Nextflow process — pass the input channel
            # through unchanged so downstream external steps can still wire.
            # 内部步骤没有 Nextflow 进程 — 将输入通道原样传递，
            # 以便下游外部步骤仍可连接。
            if getattr(binding.step, "tool_id", "") == "internal":
                if binding.dependencies:
                    # Pass through the first dependency's channel
                    dep_channel = channel_by_step.get(binding.dependencies[0], "abi_root")
                    channel_by_step[step_id] = dep_channel
                else:
                    channel_by_step[step_id] = "abi_root"
                continue
            output_channel = _channel_name(binding.process_name)
            input_channel = "abi_root"
            if binding.dependencies:
                dependency_channels = [
                    channel_by_step[dependency] for dependency in binding.dependencies
                ]
                input_channel = dependency_channels[0]
                for index, dependency_channel in enumerate(dependency_channels[1:], start=1):
                    combined = f"dep_{binding.process_name}_{index}"
                    lines.append(f"    {combined} = {input_channel}.combine({dependency_channel})")
                    input_channel = combined
            lines.append(f"    {output_channel} = {binding.process_name}({input_channel})")
            channel_by_step[step_id] = output_channel
        lines.append("}")
        return "\n".join(lines)


def _command_text(step: Any, registry: ToolRegistry, *, project_root: Path) -> str:
    tool_id = str(getattr(step, "tool_id", ""))
    if not registry.has(tool_id):
        step_id = getattr(step, "step_id", "")
        raise ToolError(f"Cannot export step {step_id}: unknown tool {tool_id!r}")
    skill = registry.create(tool_id, mock_tools=True)
    params = _params_for_step(step, project_root=project_root)
    if "output_dir" not in params and "outdir" in params:
        params["output_dir"] = params["outdir"]
    command = skill.build_command(params)
    return " ".join(shlex.quote(str(token)) for token in command)


def _smoke_command_text(step: Any, *, project_root: Path) -> str:
    outputs = getattr(step, "outputs", {})
    lines = [f"echo 'ABI Nextflow smoke step: {shlex.quote(str(getattr(step, 'step_id', '')))}'"]
    for key, value in sorted(outputs.items()):
        if value in (None, ""):
            continue
        path = _absolute_path(str(value), project_root)
        if path.suffix:
            output_path = shlex.quote(str(path))
            lines.append(f"printf 'ABI Nextflow smoke output for {key}\\n' > {output_path}")
        else:
            lines.append(f"touch {shlex.quote(str(path / '.abi_smoke_marker'))}")
    return "\n    ".join(lines)


def _output_setup_lines(outputs: Mapping[str, Any], *, project_root: Path) -> list[str]:
    directories = []
    for value in outputs.values():
        if value in (None, ""):
            continue
        path = _absolute_path(str(value), project_root)
        directory = path.parent if path.suffix else path
        if str(directory) in ("", "."):
            continue
        directory_text = str(directory)
        if directory_text not in directories:
            directories.append(directory_text)
    return [f"mkdir -p {shlex.quote(directory)}" for directory in directories]


def _tool_env_lines(step: Any, registry: ToolRegistry, *, mamba_root: Path) -> list[str]:
    tool_id = str(getattr(step, "tool_id", ""))
    if not registry.has(tool_id):
        return []
    metadata = registry.get(tool_id)
    env_name = str(metadata.get("env_name", ""))
    if not env_name:
        return []
    env_bin = mamba_root / "envs" / env_name / "bin"
    return [f"export PATH={shlex.quote(str(env_bin))}:$PATH"]


def _params_for_step(step: Any, *, project_root: Path) -> Dict[str, Any]:
    params = dict(getattr(step, "inputs", {}))
    params.update(getattr(step, "params", {}))
    params.update(getattr(step, "outputs", {}))
    path_keys = {
        "read1",
        "read2",
        "long_reads",
        "assembly",
        "database",
        "model",
        "reference",
        "genome_index",
        "annotation_gtf",
        "gtf",
        "bam",
        "alignment",
        "counts",
        "output_dir",
        "output_prefix",
        "clean_read1",
        "clean_read2",
    }
    for key, value in list(params.items()):
        if value in (None, ""):
            continue
        if key in path_keys or key.endswith("_path") or key.endswith("_dir"):
            params[key] = str(_absolute_path(str(value), project_root))
    return params


def _absolute_path(value: str, project_root: Path) -> Path:
    if "NOT_CONFIGURED" in value:
        return Path(value)
    path = Path(value)
    if path.is_absolute():
        return path
    resolved = (project_root / path).resolve()
    # S5: prevent path traversal escaping project root
    root_resolved = project_root.resolve()
    if not (str(resolved).startswith(str(root_resolved) + os.sep) or resolved == root_resolved):
        raise ToolError(
            f"Path {value!r} escapes project root {project_root}. Resolved to: {resolved}"
        )
    return resolved


def _flatten_scalars(config: Mapping[str, Any]) -> Dict[str, Any]:
    flattened: Dict[str, Any] = {}

    def visit(prefix: str, value: Any) -> None:
        if isinstance(value, Mapping):
            for nested_key, nested_value in value.items():
                key = _param_name(f"{prefix}_{nested_key}" if prefix else str(nested_key))
                visit(key, nested_value)
            return
        if isinstance(value, (str, int, float, bool)) or value is None:
            flattened[_param_name(prefix)] = value

    visit("", config)
    return {key: value for key, value in flattened.items() if key}


def _channel_name(process_name: str) -> str:
    return f"ch_{process_name}"


def _shell_token(value: str) -> str:
    token = re.sub(r"[^A-Za-z0-9_]+", "_", value).strip("_").upper()
    return token or "ABI_STEP"


def _param_name(name: str) -> str:
    value = re.sub(r"[^A-Za-z0-9_]+", "_", name).strip("_").lower()
    if value and value[0].isdigit():
        value = f"param_{value}"
    return value


def _groovy_literal(value: Any) -> str:
    if value is True:
        return "true"
    if value is False:
        return "false"
    if value is None:
        return "null"
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value).replace("\\", "\\\\").replace("'", "\\'")
    return f"'{text}'"
