---
name: tool-engineering-gap-audit
description: Audit of registered tools vs auto-download tools vs actually-used tools across all 5 ABI plugins — 2026-06-22
metadata: 
  node_type: memory
  type: project
  originSessionId: ab8752e5-48b4-43e1-ad54-fbe615506d33
---

# Tool Engineering Gap Audit — 2026-06-22

Systematic audit across all 5 ABI plugins: registered tools (tool_registry.yaml), auto-download tools (ResourceSpec/environments.yaml), and actually-used tools (pipeline_dag.yaml).

## Remediation status — 2026-06-22

The tool graph is now closed and enforced by CI:

| Plugin | Registered | In DAG | Contracts | Env assignments | Registry-only |
|--------|-----------:|-------:|----------:|----------------:|--------------:|
| metagenomic_plasmid | 65 | 65 | 65 | 65 | 0 |
| rnaseq_expression | 5 | 5 | 5 | 5 | 0 |
| wgs_bacteria | 5 | 5 | 5 | 5 | 0 |
| amplicon_16s | 10 | 10 | 10 | 10 | 0 |
| metatranscriptomics | 3 | 3 | 3 | 3 | 0 |

- The 11 unreachable registrations were removed together with stale contracts,
  skills, environment assignments, and the duplicated legacy registry.
- RNA count-matrix and amplicon OTU/phylogeny parsers are implemented; manifests
  and workflow topology match their DAGs.
- WGS AMRFinder database wiring/setup and metatranscriptomics reference-resource
  planning are implemented. Organism-specific references return actionable
  `manual_required` status instead of selecting an unsafe default.
- eggNOG-mapper has automated resource setup; ABRicate has a guided resource
  declaration. Tools such as ISEScan and inline MMseqs2 clustering do not require
  a separate external database and therefore do not receive fictitious downloads.
- Bowtie2, samtools, and report rendering are intermediate/artifact stages, not
  standard-table producers; they are contract-enforced and intentionally have no
  biological table parser.

`tests/unit/test_plugin_artifact_alignment.py` prevents registry/DAG/contract/
manifest/environment drift from recurring. Contract lint reports zero findings
for all five plugins.

## Summary Table

| Plugin | Registered | In DAG | Registered+Unused | Missing ResourceSpec (DB) | No setup_resources |
|--------|-----------|--------|-------------------|--------------------------|-------------------|
| metagenomic_plasmid | 73 | 65 | 8 | 43 | No (has full impl) |
| rnaseq_expression | 6 | 5 | 1 (clusterprofiler) | 2 (genome_index, annotation_gtf) | Partial (only conda+R) |
| wgs_bacteria | 5 | 5 | 0 | 1 (amrfinder_db orphan) | YES |
| amplicon_16s | 11 | 10 | 1 (phylogeny_build) | 0 (taxonomy_db handled) | Partial (taxonomy only) |
| metatranscriptomics | 4 | 3 | 1 (hisat2) | 2 (genome_index, annotation_gtf) | YES |

## Plugin-by-Plugin Details

### 1. metagenomic_plasmid (73 registered, 65 in DAG, 8 unused)

**Registered but NOT in DAG (8 orphans):**
- `bandage` — registered, has env, no DAG node
- `bwa` — registered, has env, no DAG node (redundant vs bowtie2/minimap2 host removal)
- `chopper` — registered, has env, no DAG node (alternative ONT QC)
- `fastplong` — registered, has env, no DAG node (long-read QC)
- `hic_evidence` — registered, has env, no DAG node (placeholder)
- `kneaddata` — registered, has env, no DAG node (alternative host removal)
- `pmlst` — registered, has env, HAS ResourceSpec (manual), no DAG node
- `porechop` — registered, has env, no DAG node (ONT adapter trimming)

**DAG tools WITHOUT any ResourceSpec (43 of 65):**
Most are tools that don't need database downloads (QC, assembly, abundance tools) — acceptable.
But some DO need databases and lack auto-download:
- `abricate` — needs card/resfinder/plasmidfinder DBs, no auto-download
- `eggnog_mapper` — needs eggNOG DB (~20GB), no auto-download
- `isescan` — needs IS profile DB, no auto-download
- `maxbin2` — deprecated in registry anyway ("PERMANENTLY DISABLED")
- `metabat2`, `concoct`, `semibin`, `das_tool` — binning tools, no external DB needed
- `minced` — CRISPR detection, no DB needed
- `mmseqs2` — no DB auto-download (uses inline clustering)

**9 DAG tools have ResourceSpec but manual-only (auto_setup=False):**
blast, conjscan, copla, gplas2, plasmaag, plasmidhostfinder, recycler, rgi, scapp

