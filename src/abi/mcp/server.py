"""Optional MCP stdio server for ABI agent tools.

The MCP server auto-generates tool registrations from the unified tool
descriptor SSOT (``abi.tool_descriptors``), eliminating the previous manual
duplication of ~150 lines of parameter declarations.

Uses ``abi.mcp._tool_factory`` to create tool functions safely with
``inspect.Signature`` instead of ``exec()``.
"""

from __future__ import annotations

import argparse
import logging
from typing import Any, Optional, Sequence

from abi.agent import ABIAgentInterface

FastMCP: Any
try:
    from mcp.server.fastmcp import FastMCP as _ImportedFastMCP
except ImportError:  # pragma: no cover - exercised when optional dependency is absent
    FastMCP = None
else:
    FastMCP = _ImportedFastMCP

_logger = logging.getLogger("abi.mcp.server")


def _register_mcp_tools(
    mcp: Any,
    agent: ABIAgentInterface,
    *,
    profile: str = "safe",
) -> None:
    """Auto-register MCP tool functions from the unified SSOT metadata.

    Selects an advertised profile from ``abi.tool_descriptors`` and creates
    properly-annotated Python functions for each tool via ``ToolDescriptor`` +
    ``make_tool_func`` — no ``exec()``.

    Legacy public aliases are included in ``ABI_AGENT_TOOLS`` so every
    transport and provider exporter exposes the same tool set.
    """
    from abi.mcp._tool_factory import ToolDescriptor, make_tool_func
    from abi.tool_descriptors import TOOL_ALIASES, select_agent_tools

    for tool_name, metadata in select_agent_tools(profile).items():
        method_name = TOOL_ALIASES.get(tool_name)
        if method_name is None:
            continue

        try:
            desc = ToolDescriptor(tool_name, metadata)
            tool_func = make_tool_func(desc, getattr(agent, method_name))
        except (ValueError, TypeError) as exc:
            _logger.warning(
                "Skipping MCP tool %r: %s",
                tool_name,
                exc,
            )
            continue

        mcp.tool()(tool_func)

    if profile != "management":
        return

    # Preserve the pre-ABI MCP name only on the compatibility/management surface.
    def autoplasm_validate_result(
        result_dir: str,
        allow_empty_tables: Optional[bool] = None,
    ) -> str:
        """Validate a metagenomic-plasmid result directory (legacy alias)."""
        return agent.autoplasm_validate_result(
            result_dir=result_dir,
            allow_empty_tables=True if allow_empty_tables is None else allow_empty_tables,
        )

    mcp.tool()(autoplasm_validate_result)


def create_server(*, profile: str = "safe") -> object:
    """Create the ABI MCP server.

    The MCP SDK is optional so the main Python 3.10 ABI environment remains
    dependency-light. Install the MCP extra or use a separate MCP environment
    before launching this server.
    """
    if FastMCP is None:
        raise RuntimeError(
            "The optional MCP SDK is not installed. Install ABI with the MCP extra "
            "in a compatible environment before running `python -m abi.mcp.server`."
        )

    mcp = FastMCP("abi")
    agent = ABIAgentInterface()
    _register_mcp_tools(mcp, agent, profile=profile)
    return mcp


def main(argv: Optional[Sequence[str]] = None) -> None:
    from abi.tool_descriptors import AGENT_TOOL_PROFILES

    parser = argparse.ArgumentParser(description="Run the ABI MCP stdio server.")
    parser.add_argument(
        "--profile",
        choices=tuple(AGENT_TOOL_PROFILES),
        default="safe",
        help="Tool visibility profile (default: safe).",
    )
    args = parser.parse_args(argv)
    server = create_server(profile=args.profile)
    server.run(transport="stdio")  # type: ignore[attr-defined]


if __name__ == "__main__":
    main()
