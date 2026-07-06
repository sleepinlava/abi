"""Plugin class structural validation at discovery time.

Validates that plugin classes satisfy the ``ABIPlugin`` protocol
at import/registration time rather than failing at runtime when
a missing method is first called.
"""

from __future__ import annotations

REQUIRED_ATTRIBUTES: set[str] = {
    "plugin_id",
    "display_name",
    "description",
    "report_title",
}

REQUIRED_METHODS: set[str] = {
    "load_config",
    "build_plan",
    "registry",
    "table_schemas",
    "parse_outputs",
    "write_report",
}


def validate_plugin_class(cls: type) -> None:
    """Validate that *cls* satisfies the ABI plugin protocol.

    Raises ``TypeError`` (matching ``Protocol`` convention) with a
    descriptive message when a required member is missing.
    """
    missing_attrs = {a for a in REQUIRED_ATTRIBUTES if not hasattr(cls, a)}
    if missing_attrs:
        _raise(cls, f"missing attributes: {', '.join(sorted(missing_attrs))}")

    missing_methods: set[str] = set()
    for method_name in REQUIRED_METHODS:
        method = getattr(cls, method_name, None)
        if not callable(method):
            missing_methods.add(method_name)
    if missing_methods:
        _raise(cls, f"missing callable methods: {', '.join(sorted(missing_methods))}")


def _raise(cls: type, msg: str) -> None:
    raise TypeError(f"ABI plugin {cls.__name__} is invalid: {msg}")
