#!/usr/bin/env python3
"""Ensure the correct ``abi`` package takes precedence on ``sys.path``.

Background
----------
When both ``abi-agent`` (this project) and ``autoplasm`` (from
PlasimSkillsForAgent) are installed in editable mode, the ``.pth``
file from ``autoplasm`` is processed *before* the ``.pth`` from
``abi-agent`` because:

* ``autoplasm`` installs into the *user* site-packages (``--user``)
* ``abi-agent`` installs into the *environment* site-packages
* User site-packages appear earlier on ``sys.path``
* Consequently ``PlasimSkillsForAgent/src/abi`` shadows ``abi/src/abi``

This script writes a tiny ``.pth`` file into the user site-packages
with a name that sorts **before** ``__editable__.autoplasm-*.pth``,
guaranteeing that the correct ``abi`` source tree is found first.

Usage
-----

.. code-block:: bash

    python scripts/dev_setup.py          # install the priority .pth
    python scripts/dev_setup.py --check  # only report, don't write
    python scripts/dev_setup.py --undo   # remove the priority .pth
"""

from __future__ import annotations

import argparse
import site
import sys
from pathlib import Path

PTH_FILENAME = "!abi_agent_priority.pth"
"""Sorts before ``__editable__.autoplasm-*.pth`` because ``!`` (0x21) < ``_`` (0x5f)."""


def _abi_src_dir() -> Path:
    """Absolute path to *this* project's ``src`` directory."""
    return Path(__file__).resolve().parents[1] / "src"


def _user_site_packages() -> Path:
    """User site-packages directory."""
    candidates = [
        Path(site.getusersitepackages()),
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    # Fallback: compute from sys.path
    for entry in sys.path:
        if ".local" in entry and "site-packages" in entry:
            return Path(entry)
    return Path(site.getusersitepackages())


def _pth_path() -> Path:
    return _user_site_packages() / PTH_FILENAME


def install() -> Path:
    """Write (or refresh) the priority ``.pth`` file."""
    target = _pth_path()
    abi_src = _abi_src_dir()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(f"{abi_src}\n", encoding="utf-8")
    return target


def uninstall() -> None:
    """Remove the priority ``.pth`` file if it exists."""
    target = _pth_path()
    if target.exists():
        target.unlink()


def check() -> int:
    """Return 0 when the fix is active, 1 otherwise."""
    target = _pth_path()
    if not target.exists():
        print(f"[MISSING] {target}")
        return 1
    abi_src = str(_abi_src_dir())
    content = target.read_text(encoding="utf-8").strip()
    if content != abi_src:
        print(f"[STALE] {target} points to {content!r}, expected {abi_src!r}")
        return 1
    print(f"[OK] {target} → {abi_src}")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Ensure abi-agent src/ has path priority.")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--check", action="store_true", help="Only print status, don't modify.")
    group.add_argument("--undo", action="store_true", help="Remove the priority .pth file.")
    args = parser.parse_args()

    if args.undo:
        uninstall()
        print(f"Removed {_pth_path()}")
        return

    if args.check:
        sys.exit(check())

    target = install()
    print(f"Installed {target}")
    print(f"  → priority path for {_abi_src_dir()}")
    # Verify
    sys.exit(check())


if __name__ == "__main__":
    main()
