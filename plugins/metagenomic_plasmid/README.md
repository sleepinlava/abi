# Metagenomic Plasmid Plugin

`metagenomic_plasmid` provides the ABI platform-aware plasmid workflow for
Illumina, ONT, PacBio HiFi, hybrid, and assembly-only inputs.

It is included in `abi-agent`; no external `autoplasm` package is required.
The canonical topology is `pipeline_dag.yaml`. The default path uses geNomad,
MMseqs2, Bakta, AMRFinderPlus, ISEScan, IntegronFinder, PlasmidFinder,
MOB-typer, and platform-aware mapping. Heavy overlapping tools are explicit
opt-ins, and MAG binning is isolated from the plasmid main path.

All normalized result TSVs are created with headers, including zero-hit runs.
Cross-sample diversity, differential abundance, and network nodes are gated by
sample metadata and record their non-run reason in `analysis_status.tsv`.

Useful commands:

```bash
abi plan --type metagenomic_plasmid --config examples/config_minimal.yaml --profile dry_run
abi dry-run --type metagenomic_plasmid --config examples/config_minimal.yaml --profile dry_run
autoplasm dry-run --config examples/config_minimal.yaml --profile dry_run
```
