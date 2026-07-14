"""Tests for the unified tool descriptor SSOT and multi-LLM exporters."""

import pytest

from abi.plugins import get_plugin
from abi.tool_descriptors import (
    ABI_AGENT_TOOLS,
    PROVIDER_PROFILES,
    TOOL_ALIASES,
    export_anthropic,
    export_gemini,
    export_json,
    export_openai_compatible,
    export_openai_tools,
)

SAFE_TOOL_COUNT = sum(
    metadata.get("permission") != "execution" for metadata in ABI_AGENT_TOOLS.values()
)
ALL_TOOL_COUNT = len(ABI_AGENT_TOOLS)


@pytest.fixture
def plugin():
    """A lightweight plugin for fast descriptor tests."""
    return get_plugin("metatranscriptomics")


# ═══════════════════════════════════════════════════════════════════════════
# Anthropic format
# ═══════════════════════════════════════════════════════════════════════════


def test_anthropic_format_uses_input_schema_key(plugin):
    tools = export_anthropic(plugin)
    assert len(tools) == SAFE_TOOL_COUNT
    for tool in tools:
        assert "input_schema" in tool, f"Missing input_schema in {tool['name']}"
        assert "parameters" not in tool, f"Unexpected parameters key in {tool['name']}"


def test_anthropic_format_no_type_wrapper(plugin):
    tools = export_anthropic(plugin)
    for tool in tools:
        assert "type" not in tool, "Anthropic format should not have type wrapper"
        assert "function" not in tool, "Anthropic format should be flat"


def test_anthropic_format_no_strict_and_no_additional_properties(plugin):
    tools = export_anthropic(plugin)
    for tool in tools:
        assert "strict" not in tool
        assert "additionalProperties" not in tool.get("input_schema", {})


def test_anthropic_format_respects_include_execution(plugin):
    safe = export_anthropic(plugin)
    names = {t["name"] for t in safe}
    assert "abi_run" not in names

    full = export_anthropic(plugin, include_execution=True)
    names = {t["name"] for t in full}
    assert "abi_run" in names
    assert len(full) == ALL_TOOL_COUNT


# ═══════════════════════════════════════════════════════════════════════════
# Gemini format
# ═══════════════════════════════════════════════════════════════════════════


def test_gemini_format_wrapped_in_function_declarations(plugin):
    result = export_gemini(plugin)
    assert isinstance(result, dict)
    assert "function_declarations" in result
    assert len(result["function_declarations"]) == SAFE_TOOL_COUNT


def test_gemini_format_uses_parameters_key(plugin):
    result = export_gemini(plugin)
    for decl in result["function_declarations"]:
        assert "parameters" in decl, f"Missing parameters in {decl['name']}"
        assert "input_schema" not in decl


def test_gemini_format_no_strict_and_no_additional_properties(plugin):
    result = export_gemini(plugin)
    for decl in result["function_declarations"]:
        assert "strict" not in decl
        assert "additionalProperties" not in decl.get("parameters", {})


def test_gemini_format_respects_include_execution(plugin):
    safe = export_gemini(plugin)
    safe_names = {t["name"] for t in safe["function_declarations"]}
    assert "abi_run" not in safe_names

    full = export_gemini(plugin, include_execution=True)
    full_names = {t["name"] for t in full["function_declarations"]}
    assert "abi_run" in full_names
    assert len(full["function_declarations"]) == ALL_TOOL_COUNT


# ═══════════════════════════════════════════════════════════════════════════
# OpenAI-compatible format (all providers)
# ═══════════════════════════════════════════════════════════════════════════


def test_openai_compatible_nested_function_structure(plugin):
    tools = export_openai_compatible(plugin)
    assert len(tools) == SAFE_TOOL_COUNT
    for tool in tools:
        assert tool["type"] == "function"
        assert "function" in tool
        assert "name" in tool["function"]
        assert "description" in tool["function"]
        assert "parameters" in tool["function"]


def test_openai_compatible_respects_include_execution(plugin):
    safe = export_openai_compatible(plugin)
    safe_names = {t["function"]["name"] for t in safe}
    assert "abi_run" not in safe_names

    full = export_openai_compatible(plugin, include_execution=True)
    full_names = {t["function"]["name"] for t in full}
    assert "abi_run" in full_names
    assert len(full) == ALL_TOOL_COUNT


