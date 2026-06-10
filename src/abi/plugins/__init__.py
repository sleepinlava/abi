"""Built-in ABI plugin registry."""

from __future__ import annotations

from importlib.metadata import entry_points
from typing import Dict, Iterable, List

ENTRY_POINT_GROUP = "abi.plugins"


def _entry_points() -> Iterable[object]:
    discovered = entry_points()
    if hasattr(discovered, "select"):
        return discovered.select(group=ENTRY_POINT_GROUP)
    return discovered.get(ENTRY_POINT_GROUP, ())


def _load_entry_point_plugins() -> Dict[str, object]:
    plugins: Dict[str, object] = {}
    for entry_point in _entry_points():
        plugin_class = entry_point.load()
        plugin = plugin_class()
        plugin_id = str(getattr(plugin, "plugin_id", entry_point.name))
        plugins[plugin_id] = plugin
    return plugins


def _builtin_plugins() -> Dict[str, object]:
    from abi.plugins.metatranscriptomics import MetatranscriptomicsPlugin

    plugins: list = [MetatranscriptomicsPlugin()]

    # metagenomic_plasmid requires autoplasm (optional dependency)
    try:
        from abi.plugins.metagenomic_plasmid import MetagenomicPlasmidPlugin

        plugins.append(MetagenomicPlasmidPlugin())
    except ImportError:
        pass

    return {str(plugin.plugin_id): plugin for plugin in plugins}


def _plugins() -> Dict[str, object]:
    plugins = _load_entry_point_plugins()
    plugins.update({key: value for key, value in _builtin_plugins().items() if key not in plugins})
    return plugins


def list_plugins() -> List[object]:
    plugins = _plugins()
    return [plugins[key] for key in sorted(plugins)]


def get_plugin(plugin_id: str) -> object:
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
