"""Local ABI runtime backed by GenericABIExecutor."""

from __future__ import annotations

import os
from typing import Any, Mapping

from abi.executor import GenericABIExecutor
from abi.internal import plugin_internal_handlers, run_plugin_preflight
from abi.provenance import RunLogger
from abi.runtimes.base import RuntimeOptions, RuntimeResult
from abi.schemas import ABIError
from abi.tables import StandardTableManager


def _skip_preflight_requested() -> bool:
    """Honor an explicit opt-in bypass of the resource/runtime preflight.

    Some plugins (e.g. autoplasm) register resources for every supported tool
    regardless of which stages are enabled in the user config, which makes the
    default preflight over-report.  Setting ``ABI_SKIP_PREFLIGHT=1`` lets an
    operator who has manually verified the enabled tools bypass the gate while
    still running real tools.  Default behavior is unchanged.
    """
    return os.environ.get("ABI_SKIP_PREFLIGHT", "").strip().lower() in {"1", "true", "yes", "on"}


def _coerce_bool(value: Any) -> bool:
    """Coerce a config value to bool, handling string representations.

    ``bool("false") == True`` in Python, so we need explicit handling for
    common string falsy values from env vars and YAML string substitution.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() not in {"", "false", "0", "no", "off", "none"}
    return bool(value)


class LocalRuntime:
    """Run ABI plans through the existing local GenericABIExecutor."""

    def __init__(self, plugin: Any, *, options: RuntimeOptions | None = None) -> None:
        self.plugin = plugin
        self.options = options or RuntimeOptions(engine="local")

    def check(self) -> None:
        return None

    def dry_run(self, plan: object, config: Mapping[str, object]) -> RuntimeResult:
        return self._run(plan, config, dry_run=True)

    def run(self, plan: object, config: Mapping[str, object]) -> RuntimeResult:
        return self._run(plan, config, dry_run=False)

    def _run(
        self,
        plan: object,
        config: Mapping[str, object],
        *,
        dry_run: bool,
    ) -> RuntimeResult:
        mock_tools = dry_run or _coerce_bool(config.get("mock_tools"))
        if not mock_tools and not _skip_preflight_requested():
            report = run_plugin_preflight(self.plugin, config, engine="local")
            if str(report.get("status", "pass")) == "fail":
                raise ABIError(
                    f"{self.plugin.plugin_id} preflight failed: "
                    + "; ".join(str(item) for item in report.get("recommendations", []))
                )
        table_manager = StandardTableManager(self.plugin.table_schemas())
        executor = GenericABIExecutor(
            self.plugin.registry(),
            RunLogger(str(config.get("log_dir", ""))),
            table_manager=table_manager,
            parse_outputs=self.plugin.parse_outputs,
            report_title=self.plugin.report_title,
            mock_tools=mock_tools,
            internal_handlers=plugin_internal_handlers(self.plugin),
        )
        outputs = executor.run(plan, config, dry_run=dry_run)
        return RuntimeResult(status="success", return_code=0, outputs=dict(outputs))