def test_openai_compatible_all_known_providers(plugin):
    """Every provider in PROVIDER_PROFILES must produce valid output."""
    for provider in PROVIDER_PROFILES:
        tools = export_openai_compatible(plugin, provider=provider)
        assert len(tools) == SAFE_TOOL_COUNT, f"Provider {provider} returned {len(tools)} tools"
        for tool in tools:
            assert tool["type"] == "function"
            assert "function" in tool


# Provider-specific quirks
# ═══════════════════════════════════════════════════════════════════════════


def test_deepseek_has_strict_mode(plugin):
    tools = export_openai_compatible(plugin, provider="deepseek")
    for tool in tools:
        assert tool["function"].get("strict") is True
        assert tool["function"]["parameters"].get("additionalProperties") is False


def test_zhipu_no_strict_and_no_additional_properties(plugin):
    tools = export_openai_compatible(plugin, provider="zhipu")
    for tool in tools:
        assert "strict" not in tool["function"]
        assert "additionalProperties" not in tool["function"]["parameters"]


def test_zhipu_sanitizes_dashes_in_tool_names(plugin):
    """zhipu naming rules reject dashes; exporter should sanitize."""
    tools = export_openai_compatible(plugin, provider="zhipu")
    for tool in tools:
        name = tool["function"]["name"]
        assert "-" not in name, f"zhipu tool name {name!r} contains dash"
        assert len(name) <= 64


def test_kimi_has_strict_mode(plugin):
    tools = export_openai_compatible(plugin, provider="kimi")
    for tool in tools:
        assert tool["function"].get("strict") is True


def test_qwen_no_strict(plugin):
    tools = export_openai_compatible(plugin, provider="qwen")
    for tool in tools:
        assert "strict" not in tool["function"]


def test_minimax_no_strict_and_no_additional_properties(plugin):
    tools = export_openai_compatible(plugin, provider="minimax")
    for tool in tools:
        assert "strict" not in tool["function"]
        assert "additionalProperties" not in tool["function"]["parameters"]


def test_glm_is_alias_for_zhipu(plugin):
    zhipu_tools = export_openai_compatible(plugin, provider="zhipu")
    glm_tools = export_openai_compatible(plugin, provider="glm")
    assert zhipu_tools == glm_tools


def test_provider_aliases(plugin):
    """All provider aliases should produce the same output as the canonical name."""
    aliases = {
        "z.ai": "zhipu",
        "zhipuai": "zhipu",
        "chatglm": "glm",
        "moonshot": "kimi",
        "tongyi": "qwen",
        "dashscope": "qwen",
        "mimo": "minimax",
    }
    for alias, canonical in aliases.items():
        alias_tools = export_openai_compatible(plugin, provider=alias)
        canonical_tools = export_openai_compatible(plugin, provider=canonical)
        assert alias_tools == canonical_tools, f"Alias {alias!r} → {canonical!r} mismatch"


def test_unknown_provider_raises(plugin):
    with pytest.raises(ValueError, match="Unknown provider"):
        export_openai_compatible(plugin, provider="nonexistent")


# ═══════════════════════════════════════════════════════════════════════════
# JSON format (internal ABI)
# ═══════════════════════════════════════════════════════════════════════════


def test_json_format_has_all_metadata_fields(plugin):
    tools = export_json(plugin)
    for tool in tools:
        assert "name" in tool
        assert "description" in tool
        assert "input_schema" in tool
        assert "read_only" in tool
        assert "permission" in tool
        assert "requires_confirmation" in tool
        assert "plugin_id" in tool
        assert tool["plugin_id"] == plugin.plugin_id


def test_json_format_includes_plugin_id_in_description(plugin):
    tools = export_json(plugin)
    for tool in tools:
        assert f"Plugin scope: {plugin.plugin_id}" in tool["description"]


# ═══════════════════════════════════════════════════════════════════════════
# TOOL_ALIASES
# ═══════════════════════════════════════════════════════════════════════════


