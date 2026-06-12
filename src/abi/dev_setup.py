"""One-time dev-environment setup: install a priority ``.pth`` file.

See ``scripts/dev_setup.py`` for the standalone version and full documentation.
"""

from __future__ import annotations

import site
import sys
from pathlib import Path

PTH_FILENAME = "!abi_agent_priority.pth"


def _abi_src_dir() -> Path:
    """Absolute path to *this* project's ``src`` directory."""
    return Path(__file__).resolve().parents[1]


def _user_site_packages() -> Path:
    return Path(site.getusersitepackages())


def _pth_path() -> Path:
    return _user_site_packages() / PTH_FILENAME


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="Install a priority .pth file for abi-agent dev setup."
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--check", action="store_true")
    group.add_argument("--undo", action="store_true")
    args = parser.parse_args()

    target = _pth_path()
    if args.undo:
        if target.exists():
            target.unlink()
            print(f"Removed {target}")
        return
    if args.check:
        abi_src = str(_abi_src_dir())
        if target.exists() and target.read_text().strip() == abi_src:
            print(f"[OK] {target} → {abi_src}")
            sys.exit(0)
        print(f"[MISSING or STALE] {target}")
        sys.exit(1)

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(f"{_abi_src_dir()}\n")
    print(f"Installed {target}")


if __name__ == "__main__":
    main()
