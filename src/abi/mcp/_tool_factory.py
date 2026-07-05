"""Safe MCP tool function factory — replaces exec() with inspect.Signature.

This module provides the canonical way to create MCP tool functions from
the unified tool descriptor SSOT (``abi.tool_descriptors``).  Instead of
using ``exec()`` to generate functions at runtime, we build them with
proper ``inspect.Signature`` objects so that FastMCP can introspect
parameter types without evaluating arbitrary code.

Usage::

    from abi.mcp._tool_factory import ToolDescriptor, make_tool_func

    metadata = {"description": "...", "properties": {"x": {"type": "string"}}, "required": ["x"]}
    desc = ToolDescriptor("my_tool", metadata)
    func = make_tool_func(desc, agent.some_method)
    mcp.tool()(func)
"""

from __future__ import annotations

import inspect
import re
from functools import wraps
from typing import Any, Callable, Optional

# Safe name patterns — reject anything that could be an injection vector.
# Only allow valid Python identifiers for both tool names and parameter names.
_TOOL_NAME_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")
_PARAM_NAME_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")

# JSON Schema type → Python type mapping for auto-generated MCP tool signatures.
_JSON_TO_PY_TYPE: dict[str, type] = {
    "string": str,
    "integer": int,
    "number": float,
    "boolean": bool,
    "array": list,
    "object": dict,
}

__all__ = [
    "ToolDescriptor",
    "make_tool_func",
    "validate_tool_name",
    "validate_param_name",
]


def validate_tool_name(name: str) -> str:
    """Validate a tool name is a safe Python identifier.

    Raises:
        ValueError: If the name is empty or contains unsafe characters.
    """
    if not _TOOL_NAME_RE.match(name):
        raise ValueError(
            f"Invalid tool name {name!r}: must be a valid Python identifier "
            f"matching {_TOOL_NAME_RE.pattern!r}"
        )
    return name


def validate_param_name(name: str) -> str:
    """Validate a parameter name is a safe Python identifier.

    Raises:
        ValueError: If the name is empty or contains unsafe characters.
    """
    if not _PARAM_NAME_RE.match(name):
        raise ValueError(
            f"Invalid parameter name {name!r}: must be a valid Python identifier "
            f"matching {_PARAM_NAME_RE.pattern!r}"
        )
    return name


class ToolDescriptor:
    """A validated tool descriptor built from the SSOT metadata.

    Attributes:
        name: The validated tool name (safe Python identifier).
        description: Human-readable tool description.
        properties: Mapping of validated parameter names to their JSON schemas.
        required: Set of required parameter names.
    """

    def __init__(self, raw_name: str, metadata: dict) -> None:
        validate_tool_name(raw_name)
        self.name = raw_name
        self.description = str(metadata.get("description", ""))
        self.properties = self._validate_properties(metadata)
        self.required = set(metadata.get("required", []))

    def _validate_properties(self, metadata: dict) -> dict[str, dict]:
        """Validate all parameter names in the properties block."""
        props = metadata.get("properties", {})
        if not isinstance(props, dict):
            return {}
        for pname in props:
            validate_param_name(str(pname))
        result: dict[str, dict] = {}
        for k, v in props.items():
            result[str(k)] = dict(v) if isinstance(v, dict) else {"type": "string"}
        return result

    def make_function_signature(self) -> inspect.Signature:
        """Generate an ``inspect.Signature`` for FastMCP introspection.

        Required parameters come first (positional-keyword), then optional
        parameters with ``None`` default.  This avoids "non-default argument
        follows default argument" syntax errors when FastMCP iterates the
        signature.
        """
        params: list[inspect.Parameter] = []

        for pname in self.properties:
            pschema = self.properties[pname]
            json_type = pschema.get("type", "string")
            py_type = _JSON_TO_PY_TYPE.get(json_type, Any)
            if pname in self.required:
                params.append(
                    inspect.Parameter(
                        pname,
                        inspect.Parameter.KEYWORD_ONLY,
                        annotation=py_type,
                    )
                )

        for pname in self.properties:
            pschema = self.properties[pname]
            json_type = pschema.get("type", "string")
            py_type = _JSON_TO_PY_TYPE.get(json_type, Any)
            if pname not in self.required:
                params.append(
                    inspect.Parameter(
                        pname,
                        inspect.Parameter.KEYWORD_ONLY,
                        default=None,
                        annotation=Optional[py_type],
                    )
                )

        return inspect.Signature(params, return_annotation=str)


def make_tool_func(
    descriptor: ToolDescriptor,
    agent_method: Callable[..., str],
) -> Callable[..., str]:
    """Create a safe MCP tool function from a ``ToolDescriptor``.

    The returned function:
    - Rejects unknown keyword arguments (defense-in-depth).
    - Wraps the agent method to preserve __doc__ and __wrapped__.
    - Has a proper ``__signature__`` for FastMCP introspection.

    Args:
        descriptor: A validated ``ToolDescriptor``.
        agent_method: The agent method to call (e.g. ``agent.dispatch``).

    Returns:
        A callable suitable for ``mcp.tool()`` registration.

    Raises:
        ValueError: If ``agent_method`` is not callable.
    """
    if not callable(agent_method):
        raise ValueError("agent_method must be callable")

    declared = set(descriptor.properties)

    @wraps(agent_method)
    def tool_func(**kwargs: Any) -> str:
        unknown = set(kwargs) - declared
        if unknown:
            raise ValueError(
                f"Unknown parameters for {descriptor.name}: {', '.join(sorted(unknown))}"
            )
        return agent_method(**kwargs)

    tool_func.__name__ = tool_func.__qualname__ = descriptor.name
    tool_func.__doc__ = descriptor.description
    tool_func.__signature__ = descriptor.make_function_signature()
    return tool_func
