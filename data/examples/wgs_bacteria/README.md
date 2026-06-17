# wgs_bacteria Example

2-sample bacterial isolate WGS with clinical vs environmental contrast.

## Files

- `config.yaml` — Plugin configuration
- `sample_sheet.tsv` — 2 samples: 1 clinical + 1 environmental

## Quick Start

```bash
# Plan
abi plan --type wgs_bacteria \
  --config data/examples/wgs_bacteria/config.yaml \
  --outdir results/wgs_example

# Dry-run
abi dry-run --type wgs_bacteria \
  --config data/examples/wgs_bacteria/config.yaml \
  --outdir results/wgs_example

# Real execution (requires SPAdes, Prokka, MLST, AMRFinderPlus)
abi run --type wgs_bacteria \
  --config data/examples/wgs_bacteria/config.yaml \
  --outdir results/wgs_example \
  --confirm-execution
```

## Tool Requirements

For real execution:

| Tool | Purpose | Install |
| --- | --- | --- |
| fastp | Read QC | conda install -c bioconda fastp |
| SPAdes | Genome assembly | conda install -c bioconda spades |
| Prokka | Genome annotation | conda install -c bioconda prokka |
| mlst | MLST typing | conda install -c bioconda mlst |
| AMRFinderPlus | AMR profiling | conda install -c bioconda ncbi-amrfinderplus |

## Reference Resources

1. **AMRFinderPlus database** — Download from NCBI:
   ```bash
   amrfinder_update --database /path/to/amrfinder_db
   ```

Update `resources.amrfinder_db` in `config.yaml` to point to your database.