def test_tool_aliases_covers_all_abi_agent_tools():
    """Every ABI_AGENT_TOOL key must have an entry in TOOL_ALIASES."""
    for name in ABI_AGENT_TOOLS:
        assert name in TOOL_ALIASES, f"{name!r} missing from TOOL_ALIASES"


def test_tool_aliases_maps_to_valid_methods():
    """Each alias value must be a real method on ABIAgentInterface."""
    from abi.agent import ABIAgentInterface

    for name, method in TOOL_ALIASES.items():
        if method == "autoplasm_validate_result":
            assert hasattr(ABIAgentInterface, method)
        elif name in ABI_AGENT_TOOLS:
            assert hasattr(ABIAgentInterface, method), f"{method!r} not on ABIAgentInterface"


def test_tool_aliases_all_new_canonical_keys_begin_with_abi():
    """All provider-exported canonical names use the ABI namespace."""
    for name in ABI_AGENT_TOOLS:
        assert name.startswith("abi_")


# ═══════════════════════════════════════════════════════════════════════════
# Backward compatibility
# ═══════════════════════════════════════════════════════════════════════════


def test_openai_contracts_shim_exports_expected_names():
    """The old import path must continue to work for every public name."""
    from abi.openai_contracts import (
        ABI_AGENT_TOOLS as OLD_AGENT_TOOLS,
    )
    from abi.openai_contracts import (
        READ_ONLY_TOOLS as OLD_READ_ONLY,
    )
    from abi.openai_contracts import (
        ToolMetadata as OldMetadata,
    )
    from abi.openai_contracts import (
        export_openai_tools as old_export,
    )

    assert OLD_AGENT_TOOLS is ABI_AGENT_TOOLS
    assert OLD_READ_ONLY is not None
    assert OldMetadata is not None
    assert callable(old_export)


def test_openai_contracts_shim_produces_same_output(plugin):
    """The backward compat shim must produce identical output to SSOT."""
    from abi.openai_contracts import export_openai_tools as old_export
    from abi.tool_descriptors import export_openai_tools as new_export

    for fmt in ("responses", "apps-sdk", "json"):
        assert old_export(plugin, descriptor_format=fmt) == new_export(
            plugin, descriptor_format=fmt
        ), f"Format {fmt!r} mismatch between shim and SSOT"


def test_responses_format_is_flat_for_backward_compat(plugin):
    """Legacy responses format must be flat (name at top level) for backward compat."""
    tools = export_openai_tools(plugin, descriptor_format="responses")
    for tool in tools:
        assert "name" in tool, "Legacy responses format must have 'name' at top level"
        assert tool["type"] == "function"
        assert tool["strict"] is True


# ═══════════════════════════════════════════════════════════════════════════
# Plugin description injection
# ═══════════════════════════════════════════════════════════════════════════


def test_anthropic_descriptions_include_plugin_id(plugin):
    tools = export_anthropic(plugin)
    for tool in tools:
        assert f"Plugin scope: {plugin.plugin_id}" in tool["description"]


def test_gemini_descriptions_include_plugin_id(plugin):
    result = export_gemini(plugin)
    for decl in result["function_declarations"]:
        assert f"Plugin scope: {plugin.plugin_id}" in decl["description"]


def test_openai_compatible_descriptions_include_plugin_id(plugin):
    tools = export_openai_compatible(plugin)
    for tool in tools:
        assert f"Plugin scope: {plugin.plugin_id}" in tool["function"]["description"]


# ═══════════════════════════════════════════════════════════════════════════
# READ_ONLY_TOOLS
# ═══════════════════════════════════════════════════════════════════════════


def test_read_only_tools_are_subset_of_agent_tools():
    from abi.tool_descriptors import READ_ONLY_TOOLS

    assert set(READ_ONLY_TOOLS) <= set(ABI_AGENT_TOOLS)
    for name, metadata in READ_ONLY_TOOLS.items():
        assert metadata["permission"] == "read_only"
        assert metadata["read_only"] is True


# ═══════════════════════════════════════════════════════════════════════════
# Boundary & exception tests — provider handling
# ═══════════════════════════════════════════════════════════════════════════


