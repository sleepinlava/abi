"""Generic ABI plan executor.

The executor is the central orchestration engine of the ABI pipeline. It takes
a fully-resolved execution plan and a plugin configuration, then:

1. Creates the output directory structure (outdir, provenance/, tables/).
2. Persists the plan and resolved config as provenance artifacts.
3. Iterates through plan steps, executing each one via the ToolRegistry.
4. Captures diagnostic context on tool failures (exit code, stderr path,
   suggested remediation) and stores it in standardized provenance tables.
5. Writes table-format outputs (TSV) through the StandardTableManager.
6. Generates a human-readable report and a machine-readable run summary.
7. Records pipeline progress events (when progress recording is enabled).

The executor supports two modes via the ``dry_run`` parameter:

- **Dry run** (``dry_run=True``): Steps are planned but external tools are
  never invoked. Instead, each step's ``_command_for_step`` builds the command
  that *would* be run, and the provenance tables reflect "dry_run" status.
  This mode is used by ``abi dry-run`` to validate plans without side effects.

- **Real run** (``dry_run=False``): External tools are invoked via
  ``ToolSkill.run()``. stdout/stderr are captured to step-specific log files,
  outputs are parsed into standard tables, and non-zero exit codes are wrapped
  as ``ToolError`` with full diagnostic detail. The first failing step stops
  the pipeline (fail-fast semantics).

Step execution flow (``_execute_step`` -> ``_run_external_step``):

  1. ``_command_for_step`` builds the shell command for the step.
  2. ``_params_for_step`` merges inputs, params, and outputs into a single
     parameter dictionary with ``output_dir`` normalization.
  3. If the tool is registered and not skipped, ``_run_external_step``
     instantiates a ``ToolSkill``, calls ``skill.run(params)``, and captures
     the result.
  4. On success (return_code == 0), ``parse_outputs`` extracts structured
     data from tool output files and ``StandardTableManager.append_rows``
     writes them to the standard tables directory.
  5. On failure, a ``ToolError`` is raised with a reason string that includes
     step_id, tool_id, exit_code, stderr/stdout paths, and suggested checks.

Error handling philosophy:

- ``ToolError`` is the canonical error type for all tool-level failures.
  It is captured with rich diagnostic context via ``_tool_failure_reason``.
- The executor does **not** retry failed steps; it halts on the first error
  and raises the ``ToolError`` after writing all available provenance.
- All provenance artifacts (commands.tsv, tool_versions.tsv, run_summary.json,
  etc.) are written even when the pipeline fails, so post-mortem inspection
  is always possible.

Provenance artifacts written to ``<outdir>/provenance/``:

==========================  ===================================================
Artifact                    Purpose
==========================  ===================================================
config.resolved.yaml        Fully-resolved plugin configuration.
resolved_inputs.tsv         Input file paths with existence checks.
commands.tsv                Per-step command, status, return code, reason.
tool_versions.tsv           Tool executables with installation status.
resources.json              Resource availability records.
environment.yml             Mamba root and tool environment listing.
run_summary.json            Machine-readable run metadata.
step_logs/*.stdout.log      Captured stdout for each external step.
step_logs/*.stderr.log      Captured stderr for each external step.
progress.json / events.json Pipeline progress snapshot (when enabled).
==========================  ===================================================

Generic executer — the orchestration engine for ABI pipelines.

执行器是 ABI 管线的核心编排引擎。它接收一个完全解析好的执行计划和插件配置，然后：
1. 创建输出目录结构。
2. 将计划和解析后的配置持久化为溯源产物。
3. 遍历计划步骤，通过 ToolRegistry 执行每个步骤。
4. 在工具失败时捕获诊断上下文，并存储到标准化的溯源表中。
5. 通过 StandardTableManager 写出表格格式的输出。
6. 生成可读报告和机器可读的运行摘要。
7. 记录管线进度事件。

支持两种模式：dry_run 模式仅构建命令但不实际执行；真实运行模式则调用外部工具，
捕获标准输出/错误，并将输出解析为标准表格。第一步失败即停止（fail-fast）。

步骤执行流程：构建命令 -> 合并参数 -> 运行外部工具 -> 解析输出 -> 写入标准表格。
错误处理：ToolError 是标准错误类型，附带 step_id、tool_id、exit_code、日志路径等诊断信息。
溯源产物始终写出，确保即使管线失败也可以进行事后检查。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Mapping

from abi._shared import _display_command
from abi.config import resolved_mamba_root, write_yaml
from abi.errors import ToolError
from abi.filesystem import ensure_directory
from abi.provenance import (
    PipelineProgressRecorder,
    RunLogger,
    write_commands_tsv,
    write_minimal_progress_artifacts,
    write_resolved_inputs_tsv,
)
from abi.report import write_generic_report
from abi.tables import StandardTableManager
from abi.tools import ToolRegistry


class GenericABIExecutor:
    """Executor for ABI plugins that only need generic command orchestration.

    This is the default executor used by most plugins. It handles the full
    lifecycle: plan deserialization -> step iteration -> tool invocation ->
    output parsing -> provenance artifact generation.

    ABI 插件的通用执行器，处理完整生命周期：计划反序列化 -> 步骤遍历 ->
    工具调用 -> 输出解析 -> 溯源产物生成。
    """

    def __init__(
        self,
        registry: ToolRegistry,
        logger: RunLogger,
        *,
        table_manager: StandardTableManager,
        parse_outputs: Callable[[str, str | Path, str], Mapping[str, Iterable[Mapping[str, Any]]]],
        report_title: str = "ABI Report",
        mock_tools: bool = False,
    ) -> None:
        # ToolRegistry provides tool discovery and instantiation.
        # ToolRegistry 提供工具发现和实例化。
        self.registry = registry
        # RunLogger writes structured per-step log lines.
        # RunLogger 写出结构化的每步日志行。
        self.logger = logger
        # StandardTableManager creates and populates standardized TSV tables.
        # StandardTableManager 创建并填充标准化的 TSV 表格。
        self.table_manager = table_manager
        # Callable that parses tool output files into table-name -> rows mappings.
        # 将工具输出文件解析为 表名->行 映射的可调用对象。
        self.parse_outputs = parse_outputs
        # Title used in the human-readable report header.
        # 用于可读报告标题的标题。
        self.report_title = report_title
        # When True, tools run with mock wrappers (no real computation).
        # 为 True 时，工具使用 mock 包装器运行（不执行真实计算）。
        self.mock_tools = mock_tools

    def dry_run(self, plan: Any, config: Mapping[str, Any]) -> Dict[str, Path]:
        """Execute a dry run — plan and validate without invoking real tools.

        Delegates to ``run()`` with ``dry_run=True``. All provenance artifacts
        are written but external tool commands are never executed.

        执行预演运行——在不调用真实工具的情况下规划和验证。
        委托给 ``run()`` 并设置 ``dry_run=True``。
        所有溯源产物都会写出，但外部工具命令不会实际执行。
        """
        return self.run(plan, config, dry_run=True)

    def run(
        self,
        plan: Any,
        config: Mapping[str, Any],
        *,
        dry_run: bool = False,
    ) -> Dict[str, Path]:
        """Execute a plan and write all provenance artifacts.

        This is the main entry point. It orchestrates the entire pipeline:

        1. Ensures output directory structure (outdir/, provenance/, tables/).
        2. Writes the execution plan JSON and resolved config YAML.
        3. Resolves input file paths and writes a resolved_inputs.tsv.
        4. Iterates over plan steps, executing each via ``_execute_step``.
        5. On the first failure, records the error and breaks (fail-fast).
        6. Writes all remaining provenance artifacts regardless of outcome.
        7. Returns a mapping of artifact labels to file paths.

        Returns a dict with keys: plan, config, commands, resolved_inputs,
        tool_versions, resources, environment, summary, tables, report,
        report_html, log, progress, progress_events.

        Raises ``ToolError`` if any step failed.

        执行计划并写出所有溯源产物。这是主入口点，编排整个管线：
        1. 确保输出目录结构。
        2. 写出执行计划 JSON 和解析后的配置 YAML。
        3. 解析输入文件路径并写出 resolved_inputs.tsv。
        4. 遍历计划步骤，通过 ``_execute_step`` 执行每个步骤。
        5. 遇到第一个失败时记录错误并停止（fail-fast）。
        6. 无论结果如何，写出所有剩余的溯源产物。
        7. 返回产物标签到文件路径的映射。

        如果任何步骤失败，抛出 ``ToolError``。
        """
        # Create the three-tier output directory structure.
        # 创建三层输出目录结构。
        outdir = ensure_directory(plan.outdir, label="Output directory")
        provenance = ensure_directory(outdir / "provenance", label="Provenance directory")
        tables_dir = ensure_directory(outdir / "tables", label="Standard tables directory")
        self.table_manager.ensure_tables(tables_dir)
        # Pre-create per-step output directories so tools don't fail on missing dirs.
        # 预先创建每个步骤的输出目录，避免工具因缺少目录而失败。
        self._ensure_step_output_dirs(plan.steps)

        # Persist the plan so it can be inspected later (e.g., by `abi inspect`).
        # 持久化计划，以便后续检查（例如通过 `abi inspect`）。
        plan_path = outdir / "execution_plan.json"
        plan_path.write_text(
            json.dumps(plan.to_dict(), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        # Write the fully-resolved config, with all profiles and overrides merged.
        # 写出完全解析后的配置，所有 profile 和覆盖项已合并。
        config_path = write_yaml(config, provenance / "config.resolved.yaml")
        # Resolve input file paths, checking whether each file actually exists.
        # 解析输入文件路径，检查每个文件是否实际存在。
        resolved_inputs_path = write_resolved_inputs_tsv(
            self._resolved_input_rows(plan, dry_run=dry_run),
            provenance / "resolved_inputs.tsv",
        )

        # Determine whether to record structured pipeline progress events.
        # Progress recording is enabled when config.execution.progress is True
        # or when the dashboard is enabled (which needs progress events).
        # 确定是否记录结构化的管线进度事件。
        # 当 config.execution.progress 为 True 或启用了 dashboard 时启用进度记录。
        execution = _execution_options(config)
        progress_recorder = (
            PipelineProgressRecorder(provenance) if bool(execution["record_progress"]) else None
        )
        if progress_recorder:
            # Emit a start_run event so downstream dashboards can track the run.
            # 发出 start_run 事件，供下游 dashboard 跟踪运行。
            progress_recorder.start_run(
                plan,
                dry_run=dry_run,
                parallel=False,
                workers=1,
            )

        # Execute each step sequentially, collecting command metadata rows.
        # With fail-fast semantics: the first failing step stops iteration.
        # 顺序执行每个步骤，收集命令元数据行。
        # 采用 fail-fast 语义：第一个失败的步骤停止迭代。
        command_rows = []
        failed_error: ToolError | None = None
        _last_step_id = "unknown"
        try:
            for step in plan.steps:
                _last_step_id = getattr(step, "tool_id", str(step))
                row, error = self._execute_step(
                    step,
                    dry_run=dry_run,
                    provenance=provenance,
                    tables_dir=tables_dir,
                    progress_recorder=progress_recorder,
                )
                command_rows.append(row)
                if error:
                    failed_error = error
                    break
        except Exception as exc:
            if not failed_error:
                failed_error = ToolError(f"Unexpected error during {_last_step_id}: {exc}")
                failed_error.__cause__ = exc

        # Summarize which standard tables were populated.
        # 汇总哪些标准表格已被填充。
        table_summary = self.table_manager.summarize(tables_dir)

        # Write all provenance artifacts — always, even on failure.
        # This ensures post-mortem diagnostics are available.
        # 写出所有溯源产物——即使失败也始终写出，确保事后诊断可用。
        commands_path = write_commands_tsv(command_rows, provenance / "commands.tsv")
        versions_path = self._write_tool_versions(provenance / "tool_versions.tsv")
        resources_path = self._write_resources(config, provenance / "resources.json")
        environment_path = self._write_environment(provenance / "environment.yml")
        report_paths = write_generic_report(
            plan,
            outdir,
            table_summary=table_summary,
            title=self.report_title,
        )

        # Finalize progress recording with the run status.
        # 以运行状态完成进度记录。
        run_status = "failed" if failed_error else "success"
        if progress_recorder:
            progress_recorder.finish_run(status=run_status)
            progress_paths = progress_recorder.paths
        else:
            # When progress recording is disabled, write a minimal static snapshot
            # so the run summary still has progress_file references.
            # 当进度记录被禁用时，写出最小的静态快照，
            # 以便运行摘要仍然有 progress_file 引用。
            progress_paths = write_minimal_progress_artifacts(
                provenance,
                plan,
                dry_run=dry_run,
                parallel=False,
                workers=1,
                status=run_status,
                command_rows=command_rows,
            )

        # Write the machine-readable run summary — the primary artifact that
        # downstream consumers (agents, dashboards, job service) read.
        # 写出机器可读的运行摘要——下游消费者（agent、dashboard、job service）读取的主要产物。
        summary_path = provenance / "run_summary.json"
        summary_path.write_text(
            json.dumps(
                {
                    "project_name": plan.project_name,
                    "analysis_type": getattr(plan, "analysis_type", ""),
                    "dry_run": dry_run,
                    "sample_count": len(plan.samples),
                    "step_count": len(plan.steps),
                    "completed_step_count": len(command_rows),
                    "status": run_status,
                    "parallel": False,
                    "workers": 1,
                    "selected_tools": plan.selected_tools,
                    "standard_tables": table_summary,
                    "progress_file": str(progress_paths["snapshot"]),
                    "progress_events": str(progress_paths["events"]),
                    "log_file": str(self.logger.log_file),
                },
                indent=2,
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )

        # Build the outputs dict — the primary return value consumed by the CLI
        # and by the ABIAgentInterface.dispatch path.
        # 构建输出字典——CLI 和 ABIAgentInterface.dispatch 路径使用的主要返回值。
        outputs = {
            "plan": plan_path,
            "config": config_path,
            "commands": commands_path,
            "resolved_inputs": resolved_inputs_path,
            "tool_versions": versions_path,
            "resources": resources_path,
            "environment": environment_path,
            "summary": summary_path,
            "tables": tables_dir,
            "report": report_paths["report"],
            "report_html": report_paths["report_html"],
            "log": self.logger.log_file,
            "progress": progress_paths["snapshot"],
            "progress_events": progress_paths["events"],
        }
        # Raise after writing all artifacts so callers can inspect provenance
        # even for failed runs.
        # 在写出所有产物后抛出，以便调用者即使对失败的运行也能检查溯源。
        if failed_error:
            raise failed_error
        return outputs

    def _execute_step(
        self,
        step: Any,
        *,
        dry_run: bool,
        provenance: Path,
        tables_dir: Path,
        progress_recorder: PipelineProgressRecorder | None,
    ) -> tuple[Dict[str, Any], ToolError | None]:
        """Execute a single plan step and return its metadata row.

        The step lifecycle:
        1. Compute the display command via ``_command_for_step``.
        2. If the step is skipped (``step.skipped``), mark it skipped.
        3. If ``dry_run`` or the tool is ``"internal"``, do nothing further.
        4. If the tool is not registered, mark it failed immediately.
        5. Otherwise, delegate to ``_run_external_step`` for real execution.

        Returns a (row_dict, error_or_none) tuple. The row dict contains
        step metadata for commands.tsv; the error is non-None only on failure.

        执行单个计划步骤并返回其元数据行。

        步骤生命周期：
        1. 通过 ``_command_for_step`` 计算显示命令。
        2. 如果步骤被跳过，标记为 skipped。
        3. 如果是 dry_run 或工具为 "internal"，不执行进一步操作。
        4. 如果工具未注册，立即标记为 failed。
        5. 否则，委托给 ``_run_external_step`` 进行真实执行。

        返回 (row_dict, error_or_none) 元组。row 字典包含用于 commands.tsv 的步骤元数据；
        error 仅在失败时非 None。
        """
        # Build the shell command for display/logging purposes.
        # 构建 shell 命令用于显示和日志记录。
        command = self._command_for_step(step, dry_run=dry_run)
        status = "dry_run" if dry_run else "success"
        reason = step.reason or ""
        return_code: int | str = ""
        parsed_status = ""
        standard_tables = ""
        failed_error: ToolError | None = None

        # Notify progress recorder that a step is starting.
        # 通知进度记录器步骤开始。
        if progress_recorder:
            progress_recorder.step_started(step)

        # Dispatch based on step state. The ordering matters:
        # skipped > dry_run/internal > unregistered > real execution.
        # 根据步骤状态进行分发。顺序很重要：
        # skipped > dry_run/internal > 未注册 > 真实执行。
        if step.skipped:
            # Step was explicitly skipped (e.g., already completed in a prior run).
            # 步骤被显式跳过（例如在之前的运行中已完成）。
            status = "skipped"
        elif dry_run or step.tool_id == "internal":
            # In dry_run mode, we never invoke external tools.
            # "internal" tools are handled by the plan itself (no external process).
            # 在 dry_run 模式下，我们从不调用外部工具。
            # "internal" 工具由计划本身处理（无外部进程）。
            pass
        elif not self.registry.has(step.tool_id):
            # Tool not found in the registry — fail immediately with a clear reason.
            # 在注册表中找不到工具——立即以明确原因失败。
            status = "failed"
            reason = f"Tool {step.tool_id!r} is not registered"
            failed_error = ToolError(reason)
        else:
            # Real execution path: invoke the external tool.
            # 真实执行路径：调用外部工具。
            result = self._run_external_step(step, provenance, tables_dir)
            status = str(result["status"])
            return_code = result["return_code"]
            reason = str(result["reason"])
            parsed_status = str(result.get("parsed_status", ""))
            standard_tables = str(result.get("standard_tables", ""))
            if status != "success":
                # Wrap non-success results in a ToolError for upstream handling.
                # 将非成功结果包装为 ToolError 供上游处理。
                failed_error = ToolError(reason)

        # Assemble the standardized command metadata row for commands.tsv.
        # 组装用于 commands.tsv 的标准化命令元数据行。
        row = {
            "step_id": step.step_id,
            "sample_id": step.sample_id,
            "step_name": step.step_name,
            "tool_id": step.tool_id,
            "category": step.category,
            "command": _display_command(command),
            "status": status,
            "return_code": return_code,
            "reason": reason,
            "parsed_status": parsed_status,
            "standard_tables": standard_tables,
        }
        # Log the step outcome to the structured run log.
        # 将步骤结果记录到结构化运行日志中。
        self.logger.log_step(step, command=command, status=status, error_message=reason)
        if progress_recorder:
            progress_recorder.step_completed(
                step,
                status=status,
                reason=reason,
                return_code=return_code,
                parsed_status=parsed_status,
                standard_tables=standard_tables,
            )
        return row, failed_error

    def _run_external_step(self, step: Any, provenance: Path, tables_dir: Path) -> Dict[str, Any]:
        """Run an external tool and parse its outputs into standard tables.

        Data flow:
        1. Instantiate a ``ToolSkill`` from the registry for the tool_id.
        2. Build parameter dict with stdout/stderr paths pointing to step log files.
        3. Call ``skill.run(params)``.
        4. If the tool raises ``ToolError`` or returns a non-zero exit code,
           capture the failure reason with diagnostic paths and return early.
        5. On success, call ``self.parse_outputs`` to extract structured data
           from tool output files, then write rows via ``StandardTableManager``.

        Returns a dict with keys: status, return_code, reason, parsed_status,
        standard_tables.

        运行外部工具并将其输出解析为标准表格。

        数据流：
        1. 从注册表为 tool_id 实例化一个 ``ToolSkill``。
        2. 构建参数字典，stdout/stderr 路径指向步骤日志文件。
        3. 调用 ``skill.run(params)``。
        4. 如果工具抛出 ``ToolError`` 或返回非零退出码，
           捕获失败原因及诊断路径并提前返回。
        5. 成功时，调用 ``self.parse_outputs`` 从工具输出文件中提取结构化数据，
           然后通过 ``StandardTableManager`` 写入行。

        返回包含 status、return_code、reason、parsed_status、standard_tables 键的字典。
        """
        # Create the ToolSkill instance. mock_tools=True means smoke/mock wrappers.
        # 创建 ToolSkill 实例。mock_tools=True 表示使用 smoke/mock 包装器。
        skill = self.registry.create(step.tool_id, mock_tools=self.mock_tools)
        step_log_dir = provenance / "step_logs"
        # Merge step inputs, params, and outputs into a single parameter dict.
        # 将步骤的 inputs、params 和 outputs 合并为单个参数字典。
        params = self._params_for_step(step, dry_run=False)
        # Route stdout and stderr to per-step log files under provenance/step_logs/.
        # This ensures output is captured for diagnostics even if the tool crashes.
        # 将 stdout 和 stderr 路由到 provenance/step_logs/ 下的每步日志文件。
        # 这确保即使工具崩溃也能捕获输出用于诊断。
        params["stdout_path"] = str(step_log_dir / f"{step.step_id}.stdout.log")
        params["stderr_path"] = str(step_log_dir / f"{step.step_id}.stderr.log")
        try:
            result = skill.run(params, dry_run=False)
        except ToolError as exc:
            # The tool itself raised an error (e.g., command not found, env failure).
            # 工具本身抛出了错误（例如命令未找到、环境失败）。
            reason = _tool_failure_reason(
                step,
                return_code="",
                stderr_path=params["stderr_path"],
                message=str(exc),
            )
            return {"status": "failed", "return_code": "", "reason": reason}
        if result.return_code != 0:
            # The tool ran but exited with a non-zero code.
            # 工具运行了但以非零代码退出。
            reason = _tool_failure_reason(
                step,
                return_code=result.return_code,
                stderr_path=str(result.outputs.get("stderr_path", params["stderr_path"])),
                stdout_path=str(result.outputs.get("stdout_path", params["stdout_path"])),
            )
            return {
                "status": "failed",
                "return_code": result.return_code,
                "reason": reason,
            }

        # Parse tool outputs into structured table data.
        # The parse_outputs callback is plugin-specific and understands each tool's
        # output format (e.g., CSV columns, TSV files, JSON).
        # 将工具输出解析为结构化表格数据。
        # parse_outputs 回调是插件特定的，理解每个工具的输出格式。
        rows_by_table = self.parse_outputs(
            step.tool_id,
            step.outputs.get("output_dir", params.get("output_dir", "")),
            str(step.sample_id or ""),
        )
        # Append the parsed rows to the standard tables directory.
        # 将解析后的行追加到标准表格目录中。
        written = self.table_manager.append_rows(tables_dir, rows_by_table)
        return {
            "status": result.status,
            "return_code": result.return_code,
            "reason": "",
            "parsed_status": "parsed" if written else "no_standard_rows",
            "standard_tables": ",".join(sorted(written)),
        }

    def _command_for_step(self, step: Any, *, dry_run: bool) -> List[str]:
        """Build the shell command tokens for a step.

        For ``"internal"`` tools, this returns a synthetic ``abi internal`` command.
        For missing tools, it returns a placeholder ``abi missing-wrapper`` command
        so the plan is still inspectable.
        For registered tools, it delegates to ``ToolSkill.build_command()``.

        In dry_run mode, tools are created with ``mock_tools=True`` so the command
        reflects the mock wrapper rather than the real executable.

        为步骤构建 shell 命令令牌。

        对于 "internal" 工具，返回合成的 ``abi internal`` 命令。
        对于缺失的工具，返回占位符 ``abi missing-wrapper`` 命令，
        以便计划仍然可检查。
        对于已注册的工具，委托给 ``ToolSkill.build_command()``。

        在 dry_run 模式下，工具以 ``mock_tools=True`` 创建，
        因此命令反映的是 mock 包装器而非真实可执行文件。
        """
        if step.tool_id == "internal":
            # Internal steps have no external tool; synthesize a representative command.
            # 内部步骤没有外部工具；合成一个代表性命令。
            return ["abi", "internal", step.step_name, "--step-id", step.step_id]
        if not self.registry.has(step.tool_id):
            # Placeholder so the plan is still readable even with missing tools.
            # 占位符，以便即使工具缺失计划仍然可读。
            return ["abi", "missing-wrapper", step.tool_id, "--step-id", step.step_id]
        # For dry runs, use mock_tools=True so the command shows a mock wrapper.
        # 对于 dry run，使用 mock_tools=True，使命令显示 mock 包装器。
        skill = self.registry.create(step.tool_id, mock_tools=self.mock_tools or dry_run)
        return skill.build_command(self._params_for_step(step, dry_run=dry_run))

    def _params_for_step(self, step: Any, *, dry_run: bool) -> Dict[str, Any]:
        """Merge step inputs, params, and outputs into a single parameter dictionary.

        The merge order is: step.inputs -> step.params -> step.outputs.
        Later keys override earlier ones. This gives outputs (user-configurable
        paths) priority over inputs (which come from the sample sheet).

        Normalizes ``outdir`` to ``output_dir`` for tools that expect the latter key.

        Injects ``dry_run`` into the params so tools can adjust behavior.

        将步骤的 inputs、params 和 outputs 合并为单个参数字典。

        合并顺序为：step.inputs -> step.params -> step.outputs。
        后面的键会覆盖前面的键。这使 outputs（用户可配置路径）
        优先于 inputs（来自样本表）。

        为期望 ``output_dir`` 键的工具将 ``outdir`` 规范化为 ``output_dir``。

        将 ``dry_run`` 注入参数中，以便工具可以调整行为。
        """
        params = dict(step.inputs)
        params.update(step.params)
        params.update(step.outputs)
        # Normalize outdir -> output_dir for tools that expect the standard key.
        # 为期望标准键的工具将 outdir 规范化为 output_dir。
        if "output_dir" not in params and "outdir" in params:
            params["output_dir"] = params["outdir"]
        params["dry_run"] = dry_run
        return params

    def _resolved_input_rows(self, plan: Any, *, dry_run: bool) -> List[Dict[str, Any]]:
        """Resolve input file paths for all steps and record their existence.

        Scans each step's merged parameters for known path-like fields (read1,
        read2, assembly, reference, etc.) and records:
        - The absolute path.
        - Whether the file/directory exists on disk.
        - Whether the value came from the sample sheet or from config/plan defaults.

        The ``source`` field helps diagnose configuration issues: paths from the
        sample sheet are annotated ``"sample"``; all others are ``"config_or_plan"``.

        This data powers the resolved_inputs.tsv provenance artifact and the
        ``abi inspect`` command.

        为所有步骤解析输入文件路径并记录其存在性。

        扫描每个步骤合并后的参数中已知的类路径字段（read1、read2、assembly、reference 等），
        并记录：
        - 绝对路径。
        - 文件/目录在磁盘上是否存在。
        - 值来自样本表还是来自配置/计划默认值。

        ``source`` 字段有助于诊断配置问题：来自样本表的路径标注为 ``"sample"``；
        其他所有路径标注为 ``"config_or_plan"``。

        此数据为 resolved_inputs.tsv 溯源产物和 ``abi inspect`` 命令提供数据。
        """
        rows = []
        # These are the known field names that carry file paths.
        # 这些是携带文件路径的已知字段名。
        path_fields = {
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
        }
        for step in plan.steps:
            params = self._params_for_step(step, dry_run=dry_run)
            for name in sorted(path_fields):
                value = params.get(name)
                if not value:
                    continue
                path = Path(str(value))
                rows.append(
                    {
                        "step_id": step.step_id,
                        "tool_id": step.tool_id,
                        "sample_id": step.sample_id or "",
                        "input_name": name,
                        "path": str(path),
                        "exists": path.exists(),
                        # Tag the origin so users can trace where each path came from.
                        # 标记来源，以便用户可以追踪每个路径的来源。
                        "source": (
                            "sample"
                            if name in step.inputs and str(step.inputs.get(name)) == str(value)
                            else "config_or_plan"
                        ),
                    }
                )
        return rows

    def _write_tool_versions(self, path: Path) -> Path:
        """Write a TSV file recording every tool's executable and installation status.

        Iterates over all tools in the registry, instantiates each skill, and
        checks installation status via ``skill.check_installation()``.

        This artifact is critical for reproducibility: it captures exactly which
        tools were available and whether they were installed at execution time.

        写出记录每个工具的可执行文件和安装状态的 TSV 文件。

        遍历注册表中的所有工具，实例化每个 skill，并通过
        ``skill.check_installation()`` 检查安装状态。

        此产物对可复现性至关重要：它精确记录了哪些工具可用以及它们在执行时是否已安装。
        """
        rows = []
        for tool in self.registry.list_tools():
            skill = self.registry.create(str(tool.get("id")), mock_tools=self.mock_tools)
            rows.append(
                {
                    "tool_id": tool.get("id"),
                    "executable": tool.get("executable", ""),
                    "env_name": tool.get("env_name", ""),
                    # Version string is left empty here; plugins can populate it.
                    # 版本字符串在此留空；插件可以填充它。
                    "version": "",
                    "status": "ok" if skill.check_installation() else "missing",
                }
            )
        path.parent.mkdir(parents=True, exist_ok=True)
        fields = ["tool_id", "executable", "env_name", "version", "status"]
        # Write manually (not via csv module) to keep the format consistent with
        # other TSV artifacts in the provenance directory.
        # 手动写入（非通过 csv 模块），以保持与溯源目录中其他 TSV 产物格式一致。
        with path.open("w", encoding="utf-8") as handle:
            handle.write("\t".join(fields) + "\n")
            for row in rows:
                handle.write("\t".join(str(row.get(field, "")) for field in fields) + "\n")
        return path

    def _write_resources(self, config: Mapping[str, Any], path: Path) -> Path:
        """Write a JSON file recording resource availability.

        Delegates to ``ToolRegistry.check_tools()`` which checks database,
        index, and model resources needed by each tool.

        写出记录资源可用性的 JSON 文件。

        委托给 ``ToolRegistry.check_tools()``，后者检查每个工具所需的数据库、
        索引和模型资源。
        """
        rows = self.registry.check_tools(mock_tools=self.mock_tools, config=config)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"resources": rows}, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        return path

    def _write_environment(self, path: Path) -> Path:
        """Write a YAML file describing the compute environment.

        Records the mamba root path and a listing of all tools with their
        environment names and executables. This is used for environment
        reproduction and debugging.

        写出描述计算环境的 YAML 文件。

        记录 mamba 根路径以及所有工具及其环境名称和可执行文件的列表。
        用于环境复现和调试。
        """
        environment = {
            "mamba_root": str(resolved_mamba_root()),
            "tools": [
                {
                    "tool_id": tool.get("id", ""),
                    "env_name": tool.get("env_name", ""),
                    "executable": tool.get("executable", ""),
                }
                for tool in self.registry.list_tools()
            ],
        }
        return write_yaml(environment, path)

    @staticmethod
    def _ensure_step_output_dirs(steps: Iterable[Any]) -> None:
        """Pre-create output directories for all steps.

        For each step's outputs, if the output path has a file extension suffix,
        create its parent directory; otherwise create the path itself as a directory.

        This is called before any step executes, so tools don't fail because
        their expected output directory doesn't exist yet.

        为所有步骤预创建输出目录。

        对于每个步骤的输出，如果输出路径有文件扩展名后缀，
        则创建其父目录；否则将路径本身作为目录创建。

        这在任何步骤执行之前调用，因此工具不会因其预期的输出目录尚不存在而失败。
        """
        for step in steps:
            for output_path in step.outputs.values():
                if output_path is None:
                    continue
                path = Path(str(output_path))
                if path.suffix:
                    # Path has a file extension (e.g., /out/results.csv) — create the parent.
                    # 路径有文件扩展名（例如 /out/results.csv）——创建父目录。
                    ensure_directory(
                        path.parent,
                        label=f"Output parent directory for {step.step_id}",
                    )
                else:
                    # Path has no extension (e.g., /out/my_tool/) — create it as a directory.
                    # 路径没有扩展名（例如 /out/my_tool/）——将其作为目录创建。
                    ensure_directory(path, label=f"Output directory for {step.step_id}")


def _execution_options(config: Mapping[str, Any]) -> Dict[str, Any]:
    """Extract execution-related options from the resolved configuration.

    Determines whether pipeline progress recording should be enabled.
    Progress is recorded when either:
    - ``config.execution.progress`` is True (default), or
    - ``config.execution.dashboard.enable`` is True (dashboard needs progress events).

    从解析后的配置中提取执行相关选项。

    确定是否应启用管线进度记录。
    当以下任一条件满足时记录进度：
    - ``config.execution.progress`` 为 True（默认），或
    - ``config.execution.dashboard.enable`` 为 True（dashboard 需要进度事件）。
    """
    execution = config.get("execution", {})
    if not isinstance(execution, Mapping):
        execution = {}
    progress = bool(execution.get("progress", True))
    dashboard = execution.get("dashboard", {})
    dashboard_enabled = isinstance(dashboard, Mapping) and bool(dashboard.get("enable", False))
    return {"record_progress": progress or dashboard_enabled}


def _tool_failure_reason(
    step: Any,
    *,
    return_code: int | str,
    stderr_path: str,
    stdout_path: str = "",
    message: str = "",
) -> str:
    """Build a structured failure reason string for a step.

    The reason string is semicolon-delimited key=value pairs designed to be
    both human-readable and machine-parseable. It always includes:
    - step_id and tool_id for traceability.
    - exit_code (or "not_started" if the tool never launched).
    - stderr_path for immediate diagnostic access.
    - suggested_checks with actionable remediation hints.

    This string is stored in commands.tsv's ``reason`` column and surfaced
    by ``abi inspect``.

    为步骤构建结构化失败原因字符串。

    原因字符串是分号分隔的 key=value 对，旨在既可人读又可机读。它始终包括：
    - step_id 和 tool_id 用于追踪。
    - exit_code（如果工具从未启动则为 "not_started"）。
    - stderr_path 用于即时诊断访问。
    - suggested_checks 包含可操作的补救建议。

    此字符串存储在 commands.tsv 的 ``reason`` 列中，并通过 ``abi inspect`` 显示。
    """
    details = [
        f"step_id={step.step_id}",
        f"tool_id={step.tool_id}",
        f"exit_code={return_code if return_code != '' else 'not_started'}",
        f"stderr_path={stderr_path}",
    ]
    if stdout_path:
        details.append(f"stdout_path={stdout_path}")
    if message:
        details.append(f"message={message}")
    # Provide actionable next steps so users and agents know where to look.
    # 提供可操作的后续步骤，以便用户和 agent 知道该查看哪里。
    details.append(
        "suggested_checks=inspect stderr/stdout logs; verify input paths, tool "
        "environment, database/model resources, and command template parameters."
    )
    return "; ".join(details)
