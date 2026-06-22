# ABI HPC Development Guide

> **Status**: Active (2026-06-18)
> **Audience**: Plugin developers deploying ABI pipelines on HPC clusters

## Overview

ABI pipelines can execute on three runtimes:

```text
Runtimes
  ├── local        — Single machine, subprocess-based (default)
  ├── nextflow     — DSL2 export via ``abi export-nextflow``
  └── hpc          — Native Slurm jobs; PBS script/submission compatibility
```

## Local Runtime (Current Default)

All Phase 2-5 development uses the local runtime.  Tools are invoked as
subprocesses via ``GenericCommandSkill`` with conda environment isolation.

### Resource requirements per tool

| Tool | CPU | Memory | Disk I/O | Typical runtime |
| --- | --- | --- | --- | --- |
| fastp | 1-4 | 2 GB | Read-heavy | 5-15 min/sample |
| STAR | 8-16 | 32 GB | Heavy | 30-60 min/sample |
| featureCounts | 1-4 | 4 GB | Light | 2-5 min/sample |
| DESeq2 (R) | 1 | 4 GB | Light | 1-5 min |
| SPAdes | 8-16 | 64 GB | Heavy | 1-4 hr/sample |
| Prokka | 4-8 | 8 GB | Moderate | 10-30 min/sample |
| MLST | 1 | 1 GB | Light | < 1 min/sample |
| AMRFinderPlus | 4-8 | 8 GB | Moderate | 5-15 min/sample |
| cutadapt | 1-4 | 2 GB | Read-heavy | 5-15 min/sample |
| vsearch | 1-4 | 8 GB | Moderate | 10-30 min/step |
| MetaPhlAn | 4-8 | 16 GB | Moderate | 20-60 min/sample |
| HUMAnN | 8-16 | 32 GB | Heavy | 1-6 hr/sample |

## HPC Execution Strategy

### Nextflow export

```bash
abi export-nextflow --type rnaseq_expression \
  --config config.yaml \
  --outdir nextflow_pipeline/
```

Produces a self-contained Nextflow DSL2 pipeline that can be submitted
to SLURM/PBS clusters.  Each tool becomes a Nextflow process with
per-step resource directives.

### Native HPC submission

```bash
abi run --type rnaseq_expression \
  --engine hpc \
  --scheduler slurm \
  --partition production \
  --account proj_abi \
  --config config.yaml \
  --confirm-execution
```

ABI creates one payload and scheduler script per worker-scoped step, submits
real `afterok` dependencies, polls `squeue` with `sacct` fallback, cancels timed
out jobs, and aggregates atomic step result files. Driver-scoped validation runs
before the first submission. `--resume` reuses only non-empty outputs whose
checksums match `provenance/checksums.json`.

Run `abi check --type <plugin> --config config.yaml --engine hpc` before
submission. Production support targets Slurm; PBS retains compatible directives
and dependency submission but has a smaller validation surface.

### Key HPC considerations for plugin developers

1. **Tool contracts declare resources**: Each ``tool_contracts/*.yaml`` should
   include realistic ``resources:`` blocks (cpu, memory, walltime) so the
   HPC scheduler can allocate correctly.

2. **Database volumes**: Plugins that reference large databases (Kraken2,
   SILVA, GTDB, MetaPhlAn, HUMAnN) should declare database paths in
   ``abi-plugin.yaml`` resources section, not hardcoded.

3. **Checkpoint/restart**: The checksum chain in ``provenance/checksums.json``
   enables resume-after-failure.  A failed step can be re-run without
   recomputing upstream steps.

4. **Parallel sample execution**: The local runtime already supports
   ``--workers N`` for intra-node parallelism.  HPC execution extends
   this to cross-node parallelism via job arrays.

## Database Management

### Resource manifest

Every real execution generates ``provenance/resource_manifest.json``:

```json
{
  "analysis_type": "metagenomic_plasmid",
  "resources": [
    {
      "id": "genomad_db",
      "path": "/shared/databases/genomad_db_v1.5",
      "version": "1.5",
      "checksum_sha256": "abc123...",
      "validated_at": "2026-06-18"
    }
  ]
}
```

### Database directory convention

```text
resources/
  genomad_db/           # geNomad marker database
  bakta_db/             # Bakta annotation database  
  amrfinder_db/         # NCBI AMRFinderPlus database
  kraken2_db/           # Kraken2/Bracken index
  silva_138/            # SILVA 16S taxonomy
  gtdb_r207/            # GTDB taxonomy
  metaphlan_db/         # MetaPhlAn marker database
  humann_db/            # HUMAnN ChocoPhlAn + UniRef
  star_index_hg38/      # STAR index for human GRCh38
  star_index_ecoli/     # STAR index for E. coli
```

### Download and validation

```bash
# Example: validate a database
abi setup-resources --type metagenomic_plasmid --confirm
# → downloads DBs, computes checksums, writes resource_manifest.json
```

## Environment Management

### Conda environments per analysis type

| Plugin | Environment | Key packages |
| --- | --- | --- |
| metagenomic_plasmid | abi-qc, abi-asm, abi-annot, abi-amr | fastp, megahit, spades, bakta, prokka, amrfinderplus |
| rnaseq_expression | rnaseq | fastp, star, featurecounts, r-deseq2 |
| wgs_bacteria | rnaseq | fastp, spades, prokka, mlst, amrfinderplus |
| amplicon_16s | amplicon | cutadapt, vsearch, python-diversity |
| metatranscriptomics | abi-qc, abi-stats | fastp, star, featurecounts |

### Container support (planned)

Docker/Singularity images as an alternative to conda environments:

```yaml
execution:
  container: docker://biocontainers/fastp:v0.23.2
```

## Performance Benchmarks

### Small test dataset (Phase 6 target)

| Plugin | Input | Tools | Walltime (local, 16 cores) |
| --- | --- | --- | --- |
| rnaseq_expression | 4 samples, 1M reads each | fastp→STAR→featureCounts→DESeq2 | ~2 hr |
| wgs_bacteria | 2 isolates, 1M reads each | fastp→SPAdes→Prokka→MLST→AMRFinderPlus | ~6 hr |
| amplicon_16s | 4 samples, 100K reads each | cutadapt→vsearch(×3)→taxonomy→diversity | ~1 hr |
| metatranscriptomics | 4 samples, 5M reads each | fastp→STAR→featureCounts | ~3 hr |

### Production dataset estimates (HPC, 32 cores × 10 nodes)

| Plugin | Samples | Reads/sample | Estimated walltime |
| --- | --- | --- | --- |
| rnaseq_expression | 100 | 50M | ~6 hr (STAR-dominated) |
| wgs_bacteria | 500 | 5M | ~12 hr (SPAdes-dominated) |
| amplicon_16s | 200 | 200K | ~4 hr (vsearch-dominated) |
| metatranscriptomics | 50 | 100M | ~24 hr (HUMAnN-dominated) |

## Security Considerations

1. **Path traversal**: All plugin path resolution uses ``abi._shared._resolve_path``
   which validates containment within project directories (B25 fix).
2. **Command injection**: ``SafeFormatDict`` prevents injection via template
   parameter values.
3. **Network isolation**: Tools flagged ``network: false`` in their contracts
   cannot access external resources during execution.
4. **Database integrity**: Resource manifests with SHA256 checksums ensure
   database files haven't been tampered with.
