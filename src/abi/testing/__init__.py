"""ABI testing utilities.

Provides shared test helpers for plugin contract validation, benchmark
assertions, and smoke test scaffolding.

Usage::

    from abi.testing import BenchmarkAssertion, BenchmarkResult, run_benchmark
    from abi.testing import assert_plugin_contract
"""

from __future__ import annotations

from abi.testing.benchmark import (
    BenchmarkAssertion,
    BenchmarkResult,
    run_benchmark,
    validate_against_expected,
)

__all__ = [
    "BenchmarkAssertion",
    "BenchmarkResult",
    "assert_plugin_contract",
    "run_benchmark",
    "validate_against_expected",
]


def assert_plugin_contract(plugin: object) -> None:
    """Verify a plugin satisfies the ABIPlugin protocol contract.

    Checks that the plugin exposes all required methods and attributes
    defined by the ABIPlugin / ABIDryRunPlugin / ABIInitializablePlugin
    protocols.

    Raises:
        AssertionError: If the plugin does not satisfy the contract.
        TypeError: If *plugin* is not recognized as a plugin object.
    """
    from abi.interfaces import ABIDryRunPlugin, ABIInitializablePlugin, ABIPlugin

    errors: list[str] = []

    # ── Core ABIPlugin ──
    if not isinstance(plugin, ABIPlugin):
        errors.append("plugin does not implement ABIPlugin protocol")

    # ── Dry-run (all current plugins support this) ──
    if isinstance(plugin, ABIDryRunPlugin):
        for method in ("plan", "dry_run", "write_report", "inspect"):
            if not hasattr(plugin, method):
                errors.append(f"ABIDryRunPlugin missing method: {method}")
    else:
        errors.append("plugin does not implement ABIDryRunPlugin")

    # ── Optional: initializable (tool installation / resource setup) ──
    if isinstance(plugin, ABIInitializablePlugin):
        for method in ("check_installation", "setup_resources"):
            if not hasattr(plugin, method):
                errors.append(f"ABIInitializablePlugin missing method: {method}")

    if errors:
        raise AssertionError(
            f"Plugin contract validation failed ({len(errors)} issues):\n"
            + "\n".join(f"  - {e}" for e in errors)
        )
