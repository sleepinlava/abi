"""Tests for ABI error hierarchy (abi.errors).

Covers:
- Exception hierarchy correctness (inheritance)
- Constructor / message propagation
- Agent-interpretability (semantic meaning of exception types)
- MissingTemplateParamError specifics
"""

from __future__ import annotations

import pytest

from abi.errors import (
    ABIError,
    ConfigError,
    MissingTemplateParamError,
    SampleSheetError,
    ToolError,
)

# ── Hierarchy Tests ────────────────────────────────────────────────────


class TestErrorHierarchy:
    def test_abi_error_is_runtime_error(self):
        """ABIError inherits from RuntimeError, not Exception directly."""
        assert issubclass(ABIError, RuntimeError)
        assert issubclass(ABIError, Exception)

    def test_config_error_is_abi_error(self):
        assert issubclass(ConfigError, ABIError)

    def test_missing_template_param_error_is_abi_error(self):
        assert issubclass(MissingTemplateParamError, ABIError)

    def test_sample_sheet_error_is_abi_error(self):
        assert issubclass(SampleSheetError, ABIError)

    def test_tool_error_is_abi_error(self):
        assert issubclass(ToolError, ABIError)

    def test_subclasses_not_siblings(self):
        """Each subclass is a sister, not parent/child of another."""
        assert not issubclass(ConfigError, ToolError)
        assert not issubclass(ToolError, ConfigError)
        assert not issubclass(SampleSheetError, MissingTemplateParamError)


# ── Constructor & Message Tests ─────────────────────────────────────────


class TestConstructor:
    @pytest.mark.parametrize(
        "exc_cls",
        [ABIError, ConfigError, SampleSheetError, ToolError, MissingTemplateParamError],
    )
    def test_no_args_creates_empty_message(self, exc_cls):
        err = exc_cls()
        assert str(err) == ""

    @pytest.mark.parametrize(
        "exc_cls",
        [ABIError, ConfigError, SampleSheetError, ToolError, MissingTemplateParamError],
    )
    def test_message_propagates(self, exc_cls):
        msg = "something went wrong"
        err = exc_cls(msg)
        assert str(err) == msg
        assert err.args == (msg,)

    @pytest.mark.parametrize(
        "exc_cls",
        [ABIError, ConfigError, SampleSheetError, ToolError, MissingTemplateParamError],
    )
    def test_multiple_args(self, exc_cls):
        err = exc_cls("one", "two")
        assert str(err) == "(one, two)"


# ── Catch-semantics Tests (agent interpretability) ──────────────────────


class TestCatchSemantics:
    def test_catch_abi_error_catches_all_subclasses(self):
        """Agent can catch ABIError to handle any ABI operational failure."""
        errors = [
            ABIError("base"),
            ConfigError("bad config"),
            SampleSheetError("bad csv"),
            ToolError("tool crashed"),
            MissingTemplateParamError("missing param"),
        ]
        for err in errors:
            try:
                raise err
            except ABIError:
                pass
            else:
                pytest.fail(f"ABIError did not catch {type(err).__name__}")

    def test_catch_runtime_error_catches_all(self):
        """ABIError (and subclasses) are also RuntimeError instances."""
        errors = [
            ABIError("base"),
            ConfigError("bad config"),
            SampleSheetError("bad csv"),
            ToolError("tool crashed"),
            MissingTemplateParamError("missing param"),
            RuntimeError("plain runtime"),
        ]
        for err in errors:
            try:
                raise err
            except RuntimeError:
                pass
            else:
                pytest.fail(f"RuntimeError did not catch {type(err).__name__}")

    def test_catch_config_error_does_not_catch_tool_error(self):
        """Agent can catch specific exception types for specialised recovery."""
        err = ConfigError("config issue")
        assert not isinstance(err, ToolError)
        assert isinstance(err, ConfigError)

    def test_catch_tool_error_does_not_catch_sample_sheet_error(self):
        err = ToolError("tool failure")
        assert not isinstance(err, SampleSheetError)
        assert isinstance(err, ToolError)


# ── TypeError: not an ABIError ──────────────────────────────────────────


class TestNotABIError:
    def test_type_error_not_caught_by_abi_error(self):
        """Standard TypeError is not an ABI operational failure."""
        err = TypeError("type mismatch")
        assert not isinstance(err, ABIError)

    def test_value_error_not_caught_by_abi_error(self):
        err = ValueError("bad value")
        assert not isinstance(err, ABIError)


# ── MissingTemplateParamError specifics ─────────────────────────────────


class TestMissingTemplateParamError:
    def test_is_abi_error(self):
        assert issubclass(MissingTemplateParamError, ABIError)

    def test_message_includes_param_name(self):
        err = MissingTemplateParamError("Template {reads} is missing")
        assert "reads" in str(err)
        assert "missing" in str(err).lower()

    def test_can_be_distinguished_from_config_error(self):
        """Agent can specialise: fix param vs fix config."""
        err = MissingTemplateParamError("missing param")
        assert not isinstance(err, ConfigError)
        assert isinstance(err, MissingTemplateParamError)

    # ── From upstream merge ──
    def test_missing_template_param_error_chain(self) -> None:
        err = MissingTemplateParamError("msg")
        assert isinstance(err, ABIError)
        assert isinstance(err, RuntimeError)

    def test_missing_template_param_error_message(self) -> None:
        assert str(MissingTemplateParamError("{foo}")) == "{foo}"


# ── isinstance checks ───────────────────────────────────────────────────


class TestIsInstance:
    def test_abi_error_is_instance_of_self(self):
        assert isinstance(ABIError(), ABIError)

    def test_subclass_is_instance_of_parent(self):
        assert isinstance(ConfigError(), RuntimeError)
        assert isinstance(ConfigError(), ABIError)

    def test_parent_is_not_instance_of_subclass(self):
        assert not isinstance(ABIError(), MissingTemplateParamError)


# ── From upstream merge: per-class behavior tests ───────────────────────


class TestABIError:
    def test_abi_error_is_runtime_error(self) -> None:
        assert isinstance(ABIError("msg"), RuntimeError)

    def test_abi_error_message(self) -> None:
        assert str(ABIError("test")) == "test"

    def test_abi_error_caught_by_base(self) -> None:
        try:
            raise ConfigError("oops")
        except ABIError:
            pass  # expected


class TestConfigError:
    def test_config_error_chain(self) -> None:
        err = ConfigError("msg")
        assert isinstance(err, ABIError)
        assert isinstance(err, ConfigError)
        assert isinstance(err, RuntimeError)

    def test_config_error_message(self) -> None:
        assert str(ConfigError("bad config")) == "bad config"


class TestSampleSheetError:
    def test_samplesheet_error_chain(self) -> None:
        err = SampleSheetError("msg")
        assert isinstance(err, ABIError)
        assert isinstance(err, RuntimeError)

    def test_samplesheet_error_message(self) -> None:
        assert str(SampleSheetError("missing col")) == "missing col"


class TestToolError:
    def test_tool_error_chain(self) -> None:
        err = ToolError("msg")
        assert isinstance(err, ABIError)
        assert isinstance(err, RuntimeError)

    def test_tool_error_message(self) -> None:
        assert str(ToolError("exec failed")) == "exec failed"


class TestExceptionIsolation:
    def test_abi_error_not_value_error(self) -> None:
        assert not isinstance(ABIError("msg"), ValueError)

    def test_abi_error_not_type_error(self) -> None:
        assert not isinstance(ABIError("msg"), TypeError)

    def test_standard_python_exceptions_not_abi(self) -> None:
        assert not isinstance(ValueError("x"), ABIError)
