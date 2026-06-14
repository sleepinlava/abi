"""Agent-Bioinformatics Interface package.

ABI is a **control plane** between AI agents and bioinformatics tools — it
provides structured JSON envelopes, provenance tracking, and execution gating.

# Quick start for AI agents / LLM agent 快速开始

If you are an AI agent encountering this package for the first time, the
fastest way to learn how to use it is::

    import abi
    print(abi.get_agent_guide())

Or from the command line::

    abi list-types --output-json
    abi doctor-agent --type <analysis_type>

# Package layout / 包结构

========================  ======================================================
Module                    Purpose
========================  ======================================================
``abi.agent``             ``ABIAgentInterface`` — unified JSON-envelope API
``abi.plugins``           Plugin registry: ``list_plugins()``, ``get_plugin()``
``abi.schemas``           Canonical types: ``SampleInput``, ``ExecutionPlan``
``abi.tools``             ``ToolRegistry``, ``ToolSkill``, ``GenericCommandSkill``
``abi.provenance``        ``RunLogger``, TSV provenance writers
``abi.diagnostics``       Error taxonomy + ``classify_exception()``
``abi.interfaces``        ``ABIPlugin``, ``ABIDryRunPlugin`` protocol classes
``abi.openai_contracts``   OpenAI function-calling tool descriptors
``abi.mcp``               Optional MCP stdio server for Claude Desktop / Claude Code
========================  ======================================================
"""

__all__ = [
    "__version__",
    "get_agent_guide",
    "list_plugins_summary",
]

__version__ = "1.0.0"


def get_agent_guide() -> str:
    """Return the essential operating guide for untrained LLM agents.

    This function produces a compact text block that teaches any LLM agent
    how to use ABI correctly on the first attempt. It covers:

    - The safe lifecycle: list-types → plan → dry-run → inspect → run
    - JSON envelope contract (success / confirmation_required / error)
    - The confirmation gate for ``run``
    - Transport methods (CLI JSON, MCP, OpenAI tools)
    - How to read results from standard tables
    - Error recovery rules

    Inject the returned text into your system prompt, or call
    ``abi doctor-agent --type <analysis_type>`` for a more detailed
    per-plugin operating guide.

    # 返回给未经训练的 LLM agent 的基本操作指南。
    # 将返回的文本注入 system prompt 即可让 agent 在首次尝试时正确操作 ABI。
    """
    return (
        "ABI (Agent-Bioinformatics Interface) Operating Guide\n"
        "=====================================================\n"
        "\n"
        "Safe call order (do not skip steps):\n"
        "  1. list_types    — discover installed analysis plugins\n"
        "  2. plan          — build execution plan, write execution_plan.json\n"
        "  3. dry_run       — render commands + provenance, NO real tools run\n"
        "  4. inspect       — check provenance for failures before execution\n"
        "  5. report        — regenerate reports from completed runs\n"
        "  6. run           — execute (REQUIRES user confirmation)\n"
        "\n"
        "JSON envelope contract (every command returns one of three):\n"
        '  success               — "result" holds the payload\n'
        '  confirmation_required — user must approve before proceeding (run only)\n'
        '  error                 — "error_code" + "diagnostic_hints" for recovery\n'
        "\n"
        "Transport methods (use any one):\n"
        "  CLI:     abi <command> --output-json\n"
        "  MCP:     abi-mcp  (configure in Claude Desktop settings)\n"
        "  OpenAI:  abi export-openai-tools --type <plugin> --format responses\n"
        "  HTTP:    abi job-service  (start server), abi job submit ...\n"
        "\n"
        "Critical rules:\n"
        "  - NEVER call abi_run without explicit user confirmation.\n"
        "  - Read tables/*.tsv for structured results, NOT raw tool stdout.\n"
        "  - On error, inspect error_code and diagnostic_hints before retrying.\n"
        "  - Call dry_run before run to validate the workflow.\n"
        "  - Use abi install-skills to register ABI skills for Claude Code.\n"
        "\n"
        "Plugin discovery:\n"
        "  import abi; abi.list_plugins_summary()  # returns list of (id, name, desc)\n"
        "  abi list-types --output-json  # from CLI\n"
    )


def list_plugins_summary() -> list[dict[str, str]]:
    """Return a summary of all installed ABI plugins.

    Returns a list of dicts with keys ``analysis_type``, ``name``, and
    ``description``. This is the programmatic equivalent of ``abi list-types``.

    # 返回所有已安装 ABI 插件的摘要列表。
    # 每个字典包含 analysis_type / name / description。
    """
    try:
        from abi.plugins import list_plugins

        return [
            {
                "analysis_type": p.plugin_id,
                "name": p.display_name,
                "description": p.description,
            }
            for p in list_plugins()
        ]
    except Exception:
        return []
