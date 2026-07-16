"""Unit tests for pure helper functions in abi.tools.

Covers functions with NO I/O, NO subprocess, NO filesystem access — 100% memory-only.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

import pytest

from abi.errors import ToolError
from abi.tools import (
    GenericCommandSkill,
    ToolRegistry,
    _derive_composite_params,
    _looks_like_path,
    _resource_fields,
)

# ── _looks_like_path ──────────────────────────────────────────────────────────


def test_looks_like_path_absolute():
    """Absolute paths are detected as file paths."""
    assert _looks_like_path("/data/sample.fq") is True


def test_looks_like_path_relative_dot_slash():
    """Paths starting with ./ or ../ are detected."""
    assert _looks_like_path("./sample.tsv") is True
    assert _looks_like_path("../data/sample.tsv") is True


def test_looks_like_path_slash_in_middle():
    """Relative paths with a slash anywhere are detected."""
    assert _looks_like_path("data/sample.fq") is True


def test_looks_like_path_known_extension():
    """Filenames with known extensions (.fa, .fasta, .fq, .fastq, .gz, .bam, .sam, etc.) match."""
    assert _looks_like_path("sample.fastq") is True
    assert _looks_like_path("sample.fq.gz") is True
    assert _looks_like_path("sample.bam") is True
    assert _looks_like_path("sample.sam") is True
    assert _looks_like_path("sample.fa") is True
    assert _looks_like_path("sample.fna") is True
    assert _looks_like_path("sample.tsv") is True
    assert _looks_like_path("sample.csv") is True
    assert _looks_like_path("sample.json") is True
    assert _looks_like_path("sample.yaml") is True
    assert _looks_like_path("sample.txt") is True
    assert _looks_like_path("sample.nwk") is True
    assert _looks_like_path("sample.R") is True
    assert _looks_like_path("sample.py") is True
    assert _looks_like_path("sample.sh") is True


def test_looks_like_path_false_dna_sequence():
    """Raw DNA sequence strings are not paths."""
    assert _looks_like_path("GTGCCAGCAGCCGCGGTAATAC") is False


def test_looks_like_path_false_simple_name():
    """Plain tool names are not paths."""
    assert _looks_like_path("metaphlan") is False
    assert _looks_like_path("featureCounts") is False


def test_looks_like_path_false_no_slash_no_known_ext():
    """Strings without slashes or known extensions are not paths."""
    assert _looks_like_path("42") is False
    assert _looks_like_path("local") is False


# ── _derive_composite_params ─────────────────────────────────────────────────


def test_derive_composite_paired_end():
    """When both read1 and read2 are present, derive metaphlan_input as comma-separated pair."""
    params: dict = {"read1": "fwd.fq", "read2": "rev.fq"}
    _derive_composite_params(params)
    assert params["metaphlan_input"] == "fwd.fq,rev.fq"
    assert params["metaphlan_long_reads_flag"] == ""
    assert params["metaphlan_long_reads"] is False
    assert params["read1"] == "fwd.fq"  # original keys preserved
    assert params["read2"] == "rev.fq"


def test_derive_composite_single_end():
    """When only read1 is present, derive metaphlan_input from it."""
    params: dict = {"read1": "reads.fq"}
    _derive_composite_params(params)
    assert params["metaphlan_input"] == "reads.fq"
    assert params["metaphlan_long_reads_flag"] == ""


def test_derive_composite_long_read():
    """When only long_reads is present, derive metaphlan_input from it."""
    params: dict = {"long_reads": "long.fq"}
    _derive_composite_params(params)
    assert params["metaphlan_input"] == "long.fq"
    assert params["metaphlan_long_reads_flag"] == "--long_reads"
    assert params["metaphlan_long_reads"] is True


def test_derive_composite_paired_wins_over_long_reads():
    """read1+read2 take precedence over long_reads when all three are present."""
    params: dict = {"read1": "fwd.fq", "read2": "rev.fq", "long_reads": "long.fq"}
    _derive_composite_params(params)
    assert params["metaphlan_input"] == "fwd.fq,rev.fq"
    # metaphlan_long_reads_flag is "" because paired-end wins (input type matches metaphlan_input)
    assert params["metaphlan_long_reads_flag"] == ""


def test_derive_composite_no_inputs():
    """When no inputs are provided, nothing is derived."""
    params: dict = {}
    _derive_composite_params(params)
    assert "metaphlan_input" not in params
    assert params["metaphlan_long_reads_flag"] == ""


def test_derive_composite_already_set():
    """When metaphlan_input is already set, it is NOT overwritten."""
    params: dict = {"metaphlan_input": "custom_input", "read1": "fwd.fq", "read2": "rev.fq"}
    _derive_composite_params(params)
    assert params["metaphlan_input"] == "custom_input"
    assert params["metaphlan_long_reads_flag"] == ""


def test_plasmid_skill_uses_canonical_metaphlan_derivation():
    from abi.plugins.metagenomic_plasmid._engine.skills.base import (
        GenericCommandSkill as PlasmidCommandSkill,
    )

    params = {"long_reads": "long.fq"}
    expected = dict(params)
    _derive_composite_params(expected)
    selected = PlasmidCommandSkill(
        {
            "id": "metaphlan",
            "command_template": "metaphlan {metaphlan_input} {metaphlan_long_reads_flag}",
        }
    ).select_params(params)

    assert selected["metaphlan_input"] == expected["metaphlan_input"]
    assert selected["metaphlan_long_reads_flag"] == expected["metaphlan_long_reads_flag"]


def test_generic_command_skill_injects_execution_resource_root(monkeypatch, tmp_path: Path):
    resource_root = tmp_path / "resources" / "autoplasm"
    monkeypatch.setenv("ABI_RESOURCE_ROOT", str(resource_root))
    skill = _make_skill({"command_template": "python {resource_root}/PLASMe/PLASMe.py {assembly}"})

    command = skill.build_command({"assembly": "assembly.fa"})

    assert command == ["python", str(resource_root / "PLASMe" / "PLASMe.py"), "assembly.fa"]


# ── GenericCommandSkill._check_dotted_fields ────────────────────────────────


def _make_skill(metadata_override: dict | None = None) -> GenericCommandSkill:
    """Construct a minimal GenericCommandSkill for testing."""
    base: dict = {"id": "test_tool"}
    if metadata_override:
        base.update(metadata_override)
    return GenericCommandSkill(base)


def test_validate_inputs_skips_contract_string_values_that_look_like_paths():
    """Output prefixes are command values, not files required before execution."""
    skill = _make_skill(
        {
            "inputs": {
                "read1": {"type": "file", "required": True},
                "output_prefix": {"type": "string", "required": True},
            }
        }
    )
    skill.validate_inputs(
        {
            "read1": str(Path(__file__).resolve()),
            "output_prefix": "/not-created-yet/S1.",
        }
    )


def test_check_dotted_fields_valid_template():
    """Template with only simple {field} references passes without error."""
    skill = _make_skill(
        {"command_template": "tool --input {input} --output {output} --threads {threads}"}
    )
    # Should not raise
    skill._check_dotted_fields()


def test_check_dotted_fields_rejects_dotted():
    """Template with {nested.field} raises ToolError."""
    skill = _make_skill({"command_template": "tool --db {database.path}"})
    with pytest.raises(ToolError, match="dotted"):
        skill._check_dotted_fields()


def test_check_dotted_fields_rejects_bracket_index():
    """Template with {arr[0]} raises ToolError."""
    skill = _make_skill({"command_template": "tool --first {inputs[0]}"})
    with pytest.raises(ToolError, match="dotted"):
        skill._check_dotted_fields()


def test_check_dotted_fields_no_placeholders():
    """Template with no format placeholders at all passes."""
    skill = _make_skill({"command_template": "tool --version"})
    # Should not raise
    skill._check_dotted_fields()


# ── GenericCommandSkill._command_without_stdout_redirect ────────────────────


def test_command_without_stdout_no_redirect():
    """Command list without '>' is returned unchanged with None target."""
    skill = _make_skill()
    cmd, target = skill._command_without_stdout_redirect(
        ["tool", "--input", "file.fq", "--output", "out/"]
    )
    assert cmd == ["tool", "--input", "file.fq", "--output", "out/"]
    assert target is None


def test_command_without_stdout_single_redirect():
    """Command list with '>' and a target strips both from the list."""
    skill = _make_skill()
    cmd, target = skill._command_without_stdout_redirect(
        ["tool", "--input", "file.fq", ">", "output.txt"]
    )
    assert cmd == ["tool", "--input", "file.fq"]
    assert target == Path("output.txt")


def test_command_without_stdout_missing_target():
    """Command ending with '>' but no target after raises ToolError."""
    skill = _make_skill()
    with pytest.raises(ToolError, match="missing a target"):
        skill._command_without_stdout_redirect(["tool", ">"])
    with pytest.raises(ToolError, match="missing a target"):
        skill._command_without_stdout_redirect(["tool", "--input", "file.fq", ">"])


def test_command_without_stdout_multiple_redirects():
    """Command with two '>' tokens raises ToolError."""
    skill = _make_skill()
    with pytest.raises(ToolError, match="multiple"):
        skill._command_without_stdout_redirect(["tool", ">", "out1.txt", ">", "out2.txt"])


# ── GenericCommandSkill.build_command ─────────────────────────────────────────


def test_build_command_does_not_insert_stop_marker_into_shell_wrapper():
    """Dash-prefixed shell-wrapper arguments must not rewrite ``sh -c`` itself."""
    template = 'sh -c \'printf "%s\\n" "$1" > "$2"\' wrapper {value} {output}'
    skill = _make_skill({"command_template": template})

    command = skill.build_command({"value": "-dash-prefixed", "output": "out.txt"})

    assert command[:3] == ["sh", "-c", 'printf "%s\\n" "$1" > "$2"']
    assert command[3:] == ["wrapper", "-dash-prefixed", "out.txt"]


# ── ToolRegistry.env_for ─────────────────────────────────────────────────────


def test_env_for_direct_hit():
    """Direct tool ID lookup in the target plugin map."""
    ToolRegistry._env_assignments = {"my_plugin": {"tool_a": "env_a"}}
    assert ToolRegistry.env_for("tool_a", plugin_name="my_plugin") == "env_a"


def test_env_for_does_not_search_across_plugins():
    """When not found in target plugin, other plugin maps are ignored."""
    ToolRegistry._env_assignments = {
        "my_plugin": {},
        "other_plugin": {"tool_b": "env_b"},
    }
    assert ToolRegistry.env_for("tool_b", plugin_name="my_plugin") == "abi-base"


def test_env_for_default_key():
    """When no direct lookup works, checks _default plugin."""
    ToolRegistry._env_assignments = {"_default": {"tool_c": "env_c"}}
    assert ToolRegistry.env_for("tool_c", plugin_name="my_plugin") == "env_c"


def test_env_for_abi_base_when_none_assigned():
    """Returns 'abi-base' when _env_assignments is None."""
    ToolRegistry._env_assignments = None
    assert ToolRegistry.env_for("any_tool", plugin_name="my_plugin") == "abi-base"


def test_env_for_abi_base_when_empty():
    """Returns 'abi-base' when _env_assignments is an empty dict."""
    ToolRegistry._env_assignments = {}
    assert ToolRegistry.env_for("any_tool", plugin_name="my_plugin") == "abi-base"


# ── _resource_fields ─────────────────────────────────────────────────────────


def test_resource_fields_extracts_fields():
    """Template fields in RESOURCE_FIELDS are extracted."""
    template = "{database} indexed with {model}"
    fields = _resource_fields(template)
    assert "database" in fields
    assert "model" in fields
    assert len(fields) == 2


def test_resource_fields_ignores_non_resource():
    """Template fields not in RESOURCE_FIELDS are skipped."""
    template = "tool --input {input} --db {database} --cpu {threads}"
    fields = _resource_fields(template)
    assert "database" in fields
    assert "input" not in fields
    assert "threads" not in fields


def test_resource_fields_no_placeholders():
    """Template with no placeholders returns an empty list."""
    assert _resource_fields("no placeholders here") == []


def test_resource_fields_dotted_nested():
    """Dotted/indexed field names are resolved to the root key."""
    template = "{database.path} and {model[0]}"
    fields = _resource_fields(template)
    assert "database" in fields
    assert "model" in fields


def test_resource_fields_deduplication():
    """Duplicate resource field references are de-duplicated."""
    template = "{database} with {database} again"
    fields = _resource_fields(template)
    assert fields == ["database"]
