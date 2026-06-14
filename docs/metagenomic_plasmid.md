# Metagenomic Plasmid Integration

The `metagenomic_plasmid` ABI plugin uses the bundled `abi.autoplasm` pipeline
(39 Python files, 9,006 lines in `plugins/metagenomic_plasmid/_engine/`). This
replaces the earlier split development model where an external `autoplasm`
package supplied the plasmid workflow.

## Public Shape

- PyPI package: `abi-agent`
- ABI plugin id: `metagenomic_plasmid`
- Internal Python namespace: `abi.autoplasm`
- Compatibility command: `autoplasm`
- Tool contracts: 67 (all bioinformatics tools in the plasmid pipeline, 32 with normalization parsers)
- Engine: 39 files under `_engine/` (pipeline, planner, DAG, parsers, normalize, report, skills, etc.)
- Pipeline DAG: `pipeline_dag.yaml` (84 nodes, 5 platforms, 16 standard tables) — single source of truth
- Step contract enforcement: `contracts/step_contract.py` — output validation, actual-output resolution, assertions, and checksum chaining

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

## Validation Position

The metagenomic plasmid route is now structured as a constrained workflow:
`pipeline_dag.yaml` defines node order, outputs, contracts, and assertions;
the generic executor writes provenance and enforces contracts after each
successful external command.

This is not yet the same as a fully validated biological workflow. The current
codebase provides the control layer needed for validation, while the remaining
work is to pin environments, version databases, curate positive/negative
benchmark datasets, and connect route-level reports to method citations. See
[Workflow Validation and Scientific Evidence Plan](workflow_validation.md).
