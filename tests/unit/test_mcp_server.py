import inspect

import pytest

from abi.agent import ABIAgentInterface


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
        "abi_validate_result",
        "abi_run",
    } <= set(mcp.tools)


def test_mcp_server_tool_signatures_cover_agent_interface_parameters(monkeypatch):
    import abi.mcp.server as server

    monkeypatch.setattr(server, "FastMCP", FakeMCP)
    mcp = server.create_server()
    mapping = {
        "abi_plan": "plan",
        "abi_dry_run": "dry_run",
        "abi_inspect": "inspect",
        "abi_report": "report",
        "abi_run": "run",
        "abi_export_nextflow": "export_nextflow",
        "abi_export_agent_context": "export_agent_context",
        "abi_doctor_agent": "doctor_agent",
        "abi_validate_result": "abi_validate_result",
    }

    for tool_name, method_name in mapping.items():
        signature = inspect.signature(getattr(ABIAgentInterface, method_name))
        agent_params = {name for name in signature.parameters if name != "self"}
        mcp_params = set(inspect.signature(mcp.tools[tool_name]).parameters)

        assert agent_params <= mcp_params, tool_name
