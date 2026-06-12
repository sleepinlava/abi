"""Built-in ABI plugin registry.

Plugin loading strategy
-----------------------
Plugins are discovered from two sources:

1. **Entry points** — packages installed in the environment can register
   plugins via ``[project.entry-points."abi.plugins"]`` in their
   ``pyproject.toml``.  These are loaded first and take precedence.

2. **Built-in plugins** — plugins shipped inside this package.  These are
   loaded lazily (only when ``list_plugins()`` or ``get_plugin()`` is
   called, not at module import time).

Optional dependencies
~~~~~~~~~~~~~~~~~~~~~
Some built-in plugins require packages that are NOT part of the core
``abi-agent`` dependency tree.  For example:

- ``metagenomic_plasmid`` needs ``autoplasm`` (install with
  ``pip install abi-agent[autoplasm]``)

These plugins use **lazy imports** — the ``autoplasm`` imports live
INSIDE the plugin's methods, not at the top of the module.  The
``try/except ImportError`` guard in ``_builtin_plugins()`` provides a
second safety layer: even if the plugin module itself is importable,
a missing dependency at class-load time won't prevent the rest of ABI
from working.

Adding a new built-in plugin
~~~~~~~~~~~~~~~~~~~~~~~~~~~~
1. Drop the plugin module into ``abi/plugins/``.
2. If it has external dependencies, make them lazy (import inside methods)
   and add the dependency to ``[project.optional-dependencies]`` in
   ``pyproject.toml``.
3. Register it in ``_builtin_plugins()`` below, wrapping the import in
   ``try/except ImportError``.
"""

from __future__ import annotations

from importlib.metadata import entry_points
from typing import Any, Dict, Iterable, List, cast

from abi.interfaces import ABIPlugin

ENTRY_POINT_GROUP = "abi.plugins"


def _entry_points() -> Iterable[Any]:
    """Discover installed entry points for the ``abi.plugins`` group.

    Handles both the modern ``entry_points().select()`` API (Python ≥3.12)
    and the legacy ``entry_points().get()`` dict-based API.
    """
    discovered = entry_points()
    if hasattr(discovered, "select"):
        return discovered.select(group=ENTRY_POINT_GROUP)
    return discovered.get(ENTRY_POINT_GROUP, ())


def _load_entry_point_plugins() -> Dict[str, ABIPlugin]:
    """Load and instantiate plugins registered via setuptools entry points.

    Entry points are discovered from installed package metadata but are
    NOT imported until ``.load()`` is called here — so a broken entry
    point in an uninstalled optional dependency won't cause errors at
    import time.
    """
    plugins: Dict[str, ABIPlugin] = {}
    for entry_point in _entry_points():
        plugin_class = entry_point.load()
        plugin = cast(ABIPlugin, plugin_class())
        plugin_id = str(getattr(plugin, "plugin_id", entry_point.name))
        plugins[plugin_id] = plugin
    return plugins


def _builtin_plugins() -> Dict[str, ABIPlugin]:
    """Instantiate plugins shipped inside the ``abi`` package.

    IMPORTANT: Every built-in plugin that depends on an optional package
    MUST be wrapped in ``try/except ImportError``.  The plugin modules
    themselves should also use lazy imports (import inside methods) so
    that the module can be imported without its optional dependencies
    installed.
    """
    # metatranscriptomics — core dependency, always available
    from abi.plugins.metatranscriptomics import MetatranscriptomicsPlugin

    plugins: list[ABIPlugin] = [MetatranscriptomicsPlugin()]

    # metagenomic_plasmid — requires the optional ``autoplasm`` package.
    # Install via: pip install abi-agent[autoplasm]
    # The plugin module (metagenomic_plasmid.py) uses lazy imports so
    # the module file can be imported; this ``ImportError`` guard catches
    # the edge case where something tries to load the class before any
    # method is called.
    try:
        from abi.plugins.metagenomic_plasmid import MetagenomicPlasmidPlugin

        plugins.append(cast(ABIPlugin, MetagenomicPlasmidPlugin()))
    except ImportError:
        pass

    return {str(plugin.plugin_id): plugin for plugin in plugins}


def _plugins() -> Dict[str, ABIPlugin]:
    plugins = _load_entry_point_plugins()
    plugins.update({key: value for key, value in _builtin_plugins().items() if key not in plugins})
    return plugins


def list_plugins() -> List[ABIPlugin]:
    plugins = _plugins()
    return [plugins[key] for key in sorted(plugins)]


def get_plugin(plugin_id: str) -> ABIPlugin:
    plugins = _plugins()
    if plugin_id not in plugins:
        available = sorted(plugins)
        if plugin_id == "metagenomic_plasmid":
            raise ValueError(
                f"Unknown ABI analysis type: {plugin_id}. "
                "This plugin requires the 'autoplasm' package. "
                f"Install with: pip install abi-agent[autoplasm]. Available: {available}"
            )
        raise ValueError(f"Unknown ABI analysis type: {plugin_id}. Available: {available}")
    return plugins[plugin_id]
