"""OpenAI-compatible tool descriptor export (backward-compatible re-exports).

.. deprecated::
    This module is kept for backward compatibility.  New code should import
    from ``abi.tool_descriptors`` which is the unified single source of truth
    covering OpenAI, Anthropic Claude, Google Gemini, and all OpenAI-compatible
    Chinese LLM providers (DeepSeek, 智谱 GLM, Kimi, 通义千问 Qwen, MiniMax).

    Existing imports like ``from abi.openai_contracts import export_openai_tools``
    continue to work unchanged.
"""

from abi.tool_descriptors import (  # noqa: F401
    ABI_AGENT_TOOLS,
    COMMON_PLAN_PROPERTIES,
    READ_ONLY_TOOLS,
    ToolMetadata,
    _strict_schema,
    export_openai_tools,
)

__all__ = [
    "ABI_AGENT_TOOLS",
    "READ_ONLY_TOOLS",
    "ToolMetadata",
    "export_openai_tools",
]
