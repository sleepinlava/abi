"""Typed errors raised by the managed ViWrap adapter."""


class ViWrapError(RuntimeError):
    """Base ViWrap plugin error."""


class ViWrapConfigError(ViWrapError, ValueError):
    """The user configuration is invalid."""


class ViWrapEnvironmentError(ViWrapError):
    """The ViWrap runtime or database is incomplete."""


class ViWrapDatabaseError(ViWrapEnvironmentError):
    """The ViWrap database tree is incomplete."""


class ViWrapInputError(ViWrapError, ValueError):
    """A ViWrap input is missing, empty, or mutually incompatible."""


class ViWrapExecutionError(ViWrapError):
    """ViWrap returned a non-zero status."""


class ViWrapParseError(ViWrapError):
    """A required ViWrap result cannot be parsed."""


ViWrapPluginError = ViWrapError
ViWrapOutputParseError = ViWrapParseError
