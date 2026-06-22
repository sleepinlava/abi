# EasyMetagenome-style ABI Plugin

This ABI-owned reimplementation provides three presets: `p0_taxonomy` for
Kraken2/Bracken taxonomy, `p1_humann4` for HUMAnN4 gene-family/pathway/KO
profiling, and `full_read_based` for both branches. It does not vendor or invoke
EasyMetagenome's GPLv3 Shell source.

The standard ABI entry point is the `easymetagenome` analysis type. The
document-format P0 loader remains available as `P0Workflow` for compatibility.

```bash
abi query --type easymetagenome --what workflows
abi check --type easymetagenome --config p1.yaml --engine hpc
abi run --type easymetagenome --config p1.yaml --engine hpc \
  --scheduler slurm --partition compute --confirm-execution
```

Select a preset in YAML with `workflow: {preset: p1_humann4}`. HUMAnN4 requires
`host_db`, `humann_nucleotide_db`, `humann_protein_db`, and `metaphlan_db`.
