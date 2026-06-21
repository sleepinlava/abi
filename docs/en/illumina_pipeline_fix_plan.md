# Illumina Pipeline Empty Table Fix Plan

## Fix Progress (2026-06-21)

| Fix | Status | Description |
|-----|--------|-------------|
| Fix 1 | 🔄 Build #4 running | kraken2 DB: capacity exceeded → retrying with load-factor 0.5 |
| Fix 2 | ⚠️ Blocked | copla: needs manual `git clone` + `pip install` |
| Fix 3 | ✅ Done | fastspar: DAG → contig_coverage_coverm, contract merge |
| Fix 4 | ✅ Done | plasmid_consensus: added logging, pipeline tracer |
| Fix 5 | ✅ Done | comparative_genomics: enabled mmseqs2 |
| Fix 6+7 | ✅ Done | 3rd sample (SRR1952517) + sample_analysis enabled |
| P3 | ⏸️ Deferred | binning, blast, gtdbtk, checkm2, host_removal, eggnog, rgi |

## Status Overview

Round 1 Illumina pipeline: **26/27 per-sample steps passed**, **5/16 tables have data**, **11 tables empty**.

## Empty Table Diagnosis

### Tables with data (5)

| Table | Rows | Source |
|-------|------|--------|
| abundance | 2,233 | coverm |
| annotations | 352 | bakta + mob_typer |
| plasmid_predictions | 96 | genomad |
| assembly_summary | 97 | megahit + quast |
| qc_summary | 36 | fastp |

### Empty tables by root cause

| # | Table | Root Cause | Category |
|---|-------|-----------|----------|
| 1 | host_predictions | host_prediction disabled (kraken2 DB .k2d files missing) | Tool Missing |
| 2 | plasmid_typing | copla not installed (only parser for this table) | Tool Missing |
| 3 | network_edges | fastspar failed — cross-sample OTU table not generated | Tool Failure |
| 4 | network_nodes | fastspar failed — cross-sample OTU table not generated | Tool Failure |
| 5 | plasmid_consensus | Bug: 96 predictions → 0 consensus rows (write_consensus_table timing) | Bug |
| 6 | visualization_outputs | Blocked by fastspar + all visualization steps pending | Blocked |
| 7 | comparative_hits | comparative_genomics disabled (mmseqs2 DB ready but not enabled) | Tool Missing |
| 8 | plasmid_bins | plasmid_binning tools not installed (metabat2/maxbin2/etc) | Tool Missing |
| 9 | bin_to_contig | Same as plasmid_bins | Tool Missing |
| 10 | differential_abundance | sample_analysis disabled (need >=3 samples for stats) | Tool Missing |
| 11 | sample_diversity | sample_analysis disabled (need >=3 samples for stats) | Tool Missing |

---

## Fix Plan

### Fix 1: Build kraken2 database from downloaded library (unblocks host_predictions)

**Problem**: 57GB raw library data exists at `resources/autoplasm/kraken2/` (library/archaea, library/bacteria, taxonomy/) but DB build step never completed — no `hash.k2d`, `taxo.k2d`, `opts.k2d` files exist. The `kraken2-build --standard --use-ftp` command downloads taxonomy + library but requires a separate `--build` step to create the `.k2d` index files.

**Fix**:
```bash
kraken2-build --build --db /root/autodl-tmp/abi/resources/autoplasm/kraken2 --threads 8
```

**Estimated time**: 1-2 hours (dustmasker masking + k2d construction from ~2.5GB library)

**Verification**: Check for `hash.k2d`, `taxo.k2d`, `opts.k2d` in the kraken2 directory.

---

#### Kraken2 Download Failure Troubleshooting (if rebuild from scratch is needed)

If the above build fails, or if a fresh database download is required, kraken2 database download failures are a **very common problem** caused by NCBI server connectivity issues, a known FTP path bug, network timeouts, or permission issues. Below is a systematic diagnosis and repair guide.

##### Cause 1: NCBI FTP Path Bug (kraken2 v2.1.2 and earlier)

Kraken2's `rsync_from_ncbi.pl` script has a **known bug** — when NCBI updates server paths, the script cannot parse the new FTP paths correctly.

**Typical error:**
```
rsync_from_ncbi.pl: unexpected FTP path (new server?)
```

**Fix A — Use the patched module (if available on cluster):**
```bash
module load biocontainers
module load kraken2/2.1.2_fixftp
kraken2-build --download-library bacteria --db mydb
```

