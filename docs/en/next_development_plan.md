# ABI Next Stage Development Plan & Technical Design

> **Status**: Active (2026-06-18)
> **Last updated**: 2026-06-18 — Direction E complete, ABI v1.3.0 + Bench v0.5 released
> **Canonical reference**: This document supersedes `docs/abi_final_development_plan.md` and `docs/demo_plan.md`.
> **Related**: `docs/workflow_validation.md`, `docs/pipeline_biological_validity.md`, `docs/plugin_development_guide.md`, `docs/hpc_development.md`

## 0. Implementation Status (2026-06-18)

| Phase | Plugin | Status | Tests | Parsers | Notes |
|-------|--------|--------|-------|---------|-------|
| 0 | metagenomic_plasmid | ✅ Stable | Full | Full (32 tools) | Flagship plugin |
| 1 | Report + figures layer | ✅ Complete | 435+ | N/A | Core capability |
| 2 | rnaseq_expression | ✅ Complete | 21 tests | 5/5 tools | +build_count_matrix tool |
| 3 | wgs_bacteria | ✅ Complete | 17 tests | 5/5 tools | AMRFinderPlus parser fixed |
| 4 | amplicon_16s | ✅ Complete | 15 tests | 7/7 tools | +merge, +phylogeny, +diversity script |
| 5 | metatranscriptomics | ✅ Complete | 10 tests | 3/3 tools | Fourth full pipeline |
| 6 | Benchmark datasets | ✅ Complete | 4 smoke tests | — | 5/5 plugins, value-level validation |
| 7 | Multi-plugin demos | ⏸️ Deferred | — | — | Depends on real input data |

**Total**: 543 tests, 0 mypy errors, 0 ruff errors, 5 functional plugins, all with `pipeline_dag.yaml`

### Direction D: Benchmark Datasets + End-to-End Tests (2026-06-18)

| Task | Description | Status |
|------|-------------|--------|
| D1 | Benchmark expected_assertions.yaml + config.yaml for amplicon_16s | ✅ |
| D2 | Benchmark expected_assertions.yaml + config.yaml for rnaseq_expression | ✅ |
| D3 | Benchmark expected_assertions.yaml + config.yaml for metagenomic_plasmid | ✅ |
| D4 | Value-level smoke tests for rnaseq and amplicon | ✅ |

### Direction E: Token Optimization + Benchmark Completion + Real Execution (2026-06-18)

| Task | Description | Status |
|------|-------------|--------|
| E1 | Plan summarization (78-95% token savings) | ✅ |
| E2 | `abi query` lightweight metadata command | ✅ |
| E3 | Error envelope sans traceback (verbose mode) | ✅ |
| E4 | Dry-run envelope reduction | ✅ |
| E5 | wgs_bacteria + metatranscriptomics benchmark data | ✅ 5/5 plugins |
| E6 | Value-level smoke tests for wgs + metatranscriptomics | ✅ |
| E7 | Bench v0.5 T31-T35 real execution tasks | ✅ |
| E8 | Bench v0.5 scoring checks + fixtures | ✅ |
| E9 | Integration test + v1.3.0 release | ✅ |

### Direction A: Amplicon Diversity + Phylogeny + AMRFinderPlus (2026-06-18)

| Task | Description | Status |
|------|-------------|--------|
| A1 | Amplicon diversity script (ASV table + alpha/beta diversity) | ✅ scripts/amplicon_diversity.py, 781 lines, 23 tests |
| A2 | WGS bacteria AMRFinderPlus parser fix | ✅ normalization + fixture + test |
| A3 | Phylogeny tree step (MAFFT + FastTree) | ✅ new DAG node, tool contract, build_plan wiring |
| A4 | _builtin_plugins() registers all 5 plugins | ✅ fixes 47 test failures in source-tree imports |

### Direction B: Engineering Infrastructure (2026-06-18)

| Task | Description | Status |
|------|-------------|--------|
| B1 | Sphinx API documentation + ReadTheDocs | ✅ docs/conf.py, api.rst, .readthedocs.yaml |
| B2 | README badges (coverage + docs) | ✅ |
| B3 | pre-commit hook version updates | ✅ ruff v0.9.0, hooks v5.0.0, mypy v1.14.0 |
| B4 | CI docs build + coverage XML | ✅ |
| B5 | _parse_sample_sheet check_files fix | ✅ all 4 inline plugins return synthetic context |

### Direction C: Docker Containerization (2026-06-18)

| Task | Description | Status |
|------|-------------|--------|
| C1 | Missing conda env YAMLs (amplicon, wgs, abi-qc, abi-stats) | ✅ 4 new env YAMLs |
| C2 | 5 plugin Dockerfiles (amplicon, rnaseq, wgs, metatx, plasmid) | ✅ docker/Dockerfile.* |
| C3 | docker-compose.yml (all 5 images + job-service) | ✅ |
| C4 | .dockerignore + CI Docker build workflow | ✅ .dockerignore + .github/workflows/docker.yml |

### Route C: Code Quality & Test Coverage (2026-06-18)

| Task | Description | Status |
|------|-------------|--------|
| C1 | contract-lint crash fix | ✅ Already resolved |
| C2 | mypy errors (5 → 0) | ✅ Clean across 138 source files |
| C3 | wgs_bacteria.py type annotations | ✅ Already clean |
| C4 | amplicon_16s I/O error handling | ✅ Already in place |
| C5 | Test coverage (+90 tests) | ✅ workflow/validation 98%, provenance 98%, hpc 66% |
| C6 | Test infrastructure improvements | ✅ smoke markers, requires_tools markers, dry-run smoke tests |

### P0-P2 Remediation (lightweight local IDE test)

| Bug | Description | Status | Commit |
|-----|-------------|--------|--------|
| P0-1 | build_count_matrix tool + DESeq2 fixes | ✅ | 77aca65 |
| P0-2 | amplicon_16s vsearch mergepairs step | ✅ | 0c0b912 |
| P1-1 | DESeq2 installation automation | ✅ | envs/rnaseq.yml, install_deseq2.R, setup_rnaseq_env.sh |
| P1-2 | amplicon taxonomy DB generation | ✅ | download_rdp_sintax.sh + synthetic fallback |
| P2 | Smoke tests with real tool execution | ✅ | test_amplicon_smoke.py (10/11 steps pass) |

