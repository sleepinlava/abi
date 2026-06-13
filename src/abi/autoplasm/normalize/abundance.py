"""Backward-compatibility shim."""

from __future__ import annotations

import sys as _sys

from abi.plugins.metagenomic_plasmid._engine.normalize.abundance import *  # noqa: F401,F403

_mod = _sys.modules[__name__]
_target = _sys.modules["abi.plugins.metagenomic_plasmid._engine.normalize.abundance"]
for _name in dir(_target):
    if _name.startswith("_") and not _name.startswith("__"):
        setattr(_mod, _name, getattr(_target, _name))

if hasattr(_target, "__all__"):
    _source_all = _target.__all__
    __all__ = list(_source_all) if isinstance(_source_all, tuple) else _source_all
