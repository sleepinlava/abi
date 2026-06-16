"""Optional MCP stdio server for ABI agent tools.

The MCP server auto-generates tool registrations from the unified tool
descriptor SSOT (``abi.tool_descriptors``), eliminating the previous manual
duplication of ~150 lines of parameter declarations.
"""

from __future__ import annotations

from typing import Any, Optional

from abi.agent import ABIAgentInterface

FastMCP: Any
try:
    from mcp.server.fastmcp import FastMCP as _ImportedFastMCP
except ImportError:  # pragma: no cover - exercised when optional dependency is absent
    FastMCP = None
else:
    FastMCP = _ImportedFastMCP

# JSON Schema type → Python type mapping for auto-generated MCP tool signatures.
_JSON_TO_PY_TYPE: dict[str, str] = {
    "string": "str",
    "integer": "int",
    "boolean": "bool",
}


def _register_mcp_tools(mcp: Any, agent: ABIAgentInterface) -> None:
    """Auto-register MCP tool functions from the unified SSOT metadata.

    Reads ``ABI_AGENT_TOOLS`` and ``TOOL_ALIASES`` from
    ``abi.tool_descriptors`` and dynamically creates properly-annotated
    Python functions for each tool.  FastMCP introspects the type hints
    to generate JSON Schema — the same information that was previously
    maintained by hand in 10 separate ``@mcp.tool()`` functions.

    The legacy ``autoplasm_validate_result`` alias is registered separately
    to preserve backward compatibility with older MCP clients.
    """
    from abi.tool_descriptors import ABI_AGENT_TOOLS, TOOL_ALIASES

    for tool_name, metadata in ABI_AGENT_TOOLS.items():
        method_name = TOOL_ALIASES.get(tool_name)
        if method_name is None:
            continue

        props = metadata.get("properties", {})
        required = set(metadata.get("required", []))

        # Sort parameters: required first, then optional (alphabetical within each).
        # This avoids "non-default argument follows default argument" syntax errors.
        param_names: list[str] = []
        # Required params first (in definition order for determinism)
        for pname in props:
            if pname in required:
                param_names.append(pname)
        # Optional params second
        for pname in props:
            if pname not in required:
                param_names.append(pname)

        param_parts: list[str] = []
        call_parts: list[str] = []
        for pname in param_names:
            pschema = props[pname]
            json_type = pschema.get("type", "string")
            py_type = _JSON_TO_PY_TYPE.get(json_type, "Any")
            if pname in required:
                param_parts.append(f"{pname}: {py_type}")
            else:
                param_parts.append(f"{pname}: Optional[{py_type}] = None")
            call_parts.append(f"{pname}={pname}")

        func_source = (
            f"def {tool_name}({', '.join(param_parts)}) -> str:\n"
            f'    """{metadata["description"]}"""\n'
            f"    return agent.{method_name}({', '.join(call_parts)})\n"
        )

        namespace: dict[str, Any] = {
            "agent": agent,
            "Optional": Optional,
            "str": str,
            "int": int,
            "bool": bool,
        }
        exec(func_source, namespace)
        tool_func = namespace[tool_name]
        mcp.tool()(tool_func)

    # Legacy alias — preserve backward compatibility with MCP clients
    # that reference the old ``autoplasm_validate_result`` tool name.
    def autoplasm_validate_result(
        result_dir: str,
        allow_empty_tables: Optional[bool] = None,
    ) -> str:
        """Validate an ABI result directory (legacy autoplasm alias)."""
        return agent.autoplasm_validate_result(
            result_dir=result_dir,
            allow_empty_tables=bool(allow_empty_tables),
        )

    mcp.tool()(autoplasm_validate_result)


def create_server() -> object:
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
    _register_mcp_tools(mcp, agent)
    return mcp


def main() -> None:
    server = create_server()
    server.run(transport="stdio")  # type: ignore[attr-defined]


if __name__ == "__main__":
    main()