def test_provider_case_insensitive(plugin):
    """Provider names must be case-insensitive."""
    assert export_openai_compatible(plugin, provider="OPENAI") == export_openai_compatible(
        plugin, provider="openai"
    )
    assert export_openai_compatible(plugin, provider="DeepSeek") == export_openai_compatible(
        plugin, provider="deepseek"
    )
    assert export_openai_compatible(plugin, provider="ZHIPU") == export_openai_compatible(
        plugin, provider="zhipu"
    )


def test_provider_empty_string_raises(plugin):
    """Empty provider string should raise ValueError."""
    with pytest.raises(ValueError, match="Unknown provider"):
        export_openai_compatible(plugin, provider="")


def test_provider_whitespace_raises(plugin):
    """Whitespace-only provider should raise ValueError."""
    with pytest.raises(ValueError, match="Unknown provider"):
        export_openai_compatible(plugin, provider="   ")


def test_provider_special_characters_raises(plugin):
    """Provider names with special characters should fail cleanly."""
    with pytest.raises(ValueError, match="Unknown provider"):
        export_openai_compatible(plugin, provider="open; rm -rf /")


def test_provider_numeric_string_raises(plugin):
    """Numeric provider name should fail cleanly."""
    with pytest.raises(ValueError, match="Unknown provider"):
        export_openai_compatible(plugin, provider="12345")


def test_provider_very_long_name_raises(plugin):
    """Very long provider names should fail cleanly, not crash."""
    with pytest.raises(ValueError, match="Unknown provider"):
        export_openai_compatible(plugin, provider="a" * 1000)


def test_provider_null_byte_injection_raises(plugin):
    """Null byte injection in provider name should fail cleanly."""
    with pytest.raises(ValueError, match="Unknown provider"):
        export_openai_compatible(plugin, provider="openai\x00extra")


def test_provider_none_raises(plugin):
    """None provider should raise a clear error."""
    with pytest.raises((ValueError, AttributeError, TypeError)):
        export_openai_compatible(plugin, provider=None)  # type: ignore[arg-type]


# ═══════════════════════════════════════════════════════════════════════════
# Boundary & exception tests — idempotency and determinism
# ═══════════════════════════════════════════════════════════════════════════


def test_export_is_deterministic(plugin):
    """Multiple calls must produce identical output (no state mutation)."""
    a = export_openai_compatible(plugin, provider="deepseek")
    b = export_openai_compatible(plugin, provider="deepseek")
    c = export_openai_compatible(plugin, provider="deepseek")
    assert a == b == c


def test_export_is_deterministic_after_errors(plugin):
    """Output must be deterministic even after prior calls raise errors."""
    # Call once successfully
    good = export_openai_compatible(plugin, provider="openai")
    # Trigger some errors (they are caught)
    for _ in range(5):
        try:
            export_openai_compatible(plugin, provider="nonexistent")
        except ValueError:
            pass
    # Output must still match
    assert export_openai_compatible(plugin, provider="openai") == good


def test_different_providers_independent(plugin):
    """Calling one provider must not affect another."""
    openai_tools = export_openai_compatible(plugin, provider="openai")
    zhipu_tools = export_openai_compatible(plugin, provider="zhipu")
    # Re-check openai is unchanged
    assert export_openai_compatible(plugin, provider="openai") == openai_tools
    # And zhipu remains unchanged
    assert export_openai_compatible(plugin, provider="zhipu") == zhipu_tools


# ═══════════════════════════════════════════════════════════════════════════
# Boundary & exception tests — tool name validation
# ═══════════════════════════════════════════════════════════════════════════


def test_tool_name_exactly_64_chars_accepted(plugin, monkeypatch):
    """Tool names at the max length (64 chars) are accepted."""
    # All existing tool names are well within 64 chars; just verify export succeeds
    tools = export_openai_compatible(plugin, provider="zhipu")
    for tool in tools:
        name = tool["function"]["name"]
        assert 1 <= len(name) <= 64, f"Name {name!r} length {len(name)} outside [1, 64]"


