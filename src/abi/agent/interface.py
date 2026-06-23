"""ABIAgentInterface — the stable, transport-neutral entry point for ABI agents.

This module exposes `ABIAgentInterface`, the single, versioned boundary through which
all agentic callers (CLI JSON, MCP servers, HTTP jobs, OpenAI function-calling) interact
with the ABI bioinformatics platform.

# Agent interaction model / Agent 交互模型

Every public method returns a JSON string following a unified three-status envelope:

    success               — operation completed; ``result`` holds the payload
    confirmation_required — the operation is gated on user approval (used by ``run``)
    error                 — operation failed; ``error`` + ``error_code`` +
                            ``diagnostic_hints`` guide automated recovery

Callers never need to parse free-text messages; they inspect ``status`` and branch.

# Lifecycle methods (safe call order) / 生命周期方法（安全调用顺序）

The recommended progression from discovery to execution is:

    1. list_types()       — discover installed analysis plugins
    2. plan()             — resolve config + inputs, persist execution_plan.json
    3. dry_run()          — render commands & provenance without executing external tools
    4. inspect()          — summarize run health from an existing result directory
    5. report()           — regenerate reports from a completed run
    6. run()              — execute (requires confirm_execution=true)

Additional utility methods:

    export_nextflow()     — export the plan as a Nextflow DSL2 workflow
    export_agent_context()— compact machine-readable guidance for agent callers
    doctor_agent()        — human-readable operating guide for an analysis type
    dispatch()            — function-calling style tool router (used by MCP/OpenAI)

# dispatch() routing / dispatch() 路由机制

``dispatch(tool_name, arguments)`` is the bridge between function-calling schemas and
the public methods. It maps hyphenated/aliased tool names (e.g. ``"dry-run"``,
``"abi_dry_run"``) to the canonical method name, then calls the method with unpacked
keyword arguments. Unknown tool names produce an immediate ``error`` envelope with
``diagnostic_hints`` so callers can self-correct.

# Design decisions / 设计决策

- Every method returns a *string* (serialized JSON) so that the interface is
  wire-format agnostic — a CLI subprocess, an MCP tool response, and an HTTP body
  all look identical.
- The ``_call`` helper enforces the envelope contract and centralizes error
  classification via ``classify_exception`` from ``abi.diagnostics``.
- ``MemoryError`` is re-raised intentionally — OOM conditions should not be
  swallowed by the error envelope.
- ``confirmation_required`` is treated as a first-class status (not an error) so
  that orchestrators can present a clear approval flow without ambiguous parsing.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Tuple, Union

import yaml

from abi._shared import _common_overrides, _plan_dict, _read_tsv
from abi.agent.context import build_agent_context, render_doctor_agent
from abi.agent.envelopes import (
    confirmation_required_envelope,
    error_envelope,
    json_dumps,
    success_envelope,
)
from abi.diagnostics import classify_exception
from abi.executor import GenericABIExecutor
from abi.exporters import NextflowExporter
from abi.interfaces import ABIResultValidationPlugin
from abi.internal import run_plugin_preflight
from abi.json_utils import load_json_object
from abi.permissions import requires_confirmation
from abi.plugins import get_plugin, list_plugins
from abi.provenance import RunLogger
from abi.results import validate_abi_result_dir
from abi.runtimes import LocalRuntime, NextflowRuntime, RuntimeOptions
from abi.schemas import ABIError
from abi.skill_installer import install_bundled_skills
from abi.tables import StandardTableManager
from abi.tool_descriptors import TOOL_ALIASES


def _validate_plugin_result_dir(
    plugin_id: str,
    result_dir: str | Path,
    *,
    allow_empty_tables: bool = True,
) -> Mapping[str, Any]:
    plugin = get_plugin(plugin_id)
    if not isinstance(plugin, ABIResultValidationPlugin):
        raise ABIError(f"Plugin {plugin_id!r} does not provide specialized result validation")
    return plugin.validate_result_dir(
        result_dir,
        allow_empty_tables=allow_empty_tables,
    )


class ABIAgentInterface:
    """ABI's stable tool boundary for CLI JSON, MCP, HTTP, and function calling.

    Every public method returns a JSON string with the same envelope:
    ``status``, ``command``, and either ``result`` or ``error``.

    # 每个公共方法都返回统一 JSON 信封, 包含 status / command / result 或 error。
    """

    def __init__(self, verbose_errors: bool = False) -> None:
        """Initialize the agent interface.

        Args:
            verbose_errors: if True, error envelopes include ``error_type``
                            (Python exception class name) for debugging.
                            Default False — agents only need error_code +
                            diagnostic_hints for automated recovery.
        """
        self.verbose_errors = verbose_errors

    # ------------------------------------------------------------------
    # Public lifecycle methods / 公共生命周期方法
    # ------------------------------------------------------------------

    def list_types(self) -> str:
        """Return installed ABI analysis plugin types as a JSON envelope.

        Role in lifecycle: **Step 1 — Discovery.**
        Call this first so the agent knows which analysis types are available
        before constructing a plan.

        Returns:
            success envelope with ``analysis_types`` (list of {analysis_type,
            name, description}) and ``count``.

        # 返回已安装的 ABI 分析插件类型, 这是生命周期第一步: 发现可用分析类型。
        """
        return self._call("list_types", self._list_types)

    def plan(
        self,
        *,
        analysis_type: str,
        config_path: Optional[Union[str, Path]] = None,
        sample_sheet: Optional[Union[str, Path]] = None,
        profile: str = "dry_run",
        mode: Optional[str] = None,
        threads: Optional[int] = None,
        outdir: Optional[str] = None,
        log_dir: Optional[str] = None,
        check_files: bool = True,
    ) -> str:
        """Build and persist an ABI execution plan without running external tools.

        Role in lifecycle: **Step 2 — Plan.**
        Resolves the plugin configuration, builds a full execution plan (ordered
        steps with tool contracts), and persists it as ``execution_plan.json`` in
        the output directory. No external tools are executed.

        Key parameters:
            analysis_type: plugin ID returned by ``list_types()``.
            config_path:   optional YAML/JSON config override.
            sample_sheet:  optional TSV mapping sample IDs to input paths.
            profile:       config profile to load (default ``"dry_run"``).
            mode:          optional workflow sub-mode (e.g. ``"plasmid"``).
            check_files:   whether to verify input file existence during planning.

        Returns:
            success envelope with ``plan_path``, ``steps`` (count), and the
            full ``plan`` dictionary.

        # 构建并持久化 ABI 执行计划, 不会运行外部工具。
        # 这是生命周期第二步: 解析配置 -> 构建步骤 -> 写入 execution_plan.json。
        """
        return self._call(
            "plan",
            self._plan,
            analysis_type=analysis_type,
            config_path=config_path,
            sample_sheet=sample_sheet,
            profile=profile,
            mode=mode,
            threads=threads,
            outdir=outdir,
            log_dir=log_dir,
            check_files=check_files,
        )

    def check(
        self,
        *,
        analysis_type: str,
        config_path: Optional[Union[str, Path]] = None,
        sample_sheet: Optional[Union[str, Path]] = None,
        profile: str = "dry_run",
        engine: str = "local",
        check_runtime: bool = True,
    ) -> str:
        """Run plugin input, resource, and optional runtime preflight checks."""
        return self._call(
            "check",
            self._check,
            analysis_type=analysis_type,
            config_path=config_path,
            sample_sheet=sample_sheet,
            profile=profile,
            engine=engine,
            check_runtime=check_runtime,
        )

    def dry_run(
        self,
        *,
        analysis_type: str,
        config_path: Optional[Union[str, Path]] = None,
        sample_sheet: Optional[Union[str, Path]] = None,
        profile: str = "dry_run",
        mode: Optional[str] = None,
        threads: Optional[int] = None,
        outdir: Optional[str] = None,
        log_dir: Optional[str] = None,
        progress: Optional[bool] = None,
        check_files: bool = True,
        resource_profile: Optional[str] = None,
        cpu_override: Optional[int] = None,
        memory_override: Optional[str] = None,
        walltime_override: Optional[str] = None,
        accelerator_override: Optional[str] = None,
        container_image: Optional[str] = None,
        container_runtime: Optional[str] = None,
    ) -> str:
        """Render commands and provenance artifacts without executing real tools.

        Role in lifecycle: **Step 3 — Dry Run.**
        Identical pipeline to ``plan()`` but additionally renders every command
        line, captures resolved inputs, and writes provenance TSV files. Tools are
        run in *mock mode* (command strings are logged, not executed). This is the
        safest way to validate a complete workflow before real execution.

        Key parameters (beyond ``plan()``):
            progress:  if True, emit progress events (JSONL) during dry run.

        Returns:
            success envelope with ``outdir``, ``outputs`` (mapping of artifact
            keys to paths), and ``written_files``.

        # 渲染命令和溯源产物, 但不真正执行外部工具。
        # 这是生命周期第三步: 以 mock 模式验证完整工作流, 是执行前最安全的检查点。
        """
        return self._call(
            "dry_run",
            self._dry_run,
            analysis_type=analysis_type,
            config_path=config_path,
            sample_sheet=sample_sheet,
            profile=profile,
            mode=mode,
            threads=threads,
            outdir=outdir,
            log_dir=log_dir,
            progress=progress,
            check_files=check_files,
            resource_profile=resource_profile,
            cpu_override=cpu_override,
            memory_override=memory_override,
            walltime_override=walltime_override,
            accelerator_override=accelerator_override,
            container_image=container_image,
            container_runtime=container_runtime,
        )

    def inspect(self, *, result_dir: Union[str, Path]) -> str:
        """Inspect an ABI result directory and summarize run health.

        Role in lifecycle: **Step 4 — Inspect.**
        Reads provenance artifacts (``commands.tsv``, ``resolved_inputs.tsv``,
        ``run_summary.json``) from a completed (or partially completed) result
        directory and surfaces failures, skipped steps, and missing inputs.

        Parameters:
            result_dir: path to a directory containing a prior ABI run's output.

        Returns:
            success envelope with ``status``, ``step_count``, ``failed_steps``,
            ``skipped_steps``, and ``missing_or_placeholder_inputs``.

        # 检查结果目录并总结运行健康状况。
        # 这是生命周期第四步: 读取溯源文件, 快速暴露失败 / 跳过 / 缺失输入。
        """
        return self._call("inspect", self._inspect, result_dir=result_dir)

    def report(
        self,
        *,
        result_dir: Union[str, Path],
        analysis_type: Optional[str] = None,
    ) -> str:
        """Regenerate ABI reports from an existing result directory.

        Role in lifecycle: **Step 5 — Report.**
        Reads the ``execution_plan.json`` from a prior run and invokes the
        plugin's ``write_report()`` hook to produce ``report/report.md``,
        ``report/report.html``, and any analysis-specific summaries. This is
        safe to call repeatedly on the same result directory.

        Parameters:
            result_dir:   path to a completed ABI run directory.
            analysis_type: optional override; auto-detected from the plan if omitted.

        Returns:
            success envelope with ``outputs`` (artifact paths) and
            ``written_files``.

        # 从已有结果目录重新生成报告。
        # 这是生命周期第五步: 读取 execution_plan.json -> 调用 write_report() -> 输出报告。
        """
        return self._call(
            "report",
            self._report,
            result_dir=result_dir,
            analysis_type=analysis_type,
        )

    def run(
        self,
        *,
        analysis_type: str,
        engine: str = "local",
        config_path: Optional[Union[str, Path]] = None,
        sample_sheet: Optional[Union[str, Path]] = None,
        profile: str = "dry_run",
        mode: Optional[str] = None,
        threads: Optional[int] = None,
        outdir: Optional[str] = None,
        log_dir: Optional[str] = None,
        workflow: Optional[Union[str, Path]] = None,
        work_dir: Optional[Union[str, Path]] = None,
        nxf_home: Optional[Union[str, Path]] = None,
        nextflow_bin: Optional[Union[str, Path]] = None,
        nextflow_profile: Optional[str] = None,
        executor: Optional[str] = None,
        resume: bool = False,
        mamba_root: Optional[Union[str, Path]] = None,
        smoke: bool = False,
        check_files: bool = True,
        confirm_execution: bool = False,
        resource_profile: Optional[str] = None,
        cpu_override: Optional[int] = None,
        memory_override: Optional[str] = None,
        walltime_override: Optional[str] = None,
        accelerator_override: Optional[str] = None,
        container_image: Optional[str] = None,
        container_runtime: Optional[str] = None,
        scheduler: Optional[str] = None,
        partition: Optional[str] = None,
        account: Optional[str] = None,
        qos: Optional[str] = None,
        hpc_timeout_seconds: Optional[float] = None,
        poll_interval_seconds: float = 30.0,
    ) -> str:
        """Run an ABI plan through a runtime backend after explicit confirmation.

        Role in lifecycle: **Step 6 — Execute.**
        This is the *only* method that executes real external tools. It requires
        ``confirm_execution=true`` as a deliberate safety gate: without it, a
        ``confirmation_required`` envelope is returned so the orchestrator can
        present an approval prompt to the user.

        **Data flow:**
            1. If ``confirm_execution`` is False -> return ``confirmation_required``
               immediately (no side effects).
            2. Resolve plugin config and build the execution plan.
            3. Select local subprocess, Nextflow DSL2, or native HPC runtime.
            4. Execute plan steps, capture return code, and collect outputs.

        Key parameters:
            engine:             ``"local"``, ``"nextflow"``, or ``"hpc"``.
            confirm_execution:  must be ``True`` to proceed past the safety gate.
            smoke:              if True with engine=local, tools run in mock mode
                                (useful for integration tests).
            resume:             resume supported completed workflow steps.
            mamba_root:         path to the conda/mamba prefix for tool environments.

        Returns:
            - ``confirmation_required`` envelope when ``confirm_execution`` is
              False (caller should re-invoke with ``confirm_execution=true``).
            - ``success`` envelope with ``runtime_status``, ``return_code``,
              ``outputs``, and ``written_files``.

        # 通过运行时后端运行 ABI 计划, 必须先显式确认。
        # 这是生命周期第六步(最后一步): 唯一真正执行外部工具的方法。
        # confirm_execution=false 时返回 confirmation_required, 作为安全闸门。
        """
        return self._call(
            "run",
            self._run,
            analysis_type=analysis_type,
            engine=engine,
            config_path=config_path,
            sample_sheet=sample_sheet,
            profile=profile,
            mode=mode,
            threads=threads,
            outdir=outdir,
            log_dir=log_dir,
            workflow=workflow,
            work_dir=work_dir,
            nxf_home=nxf_home,
            nextflow_bin=nextflow_bin,
            nextflow_profile=nextflow_profile,
            executor=executor,
            resume=resume,
            mamba_root=mamba_root,
            smoke=smoke,
            check_files=check_files,
            confirm_execution=confirm_execution,
            resource_profile=resource_profile,
            cpu_override=cpu_override,
            memory_override=memory_override,
            walltime_override=walltime_override,
            accelerator_override=accelerator_override,
            container_image=container_image,
            container_runtime=container_runtime,
            scheduler=scheduler,
            partition=partition,
            account=account,
            qos=qos,
            hpc_timeout_seconds=hpc_timeout_seconds,
            poll_interval_seconds=poll_interval_seconds,
        )

    def export_nextflow(
        self,
        *,
        analysis_type: str,
        output: Union[str, Path],
        config_path: Optional[Union[str, Path]] = None,
        sample_sheet: Optional[Union[str, Path]] = None,
        profile: str = "dry_run",
        mode: Optional[str] = None,
        threads: Optional[int] = None,
        outdir: Optional[str] = None,
        log_dir: Optional[str] = None,
        smoke: bool = False,
        mamba_root: Optional[Union[str, Path]] = None,
        check_files: bool = True,
    ) -> str:
        """Export an ABI execution plan to Nextflow DSL2 without running it.

        Utility method (not in the strict ``run()`` path).
        Builds the plan (same as ``plan()``) but serializes it as a Nextflow
        ``main.nf`` workflow file instead of executing it. Useful for portability
        and HPC environments where Nextflow is the preferred orchestrator.

        Key parameters:
            output:     path where the ``main.nf`` workflow file will be written.
            smoke:      if True, inject smoke-test parameters into the workflow.
            mamba_root: conda/mamba prefix path for containerized steps.

        Returns:
            success envelope with ``workflow`` (path), ``steps`` (count),
            and ``written_files``.

        # 将执行计划导出为 Nextflow DSL2 工作流文件, 不执行。
        # 适用于 HPC 环境或需要 Nextflow 编排的场景。
        """
        return self._call(
            "export_nextflow",
            self._export_nextflow,
            analysis_type=analysis_type,
            output=output,
            config_path=config_path,
            sample_sheet=sample_sheet,
            profile=profile,
            mode=mode,
            threads=threads,
            outdir=outdir,
            log_dir=log_dir,
            smoke=smoke,
            mamba_root=mamba_root,
            check_files=check_files,
        )

    def export_agent_context(self, *, analysis_type: str) -> str:
        """Export compact machine-readable guidance for untrained agent callers.

        Returns a dictionary with: analysis type metadata, the recommended safe
        call sequence, tool permissions, standard table names, important artifact
        paths, known error codes, and recovery rules. This is designed to be
        injected into an agent's system prompt so that even an untrained LLM can
        use ABI correctly on the first attempt.

        # 导出紧凑的机器可读指南, 供未经训练的 LLM agent 使用。
        # 包含安全调用顺序 / 工具权限 / 标准表 / 重要产物 / 错误码和恢复规则。
        """
        return self._call(
            "export_agent_context",
            self._export_agent_context,
            analysis_type=analysis_type,
        )

    def doctor_agent(self, *, analysis_type: str) -> str:
        """Return a short human-readable operating guide for an ABI analysis type.

        Renders the same information as ``export_agent_context()`` but as a
        plain-text summary intended for display to a human operator or for
        inclusion in a chat-based agent prompt.

        # 返回人类可读的简短操作指南, 适合展示给用户或注入聊天式 agent prompt。
        """
        return self._call("doctor_agent", self._doctor_agent, analysis_type=analysis_type)

    def install_skills(
        self,
        *,
        target: Optional[Union[str, Path]] = None,
        force: bool = False,
    ) -> str:
        """Install bundled ABI skills and documentation into a target directory."""
        return self._call(
            "install_skills",
            install_bundled_skills,
            target=target,
            force=force,
        )

    def query(
        self,
        *,
        analysis_type: str,
        what: str,
        step: Optional[str] = None,
    ) -> str:
        """Lightweight metadata query — no plan construction, no config loading.

        Unlike ``plan()`` which resolves config and builds a full execution plan,
        ``query()`` only reads the plugin's ``pipeline_dag.yaml`` and tool
        registry — cheap (~50ms) and suitable for quick lookups during agent
        reasoning loops.

        Query targets (``--what``):
            ``stages``     — ordered pipeline stages (from DAG categories)
            ``tools``      — all tools grouped by category
            ``platforms``  — supported sequencing platforms
            ``workflows``  — named workflow presets when the plugin declares them
            ``resources``  — inputs + outputs for a specific ``--step``
            ``inputs``     — only inputs for a specific ``--step``
            ``outputs``    — only outputs for a specific ``--step``

        # 轻量级元数据查询 — 不构建执行计划，不加载配置。
        # 仅读取 pipeline_dag.yaml 和工具注册表，~50ms，适合 agent 推理循环中的快速查询。
        """
        return self._call(
            "query",
            self._query,
            analysis_type=analysis_type,
            what=what,
            step=step,
        )

    def abi_validate_result(
        self,
        *,
        result_dir: Union[str, Path],
        allow_empty_tables: bool = True,
    ) -> str:
        """Validate an ABI result directory without modifying it.

        Checks that all expected artifacts (plan, provenance, tables, reports)
        exist and conform to the plugin's output schema. Read-only; safe to call
        at any time.

        Parameters:
            allow_empty_tables: if True, empty TSV tables do not trigger
                                validation errors (useful for no-hit results).

        # 验证 ABI 结果目录的结构完整性, 只读操作, 可随时安全调用。
        """
        return self._call(
            "abi_validate_result",
            validate_abi_result_dir,
            result_dir,
            allow_empty_tables=allow_empty_tables,
        )

    def autoplasm_validate_result(
        self,
        *,
        result_dir: Union[str, Path],
        allow_empty_tables: bool = True,
    ) -> str:
        """Backward-compatible alias for ``abi_validate_result``.

        Preserved so existing scripts referencing the old ``autoplasm`` namespace
        continue to work after the rename to ``abi``.

        # 向后兼容别名, 保留旧 autoplasm 命名空间的调用路径。
        """
        return self._call(
            "autoplasm_validate_result",
            _validate_plugin_result_dir,
            "metagenomic_plasmid",
            result_dir,
            allow_empty_tables=allow_empty_tables,
        )

    def dispatch(self, tool_name: str, arguments: Optional[Mapping[str, Any]] = None) -> str:
        """Dispatch a function-calling style tool invocation to the correct method.

        This is the bridge between LLM function-calling schemas (where tool names
        may be hyphenated like ``"dry-run"`` or prefixed like ``"abi_dry_run"``)
        and the Python method names of this class. All variants map to the same
        canonical method.

        Data flow:
            1. Look up ``tool_name`` in the aliases table.
            2. If not found -> immediate ``error`` envelope with
               ``diagnostic_hints`` and the list of available tool names.
            3. If found -> call the Python method with unpacked ``**args``.
            4. ``TypeError`` from mismatched arguments is caught and converted
               to an error envelope (so callers see a structured error, not a
               raw Python traceback).

        # 将函数调用风格的工具调用路由到正确的方法。
        # 这是 LLM function-calling schema 和 Python 方法之间的桥梁。
        # 支持连字符别名 (如 "dry-run") 和前缀别名 (如 "abi_dry_run")。
        """
        args = dict(arguments or {})
        aliases = TOOL_ALIASES
        method_name = aliases.get(tool_name, tool_name)
        method = getattr(self, method_name, None)
        if method is None:
            return json_dumps(
                error_envelope(
                    tool_name,
                    error=f"Unknown ABI agent tool: {tool_name}",
                    error_type="ValueError",
                    error_code="internal_error",
                    diagnostic_hints=[
                        {
                            "severity": "error",
                            "code": "internal_error",
                            "message": "The requested ABI tool name is not registered.",
                            "suggested_next_action": (
                                "Use one of the advertised ABI tool descriptors."
                            ),
                        }
                    ],
                    extra={"available": sorted(aliases)},
                )
            )
        # Enforce the central permission registry at the transport-neutral
        # dispatch boundary.  Short/legacy aliases resolve to their canonical
        # ``abi_*`` permission name before the handler is called.
        permission_name = tool_name
        if permission_name not in TOOL_ALIASES or not permission_name.startswith("abi_"):
            canonical = f"abi_{method_name}"
            if canonical in TOOL_ALIASES:
                permission_name = canonical
        if requires_confirmation(permission_name) and not bool(args.get("confirm_execution")):
            return json_dumps(
                confirmation_required_envelope(
                    method_name,
                    {
                        "message": "Re-run with confirm_execution=true after user approval.",
                        "tool": permission_name,
                    },
                )
            )
        try:
            return method(**args)
        except TypeError as exc:
            error_code, hints = classify_exception(exc, command=method_name)
            return json_dumps(
                error_envelope(
                    method_name,
                    error=str(exc),
                    error_type=exc.__class__.__name__,
                    error_code=error_code,
                    diagnostic_hints=hints,
                )
            )

    def _call(self, command: str, handler: Callable[..., Any], *args: Any, **kwargs: Any) -> str:
        """Central dispatch helper that enforces the JSON envelope contract.

        Every public method delegates to ``_call`` so that: (1) all exceptions
        are caught and classified via ``classify_exception``, (2) the three-status
        envelope (success / confirmation_required / error) is enforced uniformly,
        and (3) non-dict return values are automatically wrapped.

        Design decisions:
            - ``MemoryError`` is **re-raised** — OOM kills should not be swallowed
              by the error envelope; the process must terminate.
            - When the error message contains ``"Unknown ABI analysis type"``,
              we inject the full list of available plugin IDs into the error
              payload so callers can self-correct without an extra round-trip.
            - If the handler result is a mapping with ``status ==
              "confirmation_required"``, the envelope is promoted to a
              first-class ``confirmation_required`` envelope (not an error).

        # 中央调度辅助方法, 强制统一 JSON 信封契约。
        # 所有公共方法都通过 _call 来统一异常分类 / 信封格式 / 返回值包装。
        # MemoryError 被有意重新抛出, 不淹没 OOM 信号。
        """
        try:
            result = handler(*args, **kwargs)
        except MemoryError:
            raise
        except Exception as exc:
            error_code, hints = classify_exception(exc, command=command)
            extra: Dict[str, Any] = {}
            # Inject the list of available plugin IDs so callers can retry
            # immediately with a valid analysis_type without calling list_types.
            # 注入可用插件列表, 调用者无需额外调用 list_types 即可自行纠正。
            if "Unknown ABI analysis type" in str(exc):
                extra["available"] = [plugin.plugin_id for plugin in list_plugins()]
            return json_dumps(
                error_envelope(
                    command,
                    error=str(exc),
                    error_type=exc.__class__.__name__,
                    error_code=error_code,
                    diagnostic_hints=hints,
                    extra=extra,
                    verbose=self.verbose_errors,
                )
            )
        # Promote handler-returned confirmation_required to a first-class envelope.
        # This is how _run() signals the safety gate without raising an error.
        # 将 handler 返回的 confirmation_required 提升为一级信封。
        # 这是 _run() 在不抛出错误的情况下实现安全闸门的方式。
        if isinstance(result, Mapping) and result.get("status") == "confirmation_required":
            raw_result = result.get("result")
            if not isinstance(raw_result, Mapping):
                raw_result = {}
            return json_dumps(confirmation_required_envelope(command, raw_result))
        # Auto-wrap non-dict results so every success payload has a "result" key.
        # 自动包装非字典返回值, 确保每个成功载荷都有 "result" 键。
        if not isinstance(result, Mapping):
            result = {"value": result}
        return json_dumps(success_envelope(command, result))

    # ------------------------------------------------------------------
    # Private handler methods / 私有处理方法
    #
    # Each handler returns a Mapping (or a confirmation_required dict).
    # _call() wraps the return value in the appropriate JSON envelope.
    # 每个 handler 返回 Mapping (或 confirmation_required 字典)。
    # _call() 将其包装为相应的 JSON 信封。
    # ------------------------------------------------------------------

    def _list_types(self) -> Dict[str, Any]:
        """Return all registered analysis plugin metadata."""
        plugins = [
            {
                "analysis_type": plugin.plugin_id,
                "name": plugin.display_name,
                "description": plugin.description,
            }
            for plugin in list_plugins()
        ]
        return {"analysis_types": plugins, "count": len(plugins)}

    def _plan(
        self,
        *,
        analysis_type: str,
        config_path: Optional[Union[str, Path]],
        sample_sheet: Optional[Union[str, Path]],
        profile: str,
        mode: Optional[str],
        threads: Optional[int],
        outdir: Optional[str],
        log_dir: Optional[str],
        check_files: bool,
    ) -> Dict[str, Any]:
        """Build config + plan, then persist ``execution_plan.json`` to disk.

        The plugin reference is discarded after plan construction because the
        serialized plan is the canonical artifact that downstream steps consume.
        # 构建配置 + 计划, 然后将 execution_plan.json 写入磁盘。
        # 构建完成后丢弃插件引用, 因为序列化计划是下游步骤消费的规范产物。
        """
        plugin, cfg, plan = self._build_plan(
            analysis_type=analysis_type,
            config_path=config_path,
            sample_sheet=sample_sheet,
            profile=profile,
            mode=mode,
            threads=threads,
            outdir=outdir,
            log_dir=log_dir,
            check_files=check_files,
        )
        del plugin  # plugin reference is not needed after plan is serialized
        outdir_path = Path(str(cfg["outdir"]))
        outdir_path.mkdir(parents=True, exist_ok=True)
        plan_path = outdir_path / "execution_plan.json"
        plan_data = _plan_dict(plan, analysis_type)
        plan_path.write_text(
            json.dumps(plan_data, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        steps = getattr(plan, "steps", [])
        return {
            "analysis_type": analysis_type,
            "plan_path": plan_path,
            "steps": len(steps),
            "summary": _build_plan_summary(plan, analysis_type),
            "written_files": [plan_path],
            "plan": plan_data,
        }

    def _check(
        self,
        *,
        analysis_type: str,
        config_path: Optional[Union[str, Path]],
        sample_sheet: Optional[Union[str, Path]],
        profile: str,
        engine: str,
        check_runtime: bool,
    ) -> Dict[str, Any]:
        """Load configuration and run the plugin's side-effect-free preflight."""
        plugin = get_plugin(analysis_type)
        cfg = plugin.load_config(
            _optional_path(config_path),
            profile=profile,
            overrides=_common_overrides(sample_sheet=sample_sheet),
        )
        report = dict(
            run_plugin_preflight(
                plugin,
                cfg,
                engine=engine.lower().strip(),
                check_runtime=check_runtime,
            )
        )
        report.setdefault("plugin", analysis_type)
        report.setdefault("status", "pass")
        return report

    def _dry_run(
        self,
        *,
        analysis_type: str,
        config_path: Optional[Union[str, Path]],
        sample_sheet: Optional[Union[str, Path]],
        profile: str,
        mode: Optional[str],
        threads: Optional[int],
        outdir: Optional[str],
        log_dir: Optional[str],
        progress: Optional[bool],
        check_files: bool,
        resource_profile: Optional[str],
        cpu_override: Optional[int],
        memory_override: Optional[str],
        walltime_override: Optional[str],
        accelerator_override: Optional[str],
        container_image: Optional[str],
        container_runtime: Optional[str],
    ) -> Dict[str, Any]:
        """Execute a mock run: render commands + provenance, no external tools.

        Prefers the plugin's ``execute_dry_run`` hook if available; otherwise
        falls back to ``GenericABIExecutor`` with ``mock_tools=True``.
        # 执行模拟运行: 渲染命令 + 溯源产物, 不执行外部工具。
        # 优先使用插件的 execute_dry_run 钩子, 否则回退到 GenericABIExecutor mock 模式。
        """
        plugin = get_plugin(analysis_type)
        # Force mock_tools=True so external commands are only rendered, not executed.
        # 强制 mock_tools=True, 确保外部命令仅渲染不执行。
        cfg = plugin.load_config(
            _optional_path(config_path),
            profile=profile,
            overrides=_common_overrides(
                mode=mode,
                threads=threads,
                outdir=outdir,
                log_dir=log_dir,
                sample_sheet=sample_sheet,
                dry_run=True,
                progress=progress,
                resource_profile=resource_profile,
                cpu_override=cpu_override,
                memory_override=memory_override,
                walltime_override=walltime_override,
                accelerator_override=accelerator_override,
                container_image=container_image,
                container_runtime=container_runtime,
            )
            | {"mock_tools": True},
        )
        plan = plugin.build_plan(cfg, check_files=check_files)
        if hasattr(plugin, "execute_dry_run"):
            outputs = plugin.execute_dry_run(plan, cfg)
        else:
            table_manager = StandardTableManager(plugin.table_schemas())
            executor = GenericABIExecutor(
                plugin.registry(),
                RunLogger(str(cfg["log_dir"])),
                table_manager=table_manager,
                parse_outputs=plugin.parse_outputs,
                report_title=plugin.report_title,
                mock_tools=True,
            )
            outputs = executor.dry_run(plan, cfg)
        output_files = dict(outputs)
        return {
            "analysis_type": analysis_type,
            "outdir": cfg.get("outdir"),
            "outputs": output_files,
        }

    def _inspect(self, *, result_dir: Union[str, Path]) -> Dict[str, Any]:
        """Read provenance TSVs and summarize what happened in a prior run.

        Parses ``commands.tsv`` for failed/skipped steps and
        ``resolved_inputs.tsv`` for missing or placeholder (NOT_CONFIGURED) files.
        # 读取溯源 TSV 文件, 总结先前运行的执行状况。
        # 解析 commands.tsv 查找失败/跳过的步骤,
        # 解析 resolved_inputs.tsv 查找缺失或占位符文件。
        """
        root = Path(result_dir)
        provenance = root / "provenance"
        commands = _read_tsv(provenance / "commands.tsv")
        resolved_inputs = _read_tsv(provenance / "resolved_inputs.tsv")
        failed = [row for row in commands if row.get("status") == "failed"]
        skipped = [row for row in commands if row.get("status") == "skipped"]
        missing_inputs = [
            row
            for row in resolved_inputs
            if str(row.get("exists", "")).lower() == "false"
            or "NOT_CONFIGURED" in row.get("path", "")
        ]
        summary_path = provenance / "run_summary.json"
        summary = load_json_object(summary_path) if summary_path.exists() else {}
        return {
            "result_dir": root,
            "status": summary.get("status", "unknown"),
            "step_count": len(commands),
            "failed_steps": failed,
            "skipped_steps": skipped,
            "missing_or_placeholder_inputs": missing_inputs,
        }

    def _report(
        self,
        *,
        result_dir: Union[str, Path],
        analysis_type: Optional[str],
    ) -> Dict[str, Any]:
        """Regenerate reports from a completed run directory.

        Reads ``execution_plan.json`` for context and calls the plugin's
        ``write_report()`` hook to produce markdown/HTML reports. The
        ``analysis_type`` is auto-detected from the plan when not provided.
        # 从已完成运行目录重新生成报告。
        # 读取 execution_plan.json 获取上下文, 调用插件 write_report() 生成报告。
        """
        root = Path(result_dir)
        plan_path = root / "execution_plan.json"
        if not plan_path.exists():
            raise ABIError(f"Missing execution plan: {plan_path}")
        plan_data = load_json_object(plan_path)
        plugin_id = analysis_type or str(plan_data.get("analysis_type") or "metagenomic_plasmid")
        plugin = get_plugin(plugin_id)
        outputs = plugin.write_report(plan_data, root)
        output_files = dict(outputs)
        return {
            "analysis_type": plugin_id,
            "outputs": output_files,
            "written_files": _path_values(output_files),
        }

    def _run(
        self,
        *,
        analysis_type: str,
        engine: str,
        config_path: Optional[Union[str, Path]],
        sample_sheet: Optional[Union[str, Path]],
        profile: str,
        mode: Optional[str],
        threads: Optional[int],
        outdir: Optional[str],
        log_dir: Optional[str],
        workflow: Optional[Union[str, Path]],
        work_dir: Optional[Union[str, Path]],
        nxf_home: Optional[Union[str, Path]],
        nextflow_bin: Optional[Union[str, Path]],
        nextflow_profile: Optional[str],
        executor: Optional[str],
        resume: bool,
        mamba_root: Optional[Union[str, Path]],
        smoke: bool,
        check_files: bool,
        confirm_execution: bool,
        resource_profile: Optional[str],
        cpu_override: Optional[int],
        memory_override: Optional[str],
        walltime_override: Optional[str],
        accelerator_override: Optional[str],
        container_image: Optional[str],
        container_runtime: Optional[str],
        scheduler: Optional[str],
        partition: Optional[str],
        account: Optional[str],
        qos: Optional[str],
        hpc_timeout_seconds: Optional[float],
        poll_interval_seconds: float,
    ) -> Dict[str, Any]:
        """Execute the plan on a real runtime (local, Nextflow, or native HPC).

        The ``confirm_execution`` safety gate is checked first: if False, a
        ``status="confirmation_required"`` dict is returned immediately so
        ``_call()`` can promote it to the proper envelope without side effects.
        # 在真实运行时上执行计划 (local 或 Nextflow)。
        # 首先检查 confirm_execution 安全闸门: 若为 False,
        # 立即返回 confirmation_required 字典, 无任何副作用。
        """
        runtime_engine = engine.lower().strip()
        if runtime_engine not in {"local", "nextflow", "hpc"}:
            raise ABIError(
                f"Unsupported runtime engine: {engine}. Expected local, nextflow, or hpc."
            )
        # Safety gate: require explicit user confirmation before execution.
        # 安全闸门: 执行前需要显式用户确认。
        if not confirm_execution:
            return {
                "status": "confirmation_required",
                "result": {
                    "analysis_type": analysis_type,
                    "engine": runtime_engine,
                    "message": "Re-run with confirm_execution=true after user approval.",
                },
            }

        overrides = _common_overrides(
            mode=mode,
            threads=threads,
            outdir=outdir,
            log_dir=log_dir,
            sample_sheet=sample_sheet,
            resource_profile=resource_profile,
            cpu_override=cpu_override,
            memory_override=memory_override,
            walltime_override=walltime_override,
            accelerator_override=accelerator_override,
            container_image=container_image,
            container_runtime=container_runtime,
        )
        # Smoke mode with local engine: force mock_tools so no real tools run.
        # Smoke 模式 + local 引擎: 强制 mock_tools, 不执行真实工具。
        if runtime_engine == "local" and smoke:
            overrides = overrides | {"mock_tools": True}

        plugin = get_plugin(analysis_type)
        cfg = plugin.load_config(_optional_path(config_path), profile=profile, overrides=overrides)
        plan = plugin.build_plan(cfg, check_files=check_files)
        options = RuntimeOptions(
            engine=runtime_engine,
            smoke=smoke,
            nextflow_bin=_optional_path(nextflow_bin),
            work_dir=_optional_path(work_dir),
            workflow=_optional_path(workflow),
            nxf_home=_optional_path(nxf_home),
            mamba_root=_optional_path(mamba_root),
            profile=nextflow_profile,
            executor=executor,
            resume=resume,
            resource_profile=resource_profile,
            cpu_override=cpu_override,
            memory_override=memory_override,
            walltime_override=walltime_override,
            accelerator_override=accelerator_override,
            container_image=container_image,
            container_runtime=container_runtime,
            scheduler=scheduler,
            partition=partition,
            account=account,
            qos=qos,
            timeout_seconds=hpc_timeout_seconds,
            poll_interval_seconds=poll_interval_seconds,
        )
        # Select runtime backend: LocalRuntime for subprocess execution,
        # NextflowRuntime for DSL2 pipeline orchestration.
        # 选择运行时后端: LocalRuntime 用于子进程执行, NextflowRuntime 用于 DSL2 管道编排。
        runtime: Any
        if runtime_engine == "local":
            runtime = LocalRuntime(plugin, options=options)
        elif runtime_engine == "hpc":
            from abi.runtimes import HpcRuntime

            runtime = HpcRuntime(plugin, options=options)
        else:
            runtime = NextflowRuntime(plugin, options=options)
        result = runtime.run(plan, cfg)
        return {
            "analysis_type": analysis_type,
            "engine": runtime_engine,
            "runtime_status": result.status,
            "return_code": result.return_code,
            "outputs": result.outputs,
            "written_files": _path_values(result.outputs),
        }

    def _export_nextflow(
        self,
        *,
        analysis_type: str,
        output: Union[str, Path],
        config_path: Optional[Union[str, Path]],
        sample_sheet: Optional[Union[str, Path]],
        profile: str,
        mode: Optional[str],
        threads: Optional[int],
        outdir: Optional[str],
        log_dir: Optional[str],
        smoke: bool,
        mamba_root: Optional[Union[str, Path]],
        check_files: bool,
    ) -> Dict[str, Any]:
        """Build plan and serialize it as a Nextflow DSL2 workflow file.

        Uses ``NextflowExporter`` to translate the ABI execution plan into a
        portable ``main.nf`` script with conda/mamba container directives.
        # 构建计划并序列化为 Nextflow DSL2 工作流文件。
        # 使用 NextflowExporter 将 ABI 执行计划转换为可移植的 main.nf 脚本。
        """
        plugin, cfg, plan = self._build_plan(
            analysis_type=analysis_type,
            config_path=config_path,
            sample_sheet=sample_sheet,
            profile=profile,
            mode=mode,
            threads=threads,
            outdir=outdir,
            log_dir=log_dir,
            check_files=check_files,
        )
        workflow_path = NextflowExporter().write(
            plan,
            cfg,
            plugin.registry(),
            output,
            smoke=smoke,
            mamba_root=_optional_path(mamba_root),
        )
        return {
            "analysis_type": analysis_type,
            "workflow": workflow_path,
            "steps": len(getattr(plan, "steps", [])),
            "smoke": smoke,
            "written_files": [workflow_path],
        }

    def _export_agent_context(self, *, analysis_type: str) -> Dict[str, Any]:
        """Delegate to ``abi.agent.context.build_agent_context`` for the plugin.

        Returns the compact machine-readable dictionary that agents embed in
        their system prompt to understand ABI capabilities without prior training.
        # 委托给 build_agent_context, 返回紧凑的机器可读字典,
        # 供 agent 嵌入 system prompt 以理解 ABI 能力。
        """
        plugin = get_plugin(analysis_type)
        return build_agent_context(plugin)

    def _doctor_agent(self, *, analysis_type: str) -> Dict[str, Any]:
        """Delegate to ``abi.agent.context.render_doctor_agent`` for the plugin.

        Returns a human-readable text block summarizing the operating guide.
        # 委托给 render_doctor_agent, 返回人类可读的操作指南文本。
        """
        plugin = get_plugin(analysis_type)
        return {"analysis_type": analysis_type, "text": render_doctor_agent(plugin)}

    def _query(
        self,
        *,
        analysis_type: str,
        what: str,
        step: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Handle lightweight metadata queries against plugin DAG and registry.

        Reads ``pipeline_dag.yaml`` (if present) and the tool registry to answer
        structural questions about the pipeline without constructing a full plan.
        """
        from abi.config import PLUGIN_ROOT

        plugin = get_plugin(analysis_type)

        # ── Load pipeline DAG (optional — not all plugins have one) ──────────
        dag_path = PLUGIN_ROOT / analysis_type / "pipeline_dag.yaml"
        dag: Optional[Dict[str, Any]] = None
        if dag_path.is_file():
            dag = yaml.safe_load(dag_path.read_text(encoding="utf-8")) or {}

        # ── Load tool registry ──────────────────────────────────────────────
        registry = plugin.registry()
        tools: List[Dict[str, Any]] = registry.list_tools()

        # ── Dispatch by query target ────────────────────────────────────────
        what_lower = what.strip().lower()

        if what_lower == "stages":
            return _query_stages(dag, tools, analysis_type)

        if what_lower == "tools":
            return _query_tools(dag, tools)

        if what_lower == "platforms":
            return _query_platforms(dag)

        if what_lower == "workflows":
            catalog_path = PLUGIN_ROOT / analysis_type / "workflows" / "catalog.yaml"
            if not catalog_path.is_file():
                return {"pipeline": analysis_type, "workflows": [], "workflow_count": 0}
            catalog = yaml.safe_load(catalog_path.read_text(encoding="utf-8")) or {}
            workflows = catalog.get("workflows", [])
            return {
                "pipeline": analysis_type,
                "workflows": workflows,
                "workflow_count": len(workflows),
            }

        if what_lower in ("resources", "inputs", "outputs"):
            if not step:
                raise ValueError(
                    f"--step is required for --what {what}. "
                    f"Use --step <node_id> to specify which pipeline node to query."
                )
            return _query_step(dag, tools, step, what_lower)

        raise ValueError(
            f"Unknown query target: {what!r}. "
            f"Valid targets: stages, tools, platforms, workflows, resources, inputs, outputs."
        )

    def _build_plan(
        self,
        *,
        analysis_type: str,
        config_path: Optional[Union[str, Path]],
        sample_sheet: Optional[Union[str, Path]],
        profile: str,
        mode: Optional[str],
        threads: Optional[int],
        outdir: Optional[str],
        log_dir: Optional[str],
        check_files: bool,
    ) -> Tuple[Any, Mapping[str, Any], Any]:
        """Shared plan construction: resolve plugin -> load config -> build plan.

        Returns the (plugin, config, plan) tuple so callers can use the plugin
        reference (e.g. for ``write_report`` or ``registry``) without reloading.
        # 共享的计划构建逻辑: 解析插件 -> 加载配置 -> 构建计划。
        # 返回 (plugin, config, plan) 三元组, 调用者可复用插件引用。
        """
        plugin = get_plugin(analysis_type)
        cfg = plugin.load_config(
            _optional_path(config_path),
            profile=profile,
            overrides=_common_overrides(
                mode=mode,
                threads=threads,
                outdir=outdir,
                log_dir=log_dir,
                sample_sheet=sample_sheet,
            ),
        )
        plan = plugin.build_plan(cfg, check_files=check_files)
        return plugin, cfg, plan


# ------------------------------------------------------------------
# Module-level helpers / 模块级辅助函数
# ------------------------------------------------------------------


def _optional_path(value: Optional[Union[str, Path]]) -> Optional[Path]:
    """Convert a string/Path to Path, preserving None for unset values.

    Used so that downstream code receives ``Path | None`` rather than
    ``str | None``, simplifying path-handling branches.
    # 将字符串/Path 转为 Path, 保留 None 表示未设置。
    # 下游代码接收 Path | None 而非 str | None, 简化路径处理分支。
    """
    return Path(value) if value is not None else None


def _path_values(outputs: Mapping[str, Any]) -> list[Any]:
    """Collect non-None values from an outputs mapping.

    Used to build the ``written_files`` list that agents can consume directly
    without filtering None placeholders.
    # 从 outputs 映射中收集非 None 值。
    # 用于构建 written_files 列表, agent 无需自行过滤 None 占位符。
    """
    return [value for value in outputs.values() if value is not None]


def _build_plan_summary(plan: Any, analysis_type: str) -> Dict[str, Any]:
    """Extract a lightweight pipeline summary for agent consumption.

    Instead of requiring agents to read the full ``execution_plan.json``
    (which can be 5,000+ tokens for complex pipelines), this produces a
    compact summary with stages, key tools, and platforms — enough for
    an LLM to understand the workflow shape without reading the file.

    Design decisions:
    - ``stages`` are derived from ``PlanStep.category``, which every plugin
      sets when building its plan. Order follows first appearance.
    - ``key_tools`` picks the first tool in each stage, giving a
      representative tool per pipeline phase.
    - ``platforms`` are aggregated from the plan's sample inputs.

    # 从执行计划中提取轻量级流水线摘要供智能体消费。
    # 智能体无需读取完整的 execution_plan.json（复杂流水线可能 5,000+ tokens），
    # 此摘要提供 stages/key_tools/platforms，足以让 LLM 理解工作流结构。
    """
    steps = getattr(plan, "steps", []) or []

    # Unique categories in first-appearance order.
    seen: set = set()
    stages: list = []
    key_tools: list = []
    for step in steps:
        cat = (getattr(step, "category", "") or "").strip()
        if cat and cat not in seen:
            seen.add(cat)
            stages.append(cat)
            key_tools.append(getattr(step, "tool_id", ""))

    # Platforms from sample inputs.
    samples = getattr(plan, "samples", []) or []
    platforms: list = list(dict.fromkeys(getattr(s, "platform", "generic") for s in samples))

    return {
        "pipeline": analysis_type,
        "stages": stages,
        "key_tools": key_tools,
        "platforms": platforms,
    }


# ------------------------------------------------------------------
# Query helpers — used by _query() for lightweight metadata lookups
# ------------------------------------------------------------------


def _query_stages(
    dag: Optional[Dict[str, Any]],
    tools: List[Dict[str, Any]],
    analysis_type: str,
) -> Dict[str, Any]:
    """Extract ordered pipeline stages from the DAG or tool registry.

    Prefers DAG ``nodes`` (each node has a ``category`` field). Falls back
    to deduplicating ``category`` from tool registry entries.
    """
    nodes = (dag or {}).get("nodes", {})
    if nodes:
        seen: set = set()
        stages: list = []
        for _node_id, node in nodes.items():
            cat = str(node.get("category", "")).strip()
            if cat and cat not in seen:
                seen.add(cat)
                stages.append(cat)
        return {
            "pipeline": analysis_type,
            "stages": stages,
            "stage_count": len(stages),
        }

    # Fallback: derive stages from tool registry categories.
    seen = set()
    stages = []
    for tool in tools:
        cat = str(tool.get("category", "")).strip()
        if cat and cat not in seen:
            seen.add(cat)
            stages.append(cat)
    return {
        "pipeline": analysis_type,
        "stages": stages,
        "stage_count": len(stages),
    }


def _query_tools(
    dag: Optional[Dict[str, Any]],
    tools: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Return all tools grouped by category."""
    nodes = (dag or {}).get("nodes", {})
    if nodes:
        # DAG-based: map node_id → tool metadata
        result_tools: list = []
        for node_id, node in nodes.items():
            result_tools.append(
                {
                    "step_id": node_id,
                    "tool_id": node.get("tool_id", node_id),
                    "category": node.get("category", ""),
                    "optional": node.get("optional", False),
                    "depends_on": node.get("depends_on", []),
                }
            )
        return {"tools": result_tools, "tool_count": len(result_tools)}

    # Fallback: from tool registry
    result_tools = [
        {
            "tool_id": t.get("id", ""),
            "category": t.get("category", ""),
            "description": t.get("description", ""),
        }
        for t in tools
    ]
    return {"tools": result_tools, "tool_count": len(result_tools)}


def _query_platforms(dag: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Return supported platforms from the DAG."""
    platforms = (dag or {}).get("platforms", [])
    return {"platforms": list(platforms) if platforms else []}


def _query_step(
    dag: Optional[Dict[str, Any]],
    tools: List[Dict[str, Any]],
    step: str,
    what: str,
) -> Dict[str, Any]:
    """Return inputs/outputs/resources for a specific pipeline node."""
    nodes = (dag or {}).get("nodes", {})
    if step in nodes:
        node = nodes[step]
        result: Dict[str, Any] = {"step_id": step, "tool_id": node.get("tool_id", step)}
        if what in ("inputs", "resources"):
            result["inputs"] = node.get("inputs", {})
        if what in ("outputs", "resources"):
            result["outputs"] = node.get("outputs", {})
        return result

    # Fallback: search tool registry for matching tool_id
    for tool in tools:
        if tool.get("id") == step:
            result = {"step_id": step, "tool_id": step}
            if what in ("inputs", "resources"):
                result["inputs"] = tool.get("inputs", {})
            if what in ("outputs", "resources"):
                result["outputs"] = tool.get("outputs", {})
            return result

    raise ValueError(f"Step {step!r} not found in pipeline DAG or tool registry.")
