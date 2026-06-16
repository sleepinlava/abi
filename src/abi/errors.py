"""Public ABI error hierarchy -- user-facing exceptions that agents interpret.

This module defines a shallow exception tree rooted at ``ABIError``. Every
ABI exception inherits from ``ABIError`` so that agent runtimes can catch
a single type and know "this is an ABI problem, not a Python bug."

**Design principles / 设计原则**

1. **No internal-only exceptions** -- every exception in this file is
   user-facing. Internal invariants (assertion failures, programming errors)
   should use standard Python exceptions (``ValueError``, ``TypeError``) or
   assertions so they are not confused with operational failures.
   **无内部异常** -- 此文件中的所有异常都是面向用户的。内部不变量（断言失败、
   编程错误）应使用标准 Python 异常或断言，以免与操作失败混淆。

2. **Shallow hierarchy** -- three concrete subclasses cover the three failure
   domains: configuration, sample metadata, and tool operations. We keep the
   tree flat so that agent catch blocks are simple and predictable.
   **扁平层次结构** -- 三个具体子类覆盖三个故障领域：配置、样本元数据和工具操作。
   保持树扁平化使智能体的 catch 块简单且可预测。

3. **Agent-interpretable** -- when an agent catches an ``ABIError``, it can
   inspect the type and message to decide whether to retry, ask the user for
   a fix, or abort. The exception type carries semantic meaning.
   **智能体可解释** -- 当智能体捕获 ABIError 时，可通过检查类型和消息来决定
   是重试、请求用户修复还是中止。异常类型携带语义信息。

**Error hierarchy / 异常层次结构**

::

    RuntimeError
     └── ABIError              # Base: all ABI operational failures
          ├── ConfigError       # Bad config / registry metadata
          ├── SampleSheetError  # Bad sample metadata (CSV parse / validate)
          └── ToolError         # Tool planning or execution failed
"""

from __future__ import annotations

__all__ = [
    "ABIError",
    "ConfigError",
    "MissingTemplateParamError",
    "SampleSheetError",
    "ToolError",
]


class ABIError(RuntimeError):
    """Base class for all ABI user-facing errors.

    **Agent guidance / 智能体指导:**
    Catch ``ABIError`` when you want to handle *any* ABI operational failure
    uniformly. Inspect ``type(exc)`` to specialise the recovery strategy.

    **Why ``RuntimeError``? / 为何继承 RuntimeError？**
    ``RuntimeError`` signals "something went wrong at runtime that the caller
    may be able to handle." It does not imply a programming bug (``ValueError``,
    ``TypeError``) and does not require immediate process termination
    (``SystemExit``, ``KeyboardInterrupt``). This makes it the right base for
    user-facing pipeline failures.
    RuntimeError 表示"调用方可能处理得了的运行时错误"。它不暗示编程错误，
    也不需要立即终止进程。这使其成为面向用户的流水线故障的合适基类。
    """


class ConfigError(ABIError):
    """Raised when ABI configuration or registry metadata is invalid.

    **When raised / 何时抛出:**
    * Missing or unreadable config file.
    * Invalid YAML/TOML syntax in a plugin manifest.
    * Unknown platform / mode / strategy in a config value.
    * Duplicate tool registration or conflicting metadata.

    **Agent recovery / 智能体恢复策略:**
    The agent should NOT retry automatically -- the config must be fixed by
    a human or by a config-generation tool. Report the error with the exact
    file path and line so the user can correct it.
    智能体不应自动重试 -- 配置必须由人类或配置生成工具修复。
    报告错误并包含确切的文件路径和行号，以便用户纠正。
    """


class MissingTemplateParamError(ABIError):
    """Raised when a command template references an undefined parameter.

    Raised by ``SafeFormatDict`` in strict mode when the template contains
    ``{field_name}`` references that are not in the parameter dictionary
    and not listed in ``OPTIONAL_TEMPLATE_FIELDS``.

    **Agent recovery / 智能体恢复策略:**
    The agent should add the missing parameter to ``select_params()`` or
    register it in ``OPTIONAL_TEMPLATE_FIELDS``. This is a configuration
    error that must be fixed before the pipeline can run.
    智能体应将缺失参数添加到 ``select_params()`` 或注册到
    ``OPTIONAL_TEMPLATE_FIELDS``。必须修复此配置错误才能运行管线。
    """


class SampleSheetError(ABIError):
    """Raised when sample metadata cannot be parsed or validated.

    **When raised / 何时抛出:**
    * SampleSheet CSV file is missing or unreadable.
    * Required column ``sample_id`` is absent.
    * A platform value is not in ``VALID_PLATFORMS``.
    * Required read paths (``read1`` for Illumina) are missing for a sample.
    * Inconsistent group / condition assignments across samples.

    **Agent recovery / 智能体恢复策略:**
    The agent should report the specific row and column of the problem.
    If the error is a typo (e.g. "illumia" → "illumina"), the agent MAY
    suggest a correction. Never auto-fix -- the user owns the sample sheet.
    智能体应报告具体的问题行和列。如果是拼写错误，可建议修正。
    绝不自动修复 -- 用户拥有样本表的所有权。
    """


class ToolError(ABIError):
    """Raised when a registered tool cannot be planned or executed.

    **When raised / 何时抛出:**
    * A ``tool_id`` referenced in a plan step is not found in the registry.
    * A tool's preconditions are not satisfied (e.g. missing input file).
    * A tool subprocess exits with a non-zero return code.
    * A tool's output does not pass validation.

    **Agent recovery / 智能体恢复策略:**
    For missing-tool errors, the agent may suggest available alternatives.
    For execution failures, the agent should inspect stdout/stderr and the
    return code. Transient failures (OOM, network timeout) may be retried;
    deterministic failures (bad input, missing dependency) require user
    intervention.
    对于工具缺失错误，智能体可建议可用替代工具。
    对于执行失败，智能体应检查 stdout/stderr 和返回码。
    临时性故障（OOM、网络超时）可重试；确定性故障（错误输入、缺失依赖）需要用户介入。
    """