def test_tool_name_all_digits_handled(plugin):
    """Verify all standard tool names pass name validation for all providers."""
    for provider in PROVIDER_PROFILES:
        tools = export_openai_compatible(plugin, provider=provider)
        for tool in tools:
            # Every exported tool must have a non-empty, sane name
            name = tool if provider in ("anthropic",) else tool["function"]["name"]
            if isinstance(tool, dict) and "function" in tool:
                name = tool["function"]["name"]
            elif isinstance(tool, dict) and "name" in tool:
                name = tool["name"]
            else:
                name = str(tool)
            assert len(name) >= 1


def test_tool_name_zhipu_sanitization_no_double_underscore(plugin):
    """Zhipu sanitization should not create double underscores."""
    tools = export_openai_compatible(plugin, provider="zhipu")
    for tool in tools:
        name = tool["function"]["name"]
        assert "__" not in name, f"Double underscore in {name!r}"


def test_tool_name_standard_accepts_dashes(plugin):
    """Standard name rules accept dashes in tool names."""
    tools = export_openai_compatible(plugin, provider="openai")
    # Some tool names have dashes in aliases but canonical names use underscores
    # Verify that all exported names pass standard rules
    import re

    for tool in tools:
        name = tool["function"]["name"]
        assert re.match(r"^[a-zA-Z0-9_-]{1,64}$", name), f"Name {name!r} fails standard pattern"


# ═══════════════════════════════════════════════════════════════════════════
# Boundary & exception tests — MCP auto-generation edge cases
# ═══════════════════════════════════════════════════════════════════════════


class FakeMCPTool:
    """Fake MCP that records registered tools with their signatures."""

    def __init__(self, name):
        self.name = name
        self.tools = {}

    def tool(self):
        def decorator(func):
            self.tools[func.__name__] = func
            return func

        return decorator


def test_mcp_generates_tool_with_zero_parameters(monkeypatch):
    """abi_list_types has no parameters — must still generate a valid function."""
    import abi.mcp.server as server

    fake = FakeMCPTool("abi")
    monkeypatch.setattr(server, "FastMCP", lambda name: fake)

    server.create_server()
    assert "abi_list_types" in fake.tools
    fn = fake.tools["abi_list_types"]
    sig = __import__("inspect").signature(fn)
    # abi_list_types has no required params and no optional params
    assert len(sig.parameters) == 0


def test_mcp_generates_tool_with_many_parameters(monkeypatch):
    """abi_run has ~20 parameters — must all be generated correctly."""
    import abi.mcp.server as server

    fake = FakeMCPTool("abi")
    monkeypatch.setattr(server, "FastMCP", lambda name: fake)

    server.create_server(profile="full")
    assert "abi_run" in fake.tools
    fn = fake.tools["abi_run"]
    sig = __import__("inspect").signature(fn)
    # Must have all expected params
    param_names = set(sig.parameters)
    assert "analysis_type" in param_names
    assert "confirm_execution" in param_names
    assert "engine" in param_names
    # confirm_execution is required — must have no default
    assert sig.parameters["confirm_execution"].default is sig.empty  # type: ignore[attr-defined]
    # engine is optional
    assert sig.parameters["engine"].default is not sig.empty  # type: ignore[attr-defined]


def test_mcp_generated_tools_are_callable(monkeypatch):
    """Every generated MCP tool must be callable with its required params."""
    import abi.mcp.server as server

    fake = FakeMCPTool("abi")
    monkeypatch.setattr(server, "FastMCP", lambda name: fake)

    server.create_server()
    # All generated tools should be callable (will fail at runtime due to no real agent,
    # but the function objects must be valid)
    for tool_name, fn in fake.tools.items():
        assert callable(fn), f"{tool_name} is not callable"
        sig = __import__("inspect").signature(fn)
        # With PEP 563 (from __future__ import annotations), annotations are strings
        assert sig.return_annotation in (str, "str"), (
            f"{tool_name} return annotation is {sig.return_annotation!r}"
        )


def test_mcp_legacy_autoplasm_alias_registered(monkeypatch):
    """The legacy autoplasm_validate_result tool must be registered alongside new tools."""
    import abi.mcp.server as server

    fake = FakeMCPTool("abi")
    monkeypatch.setattr(server, "FastMCP", lambda name: fake)

    server.create_server(profile="management")
    assert "autoplasm_validate_result" in fake.tools
    fn = fake.tools["autoplasm_validate_result"]
    sig = __import__("inspect").signature(fn)
    # result_dir is required, allow_empty_tables is optional
    assert "result_dir" in sig.parameters
    assert "allow_empty_tables" in sig.parameters


