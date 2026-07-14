# EasyMetagenome-style ABI Plugin

This ABI-owned reimplementation provides three presets: `p0_taxonomy` for
Kraken2/Bracken taxonomy, `p1_humann4` for HUMAnN4 gene-family/pathway/KO
profiling, and `full_read_based` for both branches. It does not vendor or invoke
EasyMetagenome's GPLv3 Shell source.

The standard ABI entry point is the `easymetagenome` analysis type. The
document-format `P0Workflow` loader remains available for compatibility, but
its `run()` method is deprecated and now delegates to the canonical ABI DAG and
runtime. New callers should use the unified ABI entry points below.

```bash
abi query --type easymetagenome --what workflows
abi check --type easymetagenome --config p1.yaml --engine hpc
abi run --type easymetagenome --config p1.yaml --engine hpc \
  --scheduler slurm --partition compute --confirm-execution
```

Select a preset in YAML with `workflow: {preset: p1_humann4}`. HUMAnN4 requires
`host_db`, `humann_nucleotide_db`, `humann_protein_db`, and `metaphlan_db`.

## Published reports

The taxonomy and HUMAnN4 branches publish a Markdown report and an
`abi.report-manifest.v1` JSON manifest through the common ABI result bundle. A
single-branch run exposes them as `report_markdown` and `report_manifest`. The
`full_read_based` preset exposes branch-specific
`taxonomy_report_{markdown,manifest}` and
`functional_report_{markdown,manifest}` labels so neither report shadows the
other.

Each manifest records the workflow id, sample count, source artifacts, report
path, and the row count of each ABI standard table summarized by that report.
The deprecated `P0Workflow.run()` compatibility entry point preserves its legacy report files
while publishing the same canonical paths in `abi_outputs`, including resumed
runs. The canonical and compatibility formats are described by
`schemas/abi_report_manifest.schema.json` and
`schemas/report_manifest.schema.json`, respectively.