## 1. Project Goals

### 1.1 Overall Goal

Upgrade ABI from "a control plane capable of driving plasmid analysis" to "a reusable agent-friendly bioinformatics workflow platform."

All five bioinformatics analysis plugins are now implemented:

1. **metagenomic_plasmid**: full plasmid detection/annotation/abundance pipeline (flagship).
2. **rnaseq_expression**: bulk RNA-seq expression and differential analysis.
3. **wgs_bacteria**: bacterial isolate WGS analysis.
4. **amplicon_16s**: 16S/ITS amplicon microbiome analysis.
5. **metatranscriptomics**: microbial community transcriptome functional activity analysis.

Every plugin supports:

```bash
abi plan
abi dry-run
abi inspect
abi run --confirm-execution
abi report
abi export-nextflow
abi export-agent-context
```

Final deliverable shape:

```text
results/<analysis_type>/<run_id>/
  execution_plan.json
  provenance/
    commands.tsv
    resolved_inputs.tsv
    tool_versions.tsv
    resources.json
    resource_manifest.json
    run_summary.json
    progress.jsonl
    checksums.json
    step_logs/
  tables/
    *.tsv
  figures/
    *.png / *.svg / *.html
  report/
    report.md
    report.html
    methods.md
    limitations.md
```

---

## 2. Core Positioning

### 2.1 What ABI Is Not

ABI should not become a simple collection of bioinformatics wrappers.

**Wrong positioning:**

```text
ABI = A bunch of Python wrappers around bioinformatics tool CLIs
```

**Correct positioning:**

```text
ABI = An agent-oriented bioinformatics workflow control plane
```

ABI's core value is not "I can also run fastp, STAR, SPAdes, DADA2" but:

1. Let agents discover what analysis types are available.
2. Let agents generate constrained execution plans.
3. Let agents dry-run before real execution.
4. Let agents repair configuration based on structured error codes.
5. Produce standard provenance for every step.
6. Output results as standard tables, reports, and figures.
7. Make the entire workflow reproducible, auditable, and publication-verifiable.

### 2.2 Paper Narrative

The next-phase paper narrative should upgrade from:

```text
ABI helps agents operate a metagenomic plasmid analysis pipeline
```

To:

```text
ABI is a reusable agent-operable bioinformatics workflow layer
capable of uniformly driving plasmid analysis, transcriptome expression,
bacterial WGS, 16S microbiome, and community transcriptome workflows,
with unified DAG output, provenance, standard tables, reports, and visualizations.
```

---

## 3. Overall Architecture

### 3.1 Architecture Principles

ABI development adheres to a three-layer architecture:

```text
Agent / LLM Platform
  ↓
ABI Transport Layer
  - CLI JSON
  - MCP
  - OpenAI-compatible descriptors
  - HTTP Job Service
  ↓
ABI Core Layer
  - Lifecycle API
  - DAG planning
  - Contract enforcement
  - Provenance
  - Diagnostics
  - Permissions
  - Standard tables
  - Report and figures
  ↓
Bioinformatics Plugins
  - metagenomic_plasmid
  - rnaseq_expression
  - wgs_bacteria
  - amplicon_16s
  - metatranscriptomics
```

Core rules:

1. **Thick core**: Plugin discovery, schema, permissions, diagnostics, provenance, standard tables, contracts, execution planning, and report system all live in ABI core.
2. **Thin transport**: CLI, MCP, OpenAI descriptors, HTTP Job Service all just call `ABIAgentInterface`.
3. **Clean plugins**: Biological workflows, tool contracts, standard table schemas, parsers, and report templates belong to each plugin.
4. **Agent never imports Python classes**: Agents interact only through CLI JSON, MCP, HTTP, or tool descriptors.

### 3.2 New Core Modules

New or strengthened modules:

```text
src/abi/
  figures/
    __init__.py
    base.py           # FigureEngine, FigureSpec, render_figure
    qc.py             # QC barplots, read retention
    expression.py     # PCA, volcano, MA, heatmap
    assembly.py       # N50, contig length, GC scatter
    microbiome.py     # Taxonomy barplots, alpha/beta diversity
    amr.py            # AMR heatmap, drug class barplot

  report/
    __init__.py
    generic_report.py  # Enhanced write_generic_report (now with methods, limitations)
    methods.py         # Methods section generator
    limitations.py     # Limitations section generator
    citations.py       # Citation registry and formatter
    html.py            # HTML report renderer

  workflow/
    __init__.py
    manifest.py        # Resource manifest generation and validation
    validation.py      # Workflow validation helpers
    figure_specs.py    # Figure spec loading and validation
```

---

## 4. Generic Report & Visualization System

### 4.1 Why Reports/Figures First

If each plugin writes its own reports and figures, the codebase will become unmaintainable.

**Wrong approach:**

```text
rnaseq_expression writes its own report
wgs_bacteria writes its own report
amplicon_16s writes its own report
metatranscriptomics writes its own report
```

**Correct approach:**

```text
ABI core provides a generic report + figure engine
Plugins only declare:
  - Standard tables
  - Figure specs
  - Method citations
  - Interpretation limitations
```

This guarantees consistent output structure across all plugins and makes it easy for agents to read and interpret.

### 4.2 Figure Declaration Format

Each plugin adds a `figure_specs.yaml`:

```yaml
figures:
  - id: qc_read_counts
    type: bar
    source_table: qc_summary
    x: sample_id
    y: reads_after_filtering
    title: "Reads retained after QC"
    required: true

  - id: mapping_rate
    type: bar
    source_table: alignment_summary
    x: sample_id
    y: mapping_rate
    title: "Mapping rate per sample"
    required: true

  - id: volcano
    type: volcano
    source_table: differential_expression
    x: log2FoldChange
    y: padj
    label: gene_id
    title: "Differential expression volcano plot"
    required: false
```

Figures should NOT be generated by agents writing ad-hoc Python; they should be stably generated by ABI from standard tables and figure specs.

### 4.3 Report Template Structure

