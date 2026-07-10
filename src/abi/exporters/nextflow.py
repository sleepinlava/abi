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
from abi.execution_policy import ExecutionPolicy
from abi.internal import internal_handler_spec
from abi.tools import ToolRegistry, _disk_to_nextflow, _memory_to_nextflow


def _transitive_downstream(dag: ABIDAG, step_id: str) -> list[str]:
    """Return stable transitive consumers of *step_id*."""
    descendants: set[str] = set()
    frontier = [step_id]
    while frontier:
        current = frontier.pop()
        for candidate, dependencies in dag.edges.items():
            if current in dependencies and candidate not in descendants:
                descendants.add(candidate)
                frontier.append(candidate)
    return [candidate for candidate in dag.topological_order if candidate in descendants]


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
        execution_policy: ExecutionPolicy | None = None,
        plugin_id: str | None = None,
    ) -> str:
        """Generate a complete Nextflow DSL2 script."""
        root = Path(project_root or PROJECT_ROOT).resolve()
        policy = execution_policy or ExecutionPolicy()
        mamba = Path(mamba_root or policy.mamba_root or root / ".mamba").resolve()
        abi_dag = dag or infer_dag(
            getattr(plan, "steps", []),
            project_root=root,
            sequential_fallback=True,
        )
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
                config=config,
                execution_policy=policy,
                plugin_id=plugin_id or str(getattr(plan, "analysis_type", "")),
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
        execution_policy: ExecutionPolicy | None = None,
        plugin_id: str | None = None,
    ) -> Path:
        """Write the generated Nextflow DSL2 script to disk."""
        path = Path(output_path)
        rendered = self.export(
            plan,
            config,
            registry,
            smoke=smoke,
            project_root=project_root,
            mamba_root=mamba_root,
            dag=dag,
            execution_policy=execution_policy,
            plugin_id=plugin_id,
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(rendered, encoding="utf-8")
        os.replace(temporary, path)
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
        """Raise :exc:`ToolError` for every **driver**-scoped internal step.

        Worker-scoped handlers are now supported by C09 — they generate
        Nextflow processes that call ``abi run-step``. Driver-scoped handlers
        do not yet have a verified control-node execution path, so exporting
        one would silently skip required work.
        """
        affected: list[str] = []
        for binding in dag.bindings:
            tool_id = str(getattr(binding.step, "tool_id", ""))
            if tool_id != "internal":
                continue
            _handler_id, scope = internal_handler_spec(binding.step)
            if scope == "worker":
                # Supported — will generate a Nextflow process.
                continue
            step_id = str(getattr(binding.step, "step_id", "?"))
            handler_id = _handler_id or "?"
            downstream = _transitive_downstream(dag, step_id)
            suffix = f"; downstream: {', '.join(downstream)}" if downstream else ""
            affected.append(f"  step {step_id} (handler {handler_id!r}){suffix}")

        if affected:
            raise ToolError(
                "Nextflow export blocked: driver-scoped internal handlers are not "
                "executed by the Nextflow runtime and must not be skipped silently.\n"
                + "\n".join(affected)
                + "\n\nRun the workflow with a runtime that executes driver handlers."
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
        config: Mapping[str, Any],
        execution_policy: ExecutionPolicy,
        plugin_id: str,
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
                        smoke=smoke,
                        project_root=project_root,
                        mamba_root=mamba_root,
                        config=config,
                        plugin_id=plugin_id,
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
                    config=config,
                    execution_policy=execution_policy,
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
        config: Mapping[str, Any],
        execution_policy: ExecutionPolicy,
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
        resource_dirs = self._resource_directive_lines(
            binding, registry, config=config, execution_policy=execution_policy
        )
        container_dir = self._container_directive_line(
            binding, registry, execution_policy=execution_policy
        )
        if container_dir:
            resource_dirs.append(container_dir)
        return f"""process {process_name} {{
    tag {_groovy_literal(str(getattr(step, "step_id", process_name)))}
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
        smoke: bool,
        project_root: Path,
        mamba_root: Path,
        config: Mapping[str, Any],
        plugin_id: str,
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
            payload_section = "printf '{}\\n' > .abi_result.json\n"
        else:
            # Inline the payload as a heredoc so the worker can reconstruct
            # the step without relying on a shared filesystem.
            import json

            provenance_dir = getattr(step, "provenance_dir", None) or config.get(
                "provenance_dir", Path(str(config.get("outdir", outdir))) / "provenance"
            )
            payload = {
                "plugin_id": plugin_id,
                "step": step.to_dict(),
                "config": dict(config),
                "provenance_dir": str(provenance_dir),
                "result_path": ".abi_result.json",
            }
            payload_json = json.dumps(payload, indent=2, default=str)
            payload_section = (
                f"cat > .abi_payload.json <<'ABI_PAYLOAD'\n{payload_json}\nABI_PAYLOAD\n"
                "chmod 600 .abi_payload.json\n"
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
    path '.abi_result.json'

    script:
    '''
{script}
    '''
}}"""

    def _resource_directive_lines(
        self,
        binding: StepBinding,
        registry: ToolRegistry,
        *,
        config: Mapping[str, Any] | None = None,
        execution_policy: ExecutionPolicy | None = None,
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
        policy = execution_policy or ExecutionPolicy()
        spec = resolve_resources_v2(
            tool_id,
            meta,
            config=config,
            cli_overrides=policy.invocation_overrides,
            resource_profile=policy.resource_profile,
            resource_profiles_dir=policy.resource_profiles_dir,
        )

        # Only emit non-default values / 只输出非默认值
        lines: list[str] = []
        defaults = ResourceSpec()
        lines.append(f"    cpus {spec.cpu}")
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
        *,
        execution_policy: ExecutionPolicy | None = None,
    ) -> str | None:
        """Render Nextflow ``container`` directive if a container image is set.

        Checks the tool's registry metadata for a ``container_image`` field.
        / 如果设置了容器镜像，渲染 Nextflow container 指令。
        """
        from abi.tools import resolve_container_image

        step = binding.step
        tool_id = getattr(step, "tool_id", "")
        meta = registry.get(tool_id) if tool_id else {}
        policy = execution_policy or ExecutionPolicy()
        image = policy.container_image or resolve_container_image(tool_id, meta)
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
            if getattr(binding.step, "tool_id", "") == "internal":
                _handler_id, scope = internal_handler_spec(binding.step)
                if scope == "driver":
                    raise ToolError(
                        f"Driver-scoped internal step {step_id} ({_handler_id!r}) was not rejected"
                    )
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
