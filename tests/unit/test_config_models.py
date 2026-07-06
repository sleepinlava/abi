"""Tests for abi.config_models — Pydantic configuration models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from abi.config_models import (
    ABIConfig,
    AlignmentConfig,
    DifferentialExpressionConfig,
    ExecutionConfig,
    InputConfig,
    RNASeqConfig,
)

# ── ExecutionConfig ──────────────────────────────────────────────────────────


class TestExecutionConfigDefaults:
    """Default values for ExecutionConfig."""

    def test_default_construction(self) -> None:
        cfg = ExecutionConfig()
        assert cfg.parallel is False
        assert cfg.workers == 1
        assert cfg.error_policy == "halt"
        assert cfg.record_progress is False
        assert cfg.tool_timeout_seconds is None

    def test_model_dump_defaults(self) -> None:
        cfg = ExecutionConfig()
        d = cfg.model_dump()
        assert d == {
            "parallel": False,
            "workers": 1,
            "error_policy": "halt",
            "record_progress": False,
            "tool_timeout_seconds": None,
        }


class TestExecutionConfigValidation:
    """Field-level validation rules."""

    def test_workers_minimum(self) -> None:
        with pytest.raises(ValidationError) as exc:
            ExecutionConfig(workers=0)
        assert "workers" in str(exc.value)

    def test_workers_maximum(self) -> None:
        with pytest.raises(ValidationError) as exc:
            ExecutionConfig(workers=129)
        assert "workers" in str(exc.value)

    def test_workers_at_boundaries(self) -> None:
        assert ExecutionConfig(workers=1).workers == 1
        assert ExecutionConfig(workers=128).workers == 128

    def test_error_policy_valid_values(self) -> None:
        assert ExecutionConfig(error_policy="halt").error_policy == "halt"
        assert ExecutionConfig(error_policy="continue").error_policy == "continue"

    def test_error_policy_invalid_value(self) -> None:
        with pytest.raises(ValidationError) as exc:
            ExecutionConfig(error_policy="retry")
        assert "error_policy" in str(exc.value)


class TestExecutionConfigCustom:
    """Custom values via constructor and model_validate."""

    def test_custom_via_constructor(self) -> None:
        cfg = ExecutionConfig(
            parallel=True, workers=8, error_policy="continue", tool_timeout_seconds=30.0
        )
        assert cfg.parallel is True
        assert cfg.workers == 8
        assert cfg.error_policy == "continue"
        assert cfg.tool_timeout_seconds == 30.0

    def test_custom_via_model_validate(self) -> None:
        cfg = ExecutionConfig.model_validate(
            {"parallel": True, "workers": 16, "error_policy": "continue"}
        )
        assert cfg.parallel is True
        assert cfg.workers == 16

    def test_record_progress(self) -> None:
        assert ExecutionConfig(record_progress=True).record_progress is True


# ── ABIConfig ────────────────────────────────────────────────────────────────


class TestABIConfigDefaults:
    """Default values and nested defaults for ABIConfig."""

    def test_default_construction(self) -> None:
        cfg = ABIConfig()
        assert cfg.project_name == "ABI Analysis"
        assert cfg.outdir == "results"
        assert cfg.mode == "auto"
        assert cfg.threads == 4
        assert cfg.mamba_root is None
        assert cfg.resources == {}

    def test_execution_default_is_execution_config(self) -> None:
        cfg = ABIConfig()
        assert isinstance(cfg.execution, ExecutionConfig)
        assert cfg.execution.parallel is False
        assert cfg.execution.workers == 1
        assert cfg.execution.error_policy == "halt"

    def test_execution_default_factory_independent(self) -> None:
        """Each ABIConfig gets its own ExecutionConfig instance."""
        a = ABIConfig()
        b = ABIConfig()
        a.execution.workers = 32
        assert b.execution.workers == 1  # unaffected

    def test_resources_default_factory_independent(self) -> None:
        a = ABIConfig()
        b = ABIConfig()
        a.resources["key"] = "value"
        assert "key" not in b.resources

    def test_model_dump_defaults(self) -> None:
        d = ABIConfig().model_dump()
        assert d["project_name"] == "ABI Analysis"
        assert d["outdir"] == "results"
        assert d["mode"] == "auto"
        assert d["threads"] == 4
        assert d["execution"]["workers"] == 1


class TestABIConfigExtraAllow:
    """The ``extra="allow"`` model config."""

    def test_unknown_field_accepted(self) -> None:
        cfg = ABIConfig.model_validate({"custom_plugin_key": "value"})
        assert cfg.model_extra == {"custom_plugin_key": "value"}

    def test_extra_field_preserved_in_model_dump(self) -> None:
        cfg = ABIConfig.model_validate({"project_name": "Test", "custom_flag": True})
        d = cfg.model_dump()
        assert d["custom_flag"] is True

    def test_extra_field_accessible_via_extra(self) -> None:
        cfg = ABIConfig.model_validate({"custom_flag": True})
        assert cfg.model_extra is not None
        assert cfg.model_extra["custom_flag"] is True


class TestABIConfigValidation:
    """Field-level validation on ABIConfig."""

    def test_threads_minimum(self) -> None:
        with pytest.raises(ValidationError) as exc:
            ABIConfig(threads=0)
        assert "threads" in str(exc.value)

    def test_threads_maximum(self) -> None:
        with pytest.raises(ValidationError) as exc:
            ABIConfig(threads=1025)
        assert "threads" in str(exc.value)

    def test_threads_at_boundaries(self) -> None:
        assert ABIConfig(threads=1).threads == 1
        assert ABIConfig(threads=1024).threads == 1024

    def test_mode_valid_values(self) -> None:
        assert ABIConfig(mode="auto").mode == "auto"
        assert ABIConfig(mode="interactive").mode == "interactive"

    def test_mode_invalid_value(self) -> None:
        with pytest.raises(ValidationError) as exc:
            ABIConfig(mode="dry_run")
        assert "mode" in str(exc.value)


class TestABIConfigFromDict:
    """The ``from_dict()`` legacy bridge method."""

    def test_from_empty_dict(self) -> None:
        cfg = ABIConfig.from_dict({})
        assert cfg.project_name == "ABI Analysis"

    def test_from_dict_with_fields(self) -> None:
        cfg = ABIConfig.from_dict(
            {
                "project_name": "My Project",
                "threads": 8,
                "mode": "interactive",
            }
        )
        assert cfg.project_name == "My Project"
        assert cfg.threads == 8
        assert cfg.mode == "interactive"

    def test_from_dict_with_nested_execution(self) -> None:
        cfg = ABIConfig.from_dict(
            {
                "execution": {"workers": 16, "error_policy": "continue"},
            }
        )
        assert cfg.execution.workers == 16
        assert cfg.execution.error_policy == "continue"

    def test_from_dict_with_extra_fields(self) -> None:
        cfg = ABIConfig.from_dict({"custom_plugin_option": 42})
        assert cfg.model_extra == {"custom_plugin_option": 42}

    def test_from_dict_invalid_raises(self) -> None:
        with pytest.raises(ValidationError):
            ABIConfig.from_dict({"threads": 0})


class TestABIConfigToDictRoundTrip:
    """``to_dict()`` → ``from_dict()`` preserves values."""

    def test_round_trip_defaults(self) -> None:
        original = ABIConfig()
        round_tripped = ABIConfig.from_dict(original.to_dict())
        assert round_tripped.project_name == original.project_name
        assert round_tripped.threads == original.threads
        assert round_tripped.execution.workers == original.execution.workers

    def test_round_trip_custom(self) -> None:
        original = ABIConfig(
            project_name="Custom",
            threads=32,
            mode="interactive",
            execution=ExecutionConfig(workers=64, error_policy="continue"),
        )
        rt = ABIConfig.from_dict(original.to_dict())
        assert rt.project_name == "Custom"
        assert rt.threads == 32
        assert rt.mode == "interactive"
        assert rt.execution.workers == 64
        assert rt.execution.error_policy == "continue"

    def test_round_trip_with_extra_fields(self) -> None:
        original = ABIConfig.model_validate(
            {
                "project_name": "Test",
                "custom_extra": "preserved",
            }
        )
        rt = ABIConfig.from_dict(original.to_dict())
        assert rt.model_extra == {"custom_extra": "preserved"}


class TestABIConfigModelValidate:
    """``model_validate()`` accepts plain dicts."""

    def test_model_validate_plain_dict(self) -> None:
        cfg = ABIConfig.model_validate({"project_name": "ViaDict", "threads": 12})
        assert cfg.project_name == "ViaDict"
        assert cfg.threads == 12

    def test_model_validate_nested_dict(self) -> None:
        cfg = ABIConfig.model_validate(
            {
                "execution": {"parallel": True, "workers": 8},
            }
        )
        assert cfg.execution.parallel is True
        assert cfg.execution.workers == 8


# ── InputConfig ──────────────────────────────────────────────────────────────


class TestInputConfig:
    """Sample sheet input configuration."""

    def test_default_sample_sheet(self) -> None:
        cfg = InputConfig()
        assert cfg.sample_sheet == "sample_sheet.tsv"

    def test_custom_sample_sheet(self) -> None:
        cfg = InputConfig(sample_sheet="my_samples.csv")
        assert cfg.sample_sheet == "my_samples.csv"

    def test_model_validate(self) -> None:
        cfg = InputConfig.model_validate({"sample_sheet": "data/samples.tsv"})
        assert cfg.sample_sheet == "data/samples.tsv"


# ── AlignmentConfig ──────────────────────────────────────────────────────────


class TestAlignmentConfig:
    """Alignment tool configuration."""

    def test_default_tool(self) -> None:
        cfg = AlignmentConfig()
        assert cfg.tool == "star"

    def test_custom_tool_via_constructor(self) -> None:
        cfg = AlignmentConfig(tool="bowtie2")
        assert cfg.tool == "bowtie2"

    def test_custom_tool_via_model_validate(self) -> None:
        cfg = AlignmentConfig.model_validate({"tool": "hisat2"})
        assert cfg.tool == "hisat2"


# ── DifferentialExpressionConfig ─────────────────────────────────────────────


class TestDifferentialExpressionConfigDefaults:
    """Default values."""

    def test_defaults(self) -> None:
        cfg = DifferentialExpressionConfig()
        assert cfg.comparison == "treatment_vs_control"
        assert cfg.alpha == pytest.approx(0.05)

    def test_model_dump(self) -> None:
        d = DifferentialExpressionConfig().model_dump()
        assert d["comparison"] == "treatment_vs_control"
        assert d["alpha"] == pytest.approx(0.05)


class TestDifferentialExpressionConfigValidation:
    """Alpha must be in [0.0, 1.0]."""

    def test_alpha_below_zero_raises(self) -> None:
        with pytest.raises(ValidationError) as exc:
            DifferentialExpressionConfig(alpha=-0.01)
        assert "alpha" in str(exc.value)

    def test_alpha_above_one_raises(self) -> None:
        with pytest.raises(ValidationError) as exc:
            DifferentialExpressionConfig(alpha=1.01)
        assert "alpha" in str(exc.value)

    def test_alpha_at_boundaries(self) -> None:
        assert DifferentialExpressionConfig(alpha=0.0).alpha == 0.0
        assert DifferentialExpressionConfig(alpha=1.0).alpha == 1.0


class TestDifferentialExpressionConfigCustom:
    """Custom values."""

    def test_custom_comparison_and_alpha(self) -> None:
        cfg = DifferentialExpressionConfig(comparison="A_vs_B", alpha=0.01)
        assert cfg.comparison == "A_vs_B"
        assert cfg.alpha == 0.01


# ── RNASeqConfig ─────────────────────────────────────────────────────────────


class TestRNASeqConfigDefaults:
    """Default construction and inheritance."""

    def test_default_construction(self) -> None:
        cfg = RNASeqConfig()
        # Inherited from ABIConfig
        assert cfg.project_name == "ABI Analysis"
        assert cfg.outdir == "results"
        assert cfg.mode == "auto"
        assert cfg.threads == 4
        assert cfg.mamba_root is None
        # RNASeqConfig-specific
        assert cfg.log_dir == "logs/rnaseq_expression"

    def test_nested_defaults(self) -> None:
        cfg = RNASeqConfig()
        assert isinstance(cfg.execution, ExecutionConfig)
        assert isinstance(cfg.input, InputConfig)
        assert isinstance(cfg.alignment, AlignmentConfig)
        assert isinstance(cfg.differential_expression, DifferentialExpressionConfig)

    def test_nested_default_values(self) -> None:
        cfg = RNASeqConfig()
        assert cfg.input.sample_sheet == "sample_sheet.tsv"
        assert cfg.alignment.tool == "star"
        assert cfg.differential_expression.alpha == pytest.approx(0.05)

    def test_nested_factories_are_independent(self) -> None:
        a = RNASeqConfig()
        b = RNASeqConfig()
        a.input.sample_sheet = "modified.tsv"
        assert b.input.sample_sheet == "sample_sheet.tsv"


class TestRNASeqConfigInheritance:
    """RNASeqConfig inherits ABIConfig behavior."""

    def test_is_subclass_of_abi_config(self) -> None:
        cfg = RNASeqConfig()
        assert isinstance(cfg, ABIConfig)

    def test_extra_allow_inherited(self) -> None:
        cfg = RNASeqConfig.model_validate({"custom_rnaseq_field": 99})
        assert cfg.model_extra == {"custom_rnaseq_field": 99}

    def test_inherited_validation(self) -> None:
        with pytest.raises(ValidationError):
            RNASeqConfig(threads=0)

    def test_from_dict_works(self) -> None:
        cfg = RNASeqConfig.from_dict(
            {
                "project_name": "RNA Study",
                "threads": 16,
                "log_dir": "custom_logs",
            }
        )
        assert cfg.project_name == "RNA Study"
        assert cfg.threads == 16
        assert cfg.log_dir == "custom_logs"


class TestRNASeqConfigRoundTrip:
    """``to_dict()`` → ``from_dict()`` for RNASeqConfig."""

    def test_round_trip_defaults(self) -> None:
        original = RNASeqConfig()
        rt = RNASeqConfig.from_dict(original.to_dict())
        assert rt.project_name == original.project_name
        assert rt.log_dir == original.log_dir
        assert rt.input.sample_sheet == original.input.sample_sheet
        assert rt.alignment.tool == original.alignment.tool

    def test_round_trip_custom(self) -> None:
        original = RNASeqConfig(
            project_name="Custom RNA",
            threads=24,
            log_dir="custom/logs",
            input=InputConfig(sample_sheet="rna_samples.tsv"),
            differential_expression=DifferentialExpressionConfig(comparison="mut_vs_wt"),
        )
        rt = RNASeqConfig.from_dict(original.to_dict())
        assert rt.project_name == "Custom RNA"
        assert rt.threads == 24
        assert rt.log_dir == "custom/logs"
        assert rt.input.sample_sheet == "rna_samples.tsv"
        assert rt.differential_expression.comparison == "mut_vs_wt"


class TestRNASeqConfigModelValidate:
    """``model_validate()`` with plain dicts."""

    def test_model_validate_plain_dict(self) -> None:
        cfg = RNASeqConfig.model_validate(
            {
                "project_name": "Via Dict",
                "input": {"sample_sheet": "dict_samples.tsv"},
            }
        )
        assert cfg.project_name == "Via Dict"
        assert cfg.input.sample_sheet == "dict_samples.tsv"

    def test_model_validate_nested_alignment(self) -> None:
        cfg = RNASeqConfig.model_validate(
            {
                "alignment": {"tool": "bowtie2"},
            }
        )
        assert cfg.alignment.tool == "bowtie2"
