# Plugin Development Guide

ABI plugins expose biological analysis types behind the shared lifecycle API.

## Minimum Python Interface

Implement the `abi.interfaces.ABIPlugin` protocol:

- `plugin_id`
- `display_name`
- `description`
- `report_title`
- `load_config()`
- `build_plan()`
- `registry()`
- `table_schemas()`
- `parse_outputs()`
- `write_report()`

Register the plugin with:

```toml
[project.entry-points."abi.plugins"]
my_analysis = "my_package.plugins:MyPlugin"
```

## Plugin Directory

Recommended layout:

```text
plugins/my_analysis/
  abi-plugin.yaml
  config_default.yaml
  sample_sheet_template.tsv
  tool_registry.yaml
  standard_tables.yaml
  tool_contracts/
    tool_a.yaml
  skills/
    tool_a/SKILL.md
```

## Tool Contracts

Contracts are machine-readable and must match the runtime registry:

- `tool_id`
- `category`
- `execution.env_name`
- `execution.executable`
- `execution.command_template`
- declared input/output template fields
- normalized standard table names

Use `assert_plugin_contract(plugin)` in plugin tests.

## Standard Tables

Parsers must only write tables declared by the plugin. Empty tables should still
exist with stable headers so agents can inspect results without parsing raw
tool output.

## Execution Safety

Plugins should make `plan` and `dry_run` safe for agents. Real external tool
execution must only happen through `run` after explicit confirmation.