Every plugin report should uniformly contain:

```text
1. Executive summary
2. Input dataset summary
3. Workflow overview
4. QC results
5. Main biological results
6. Figures
7. Standard tables
8. Methods
9. Tool versions
10. Database/resource manifest
11. Known limitations
12. Citations
```

---

## 5. Plugin Development Standard

Each plugin directory adopts a uniform structure:

```text
plugins/<analysis_type>/
  abi-plugin.yaml
  config_default.yaml
  sample_sheet_template.tsv
  tool_registry.yaml
  standard_tables.yaml
  figure_specs.yaml
  citation_registry.yaml
  limitations.yaml
  tool_contracts/
    <tool>.yaml
  skills/
    <tool>/SKILL.md
  tests/
    fixtures/
    expected_tables/
```

Each plugin must implement:

```python
class MyPlugin(ABIPlugin):
    plugin_id: str
    display_name: str
    description: str
    report_title: str

    def load_config(self): ...
    def build_plan(self): ...
    def registry(self): ...
    def table_schemas(self): ...
    def parse_outputs(self): ...
    def write_report(self): ...
```

---

## 6. Five Plugin Development Plans

### 6.1 metagenomic_plasmid: Strengthen the Flagship

#### Current State

**metagenomic_plasmid** is already ABI's flagship plugin with a complex DAG, tool contracts, standard tables, and plasmid analysis engine.

Continue strengthening, not blindly adding tools:

1. Report quality.
2. Figure output.
3. Database manifest.
4. Benchmark dataset.
5. Real execution demo.
6. Literature citations and interpretation limitations.

#### Next Tasks

| Task | Content | Priority |
| --- | --- | --- |
| Report upgrade | Output `report.html`, `methods.md`, `limitations.md` | P0 |
| Figure completion | Plasmid prediction, abundance, AMR, host prediction, network | P0 |
| Resource manifest | geNomad DB, Bakta DB, AMR DB, Kraken2 DB, etc. | P0 |
| Demo B | 8-tool core sub-path real execution | P0 |
| Benchmark fixture | Small positive/negative plasmid dataset | P1 |
| Optional tool tiering | `validated` / `available` / `experimental` | P1 |

#### Recommended Core Sub-path

```text
fastp
  → MEGAHIT / metaSPAdes
  → geNomad
  → Bakta / Prokka
  → AMRFinderPlus
  → CoverM
  → plasmid typing
  → summary statistics
  → report
```

#### Standard Figures

| Figure | File |
| --- | --- |
| QC read retention | `figures/qc_read_retention.png` |
| Assembly N50 / contig count | `figures/assembly_qc.png` |
| Plasmid length distribution | `figures/plasmid_length_distribution.png` |
| Plasmid score distribution | `figures/plasmid_score_distribution.png` |
| Plasmid abundance heatmap | `figures/plasmid_abundance_heatmap.png` |
| AMR gene heatmap | `figures/amr_heatmap.png` |
| Predicted host barplot | `figures/host_prediction_summary.png` |

### 6.2 rnaseq_expression: First New Full Pipeline Plugin

#### Positioning

**rnaseq_expression** is a bulk RNA-seq expression analysis plugin, targeting FASTQ → differential expression tables → report.

#### Recommended DAG

```text
FASTQ
  → fastp
  → STAR / HISAT2
  → featureCounts
  → DESeq2
  → enrichment analysis
  → report + figures
```

#### Tool Chain

| Stage | Default Tool | Alternative |
| --- | --- | --- |
| QC | fastp | FastQC, MultiQC |
| Alignment | STAR | HISAT2 |
| Quantification | featureCounts | Salmon/Kallisto |
| Differential expression | DESeq2 | edgeR |
| Enrichment | clusterProfiler / gseapy | GOATOOLS |

#### Standard Tables

| Table | Content |
| --- | --- |
| `qc_summary.tsv` | Reads, Q20/Q30, GC, filtering ratio |
| `alignment_summary.tsv` | Mapping rate, unique mapping, multi-mapping |
| `gene_counts.tsv` | Raw gene count matrix |
| `normalized_expression.tsv` | TPM/CPM/DESeq2 normalized counts |
| `differential_expression.tsv` | gene_id, log2FC, pvalue, padj |
| `enrichment_results.tsv` | GO/KEGG/pathway enrichment |

#### Figures

| Figure | File |
| --- | --- |
| QC reads barplot | `figures/qc_read_counts.png` |
| Mapping rate barplot | `figures/mapping_rate.png` |
| PCA | `figures/pca_expression.png` |
| Volcano plot | `figures/volcano_DEG.png` |
| MA plot | `figures/ma_plot.png` |
| Top DEG heatmap | `figures/top_deg_heatmap.png` |
| Enrichment dotplot | `figures/enrichment_dotplot.png` |

#### Acceptance Commands

```bash
abi plan --type rnaseq_expression \
  --config examples/rnaseq_expression/config.yaml \
  --outdir results/rnaseq_demo

abi dry-run --type rnaseq_expression \
  --config examples/rnaseq_expression/config.yaml \
  --outdir results/rnaseq_demo

abi run --type rnaseq_expression \
  --config examples/rnaseq_expression/config.yaml \
  --outdir results/rnaseq_demo \
  --confirm-execution

abi report --type rnaseq_expression \
  --result-dir results/rnaseq_demo
```

#### Minimum Acceptance Criteria

```text
tables/gene_counts.tsv exists
tables/normalized_expression.tsv exists
tables/differential_expression.tsv exists
figures/pca_expression.png exists
figures/volcano_DEG.png exists
report/report.html exists
provenance/tool_versions.tsv exists
provenance/resource_manifest.json exists
```

### 6.3 wgs_bacteria: Second New Full Pipeline Plugin

#### Positioning

**wgs_bacteria** is a bacterial isolate WGS analysis plugin — not metagenomics, not complex community binning.

#### Recommended DAG

```text
FASTQ
  → fastp
  → SPAdes / Unicycler
  → QUAST
  → Prokka / Bakta
  → MLST
  → AMRFinderPlus / ABRicate
  → plasmid / virulence optional modules
  → report + figures
```

#### Tool Chain

