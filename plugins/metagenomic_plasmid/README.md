# Metagenomic Plasmid Plugin

This plugin is an adapter over the existing AutoPlasm implementation.

It requires the `autoplasm` package to be installed:

```bash
pip install abi-agent[autoplasm]
```

When installed, it delegates planning, execution, parsing, and reporting to AutoPlasm's
planner, pipeline executor, parsers, and report generators.
