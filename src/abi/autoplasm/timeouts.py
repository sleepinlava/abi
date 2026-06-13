"""Backward-compatibility shim — proxies to abi.plugins.metagenomic_plasmid._engine.timeouts."""

from __future__ import annotations

import sys as _sys
from abi.plugins.metagenomic_plasmid._engine.timeouts import *  # noqa: F401,F403

_mod = _sys.modules[__name__]
_target = _sys.modules["abi.plugins.metagenomic_plasmid._engine.timeouts"]
for _name in dir(_target):
    if _name.startswith("_") and not _name.startswith("__"):
        setattr(_mod, _name, getattr(_target, _name))

# Ensure __all__ stays aligned
if hasattr(_target, "__all__"):
    __all__ = list(_target.__all__)