**1 ResourceSpec orphan (has ResourceSpec but NOT in DAG):** pmlst

**Env assignments are fully aligned:** All 73 registered tools have env assignments. No gaps.

### 2. rnaseq_expression (6 registered, 5 in DAG)

**Gaps found:**

| # | Severity | Gap |
|---|----------|-----|
| 1 | HIGH | `build_count_matrix` has NO output parser — parse_outputs() returns {} |
| 2 | HIGH | `build_count_matrix` missing from core_contracts in abi-plugin.yaml |
| 3 | MEDIUM | `clusterprofiler` is a phantom tool: registered, contracted, but NO DAG node, NO R script, conda dep missing |
| 4 | MEDIUM | `rnaseq` conda env lacks `bioconductor-clusterprofiler` |
| 5 | LOW | No plugin-level check_resources/setup_resources for genome_index/annotation_gtf |
| 6 | LOW | Dead hisat2 branch in parse_outputs (copy-paste from metatranscriptomics) |

### 3. wgs_bacteria (5 registered, 5 in DAG — clean alignment)

**Gaps found:**

| # | Severity | Gap |
|---|----------|-----|
| 1 | MEDIUM | `amrfinder_db` declared in config but NOT referenced by command template — orphan config |
| 2 | MEDIUM | No setup_resources implementation — `abi setup-resources --type wgs_bacteria` errors out |
| 3 | LOW | Citation registry has 5 spurious entries (unicycler, quast, bakta, abricate, plasmidfinder) |
| 4 | LOW | amrfinderplus tool_contract vs tool_registry template mismatch (GFF parameter) |

### 4. amplicon_16s (11 registered, 10 in DAG)

**Gaps found:**

| # | Severity | Gap |
|---|----------|-----|
| 1 | MEDIUM | `phylogeny_build` is registered but NOT in DAG — dead code (DAG uses 3-step phylogeny instead) |
| 2 | MEDIUM | abi-plugin.yaml workflow declaration stale vs DAG (missing vsearch_mergepairs, wrong phylogeny) |
| 3 | MEDIUM | core_contracts list incomplete — 4 tools with full contracts not declared as core |
| 4 | LOW | parse_outputs() has no handlers for vsearch_otu, phylogeny_combine, phylogeny_mafft, phylogeny_tree, phylogeny_build |

### 5. metatranscriptomics (4 registered, 3 in DAG)

**Gaps found:**

| # | Severity | Gap |
|---|----------|-----|
| 1 | MEDIUM | `hisat2` fully registered but unreachable from DAG — no DAG node exists |
| 2 | HIGH | No setup_resources implementation — `abi setup-resources --type metatranscriptomics` errors out |
| 3 | MEDIUM | Reference data is placeholder-only (GENOME_INDEX_NOT_CONFIGURED, ANNOTATION_GTF_NOT_CONFIGURED) — no downloader |

## Cross-Cutting Issues

### No setup_resources for 2 of 5 plugins
wgs_bacteria and metatranscriptomics have NO setup_resources path. Calling `abi setup-resources --type <plugin>` without `--dry-run` raises ABIError.

### Phantom/Orphan Tools (registered but unreachable)
- metagenomic_plasmid: 8 (bandage, bwa, chopper, fastplong, hic_evidence, kneaddata, pmlst, porechop)
- rnaseq_expression: 1 (clusterprofiler)
- amplicon_16s: 1 (phylogeny_build)
- metatranscriptomics: 1 (hisat2)
- wgs_bacteria: 0

**Total: 11 phantom tools across all plugins**

### Missing Output Parsers
- rnaseq_expression: build_count_matrix returns {}
- amplicon_16s: 5 tools (vsearch_otu + 4 phylogeny steps) return {}

### Database Auto-Download Coverage
- metagenomic_plasmid: 13/65 DAG tools have auto-setup ResourceSpec (20%)
- Other 4 plugins: near-zero (only amplicon taxonomy_db has a downloader)

### Stale Workflow Declarations
- amplicon_16s abi-plugin.yaml workflow doesn't match DAG topology

**Why:** Tool registration, resource provisioning, and pipeline DAG are maintained in separate files with no automated cross-reference validation. Tools get added to the registry without being wired into the DAG, and tools get added to the DAG without corresponding parsers or resource specs.

**How to apply:** 
1. Add automated cross-reference validation (compare tool_registry ↔ pipeline_dag ↔ tool_contracts ↔ parsers)
2. Write setup_resources for wgs_bacteria and metatranscriptomics
3. Prune or wire-in the 11 phantom tools
4. Add missing output parsers for build_count_matrix and amplicon phylogeny steps