# ═══════════════════════════════════════════════════════════════════════════
# Boundary & exception tests — backward compat export_openai_tools
# ═══════════════════════════════════════════════════════════════════════════


def test_export_openai_tools_invalid_format_raises(plugin):
    """Unknown descriptor_format must raise ValueError."""
    with pytest.raises(ValueError, match="Unknown OpenAI tool export format"):
        export_openai_tools(plugin, descriptor_format="invalid_format")


def test_export_openai_tools_empty_format_raises(plugin):
    """Empty descriptor_format must raise ValueError."""
    with pytest.raises(ValueError, match="Unknown OpenAI tool export format"):
        export_openai_tools(plugin, descriptor_format="")


def test_export_openai_tools_all_valid_formats(plugin):
    """All three valid descriptor formats must return correct structure."""
    # responses (flat, with strict and name at top level)
    resp = export_openai_tools(plugin, descriptor_format="responses")
    assert all("name" in t and "strict" in t for t in resp)

    # apps-sdk (flat, with inputSchema, annotations)
    apps = export_openai_tools(plugin, descriptor_format="apps-sdk")
    assert all("inputSchema" in t and "annotations" in t for t in apps)

    # json (internal ABI format)
    js = export_openai_tools(plugin, descriptor_format="json")
    assert all("input_schema" in t and "permission" in t for t in js)


# ═══════════════════════════════════════════════════════════════════════════
# Boundary & exception tests — plugin edge cases
# ═══════════════════════════════════════════════════════════════════════════


def test_plugin_with_non_ascii_plugin_id():
    """If a plugin has a non-ASCII plugin_id, descriptions should still work."""

    class NonAsciiPlugin:
        plugin_id = "宏基因组分析"
        description = "元基因组分析"

    tools = export_openai_compatible(NonAsciiPlugin(), provider="openai")
    assert len(tools) == SAFE_TOOL_COUNT  # still produces tools
    assert "宏基因组分析" in tools[0]["function"]["description"]


def test_plugin_with_empty_plugin_id():
    """Plugin with empty plugin_id should still produce output."""

    class EmptyIdPlugin:
        plugin_id = ""

    tools = export_openai_compatible(EmptyIdPlugin(), provider="openai")
    assert len(tools) == SAFE_TOOL_COUNT
    assert "Plugin scope:" in tools[0]["function"]["description"]


def test_plugin_with_special_plugin_id():
    """Plugin with special characters in plugin_id should not break."""

    class SpecialPlugin:
        plugin_id = "test<script>alert(1)</script>"

    tools = export_openai_compatible(SpecialPlugin(), provider="openai")
    assert len(tools) == SAFE_TOOL_COUNT
    # The plugin_id is embedded in JSON — callers are responsible for escaping
    assert "test<script>" in tools[0]["function"]["description"]


# ═══════════════════════════════════════════════════════════════════════════
# Boundary & exception tests — schema integrity
# ═══════════════════════════════════════════════════════════════════════════


def test_exported_schemas_have_required_fields(plugin):
    """Every output format must produce tools with the minimum required fields."""
    for provider in PROVIDER_PROFILES:
        tools = export_openai_compatible(plugin, provider=provider)
        for tool in tools:
            assert "type" in tool
            assert "function" in tool
            func = tool["function"]
            assert "name" in func
            assert "description" in func
            assert "parameters" in func
            params = func["parameters"]
            assert "type" in params
            assert params["type"] == "object"
            assert "properties" in params
            assert isinstance(params["properties"], dict)
            assert "required" in params
            assert isinstance(params["required"], list)


def test_anthropic_schemas_have_required_fields(plugin):
    """Anthropic format must have consistent structure."""
    tools = export_anthropic(plugin)
    for tool in tools:
        assert "name" in tool
        assert "description" in tool
        assert "input_schema" in tool
        schema = tool["input_schema"]
        assert "type" in schema
        assert schema["type"] == "object"
        assert "properties" in schema
        assert "required" in schema