| Stage | Default Tool | Alternative |
| --- | --- | --- |
| QC | fastp | FastQC, MultiQC |
| Assembly | SPAdes | Unicycler |
| Assembly QC | QUAST | — |
| Annotation | Prokka | Bakta |
| MLST | mlst | PubMLST schemes |
| AMR | AMRFinderPlus | ABRicate |
| Plasmid typing | PlasmidFinder | MOB-suite |
| Virulence | VFDB/ABRicate | — |

#### Standard Tables

| Table | Content |
| --- | --- |
| `qc_summary.tsv` | Read QC |
| `assembly_qc.tsv` | Contigs, N50, total length, GC |
| `annotation_summary.tsv` | CDS, rRNA, tRNA, pseudogene counts |
| `mlst.tsv` | Scheme, ST, allele profile |
| `amr_genes.tsv` | Resistance genes, identity, coverage, drug class |
| `virulence_genes.tsv` | Virulence genes, optional |
| `plasmid_replicons.tsv` | Plasmid replicons, optional |

#### Figures

| Figure | File |
| --- | --- |
| Assembly QC barplot | `figures/assembly_qc.png` |
| Genome size vs GC scatter | `figures/genome_gc_scatter.png` |
| AMR heatmap | `figures/amr_heatmap.png` |
| Drug class barplot | `figures/amr_drug_class.png` |
| MLST summary | `figures/mlst_summary.png` |
| Annotation composition | `figures/annotation_composition.png` |

#### Minimum Acceptance Criteria

```text
tables/assembly_qc.tsv exists
tables/annotation_summary.tsv exists
tables/mlst.tsv exists
tables/amr_genes.tsv exists
figures/assembly_qc.png exists
figures/amr_heatmap.png exists
report/report.html exists
```

### 6.4 amplicon_16s: Third New Full Pipeline Plugin

#### Positioning

**amplicon_16s** is an ASV-based 16S/ITS microbiome analysis plugin.

#### Recommended DAG

```text
FASTQ
  → cutadapt
  → DADA2
  → chimera removal
  → taxonomy assignment
  → phylogeny
  → alpha diversity
  → beta diversity
  → differential abundance optional
  → report + figures
```

#### Tool Chain

| Stage | Default Tool | Alternative |
| --- | --- | --- |
| Primer trimming | cutadapt | fastp |
| Denoising | DADA2 | QIIME2 dada2 |
| Taxonomy | SILVA classifier | GTDB / Greengenes |
| Phylogeny | MAFFT + FastTree | QIIME2 phylogeny |
| Diversity | QIIME2 diversity | scikit-bio |
| Differential abundance | ANCOM / ALDEx2 | DESeq2-style exploratory |

#### Standard Tables

| Table | Content |
| --- | --- |
| `primer_trim_summary.tsv` | Primer trimming stats |
| `denoising_stats.tsv` | Input, filtered, denoised, merged, nonchimera reads |
| `asv_table.tsv` | ASV abundance matrix |
| `taxonomy.tsv` | ASV taxonomy |
| `alpha_diversity.tsv` | Shannon, Observed ASVs, Faith PD, etc. |
| `beta_diversity.tsv` | Distance matrix summary |
| `differential_abundance.tsv` | Optional differential abundance results |

#### Figures

| Figure | File |
| --- | --- |
| Reads retention plot | `figures/read_retention.png` |
| Taxonomy stacked barplot | `figures/taxonomy_barplot_phylum.png` |
| Alpha diversity boxplot | `figures/alpha_diversity_boxplot.png` |
| PCoA plot | `figures/beta_diversity_pcoa.png` |
| ASV prevalence plot | `figures/asv_prevalence.png` |
| Top taxa heatmap | `figures/top_taxa_heatmap.png` |

#### Report Must State Limitations

1. 16S/ITS is relative abundance analysis, not absolute bacterial load.
2. Primer region strongly affects taxonomic results.
3. SILVA/GTDB/Greengenes database version must appear in methods.
4. Low-abundance taxa interpretation requires caution.
5. Differential abundance is exploratory analysis; do not over-claim.

### 6.5 metatranscriptomics: Fourth New Full Pipeline Plugin

#### Positioning

**metatranscriptomics** is a microbial community transcriptional activity analysis plugin — must not be confused with ordinary bulk RNA-seq.

#### Recommended DAG

```text
FASTQ
  → fastp
  → SortMeRNA
  → host removal optional
  → MetaPhlAn
  → HUMAnN
  → gene family / pathway profiling
  → normalization + group comparison
  → report + figures
```

#### Tool Chain

| Stage | Default Tool | Alternative |
| --- | --- | --- |
| QC | fastp | FastQC, MultiQC |
| rRNA removal | SortMeRNA | bbduk |
| Host removal | Bowtie2 | minimap2 |
| Taxonomic profiling | MetaPhlAn | Kraken2 |
| Functional profiling | HUMAnN | eggNOG-mapper |
| Statistics | Python/R scripts | MaAsLin2 |

#### Standard Tables

| Table | Content |
| --- | --- |
| `qc_summary.tsv` | Read QC |
| `rrna_filter_summary.tsv` | rRNA/non-rRNA read ratio |
| `host_removal_summary.tsv` | Host read removal ratio |
| `taxonomic_expression.tsv` | Active species/genus relative expression |
| `gene_family_expression.tsv` | Gene family abundance |
| `pathway_expression.tsv` | Pathway abundance/coverage |
| `functional_activity_summary.tsv` | Inter-group functional activity difference summary |

#### Figures

| Figure | File |
| --- | --- |
| rRNA depletion plot | `figures/rrna_filtering.png` |
| Taxonomic activity barplot | `figures/taxonomic_activity.png` |
| Pathway heatmap | `figures/pathway_heatmap.png` |
| Gene family PCA | `figures/gene_family_pca.png` |
| Top pathway differential plot | `figures/top_pathway_diff.png` |
| Taxon-function contribution plot | `figures/taxon_function_contribution.png` |

#### Report Must State Limitations

1. RNA abundance ≠ protein activity.
2. Relative expression affected by sequencing depth, rRNA removal efficiency, database version.
3. Incomplete host removal contaminates results.
4. HUMAnN stratified results require cautious interpretation.
5. Do not equate relative expression with absolute functional activity.

