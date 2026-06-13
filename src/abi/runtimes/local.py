"""Local ABI runtime backed by GenericABIExecutor."""

from __future__ import annotations

from typing import Any, Mapping

from abi._compat.logger import RunLogger
from abi.executor import GenericABIExecutor
from abi.runtimes.base import RuntimeOptions, RuntimeResult
from abi.tables import StandardTableManager


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
        table_manager = StandardTableManager(self.plugin.table_schemas())
        executor = GenericABIExecutor(
            self.plugin.registry(),
            RunLogger(str(config["log_dir"])),
            table_manager=table_manager,
            parse_outputs=self.plugin.parse_outputs,
            report_title=self.plugin.report_title,
            mock_tools=dry_run or bool(config.get("mock_tools")),
        )
        outputs = executor.run(plan, config, dry_run=dry_run)
        return RuntimeResult(status="success", return_code=0, outputs=dict(outputs))