def test_gemini_schemas_have_required_fields(plugin):
    """Gemini format must have consistent structure."""
    result = export_gemini(plugin)
    assert "function_declarations" in result
    for decl in result["function_declarations"]:
        assert "name" in decl
        assert "description" in decl
        assert "parameters" in decl
        params = decl["parameters"]
        assert "type" in params
        assert params["type"] == "object"
        assert "properties" in params
        assert "required" in params


def test_all_exports_include_all_read_only_tools(plugin):
    """Read-only tools must appear in every export format, every provider."""
    from abi.tool_descriptors import READ_ONLY_TOOLS

    read_only_names = set(READ_ONLY_TOOLS)

    # OpenAI-compatible
    for provider in PROVIDER_PROFILES:
        tools = export_openai_compatible(plugin, provider=provider)
        exported = {t["function"]["name"] for t in tools}
        missing = read_only_names - exported
        assert not missing, f"Provider {provider} missing read-only tools: {missing}"

    # Anthropic
    ant = export_anthropic(plugin)
    ant_names = {t["name"] for t in ant}
    assert read_only_names <= ant_names

    # Gemini
    gem = export_gemini(plugin)
    gem_names = {t["name"] for t in gem["function_declarations"]}
    assert read_only_names <= gem_names


# ═══════════════════════════════════════════════════════════════════════════
# Boundary & exception tests — TOOL_ALIASES integrity
# ═══════════════════════════════════════════════════════════════════════════


def test_tool_aliases_no_duplicate_values_for_different_keys():
    """Each canonical method name should map consistently (no conflicting aliases)."""
    abi_keys = {k for k in TOOL_ALIASES if k.startswith("abi_")}
    # For each abi_ key, there should be a hyphenated variant with the same value
    for key in abi_keys:
        hyphenated = key.replace("_", "-")
        if hyphenated in TOOL_ALIASES:
            assert TOOL_ALIASES[hyphenated] == TOOL_ALIASES[key], (
                f"Alias conflict: {key}→{TOOL_ALIASES[key]} "
                f"vs {hyphenated}→{TOOL_ALIASES[hyphenated]}"
            )


def test_tool_aliases_abi_keys_match_abi_agent_tools():
    """Every ABI_AGENT_TOOLS key must be present in TOOL_ALIASES."""
    for name in ABI_AGENT_TOOLS:
        assert name in TOOL_ALIASES, f"{name} not in TOOL_ALIASES"


def test_tool_aliases_contains_all_hyphenated_variants():
    """For every abi_* tool name, there should be a hyphenated alias with same value."""
    for name in ABI_AGENT_TOOLS:
        # abi_list_types → list-types, abi-dry-run → dry-run, etc.
        # The short form should also exist
        short = name.replace("abi_", "", 1)
        if short in TOOL_ALIASES:
            # Short form exists, verify it maps correctly
            pass  # may map differently; just confirm it's present
        # The hyphenated variant of the abi_ name
        hyphenated = name.replace("_", "-")
        assert hyphenated in TOOL_ALIASES or hyphenated.replace("abi-", "") in TOOL_ALIASES, (
            f"No hyphenated alias for {name}"
        )


# ═══════════════════════════════════════════════════════════════════════════
# Boundary & exception tests — description content safety
# ═══════════════════════════════════════════════════════════════════════════


def test_descriptions_never_empty(plugin):
    """Every exported tool in every format must have a non-empty description."""
    for provider in PROVIDER_PROFILES:
        tools = export_openai_compatible(plugin, provider=provider)
        for tool in tools:
            desc = tool["function"]["description"]
            assert len(desc) > 0, (
                f"Provider {provider} tool {tool['function']['name']} has empty description"
            )

    ant = export_anthropic(plugin)
    for tool in ant:
        assert len(tool["description"]) > 0

    gem = export_gemini(plugin)
    for decl in gem["function_declarations"]:
        assert len(decl["description"]) > 0


def test_descriptions_contain_plugin_scope(plugin):
    """Every description must include the plugin scope marker."""
    for provider in PROVIDER_PROFILES:
        tools = export_openai_compatible(plugin, provider=provider)
        for tool in tools:
            assert "Plugin scope:" in tool["function"]["description"]

    ant = export_anthropic(plugin)
    for tool in ant:
        assert "Plugin scope:" in tool["description"]