---

## 7. Development Priorities

### 7.1 Overall Sequence

```text
Phase 0: Stabilize current metagenomic_plasmid full pipeline
Phase 1: Implement generic report + figures layer
Phase 2: Develop rnaseq_expression full pipeline
Phase 3: Develop wgs_bacteria full pipeline
Phase 4: Develop amplicon_16s full pipeline
Phase 5: Develop metatranscriptomics full pipeline
Phase 6: Supplement benchmark datasets + validation
Phase 7: Multi-plugin demos + paper results collation
```

### 7.2 Priority Table

| Priority | Module | Reason | Target |
| --- | --- | --- | --- |
| P0 | Generic report + figures | Shared by all plugins; do first to avoid duplication | Unified report system |
| P0 | rnaseq_expression | Short tool chain, easy to validate, good for real demo | First new full pipeline |
| P1 | wgs_bacteria | Intuitive results, high report value | Second new full pipeline |
| P2 | amplicon_16s | High microbiome ecological value | Third new full pipeline |
| P3 | metatranscriptomics | Complex, database-heavy, difficult interpretation | Last |

---

## 8. Technical Implementation Details

### 8.1 Workflow Manifest

Each plugin's `abi-plugin.yaml` must include a workflow declaration:

```yaml
workflow:
  name: "RNA-seq expression workflow"
  version: "0.1.0"
  route: "default"
  citations:
    - tool: fastp
      stage: qc
      citation: "Chen et al. 2018, Bioinformatics"
    - tool: STAR
      stage: alignment
      citation: "Dobin et al. 2013, Bioinformatics"
  steps:
    - id: qc_fastp
      tool: fastp
      after: []
      required: true
    - id: align_star
      tool: star
      after: [qc_fastp]
      required: true
    - id: quantify_featurecounts
      tool: featurecounts
      after: [align_star]
      required: true
    - id: differential_expression_deseq2
      tool: deseq2
      after: [quantify_featurecounts]
      required: false
```

### 8.2 Tool Contract

Every tool must have `tool_contracts/<tool>.yaml`:

```yaml
tool_id: fastp
category: qc
execution:
  env_name: rnaseq
  executable: fastp
  version_command: "fastp --version"
  command_template: >
    fastp
    -i {read1}
    -I {read2}
    -o {clean_read1}
    -O {clean_read2}
    --json {json_report}
    --html {html_report}
inputs:
  read1:
    type: file
    required: true
    extensions: [".fastq", ".fastq.gz"]
  read2:
    type: file
    required: false
    extensions: [".fastq", ".fastq.gz"]
outputs:
  clean_read1:
    type: file
    min_size: "1KB"
  clean_read2:
    type: file
    required: false
    min_size: "1KB"
  json_report:
    type: file
    required_keys:
      - summary
assertions:
  - "output_json.summary.after_filtering.total_reads > 0"
standard_tables:
  - qc_summary
```

### 8.3 Standard Tables

Each plugin must declare table structures in `standard_tables.yaml`:

```yaml
tables:
  qc_summary:
    path: tables/qc_summary.tsv
    columns:
      - name: sample_id
        type: string
        required: true
      - name: reads_before_filtering
        type: integer
        required: true
      - name: reads_after_filtering
        type: integer
        required: true
      - name: q30_rate
        type: float
        required: false
      - name: gc_content
        type: float
        required: false
```

Principles:

1. Parsers may only write declared standard tables.
2. Empty tables still write stable headers.
3. Reports only read standard tables, never parse raw tool output.
4. Agents only interpret standard tables, never guess from intermediate files.

### 8.4 Resource Manifest

Every real execution workflow must generate:

```json
{
  "analysis_type": "rnaseq_expression",
  "resources": [
    {
      "id": "reference_genome",
      "path": "resources/hg38/genome.fa",
      "version": "GRCh38.p14",
      "source_url": "https://...",
      "checksum_sha256": "...",
      "license": "unknown",
      "validated_at": "2026-06-18"
    },
    {
      "id": "annotation_gtf",
      "path": "resources/gencode/gencode.v44.annotation.gtf",
      "version": "GENCODE v44",
      "checksum_sha256": "...",
      "validated_at": "2026-06-18"
    }
  ]
}
```

Without a resource manifest, a workflow can only be called "runnable", not "reproducible".

### 8.5 Report Generation

Report generation flow:

```text
provenance/
  + tables/
  + figures/
  + citation_registry.yaml
  + limitations.yaml
  → report.md
  → report.html
  → methods.md
```

`methods.md` must contain:

1. Tool name for each step.
2. Tool version.
3. Command parameters.
4. Database version.
5. Resource checksum.
6. Literature citations.
7. Interpretation limitations.

---

## 9. Testing Strategy

### 9.1 Unit Tests

Each plugin must have at minimum:

```text
tests/
  test_plugin_contract.py
  test_plan.py
  test_dry_run.py
  test_parse_outputs.py
  test_write_report.py
  test_figure_specs.py
```

Required tests:

1. Plugin discoverable via `abi list-types`.
2. `abi plan` produces valid `execution_plan.json`.
3. `abi dry-run` generates provenance.
4. Tool contracts pass contract-lint.
5. Parser can generate standard tables from fixture raw output.
6. Report can be generated from standard tables.
7. Figure specs only reference existing standard tables and fields.

### 9.2 Integration Tests

Each plugin needs a tiny fixture:

```text
data/examples/<analysis_type>/
  sample_sheet.tsv
  config.yaml
  raw/
  expected/
    tables/
    report/
```

CI must run at minimum:

```bash
abi plan --type <analysis_type> --config data/examples/<analysis_type>/config.yaml
abi dry-run --type <analysis_type> --config data/examples/<analysis_type>/config.yaml
abi report --type <analysis_type> --result-dir results/<analysis_type>
abi contract-lint --type <analysis_type>
```

Real execution need not run in CI but must have reproducible experiment records locally or on HPC.

### 9.3 Biological Validation

Each production route needs at minimum one small benchmark dataset:

