"""ABI Doctor — health check and diagnostic reporting."""
from __future__ import annotations
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

@dataclass
class HealthCheck:
    name: str
    status: str
    message: str
    details: dict = field(default_factory=dict)

@dataclass
class HealthReport:
    checks: list[HealthCheck]
    @property
    def passed(self) -> bool:
        return all(c.status != "failed" for c in self.checks)
    @property
    def summary(self) -> dict:
        return {
            "total": len(self.checks),
            "passed": sum(1 for c in self.checks if c.status == "passed"),
            "failed": sum(1 for c in self.checks if c.status == "failed"),
            "warning": sum(1 for c in self.checks if c.status == "warning"),
            "healthy": self.passed,
        }
    def to_dict(self) -> dict:
        return {
            "summary": self.summary,
            "checks": [
                {"name": c.name, "status": c.status, "message": c.message, "details": c.details}
                for c in self.checks
            ],
        }

class Doctor:
    def run_all(self, *, analysis_type: str | None = None) -> HealthReport:
        checks = [self._check_python(), self._check_install(), self._check_plugins()]
        if analysis_type:
            checks.append(self._check_resources(analysis_type))
            checks.append(self._check_tools(analysis_type))
        return HealthReport(checks=checks)

    @staticmethod
    def _check_python() -> HealthCheck:
        v = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        ok = sys.version_info >= (3, 10)
        return HealthCheck(
            name="python_version",
            status="passed" if ok else "failed",
            message=f"Python {v} on {sys.platform}" + (" (supported)" if ok else " (3.10+ required)"),
            details={"version": v, "platform": sys.platform, "executable": sys.executable},
        )

    @staticmethod
    def _check_install() -> HealthCheck:
        try:
            import abi
            ver = getattr(abi, "__version__", "unknown")
            return HealthCheck(name="abi_install", status="passed",
                message=f"ABI {ver}", details={"version": ver, "path": str(Path(abi.__file__).parent)})
        except ImportError:
            return HealthCheck(name="abi_install", status="failed", message="ABI not importable")

    @staticmethod
    def _check_plugins() -> HealthCheck:
        try:
            from abi.plugins import list_plugins
            plugins = list_plugins()
            ids = sorted(p.plugin_id for p in plugins)
            return HealthCheck(name="plugins", status="passed" if plugins else "warning",
                message=f"{len(plugins)} plugins: {", ".join(ids)}",
                details={"count": len(plugins), "plugins": ids})
        except Exception as e:
            return HealthCheck(name="plugins", status="failed", message=str(e), details={"error": str(e)})

    @staticmethod
    def _check_resources(analysis_type: str) -> HealthCheck:
        try:
            from abi.plugins import get_plugin
            plugin = get_plugin(analysis_type)
            if not hasattr(plugin, "check_resources"):
                return HealthCheck(name=f"resources.{analysis_type}", status="skipped",
                    message="no check_resources()")
            resources = plugin.check_resources({})
            ok = [r for r in resources if r.get("status")=="ok"]
            missing = [r for r in resources if r.get("status") in ("missing","incomplete")]
            errors = [r for r in resources if r.get("status")=="error"]
            s = "failed" if errors else ("warning" if missing else "passed")
            return HealthCheck(name=f"resources.{analysis_type}", status=s,
                message=f"{len(ok)} OK, {len(missing)} missing, {len(errors)} errors",
                details={"total":len(resources),"ok":len(ok),"missing":len(missing),"errors":len(errors)})
        except Exception as e:
            return HealthCheck(name=f"resources.{analysis_type}", status="failed", message=str(e))

    @staticmethod
    def _check_tools(analysis_type: str) -> HealthCheck:
        try:
            from abi.plugins import get_plugin
            plugin = get_plugin(analysis_type)
            if not hasattr(plugin, "registry"):
                return HealthCheck(name=f"tools.{analysis_type}", status="skipped", message="no registry()")
            tools = plugin.registry().list_tools()
            return HealthCheck(name=f"tools.{analysis_type}", status="passed" if tools else "warning",
                message=f"{len(tools)} tools", details={"tool_count": len(tools)})
        except Exception as e:
            return HealthCheck(name=f"tools.{analysis_type}", status="failed", message=str(e))
