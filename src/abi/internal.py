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
        return _run_generic_preflight(plugin, config, check_runtime=check_runtime)
    report = preflight(config, engine=engine, check_runtime=check_runtime)
    if not isinstance(report, Mapping):
        raise TypeError("plugin.preflight() must return a mapping")
    return report


def _run_generic_preflight(
    plugin: Any,
    config: Mapping[str, Any],
    *,
    check_runtime: bool,
) -> Mapping[str, Any]:
    """Provide a strict baseline preflight for plugins without a custom hook."""
    checks: list[dict[str, Any]] = []

    try:
        context = plugin.build_sample_context(config, check_files=True)
        checks.append(
            {
                "name": "inputs",
                "status": "pass",
                "sample_count": len(getattr(context, "samples", [])),
            }
        )
    except Exception as exc:
        checks.append({"name": "inputs", "status": "fail", "message": str(exc)})

    resource_checker = getattr(plugin, "check_resources", None)
    if callable(resource_checker):
        try:
            for row in resource_checker(config):
                status = str(row.get("status", "missing"))
                checks.append(
                    {
                        "name": f"resource:{row.get('resource_id', 'unknown')}",
                        "status": "pass" if status in {"ok", "not_required"} else "fail",
                        "details": dict(row),
                    }
                )
        except Exception as exc:
            checks.append({"name": "resources", "status": "fail", "message": str(exc)})

    if check_runtime:
        try:
            for row in plugin.registry().check_tools(config=config):
                if not bool(row.get("required", True)):
                    continue
                installed = bool(row.get("installed"))
                resource_status = str(row.get("resource_status", "ok"))
                checks.append(
                    {
                        "name": f"tool:{row.get('tool_id', 'unknown')}",
                        "status": (
                            "pass"
                            if installed and resource_status in {"ok", "not_required"}
                            else "fail"
                        ),
                        "details": dict(row),
                    }
                )
        except Exception as exc:
            checks.append({"name": "runtime", "status": "fail", "message": str(exc)})

    failures = [item for item in checks if item["status"] == "fail"]
    return {
        "plugin": getattr(plugin, "plugin_id", ""),
        "status": "fail" if failures else "pass",
        "checks": checks,
        "recommendations": [f"Fix failed preflight check: {item['name']}" for item in failures],
    }
