"""Unit tests for SafeFormatDict strict mode and template parameter validation."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

import pytest

from abi.errors import MissingTemplateParamError
from abi.tools import ResourceSpec, SafeFormatDict, resolve_resources


class TestSafeFormatDictLenient:
    """Lenient mode (default): missing keys → "" + WARNING."""

    def test_known_key_returns_value(self):
        d = SafeFormatDict({"input": "file.fasta", "threads": 4})
        assert d["input"] == "file.fasta"
        assert d["threads"] == 4

    def test_missing_key_returns_empty_string(self):
        d = SafeFormatDict({"input": "file.fasta"})
        result = d["nonexistent"]
        assert result == ""

    def test_missing_key_is_recorded(self):
        d = SafeFormatDict({"input": "file.fasta"})
        _ = d["optional_flag"]
        _ = d["another_missing"]
        assert "optional_flag" in d.missing_keys
        assert "another_missing" in d.missing_keys

    def test_format_map_substitutes_missing_with_empty(self):
        template = "tool --input {input} --flag {optional_flag}"
        d = SafeFormatDict({"input": "file.fasta"})
        result = template.format_map(d)
        assert result == "tool --input file.fasta --flag "
        assert "optional_flag" in d.missing_keys

    def test_format_map_with_all_keys_present(self):
        template = "tool --input {input} --threads {threads}"
        d = SafeFormatDict({"input": "file.fasta", "threads": 8})
        result = template.format_map(d)
        assert result == "tool --input file.fasta --threads 8"
        assert d.missing_keys == []

    def test_missing_keys_deduplication(self):
        """Same key requested multiple times → recorded once per lookup."""
        d = SafeFormatDict({"input": "file.fasta"})
        _ = d["missing"]
        _ = d["missing"]
        assert d.missing_keys == ["missing", "missing"]


class TestSafeFormatDictStrict:
    """Strict mode: missing keys → MissingTemplateParamError."""

    def test_strict_raises_on_missing(self):
        d = SafeFormatDict({"input": "file.fasta"}, strict=True, tool_name="fastp")
        with pytest.raises(MissingTemplateParamError) as excinfo:
            _ = d["undefined_param"]
        assert "undefined_param" in str(excinfo.value)
        assert "fastp" in str(excinfo.value)

    def test_strict_does_not_raise_for_known_keys(self):
        d = SafeFormatDict({"input": "file.fasta", "threads": 4}, strict=True)
        assert d["input"] == "file.fasta"
        assert d["threads"] == 4

    def test_strict_via_env_var(self, monkeypatch):
        """ABI_STRICT_TEMPLATES=1 enables strict mode when not explicitly set."""
        monkeypatch.setenv("ABI_STRICT_TEMPLATES", "1")
        d = SafeFormatDict({"input": "file.fasta"})
        assert d.strict is True
        with pytest.raises(MissingTemplateParamError):
            _ = d["undefined"]

    def test_strict_records_missing_before_raising(self):
        d = SafeFormatDict({"input": "file.fasta"}, strict=True)
        try:
            _ = d["param1"]
        except MissingTemplateParamError:
            pass
        assert "param1" in d.missing_keys

    def test_explicit_strict_overrides_env(self, monkeypatch):
        """Explicit strict=False overrides ABI_STRICT_TEMPLATES=1."""
        monkeypatch.setenv("ABI_STRICT_TEMPLATES", "1")
        d = SafeFormatDict({"input": "file.fasta"}, strict=False)
        assert d.strict is False
        result = d["undefined"]
        assert result == ""

    def test_format_map_raises_in_strict_mode(self):
        template = "tool --input {input} --flag {undefined_flag}"
        d = SafeFormatDict({"input": "file.fasta"}, strict=True)
        with pytest.raises(MissingTemplateParamError):
            template.format_map(d)


class TestSafeFormatDictToolName:
    """Tool name is included in error messages."""

    def test_tool_name_in_error(self):
        d = SafeFormatDict({}, strict=True, tool_name="kraken2")
        with pytest.raises(MissingTemplateParamError) as excinfo:
            _ = d["database"]
        assert "kraken2" in str(excinfo.value)

    def test_tool_name_defaults_to_empty(self):
        d = SafeFormatDict({}, strict=True)
        with pytest.raises(MissingTemplateParamError) as excinfo:
            _ = d["missing"]
        assert "unknown" in str(excinfo.value)


# ═══════════════════════════════════════════════════════════════════════════
# ResourceSpec tests (Phase 1)
# ═══════════════════════════════════════════════════════════════════════════


class TestResourceSpec:
    """Unit tests for ResourceSpec dataclass."""

    def test_defaults(self):
        spec = ResourceSpec()
        assert spec.cpu == 1
        assert spec.memory == "4GB"
        assert spec.walltime == "01:00:00"
        assert spec.accelerator is None
        assert spec.disk is None

    def test_from_metadata_extracts_resources(self):
        metadata = {
            "id": "spades",
            "resources": {"cpu": 16, "memory": "64GB", "walltime": "08:00:00"},
        }
        spec = ResourceSpec.from_metadata(metadata)
        assert spec.cpu == 16
        assert spec.memory == "64GB"
        assert spec.walltime == "08:00:00"

    def test_from_metadata_without_resources_returns_defaults(self):
        spec = ResourceSpec.from_metadata({"id": "fastp"})
        assert spec.cpu == 1
        assert spec.memory == "4GB"

    def test_from_metadata_partial_uses_defaults(self):
        spec = ResourceSpec.from_metadata({"resources": {"cpu": 8}})
        assert spec.cpu == 8
        assert spec.memory == "4GB"  # default
        assert spec.walltime == "01:00:00"  # default

    def test_from_profile(self):
        profile = {"cpu": 32, "memory": "128GB"}
        spec = ResourceSpec.from_profile(profile)
        assert spec.cpu == 32
        assert spec.memory == "128GB"
        assert spec.walltime == "01:00:00"  # default

    def test_merge_applies_non_default_overrides(self):
        base = ResourceSpec(cpu=8, memory="16GB", walltime="02:00:00")
        overrides = ResourceSpec(cpu=32)  # only cpu set, others default
        merged = base.merge(overrides)
        assert merged.cpu == 32  # overridden
        assert merged.memory == "16GB"  # preserved
        assert merged.walltime == "02:00:00"  # preserved

    def test_merge_with_none_returns_self(self):
        spec = ResourceSpec(cpu=8)
        result = spec.merge(None)
        assert result.cpu == 8


class TestResourceSpecDirectives:
    """Scheduler-specific directive rendering."""

    def test_to_nextflow_directives(self):
        spec = ResourceSpec(cpu=8, memory="16GB", walltime="04:00:00")
        dirs = spec.to_nextflow_directives()
        assert "cpus 8" in dirs
        assert "memory '16.GB'" in dirs
        assert "time '04:00:00'" in dirs

    def test_to_nextflow_with_disk(self):
        spec = ResourceSpec(cpu=4, memory="8GB", walltime="01:00:00", disk="50GB")
        dirs = spec.to_nextflow_directives()
        assert "disk '50.GB'" in dirs

    def test_to_slurm_directives(self):
        spec = ResourceSpec(cpu=16, memory="64GB", walltime="08:00:00")
        dirs = spec.to_slurm_directives()
        assert "#SBATCH --cpus-per-task=16" in dirs
        assert "#SBATCH --mem=64G" in dirs
        assert "#SBATCH --time=08:00:00" in dirs

    def test_to_pbs_directives(self):
        spec = ResourceSpec(cpu=8, memory="32GB", walltime="04:00:00")
        dirs = spec.to_pbs_directives()
        assert "#PBS -l nodes=1:ppn=8" in dirs
        assert "#PBS -l mem=32g" in dirs
        assert "#PBS -l walltime=04:00:00" in dirs

    @pytest.mark.parametrize(
        "memory_in,nextflow_out,slurm_out",
        [
            ("8GB", "8.GB", "8G"),
            ("16MB", "16.MB", "16M"),
            ("2TB", "2.TB", "2T"),
            ("4G", "4.GB", "4G"),
            ("32gb", "32.GB", "32G"),
        ],
    )
    def test_memory_format_variants(self, memory_in, nextflow_out, slurm_out):
        spec = ResourceSpec(cpu=4, memory=memory_in)
        nf = "\n".join(spec.to_nextflow_directives())
        assert f"memory '{nextflow_out}'" in nf
        slurm = "\n".join(spec.to_slurm_directives())
        assert f"--mem={slurm_out}" in slurm


class TestResolveResources:
    """Layered resource resolution."""

    def test_hardcoded_defaults_when_nothing_provided(self):
        spec = resolve_resources("fastp", {})
        assert spec.cpu == 1
        assert spec.memory == "4GB"

    def test_cli_overrides_have_highest_priority(self):
        cli = ResourceSpec(cpu=64)
        spec = resolve_resources(
            "spades",
            {"resources": {"cpu": 8}},
            cli_overrides=cli,
        )
        assert spec.cpu == 64  # CLI wins

    def test_tool_contract_overrides_defaults(self):
        spec = resolve_resources(
            "spades",
            {"resources": {"cpu": 16, "memory": "64GB"}},
        )
        assert spec.cpu == 16
        assert spec.memory == "64GB"

    def test_config_defaults_override_contract(self):
        spec = resolve_resources(
            "spades",
            {"resources": {"cpu": 8, "memory": "8GB"}},
            config={"execution": {"resources": {"defaults": {"cpu": 12}}}},
        )
        assert spec.cpu == 12  # config overrides contract
        assert spec.memory == "8GB"  # contract preserved

    def test_config_tool_override_has_higher_priority(self):
        spec = resolve_resources(
            "spades",
            {"resources": {"cpu": 8}},
            config={
                "execution": {
                    "resources": {
                        "defaults": {"cpu": 12},
                        "tool_overrides": {"spades": {"cpu": 32}},
                    }
                }
            },
        )
        assert spec.cpu == 32  # per-tool override wins

    def test_unknown_tool_id_uses_defaults(self):
        spec = resolve_resources("nonexistent", {})
        assert spec.cpu == 1

    def test_resource_profile_loads_from_disk(self):
        """dev_small profile should be loadable."""
        spec = resolve_resources("fastp", {}, resource_profile="dev_small")
        assert spec.cpu == 1  # dev_small profile
        assert spec.memory == "2GB"
