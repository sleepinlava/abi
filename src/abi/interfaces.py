"""Public ABI plugin interfaces."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional, Protocol

from abi.schemas import ABIExecutionPlan
from abi.tools import ToolRegistry

__all__ = [
    "ABIDryRunPlugin",
    "ABIInitializablePlugin",
    "ABIPlugin",
]


class ABIPlugin(Protocol):
    plugin_id: str
    display_name: str
    description: str
    report_title: str

    def load_config(
        self,
        config_path: str | Path | None = None,
        *,
        profile: str | None = None,
        overrides: Optional[Mapping[str, Any]] = None,
    ) -> Dict[str, Any]: ...

    def build_plan(
        self,
        config: Mapping[str, Any],
        *,
        check_files: bool = True,
    ) -> ABIExecutionPlan: ...

    def registry(self) -> ToolRegistry: ...

    def table_schemas(self) -> Mapping[str, Iterable[str]]: ...

    def parse_outputs(
        self,
        tool_id: str,
        output_dir: str | Path,
        sample_id: str,
    ) -> Mapping[str, Iterable[Mapping[str, Any]]]: ...

    def write_report(self, plan: Any, result_dir: str | Path) -> Dict[str, Path]: ...


class ABIDryRunPlugin(ABIPlugin, Protocol):
    def execute_dry_run(self, plan: Any, config: Mapping[str, Any]) -> Dict[str, Path]: ...


class ABIInitializablePlugin(ABIPlugin, Protocol):
    root: Path
