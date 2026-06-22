"""Transport-neutral execution contract for ABI internal DAG nodes."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Protocol, runtime_checkable


@dataclass(frozen=True)
class InternalHandlerContext:
    """Filesystem and configuration context supplied to an internal handler."""

    outdir: Path
    provenance_dir: Path
    tables_dir: Path
    dry_run: bool = False


@dataclass
class InternalHandlerResult:
    """Normalized result returned by every internal handler."""

    status: str = "success"
    message: str = ""
    tables: Mapping[str, Iterable[Mapping[str, Any]]] = field(default_factory=dict)
    artifacts: Mapping[str, str | Path] = field(default_factory=dict)


@runtime_checkable
class ABIInternalHandler(Protocol):
    """Executable implementation of a transport-neutral internal DAG node."""

    handler_id: str
    execution_scope: str

    def run(
        self,
        step: Any,
        config: Mapping[str, Any],
        context: InternalHandlerContext,
    ) -> InternalHandlerResult: ...


@dataclass(frozen=True)
class FunctionInternalHandler:
    """Small adapter for registering ordinary functions as handlers."""

    handler_id: str
    function: Callable[[Any, Mapping[str, Any], InternalHandlerContext], InternalHandlerResult]
    execution_scope: str = "worker"

    def run(
        self,
        step: Any,
        config: Mapping[str, Any],
        context: InternalHandlerContext,
    ) -> InternalHandlerResult:
        return self.function(step, config, context)


def plugin_internal_handlers(plugin: Any) -> dict[str, ABIInternalHandler]:
    """Return and validate optional handlers registered by a plugin."""
    factory = getattr(plugin, "internal_handlers", None)
    if factory is None:
        return {}
    raw = factory()
    if not isinstance(raw, Mapping):
        raise TypeError("plugin.internal_handlers() must return a mapping")
    handlers: dict[str, ABIInternalHandler] = {}
    for key, handler in raw.items():
        handler_id = str(key)
        if not isinstance(handler, ABIInternalHandler):
            raise TypeError(f"Internal handler {handler_id!r} does not satisfy ABIInternalHandler")
        if handler.handler_id != handler_id:
            raise ValueError(
                f"Internal handler key {handler_id!r} does not match {handler.handler_id!r}"
            )
        if handler.execution_scope not in {"driver", "worker"}:
            raise ValueError(
                f"Internal handler {handler_id!r} has invalid execution_scope "
                f"{handler.execution_scope!r}"
            )
        handlers[handler_id] = handler
    return handlers


def internal_handler_spec(step: Any) -> tuple[str, str]:
    """Read the planner-transported handler ID and execution scope from a step."""
    params = getattr(step, "params", {})
    raw = params.get("_internal_handler", {}) if isinstance(params, Mapping) else {}
    if not isinstance(raw, Mapping):
        return "", "worker"
    return str(raw.get("handler_id", "")), str(raw.get("execution_scope", "worker"))


def run_plugin_preflight(
    plugin: Any,
    config: Mapping[str, Any],
    *,
    engine: str,
    check_runtime: bool = True,
) -> Mapping[str, Any]:
    """Invoke an optional plugin preflight and enforce its structured result."""
    preflight = getattr(plugin, "preflight", None)
    if preflight is None:
        return {"status": "pass", "plugin": getattr(plugin, "plugin_id", "")}
    report = preflight(config, engine=engine, check_runtime=check_runtime)
    if not isinstance(report, Mapping):
        raise TypeError("plugin.preflight() must return a mapping")
    return report
