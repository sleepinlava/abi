# Metagenomic Plasmid Plugin

`metagenomic_plasmid` adapts the bundled `abi.autoplasm` pipeline to the ABI
plugin contract.

It is included in `abi-agent`; no external `autoplasm` package is required.
The plugin delegates configuration, planning, dry-run execution, parsing, and
report generation to `abi.autoplasm`.

Useful commands:

```bash
abi plan --type metagenomic_plasmid --config examples/config_minimal.yaml --profile dry_run
abi dry-run --type metagenomic_plasmid --config examples/config_minimal.yaml --profile dry_run
autoplasm dry-run --config examples/config_minimal.yaml --profile dry_run
```
