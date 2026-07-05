"""Tests for safe MCP tool function generation."""

from __future__ import annotations

import inspect

import pytest

from abi.mcp._tool_factory import ToolDescriptor, make_tool_func


def test_tool_descriptor_builds_keyword_only_signature() -> None:
    desc = ToolDescriptor(
        "run_tool",
        {
            "description": "Run a tool",
            "properties": {
                "input_path": {"type": "string"},
                "threads": {"type": "integer"},
            },
            "required": ["input_path"],
        },
    )

    sig = desc.make_function_signature()
    params = sig.parameters

    assert list(params) == ["input_path", "threads"]
    assert params["input_path"].kind is inspect.Parameter.KEYWORD_ONLY
    assert params["input_path"].default is inspect.Parameter.empty
    assert params["input_path"].annotation is str
    assert params["threads"].default is None


def test_tool_descriptor_rejects_unsafe_names() -> None:
    with pytest.raises(ValueError, match="Invalid tool name"):
        ToolDescriptor("bad-name", {"properties": {}})
    with pytest.raises(ValueError, match="Invalid parameter name"):
        ToolDescriptor("good_name", {"properties": {"bad-name": {"type": "string"}}})


def test_make_tool_func_rejects_unknown_kwargs_and_calls_agent_method() -> None:
    calls: list[dict] = []

    def agent_method(**kwargs: object) -> str:
        calls.append(dict(kwargs))
        return "ok"

    desc = ToolDescriptor(
        "dispatch",
        {
            "description": "Dispatch",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    )
    func = make_tool_func(desc, agent_method)

    assert func(query="abc") == "ok"
    assert calls == [{"query": "abc"}]
    assert func.__name__ == "dispatch"
    assert inspect.signature(func).parameters["query"].annotation is str

    with pytest.raises(ValueError, match="Unknown parameters"):
        func(query="abc", extra=True)
