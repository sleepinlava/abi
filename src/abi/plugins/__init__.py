"""Built-in ABI plugin registry."""

from __future__ import annotations

import warnings
from importlib.metadata import entry_points
from typing import Any, Dict, Iterable, List, cast

from abi.interfaces import ABIPlugin

ENTRY_POINT_GROUP = "abi.plugins"


def _entry_points() -> Iterable[Any]:
    discovered = entry_points()
    if hasattr(discovered, "select"):
        return discovered.select(group=ENTRY_POINT_GROUP)
    return discovered.get(ENTRY_POINT_GROUP, ())  # type: ignore[attr-defined]  # present on 3.10/3.11


def _load_entry_point_plugins() -> Dict[str, ABIPlugin]:
    plugins: Dict[str, ABIPlugin] = {}
    for entry_point in _entry_points():
        try:
            plugin_class = entry_point.load()
            plugin = cast(ABIPlugin, plugin_class())
        except MemoryError:
            raise
        except Exception as exc:
            warnings.warn(
                f"Skipping ABI plugin entry point {entry_point.name!r}: {exc}",
                RuntimeWarning,
                stacklevel=2,
            )
            continue
        plugin_id = str(getattr(plugin, "plugin_id", entry_point.name))
        plugins[plugin_id] = plugin
    return plugins


def _builtin_plugins() -> Dict[str, ABIPlugin]:
    from abi.plugins.amplicon_16s import Amplicon16SPlugin
    from abi.plugins.easymetagenome import EasyMetagenomePlugin
    from abi.plugins.metagenomic_plasmid import MetagenomicPlasmidPlugin
    from abi.plugins.metatranscriptomics import MetatranscriptomicsPlugin
    from abi.plugins.rnaseq_expression import RNASeqExpressionPlugin
    from abi.plugins.viral_viwrap import ViralViWrapPlugin
    from abi.plugins.wgs_bacteria import WGSBacteriaPlugin

    plugins: List[ABIPlugin] = [
        Amplicon16SPlugin(),
        EasyMetagenomePlugin(),
        MetagenomicPlasmidPlugin(),
        MetatranscriptomicsPlugin(),
        RNASeqExpressionPlugin(),
        WGSBacteriaPlugin(),
        ViralViWrapPlugin(),
    ]
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
        raise ValueError(f"Unknown ABI analysis type: {plugin_id}. Available: {sorted(plugins)}")
    return plugins[plugin_id]