| Plugin | Benchmark dataset type |
| --- | --- |
| metagenomic_plasmid | Known plasmid positive + chromosomal negative |
| rnaseq_expression | Public RNA-seq with known condition contrast |
| wgs_bacteria | Known bacterial isolate with known MLST/AMR |
| amplicon_16s | Mock community with known composition |
| metatranscriptomics | Small synthetic/community RNA dataset |

Each benchmark dataset must contain:

```text
expected_tables/
  qc_summary.tsv
  main_result.tsv
expected_assertions.yaml
```

---

## 10. Demo Design

### 10.1 Demo A: rnaseq_expression Real Execution

Goal: Prove that a new plugin can complete end-to-end execution.

```text
Public RNA-seq dataset
  → Agent + ABI plan
  → dry-run
  → Fault injection and recovery
  → run
  → report
  → Comparison with manual baseline
```

Success criteria:

| Metric | Threshold |
| --- | --- |
| Complete plan/dry-run/run/report | Required |
| Generate gene_counts.tsv | Required |
| Generate differential_expression.tsv | Required |
| PCA/volcano figures exist | Required |
| Counts correlation with manual baseline | Pearson r ≥ 0.95 |
| Provenance complete | Required |

### 10.2 Demo B: metagenomic_plasmid Core Sub-path Real Execution

Goal: Prove flagship plugin is truly runnable.

Core path:

```text
fastp → assembly → geNomad → annotation → abundance → typing → report
```

Success criteria:

| Metric | Threshold |
| --- | --- |
| Execute 6–8 core tools | Required |
| Detect missing_input/missing_resource/tool_not_found | ≥ 3 categories |
| Agent repairs each fault | ≤ 3 steps |
| plasmid_detection overlap with manual baseline | ≥ 90% |
| Provenance complete | Required |

### 10.3 Demo C: Cross-plugin Dry-run

Goal: Prove ABI control plane is portable.

At minimum cover:

```text
metagenomic_plasmid
rnaseq_expression
wgs_bacteria
amplicon_16s
```

Success criteria:

| Metric | Threshold |
| --- | --- |
| All plugins list-types | Required |
| All plugins can plan | Required |
| All plugins can dry-run | Required |
| All plugins generate report skeleton | Required |
| Standard table schemas exportable | Required |

---

## 11. Timeline

### 11.1 Recommended 12-Week Development Plan

| Week | Task | Deliverable |
| --- | --- | --- |
| Week 1 | Generic report/figures schema design | `figure_specs.yaml` schema, report API |
| Week 2 | metagenomic_plasmid report upgrade | Plasmid HTML report + figures |
| Week 3 | rnaseq_expression plugin skeleton | Plugin manifest, tool registry, contracts |
| Week 4 | rnaseq_expression parser/report | Standard tables, figures, report |
| Week 5 | rnaseq_expression real execution demo | Demo A results |
| Week 6 | wgs_bacteria plugin skeleton | DAG, contracts, sample sheet |
| Week 7 | wgs_bacteria parser/report | Assembly/AMR/MLST standard tables |
| Week 8 | wgs_bacteria demo | Small isolate WGS results |
| Week 9 | amplicon_16s plugin skeleton | DADA2/QIIME2 route |
| Week 10 | amplicon_16s parser/report | ASV/taxonomy/diversity standard tables |
| Week 11 | metatranscriptomics plugin | SortMeRNA/MetaPhlAn/HUMAnN route |
| Week 12 | Full plugin contract-lint + docs | Release candidate |

---

## 12. Acceptance Criteria

### 12.1 Engineering Acceptance

Must pass before every merge:

```bash
pytest
ruff check src/abi tests
ruff format --check src/abi tests
mypy src/abi/ --ignore-missing-imports
python -m build
python -m twine check dist/*
```

Each plugin must pass:

```bash
abi list-types
abi plan --type <plugin>
abi dry-run --type <plugin>
abi report --type <plugin>
abi contract-lint --type <plugin>
```

### 12.2 Plugin Acceptance

Each plugin must have:

1. `abi-plugin.yaml`
2. `tool_registry.yaml`
3. `standard_tables.yaml`
4. `figure_specs.yaml`
5. `citation_registry.yaml`
6. `tool_contracts/*.yaml`
7. Sample sheet template
8. Config default
9. Parser
10. Report writer
11. Minimum fixture
12. Contract-lint test
13. Dry-run test
14. Report test

### 12.3 Scientific Verifiability Acceptance

Each route must satisfy:

1. DAG version pinned.
2. Config validated via schema.
3. Every step affecting biological conclusions has output contract.
4. Tool versions recordable.
5. Database versions recordable.
6. Resource checksums recordable.
7. At least one benchmark dataset.
8. At least one positive control.
9. At least one negative/failure fixture.
10. Report includes methods, citations, limitations.

---

## 13. Risks and Controls

### 13.1 Biggest Risk: Scope Creep

**Risk:**

```text
Simultaneously doing 4 new plugins + plasmid report + benchmark + paper
```

**Control:**

```text
First do generic report/figures layer
Then fully punch through rnaseq_expression only
Then advance wgs_bacteria
Finally do amplicon_16s and metatranscriptomics
```

### 13.2 Database Risk

High-risk plugins:

1. metagenomic_plasmid
2. metatranscriptomics
3. amplicon_16s

Control strategy:

1. Databases do not enter git.
2. Databases stored in `resources/`.
3. Every database must have manifest.
4. Demos use minimal databases or small test databases.
5. Large databases only used on HPC / local full runs.

### 13.3 Biological Over-claiming Risk

**Prohibited claims:**

```text
ABI discovered new biological mechanisms
ABI proved a certain plasmid-host relationship
ABI proved absolute abundance changes for a certain bacterium
```

**Allowed claims:**

```text
ABI produced computational results consistent with manual expert pipelines
ABI enabled agents to controllably complete literature-aligned bioinformatics workflows
ABI recorded complete provenance and auditable reports
ABI output interpretable standard tables and visualizations
```

---

## 14. Final Deliverables

### 14.1 Code Deliverables

