from __future__ import annotations

import pytest

from abi.errors import (
    ABIError,
    ConfigError,
    MissingTemplateParamError,
    SampleSheetError,
    ToolError,
)


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


class TestMissingTemplateParamError:
    def test_missing_template_param_error_chain(self) -> None:
        err = MissingTemplateParamError("msg")
        assert isinstance(err, ABIError)
        assert isinstance(err, RuntimeError)

    def test_missing_template_param_error_message(self) -> None:
        assert str(MissingTemplateParamError("{foo}")) == "{foo}"


class TestExceptionIsolation:
    def test_abi_error_not_value_error(self) -> None:
        assert not isinstance(ABIError("msg"), ValueError)

    def test_abi_error_not_type_error(self) -> None:
        assert not isinstance(ABIError("msg"), TypeError)

    def test_standard_python_exceptions_not_abi(self) -> None:
        assert not isinstance(ValueError("x"), ABIError)