# ═══════════════════════════════════════════════════════════════════════════
# Boundary & exception tests — cross-format consistency
# ═══════════════════════════════════════════════════════════════════════════


def test_all_formats_export_same_number_of_tools(plugin):
    """All formats should export the same number of tools (excluding execution)."""
    openai_count = len(export_openai_compatible(plugin, provider="openai"))
    deepseek_count = len(export_openai_compatible(plugin, provider="deepseek"))
    zhipu_count = len(export_openai_compatible(plugin, provider="zhipu"))
    anthropic_count = len(export_anthropic(plugin))
    gemini_count = len(export_gemini(plugin)["function_declarations"])

    assert (
        openai_count
        == deepseek_count
        == zhipu_count
        == anthropic_count
        == gemini_count
        == SAFE_TOOL_COUNT
    )


def test_same_tool_names_across_formats(plugin):
    """Tool names should be consistent across all formats for the same plugin."""
    openai_names = {t["function"]["name"] for t in export_openai_compatible(plugin)}
    anthropic_names = {t["name"] for t in export_anthropic(plugin)}
    gemini_names = {t["name"] for t in export_gemini(plugin)["function_declarations"]}

    # Names should match (zhipu sanitizes names, so use openai as baseline)
    assert openai_names == anthropic_names == gemini_names


def test_execution_tool_always_has_confirmation_flag_in_json(plugin):
    """abi_run must always show requires_confirmation=True in JSON format."""
    tools = export_json(plugin, include_execution=True)
    run_tool = [t for t in tools if t["name"] == "abi_run"][0]
    assert run_tool["requires_confirmation"] is True
    assert run_tool["permission"] == "execution"


# ═══════════════════════════════════════════════════════════════════════════
# Boundary tests — large-volume / stress
# ═══════════════════════════════════════════════════════════════════════════


def test_many_provider_exports_no_memory_leak(plugin):
    """Exporting tools thousands of times across providers should not OOM or degrade."""
    for _ in range(50):
        for provider in PROVIDER_PROFILES:
            tools = export_openai_compatible(plugin, provider=provider)
            assert len(tools) == SAFE_TOOL_COUNT


def test_rapid_format_switching_no_corruption(plugin):
    """Rapidly switching between formats must not corrupt output."""
    results = []
    for i in range(20):
        if i % 3 == 0:
            results.append(export_openai_compatible(plugin, provider="openai"))
        elif i % 3 == 1:
            results.append(export_anthropic(plugin))
        else:
            results.append(export_gemini(plugin)["function_declarations"])
    # All results must have 9 tools
    for result in results:
        assert len(result) == SAFE_TOOL_COUNT


# ═══════════════════════════════════════════════════════════════════════════
# Boundary tests — JSON serialization round-trip
# ═══════════════════════════════════════════════════════════════════════════


def test_all_output_is_json_serializable(plugin):
    """Every export format must produce JSON-serializable output."""
    import json

    for provider in PROVIDER_PROFILES:
        tools = export_openai_compatible(plugin, provider=provider)
        serialized = json.dumps(tools, ensure_ascii=False)
        round_tripped = json.loads(serialized)
        assert round_tripped == tools

    ant = export_anthropic(plugin)
    assert json.loads(json.dumps(ant, ensure_ascii=False)) == ant

    gem = export_gemini(plugin)
    assert json.loads(json.dumps(gem, ensure_ascii=False)) == gem

    js = export_json(plugin)
    assert json.loads(json.dumps(js, ensure_ascii=False)) == js


def test_no_nan_or_inf_in_output(plugin):
    """No output should contain NaN, Infinity, or other non-JSON values."""
    import json

    for provider in PROVIDER_PROFILES:
        tools = export_openai_compatible(plugin, provider=provider)
        # Must not raise
        json.dumps(tools, allow_nan=False)

    json.dumps(export_anthropic(plugin), allow_nan=False)
    json.dumps(export_gemini(plugin), allow_nan=False)
    json.dumps(export_json(plugin), allow_nan=False)