```text
src/abi/figures/
src/abi/report/         (enhanced)
plugins/rnaseq_expression/   (enhanced)
plugins/wgs_bacteria/        (enhanced)
plugins/amplicon_16s/        (enhanced)
plugins/metatranscriptomics/ (enhanced)
```

### 14.2 Documentation Deliverables

```text
docs/
  next_development_plan.md
  plugin_report_figure_spec.md
  rnaseq_expression_workflow.md
  wgs_bacteria_workflow.md
  amplicon_16s_workflow.md
  metatranscriptomics_workflow.md
  workflow_validation.md
```

### 14.3 Demo Deliverables

```text
results/
  plasmid_demo/
  rnaseq_demo/
  wgs_bacteria_demo/
  amplicon_16s_demo/
  metatranscriptomics_demo/
```

Each demo contains at minimum:

```text
execution_plan.json
provenance/
tables/
figures/
report/
```

---

## 15. Concluding Judgment

The next development phase should not continue circling around a "single plasmid pipeline" but should treat the existing plasmid plugin as a flagship case study, then abstract out a generic report, visualization, standard table, and resource manifest system.

The most reasonable route is:

```text
metagenomic_plasmid existing full pipeline
  ↓
Generic report + figures layer
  ↓
rnaseq_expression full pipeline
  ↓
wgs_bacteria full pipeline
  ↓
amplicon_16s full pipeline
  ↓
metatranscriptomics full pipeline
  ↓
Multi-plugin demos + benchmark validation + paper case studies
```

This route simultaneously serves three goals:

1. **Product goal**: ABI becomes a reusable bioinformatics agent workflow platform.
2. **Engineering goal**: All plugins share lifecycle, contracts, standard tables, reports, and provenance.
3. **Paper goal**: Prove ABI's core value is not a single plasmid pipeline but a cross-analysis-type agent-operability control plane.

## First Step to Execute

Do NOT immediately start all four plugins simultaneously. The first step should be:

```text
First make report + figures + methods + resource_manifest into ABI core generic capabilities.
```

Once this step is done, the next four plugins are just template extensions; without this step, the result will be four duplicate report systems.

---

# Direction E：ABI v1.3 Token优化 + v0.5 Benchmark真实执行

> **Status**: Active (2026-06-18)
> **Dependencies**: Direction A + B + C + D 基本完成
> **Priority**: P0（token优化）+ P1（benchmark数据集）+ P2（真实执行任务）

## E.0 核心洞察

### E.0.1 性能分析结论（2026-06-18 实测）

| 指标 | 测量值 | 评价 |
|------|--------|------|
| Python import | 228ms | 快 |
| `abi list-types` | 276ms | 快 |
| `abi plan` | 315ms | 快 |
| `abi dry-run` | 361ms | 快 |
| Agent 上下文（plasmid） | ~2,500 bytes | 极轻量 |
| Agent 工具数 | 9 个（插件无关） | 稳定 |
| 单任务 token 消耗（3-tool） | ~3,300 | 正常 |
| 单任务 token 消耗（84-tool） | ~8,500 | 可优化 |

**ABI 架构对 agent 是合理的**。不慢、不臃肿。但 token 消耗有优化空间——特别是 plan 输出（84-step plasmid plan ~5,000+ tokens）。

### E.0.2 Token 浪费分析

```
消耗来源                        tokens    占比    可优化
──────────────────────────────────────────────────────────
系统 prompt（工具定义，一次性）    1,845     56%    ❌ 必要
Agent 推理（所有回合）             800-1200  30%    ❌ LLM 固有
abi plan（读 execution_plan.json）869      26%    ✅ 摘要化可省 78%
abi dry-run（信封）               197       6%    ✅ 精简可省 50%
abi inspect                      503      15%    ⚠️ 中等
abi report                       38        1%    ❌ 已很小
```

### E.0.3 优化目标

| 优化 | 代码量 | 节省 tokens |
|------|--------|------------|
| plan 输出摘要化 | ~30 行 | -78%（plasmid plan） |
| 错误响应去 traceback | ~20 行 | -80%（错误场景） |
| abi query 接口 | ~80 行 | -90%（轻量查询） |
| dry-run 信封精简 | ~20 行 | -50% |
| **合计** | **~150 行** | **单任务 -45~78%** |

---

## E.1 Phase 1：ABI Token 优化（Week 1 Day 1-3）

### E.1.1 Plan 输出摘要化

**文件**：`src/abi/agent/envelopes.py`

ABI 的 `build_plan_envelope()` 当前只返回 `{"plan": "<path>", "steps": N}`。Agent 必须再读 `execution_plan.json`（plasmid: ~5,000+ tokens）才能理解 workflow。

优化：envelope 注入摘要，agent 不需要读文件。

```json
{
  "plan": "/tmp/plan/execution_plan.json",
  "steps": 84,
  "summary": {
    "pipeline": "metagenomic_plasmid",
    "stages": ["qc", "assembly", "gene_prediction", "plasmid_detection", "annotation", "abundance"],
    "key_tools": ["fastp", "megahit", "prodigal", "genomad", "bakta", "coverm"],
    "platforms": ["illumina", "ont", "pacbio_hifi", "hybrid", "assembly"]
  }
}
```

**实现**：DAG 在 plan 阶段已加载到内存，envelope 构建时提取 stage 分组。

### E.1.2 错误响应去 traceback

**文件**：`src/abi/agent/envelopes.py`

当前错误信封包含完整 Python traceback。Agent 只需要：
- `error_code`（机器可读，用于自动恢复）
- `diagnostic_hints`（自然语言，用于推理）
- `suggested_action`（下一步建议）

traceback → `--debug` 模式保留。

### E.1.3 新增 `abi query` 接口

**文件**：`src/abi/cli.py`（~50 行）+ `src/abi/agent/interface.py`（~30 行）

```bash
abi query --type <plugin> --what stages|tools|platforms
abi query --type <plugin> --step <id> --what resources|inputs|outputs
```

**设计原则**：不是替代 `abi plan`，而是提供轻量替代路径。Agent 在只需要查询元信息时不用跑完整 plan。底层复用已有的 DAG + tool_registry 加载。

### E.1.4 Dry-run 信封精简

