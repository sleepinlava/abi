import inspect

import pytest

from abi.agent import ABIAgentInterface
from abi.tool_descriptors import ABI_AGENT_TOOLS, TOOL_ALIASES


class FakeMCP:
    def __init__(self, name):
        self.name = name
        self.tools = {}

    def tool(self):
        def decorator(func):
            self.tools[func.__name__] = func
            return func

        return decorator


def test_mcp_server_module_imports_without_optional_dependency():
    import abi.mcp.server as server

    assert hasattr(server, "create_server")


def test_mcp_server_reports_missing_optional_dependency(monkeypatch):
    import abi.mcp.server as server

    monkeypatch.setattr(server, "FastMCP", None)

    with pytest.raises(RuntimeError, match="optional MCP SDK"):
        server.create_server()


def test_mcp_server_exposes_agent_context_and_validation_tools(monkeypatch):
    import abi.mcp.server as server

    monkeypatch.setattr(server, "FastMCP", FakeMCP)

    mcp = server.create_server()

    assert {
        "abi_list_types",
        "abi_plan",
        "abi_dry_run",
        "abi_inspect",
        "abi_report",
        "abi_export_nextflow",
        "abi_export_agent_context",
        "abi_doctor_agent",
        "abi_install_skills",
        "abi_validate_result",
        "abi_run",
    } <= set(mcp.tools)


def test_mcp_server_tool_signatures_cover_agent_interface_parameters(monkeypatch):
    import abi.mcp.server as server

    monkeypatch.setattr(server, "FastMCP", FakeMCP)
    mcp = server.create_server()
    mapping = {
        name: TOOL_ALIASES[name]
        for name in ABI_AGENT_TOOLS
        if name in TOOL_ALIASES and not name.startswith("autoplasm")
    }

    for tool_name, method_name in mapping.items():
        signature = inspect.signature(getattr(ABIAgentInterface, method_name))
        agent_params = {name for name in signature.parameters if name != "self"}
        mcp_params = set(inspect.signature(mcp.tools[tool_name]).parameters)

        assert agent_params <= mcp_params, tool_name


def test_mcp_server_skips_invalid_descriptors_with_warning(caplog, monkeypatch):
    import abi.mcp.server as server
    from abi import tool_descriptors

    monkeypatch.setattr(
        tool_descriptors,
        "ABI_AGENT_TOOLS",
        {"invalid-tool-name": {"properties": {}, "required": []}},
    )
    monkeypatch.setattr(tool_descriptors, "TOOL_ALIASES", {"invalid-tool-name": "query"})

    mcp = FakeMCP("abi")
    with caplog.at_level("WARNING", logger="abi.mcp.server"):
        server._register_mcp_tools(mcp, ABIAgentInterface())

    assert "invalid-tool-name" not in mcp.tools
    assert "Skipping MCP tool 'invalid-tool-name'" in caplog.text
    assert "autoplasm_validate_result" in mcp.tools


def test_mcp_main_runs_stdio_transport(monkeypatch):
    import abi.mcp.server as server

    calls = []

    class FakeServer:
        def run(self, *, transport):
            calls.append(transport)

    monkeypatch.setattr(server, "create_server", FakeServer)

    server.main()

    assert calls == ["stdio"]
