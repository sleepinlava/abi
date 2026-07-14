import inspect
import json

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

    def run(self, *, transport):
        self.transport = transport


def test_mcp_server_module_imports_without_optional_dependency():
    import abi.mcp.server as server

    assert hasattr(server, "create_server")


def test_mcp_server_reports_missing_optional_dependency(monkeypatch):
    import abi.mcp.server as server

    monkeypatch.setattr(server, "FastMCP", None)

    with pytest.raises(RuntimeError, match="optional MCP SDK"):
        server.create_server()


def test_mcp_server_safe_profile_exposes_planning_but_not_execution_or_management(monkeypatch):
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
    } <= set(mcp.tools)
    assert "abi_run" not in mcp.tools
    assert "abi_install_skills" not in mcp.tools
    assert "abi_autoplasm_validate_result" not in mcp.tools
    assert "autoplasm_validate_result" not in mcp.tools


def test_mcp_server_full_profile_adds_execution_but_not_management(monkeypatch):
    import abi.mcp.server as server

    monkeypatch.setattr(server, "FastMCP", FakeMCP)

    mcp = server.create_server(profile="full")

    assert "abi_run" in mcp.tools
    assert "abi_install_skills" not in mcp.tools
    assert "abi_autoplasm_validate_result" not in mcp.tools
    assert "autoplasm_validate_result" not in mcp.tools


def test_mcp_server_discovery_profile_is_read_only(monkeypatch):
    import abi.mcp.server as server

    monkeypatch.setattr(server, "FastMCP", FakeMCP)

    mcp = server.create_server(profile="discovery")

    assert {"abi_list_types", "abi_query", "abi_inspect", "abi_validate_result"} <= set(mcp.tools)
    assert "abi_plan" not in mcp.tools
    assert "abi_dry_run" not in mcp.tools
    assert "abi_run" not in mcp.tools


def test_mcp_full_profile_run_still_requires_confirmation(monkeypatch):
    import abi.mcp.server as server

    monkeypatch.setattr(server, "FastMCP", FakeMCP)
    mcp = server.create_server(profile="full")

    response = json.loads(
        mcp.tools["abi_run"](
            analysis_type="metatranscriptomics",
            confirm_execution=False,
        )
    )

    assert response["status"] == "confirmation_required"
    assert response["command"] == "run"


def test_mcp_server_management_profile_preserves_complete_legacy_surface(monkeypatch):
    import abi.mcp.server as server

    monkeypatch.setattr(server, "FastMCP", FakeMCP)

    mcp = server.create_server(profile="management")

    assert set(ABI_AGENT_TOOLS) <= set(mcp.tools)
    assert "autoplasm_validate_result" in mcp.tools


def test_mcp_server_rejects_unknown_profile(monkeypatch):
    import abi.mcp.server as server

    monkeypatch.setattr(server, "FastMCP", FakeMCP)

    with pytest.raises(ValueError, match="Unknown agent tool profile"):
        server.create_server(profile="unknown")


def test_mcp_cli_selects_requested_profile_and_runs_stdio(monkeypatch):
    import abi.mcp.server as server

    fake = FakeMCP("abi")
    monkeypatch.setattr(server, "FastMCP", lambda name: fake)

    server.main(["--profile", "full"])

    assert "abi_run" in fake.tools
    assert fake.transport == "stdio"


def test_mcp_server_tool_signatures_cover_agent_interface_parameters(monkeypatch):
    import abi.mcp.server as server

    monkeypatch.setattr(server, "FastMCP", FakeMCP)
    mcp = server.create_server()
    mapping = {
        name: TOOL_ALIASES[name]
        for name in mcp.tools
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
        {
            "invalid-tool-name": {"properties": {}, "required": []},
            "autoplasm_validate_result": {"properties": {}, "required": []},
        },
    )
    monkeypatch.setattr(
        tool_descriptors,
        "TOOL_ALIASES",
        {
            "invalid-tool-name": "query",
            "autoplasm_validate_result": "autoplasm_validate_result",
        },
    )
    monkeypatch.setattr(
        tool_descriptors,
        "select_agent_tools",
        lambda profile: {
            "invalid-tool-name": {"properties": {}, "required": []},
            "autoplasm_validate_result": {"properties": {}, "required": []},
        },
    )

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
        def __init__(self, *, profile: str = "safe"):
            pass

        def run(self, *, transport):
            calls.append(transport)

    monkeypatch.setattr(server, "create_server", FakeServer)

    server.main(argv=[])

    assert calls == ["stdio"]