移除 envelope 中自动列出的所有 provenance 文件列表。Agent 按需使用 `abi inspect` 查询。

---

## E.2 Phase 2：Benchmark 数据集补齐（Week 1 Day 4-5 + Week 2 Day 1）

当前状态：2/5 插件有完整 benchmark 数据（amplicon + rnaseq）。

### E.2.1 wgs_bacteria benchmark

```
data/benchmarks/wgs_bacteria/
  expected_assertions.yaml    # qc/assembly/annotation/mlst/amr 值级断言
  config.yaml                 # 可执行配置（小规模合成数据）
```

使用合成细菌基因组 + paired-end reads，验证 contig 数、N50、MLST 检出。

### E.2.2 metatranscriptomics benchmark

```
data/benchmarks/metatranscriptomics/
  expected_assertions.yaml    # qc/alignment/expression 值级断言
  config.yaml                 # 可执行配置
```

复用 rnaseq 的合成数据生成逻辑。

### E.2.3 metagenomic_plasmid benchmark 完善

```
data/benchmarks/metagenomic_plasmid/
  expected_assertions.yaml    # 已有 ✅
  config.yaml                 # 新增：指向 plasmid_refseq_smoke 数据
```

使用 3 个 RefSeq 质粒 + 染色体 negative control。

---

## E.3 Phase 3：Bench v0.5 — 真实执行任务（Week 2 Day 2-5）

### E.3.1 新任务 T31-T35

| 任务 | 插件 | 分值 | 核心评分 |
|------|------|------|---------|
| T31 | metagenomic_plasmid | 15 | pipeline_completed(3) + assertions_validated(6) + discrepancy_analyzed(4) + provenance(2) |
| T32 | rnaseq_expression | 15 | 同上 |
| T33 | amplicon_16s | 15 | 同上 |
| T34 | wgs_bacteria | 15 | 同上 |
| T35 | metatranscriptomics | 15 | 同上 |

**关键变化**：`allowed_actions.real_tool_execution: true`。评分从"文件存在"升级到"值正确"。

### E.3.2 新 fixture

```
bench/fixtures/plasmid_benchmark/     # → ABI data/benchmarks/metagenomic_plasmid/
bench/fixtures/rnaseq_benchmark/      # → ABI data/benchmarks/rnaseq_expression/
bench/fixtures/amplicon_benchmark/    # → ABI data/benchmarks/amplicon_16s/
bench/fixtures/wgs_benchmark/         # → ABI data/benchmarks/wgs_bacteria/
bench/fixtures/metatranscriptomics_benchmark/  # → ABI data/benchmarks/metatranscriptomics/
```

### E.3.3 新增检查项

```yaml
# rubric.yaml 新增
pipeline_completed:     {function: check_pipeline_completed, points: 3}
assertions_validated:   {function: check_assertions_validated, points: 6}
discrepancy_analyzed:   {function: check_discrepancy_analyzed, points: 4}
```

### E.3.4 BENCHMARK_SPEC + run_group.py

```python
REAL_EXEC_TASKS = ["T31", "T32", "T33", "T34", "T35"]
FULL_V0_5_TASKS = FULL_V0_4_TASKS + REAL_EXEC_TASKS  # 30 → 35 tasks
```

---

## E.4 Phase 4：集成测试 + 发布（Week 3）

### E.4.1 验证步骤

```bash
# Token 优化验证
abi plan --type metagenomic_plasmid --outdir /tmp/test | \
  python3 -c "import sys,json; d=json.load(sys.stdin); assert 'summary' in d"

# Benchmark 验证（需真实 conda 环境）
pytest tests/smoke/test_wgs_benchmark.py -v -m requires_tools
pytest tests/smoke/test_metatranscriptomics_benchmark.py -v -m requires_tools

# Bench 模拟模式
python bench/harness/run_group.py --group G3 --tasks real_exec \
  --replicates 1 --agent-mode simulated
```

### E.4.2 发布

```
ABI v1.3.0: token优化 + benchmark数据集 + abi query
Bench v0.5.0: 真实执行任务 + 5插件benchmark覆盖
```

---

## E.5 工具栈总结

全部 Python 3.10+，不引入新语言：

| 阶段 | 工具 | 新增依赖 |
|------|------|---------|
| Token优化 | Python（envelopes.py + cli.py） | 无 |
| Benchmark数据 | Python + BioPython | `biopython` |
| 真实执行 | Python + subprocess | 无 |
| 测试 | pytest | 无 |

---

## E.6 时间线

```
Week 1 Day 1-3:  Phase 1 Token优化（~150行）
Week 1 Day 4-5:  Phase 2.1-2.2 (wgs + metatranscriptomics benchmark)
Week 2 Day 1:     Phase 2.3 (plasmid benchmark完善) + 验证
Week 2 Day 2-4:   Phase 3.1-3.3 (T31-T35 + fixtures + checks)
Week 2 Day 5:     Phase 3.4 (BENCHMARK_SPEC + run_group.py)
Week 3 Day 1-2:   Phase 4.1 (集成测试)
Week 3 Day 3:     Phase 4.2 (发布)
```

---

## E.7 验收标准

**Phase 1**：
- [ ] `abi plan` 返回 `summary` 字段，agent 不需要读文件即可理解 workflow
- [ ] `abi query` 可查询 stages/tools/platforms/resources/inputs/outputs
- [ ] 错误响应不含 traceback，包含 diagnostic_hints + suggested_action
- [ ] plasmid plan token 消耗从 ~5,000 降到 ~250

**Phase 2**：
- [ ] 5/5 插件有 `data/benchmarks/<plugin>/expected_assertions.yaml`
- [ ] 5/5 插件有 `data/benchmarks/<plugin>/config.yaml`
- [ ] 在真实 conda 环境下 benchmark tests 全部通过

**Phase 3**：
- [ ] T31-T35 在 simulated 模式下满分
- [ ] T31-T35 在至少一个真实 LLM 下通过
- [ ] 评分包含值级验证（非仅文件存在）

**Phase 4**：
- [ ] `abi --version` → 1.3.0
- [ ] Bench BENCHMARK_SPEC → version 0.5.0
- [ ] 两个仓库 git tag 已推送
