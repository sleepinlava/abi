# Metagenomic Plasmid Integration

The `metagenomic_plasmid` ABI plugin uses the bundled `abi.autoplasm` pipeline.
This replaces the earlier split development model where an external
`autoplasm` package supplied the plasmid workflow.

## Public Shape

- PyPI package: `autoplasm-abi`
- ABI plugin id: `metagenomic_plasmid`
- Internal Python namespace: `abi.autoplasm`
- Compatibility command: `autoplasm`

There is no supported top-level `import autoplasm` API.

## Common Commands

```bash
abi plan --type metagenomic_plasmid \
  --config examples/config_minimal.yaml \
  --profile dry_run

abi dry-run --type metagenomic_plasmid \
  --config examples/config_minimal.yaml \
  --profile dry_run

autoplasm dry-run \
  --config examples/config_minimal.yaml \
  --profile dry_run
```

For real execution, prepare the repository-local mamba environments and required
databases first. Dry-run output is planning evidence, not proof that external
bioinformatics tools or databases are production-ready.

## Resource Boundaries

The package includes small configs, tool contracts, test fixtures, and examples.
It does not include real databases, mamba environments, or user results.

Use `resources/` for local databases and keep those files outside git.
