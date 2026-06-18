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
    defined by the ABIPlugin base protocol. ABIDryRunPlugin and
    ABIInitializablePlugin are optional extensions — plugins are not
    required to implement them.

    Raises:
        AssertionError: If the plugin does not satisfy the base contract.
        TypeError: If *plugin* is not recognized as a plugin object.
    """
    from abi.interfaces import ABIDryRunPlugin, ABIInitializablePlugin, ABIPlugin

    errors: list[str] = []

    # ── Core ABIPlugin (required) ──────────────────────────────────────
    if not isinstance(plugin, ABIPlugin):
        errors.append("plugin does not implement ABIPlugin protocol")

    if errors:
        raise AssertionError(
            f"Plugin contract validation failed ({len(errors)} issues):\n"
            + "\n".join(f"  - {e}" for e in errors)
        )

    # ── Dry-run extension (optional) ───────────────────────────────────
    if isinstance(plugin, ABIDryRunPlugin):
        for method in ("execute_dry_run",):
            if not hasattr(plugin, method):
                errors.append(f"ABIDryRunPlugin missing method: {method}")

    # ── Initializable extension (optional) ────────────────────────────
    if isinstance(plugin, ABIInitializablePlugin):
        for attr in ("root",):
            if not hasattr(plugin, attr):
                errors.append(f"ABIInitializablePlugin missing attribute: {attr}")

    if errors:
        raise AssertionError(
            f"Plugin contract validation failed ({len(errors)} issues):\n"
            + "\n".join(f"  - {e}" for e in errors)
        )