**Fix B — Manually patch `rsync_from_ncbi.pl`:**
```bash
# Locate the script
find $(conda info --base)/envs -name "rsync_from_ncbi.pl" 2>/dev/null
# Or: which kraken2-build  # then inspect the installation directory
```
Modify the FTP path parsing logic. See [GitHub Issue #292](https://github.com/DerrickWood/kraken2/issues/292) for the specific patch.

##### Cause 2: Network Connectivity Issues (timeout / DNS resolution failure)

**Typical errors:**
```
rsync: getaddrinfo: ftp.ncbi.nlm.nih.gov 873: Temporary failure in name resolution
FTP connection error: Net::FTP: connect: timeout
```

**Fixes:**

1. **Switch download protocol — try `--use-ftp`:**
   ```bash
   # Default uses rsync; if rsync fails, try FTP
   kraken2-build --download-library bacteria --db mydb --use-ftp

   # If FTP fails, try rsync (remove --use-ftp)
   kraken2-build --download-library bacteria --db mydb
   ```

2. **Test NCBI connectivity directly:**
   ```bash
   ping ftp.ncbi.nlm.nih.gov
   rsync ftp.ncbi.nlm.nih.gov::genomes/refseq/bacteria/assembly_summary.txt
   ```
   If these timeout, a firewall or network policy may be blocking the connection.

3. **Wait and retry** — NCBI servers are sometimes temporarily unstable. Waiting 10–30 minutes before retrying often resolves the issue.

##### Cause 3: Permission Issues

**Typical error:**
```
mv: cannot move 'x' to 'assembly_summary.txt': Permission denied
```

**Fixes:**
```bash
# Option 1: Force overwrite in download_genomic_library.sh (line 53: mv x assembly_summary.txt → mv -f x assembly_summary.txt)

# Option 2: Auto-confirm with yes pipe
yes y | kraken2-build --download-library human --db mydb

# Option 3: Use FTP mode (respects umask permissions)
kraken2-build --download-library human --db mydb --use-ftp
```

##### Cause 4: Alternative — Download Pre-built Database (Recommended Fallback)

If `kraken2-build` repeatedly fails, **download an official pre-built database** to completely bypass the build process:

```bash
# Standard database (~8GB, suitable for most analyses)
wget https://genome-idx.s3.amazonaws.com/kraken/k2_standard_20230605.tar.gz

# Extract
mkdir -p k2_standard
tar -xzvf k2_standard_20230605.tar.gz -C k2_standard

# Use directly
kraken2 --db k2_standard --threads 8 --report report.txt --paired reads_1.fq reads_2.fq
```

Other pre-built options:
| Database | Size | Contents |
|----------|------|----------|
| `k2_standard_20230605.tar.gz` | ~8GB | Standard (archaea, bacteria, viral, human) |
| `k2_minusb_20230605.tar.gz` | ~8GB | MiniKraken2 (reduced) |
| `k2_pluspf_20230605.tar.gz` | Larger | PlusPF (prokaryotes + eukaryotes + viruses) |

##### Complete Build-from-Scratch Workflow (if `kraken2-build` is required)

```bash
mkdir -p my_kraken_db

# Step 1: Download taxonomy
kraken2-build --download-taxonomy --db my_kraken_db --use-ftp

# Step 2: Download libraries (download individually — failures can be retried separately)
kraken2-build --download-library archaea --db my_kraken_db --use-ftp
kraken2-build --download-library bacteria --db my_kraken_db --use-ftp
kraken2-build --download-library viral --db my_kraken_db --use-ftp

# Step 3: Build the database (dustmasker + k2d index construction)
kraken2-build --build --db my_kraken_db --threads 24

# Step 4: Clean intermediate files
kraken2-build --clean --db my_kraken_db
```

##### Summary: Fix Priority Order

| Priority | Action | When to use |
|----------|--------|-------------|
| 1 | `kraken2-build --build` (current fix) | Raw library already downloaded, only indexing needed |
| 2 | Add `--use-ftp` flag | rsync protocol blocked / timeout |
| 3 | Patch `rsync_from_ncbi.pl` | "unexpected FTP path" error |
| 4 | Check network + wait + retry | Transient NCBI server issues |
| 5 | Download pre-built database | All build attempts fail — simplest and most reliable |
| 6 | Check disk space + permissions | "Permission denied" or "No space left on device" |

---

### Fix 2: Install copla tool (unblocks plasmid_typing)

**Problem**: `plasmid_typing` table is ONLY populated by `parse_copla` (see `parsers.py:721`). plasmidfinder writes to `plasmid_predictions` + `annotations`, mob_typer writes to `plasmid_predictions` + `annotations` + `host_predictions`. Neither writes to `plasmid_typing`. copla must be installed for this table to have data.

**Fix**:
```bash
abi setup-resources --type metagenomic_plasmid --resource copla_tool --confirm
```

**Dependencies**: copla_tool ResourceSpec has `auto_setup=False` — requires explicit `--resource` flag.

---

### Fix 3: Fix fastspar cross-sample OTU aggregation (unblocks network + visualization)

**Problem**: `multisample_network_fastspar` is a cross_sample node depending on `abundance_coverm.tpm_table` (a per_sample node). The input spec has `source: abundance_coverm.tpm_table` but no `aggregate: per_sample_outputs`. The DAG planner resolves only the first sample's TPM path. Additionally, the path template resolves to `10_abundance/plasmid_abundance_tpm.tsv` which doesn't exist — per-sample files are at `10_abundance/<sample_id>/<sample_id>_tpm.tsv`.

**Error from stderr**:
```
fastspar: error: OTU table /root/autodl-tmp/abi-illumina-full-run/10_abundance/plasmid_abundance_tpm.tsv does not exist
```

**Fix** — Two options:

**Option A (Recommended)**: Add `aggregate: per_sample_outputs` to the fastspar input in `pipeline_dag.yaml` and update the command template to use a wrapper that merges per-sample TPM tables:
```yaml
# In multisample_network_fastspar inputs:
abundance_table:
  type: file
  format: tsv
  source: abundance_coverm.tpm_table
  aggregate: per_sample_outputs  # ADD THIS
```

Then modify `fastspar.yaml` command_template to use a merge script:
```bash
python -c "
import pandas as pd, sys
tables = '{abundance_table}'.split(',')
dfs = [pd.read_csv(t, sep='\t', index_col=0) for t in tables]
merged = pd.concat(dfs, axis=1).fillna(0)
merged.to_csv('{output_dir}/plasmid_abundance_tpm.tsv', sep='\t')
" && fastspar --otu_table {output_dir}/plasmid_abundance_tpm.tsv ...
```

**Option B**: Add a dedicated `multisample_merge_abundance` cross_sample node to the DAG that takes `aggregate: per_sample_outputs`, merges TPM tables, and exposes the merged file as output. Fastspar then references this node.

**Files to change**:
- `plugins/metagenomic_plasmid/pipeline_dag.yaml` — fix fastspar input
- `plugins/metagenomic_plasmid/tool_contracts/fastspar.yaml` — update command template
- Possibly: `src/abi/dag_planner.py` — improve cross_sample single-sample fallback

---

### Fix 4: Debug plasmid_consensus empty table

**Problem**: 96 `plasmid_predictions` rows exist (all from genomad). Config has `plasmid_detection.tools: [genomad]`, strategy defaults to `single_tool`. The consensus logic in `standard_tables.py:write_consensus_table` should produce 96 rows (strategy `single_tool` returns `support_count > 0` which is always true for 1 tool). But only a header was written.

**Hypothesis**: `_refresh_consensus_and_fastas` in `pipeline.py:483` is called during per-sample execution BEFORE all samples' plasmid_predictions rows have been written to the shared TSV. When the function reads `plasmid_predictions.tsv` via `read_standard_table`, it may get partial or empty results.

Investigating the call chain:
1. Per-sample step `SRR1952439_plasmid_consensus` completes (progress.json shows success)
2. `_refresh_consensus_and_fastas` is called which calls `write_consensus_table`
3. `write_consensus_table` reads `plasmid_predictions` from the shared `tables/` directory
4. At this point, `SRR1952519_plasmid_detect_genomad` may or may not have written its rows yet

But even if only SRR1952439 data was available, that sample alone produced ~48 predictions. So the table should have at least 48 rows, not 0.

**Alternative hypothesis**: The consensus step ran twice (once per sample via per_sample scope), and the SECOND run with `append=False` (line 357: `write_standard_table(tables_dir, "plasmid_consensus", consensus_rows, append=False)`) overwrote the first run's output. If the second run had empty `consensus_rows` (e.g., because `plasmid_predictions` was read during a race condition), it would truncate the table to header-only.

**Investigation steps**:
1. Add logging to `write_consensus_table` — print `len(predictions)`, `len(consensus_source)`, `len(consensus_rows)` before write
2. Check if `_refresh_consensus_and_fastas` is called once or multiple times
3. Consider changing `append=False` to `append=True` or making the call once at cross-sample scope

**Files to change**:
- `plugins/metagenomic_plasmid/_engine/pipeline.py` — trace call timing
- `plugins/metagenomic_plasmid/_engine/standard_tables.py` — fix append behavior or add diagnostics

---

### Fix 5: Enable comparative_genomics with mmseqs2 (unblocks comparative_hits)

**Problem**: `comparative_genomics: enable: false` in config. mmseqs2 database (1.6GB) is downloaded and ready. No blocker except config.

**Fix**: In `config_illumina_full.yaml`:
```yaml
comparative_genomics:
  enable: true
  tools: [mmseqs2]
```

---

### Fix 6: Add 3rd sample (unblocks differential_abundance + sample_diversity)

**Problem**: `differential_abundance` and `sample_diversity` require >=3 samples for meaningful statistical tests (beta diversity, differential abundance testing). Only 2 samples currently.

**Fix**: Add a 3rd sample to `sample_sheet_illumina_test.tsv`. Selection criteria:
- Paired-end Illumina metagenomic data from SRA
- Small file size (fast download)
- Verify gzip integrity with `gzip -t` before adding

**Candidate SRR accessions** (same study SRP051182 or similar):
- To be selected based on fastq-dump availability

---

### Fix 7: Enable sample_analysis

**Problem**: `sample_analysis: enable: false` in config.

**Fix**: After Fix 6 (3 samples exist), enable in config:
```yaml
sample_analysis:
  enable: true
```

---

## Deferred Items (P3 — Large downloads / complex installs)

| Item | Reason | Estimated effort |
|------|--------|-----------------|
| plasmid binning tools (plasmaag, gplas2, metabat2, maxbin2, concoct, semibin, das_tool, scapp, recycler, mob_recon) | Requires conda installs + git clones + DB downloads for each tool | 4-6 hours |
| blast DB | ~150GB nt database download | 12+ hours download |
| gtdbtk DB | ~56GB download | 2-3 hours |
| checkm2 | Python version conflict (stats env py3.10, checkm2 needs <3.9 or >3.12) | Needs separate conda env |
| host_removal (bwa + kneaddata) | No host reference genome available | Requires host genome FASTA |
| eggnog_mapper, rgi | No ResourceSpec; conda executable availability unknown | TBD |

---

## Execution Order

```
Phase 1 (parallel start):
  ├── Fix 1: kraken2-build --build (background, 1-2 hours)
  ├── Fix 2: copla installation (~5 min)
  └── Fix 3: fastspar OTU aggregation (code change, ~30 min)

Phase 2:
  ├── Fix 4: Debug plasmid_consensus (code investigation)
  ├── Fix 5: Enable comparative_genomics (config change)
  └── Fix 6: Add 3rd sample + Fix 7: Enable sample_analysis

Phase 3: Re-run pipeline
  └── abi run --type metagenomic_plasmid --config config_illumina_full.yaml --confirm-execution
      Target: 14/16 tables with data

Phase 4: Verify
  └── Compare table row counts, verify all fixable tables populated
```

## Expected Outcome

| Table | Before | After | Source of Fix |
|-------|--------|-------|--------------|
| host_predictions | 0 | data | Fix 1 (kraken2 build) |
| plasmid_typing | 0 | data* | Fix 2 (copla) |
| network_edges | 0 | data | Fix 3 (OTU aggregation) |
| network_nodes | 0 | data | Fix 3 (OTU aggregation) |
| plasmid_consensus | 0 | 96 | Fix 4 (bug fix) |
| visualization_outputs | 0 | data | Auto (blocked→unblocked) |
| comparative_hits | 0 | data | Fix 5 (enable mmseqs2) |
| differential_abundance | 0 | data* | Fix 6+7 (3rd sample) |
| sample_diversity | 0 | data* | Fix 6+7 (3rd sample) |
| plasmid_bins | 0 | 0 | Deferred (P3) |
| bin_to_contig | 0 | 0 | Deferred (P3) |

*If biological signal exists in the data.
