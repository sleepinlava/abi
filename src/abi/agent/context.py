"""Agent context and doctor text for ABI plugins.

# Why these functions exist / 为什么需要这些函数?

ABI is designed to be called by LLM-based agents (OpenAI function-calling,
MCP servers, Claude tool use, etc.). These agents may have **no prior training**
on ABI's specific API. ``build_agent_context`` and ``render_doctor_agent``
produce the shortest possible "operating spec" that, when injected into an
agent's system prompt, teaches it:

1. The safe call order (lifecycle sequence).
2. Which tools are unsafe and require user confirmation.
3. The standard output tables (so the agent reads results from the right place).
4. The important artifacts (so the agent knows which files matter).
5. The error taxonomy (so the agent can self-recover from failures).
6. Recovery rules (immediate next-steps when something fails).

Without this context, an untrained LLM might:
- Call ``run()`` before ``plan()`` or ``dry_run()``, wasting compute.
- Parse raw tool stdout instead of reading standardized ``tables/*.tsv``.
- Fail to recognize a ``confirmation_required`` status and get stuck.
- Miss recoverable errors because it doesn't know the error codes.

With this context injected, even a zero-shot agent can operate ABI correctly.

# 设计目标

- ``build_agent_context`` 输出机器可读字典, 适合注入 system prompt。
- ``render_doctor_agent`` 输出人类可读文本, 适合展示给用户或聊天式 agent prompt。
- ``SAFE_SEQUENCE`` 定义了标准生命周期顺序, 防止 agent 跳过关键步骤。
- ``IMPORTANT_ARTIFACTS`` 告诉 agent 哪些文件是结果产物的权威来源。
"""

from __future__ import annotations

from typing import Any, Dict, List

from abi.diagnostics import ERROR_CODES
from abi.openai_contracts import ABI_AGENT_TOOLS, export_openai_tools
from abi.permissions import TOOL_PERMISSIONS, PermissionLevel

__all__ = ["build_agent_context", "render_doctor_agent"]


# Recommended safe call order for the agent lifecycle.
# An agent should never skip a step in this sequence without good reason.
# 推荐的 agent 生命周期安全调用顺序。
# Agent 不应无故跳过此序列中的任何步骤。
SAFE_SEQUENCE = ["list_types", "plan", "dry_run", "inspect", "report", "run"]

# Key output artifacts the agent should know about.
# These are the canonical locations for results; agents should reference these
# rather than parsing raw tool stdout or intermediate scratch files.
# Agent 应知晓的关键输出产物。
# 这些是结果的规范位置, agent 应引用这些文件而非解析原始工具 stdout。
IMPORTANT_ARTIFACTS = [
    "execution_plan.json",
    "provenance/commands.tsv",
    "provenance/resolved_inputs.tsv",
    "provenance/tool_versions.tsv",
    "provenance/resources.json",
    "provenance/progress.jsonl",
    "tables/*.tsv",
    "report/report.md",
    "report/report.html",
]


def build_agent_context(plugin: Any) -> Dict[str, Any]:
    """Return the compact machine-readable context an agent needs for ABI.

    This is the primary integration point for untrained LLM agents. The returned
    dictionary should be injected into the agent's system prompt or tool
    descriptions so it can operate ABI correctly on the first attempt.

    Data included / 包含的数据:

        analysis_type / display_name / description
            Plugin identity — tells the agent *what* this analysis does.

        safe_sequence
            The canonical lifecycle order. The agent should follow this sequence
            unless there is a specific reason to deviate.

        execution_requires_confirmation / unsafe_tools
            Signals that ``run`` (and other execution tools) need explicit user
            approval. Prevents the agent from running expensive pipelines
            autonomously.

        default_exported_tools / tool_permissions
            The set of tool descriptors the agent should advertise in its
            function-calling schema, plus the permission level of each.

        standard_tables
            The names of TSV tables in ``tables/``. The agent should read these
            for structured results instead of parsing raw tool outputs.

        important_artifacts
            Key file paths the agent may need to reference or return to the user.

        error_codes
            The complete set of stable error codes from ``abi.diagnostics``,
            so the agent knows what to expect in error envelopes.

        recovery_rules
            Heuristic rules the agent can follow to self-recover from common
            failure modes without human intervention.

    # 这是 LLM agent 的主要集成点。
    # 返回的字典应注入 agent 的 system prompt, 使其在首次尝试时即可正确操作 ABI。
    # 包含: 插件身份 / 安全序列 / 执行确认要求 / 工具权限 / 标准表 / 重要产物 / 错误码 / 恢复规则。
    """
    table_schemas = plugin.table_schemas()
    standard_tables = sorted(str(name) for name in table_schemas)
    # Export tool descriptors without execution tools so agents advertise a
    # safe-by-default tool set. Execution tools are listed separately as
    # "unsafe_tools" requiring confirmation.
    # 导出不包含执行工具的工具描述符, 确保 agent 默认发布安全工具集。
    # 执行工具单独列为 "unsafe_tools", 需要用户确认。
    tools = export_openai_tools(plugin, descriptor_format="json", include_execution=False)
    execution_tools = [
        name
        for name, permission in TOOL_PERMISSIONS.items()
        if permission == PermissionLevel.EXECUTION
    ]
    return {
        "analysis_type": plugin.plugin_id,
        "display_name": plugin.display_name,
        "description": plugin.description,
        "safe_sequence": list(SAFE_SEQUENCE),
        "execution_requires_confirmation": True,
        "unsafe_tools": sorted(execution_tools),
        "default_exported_tools": [tool["name"] for tool in tools],
        "tool_permissions": {
            name: metadata["permission"] for name, metadata in ABI_AGENT_TOOLS.items()
        },
        "standard_tables": standard_tables,
        "important_artifacts": list(IMPORTANT_ARTIFACTS),
        "error_codes": sorted(ERROR_CODES),
        "recovery_rules": [
            "Call dry_run before run.",
            "Do not call abi_run unless the user has approved execution.",
            "On errors, inspect error_code and diagnostic_hints before changing inputs.",
            "Read standard tables under tables/ instead of parsing raw tool outputs.",
        ],
    }


def render_doctor_agent(plugin: Any) -> str:
    """Render a short human-readable operating guide for agent users.

    Produces the same information as ``build_agent_context`` but formatted as
    plain text suitable for display in a terminal, chat window, or a
    human-oriented agent prompt.

    The format is intentionally terse — at most a few dozen lines — so it can
    be included in a prompt without consuming excessive context window tokens.

    # 生成人类可读的简短操作指南。
    # 格式刻意精简 (最多几十行), 可在不消耗过多上下文窗口的情况下嵌入 prompt。
    """
    context = build_agent_context(plugin)
    lines: List[str] = [
        f"ABI agent guide for {context['analysis_type']}",
        "",
        "Safe call order:",
        "  " + " -> ".join(context["safe_sequence"]),
        "",
        "Rules:",
        "  - Use CLI JSON, MCP, HTTP jobs, or OpenAI descriptors as transports.",
        "  - Treat ABIAgentInterface as the business boundary.",
        "  - Never execute abi_run without explicit user approval.",
        "  - Read tables/*.tsv for results instead of raw tool outputs.",
        "  - Use error_code and diagnostic_hints for recovery.",
        "",
        "Standard tables:",
    ]
    lines.extend(f"  - {name}" for name in context["standard_tables"])
    lines.extend(
        [
            "",
            "Important artifacts:",
        ]
    )
    lines.extend(f"  - {path}" for path in context["important_artifacts"])
    return "\n".join(lines) + "\n"
