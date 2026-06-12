"""Agent-Bioinformatics Interface package."""

from __future__ import annotations

import os
import sys
from pathlib import Path

__all__ = ["__version__"]

__version__ = "0.1.0"


def _warn_if_wrong_location() -> None:
    """Emit a warning when a conflicting ``abi`` package shadows this one.

    This can happen when another project that also contains an ``abi``
    package (e.g. an older editable install of ``autoplasm`` from
    PlasimSkillsForAgent) appears earlier on ``sys.path``.

    Run ``python scripts/dev_setup.py`` (or ``abi-dev-setup``) to
    install a priority ``.pth`` file that guarantees the correct
    package is found first.
    """
    expected_marker = os.environ.get("ABI_SRC_ROOT", "")
    if expected_marker:
        expected = Path(expected_marker) / "abi" / "__init__.py"
        actual = Path(__file__).resolve()
        if expected.resolve() != actual:
            import warnings

            warnings.warn(
                f"abi package loaded from unexpected location:\n"
                f"  loaded  : {actual}\n"
                f"  expected: {expected}\n"
                f"Run: python scripts/dev_setup.py   (or: abi-dev-setup)",
                stacklevel=2,
            )
    # Best-effort detection without ABI_SRC_ROOT: look for PlasimSkillsForAgent shadowing.
    current = Path(__file__).resolve()
    for entry in sys.path:
        entry_path = Path(entry)
        if entry_path.name == "src" and "PlasimSkillsForAgent" in str(entry_path):
            candidate_init = entry_path / "abi" / "__init__.py"
            if candidate_init.resolve() == current:
                import warnings

                warnings.warn(
                    f"abi was loaded from PlasimSkillsForAgent ({current}), "
                    f"not from the standalone abi-agent project.\n"
                    f"Run: python scripts/dev_setup.py   (or: abi-dev-setup)",
                    stacklevel=2,
                )
            break


_warn_if_wrong_location()
