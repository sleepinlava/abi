# Demo Artifacts

Store curated, small demo result bundles here when preparing a release or paper
artifact. Large generated results should stay outside git and be referenced by
manifest.

Canonical dry-run demos are generated from:

```bash
abi dry-run --type metatranscriptomics --outdir results/rnaseq_demo
abi dry-run --type metagenomic_plasmid --config examples/config_minimal.yaml --outdir results/plasmid_demo
```
