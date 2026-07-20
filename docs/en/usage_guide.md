# Using ABI: From a Biological Question to Results

This guide is for people who want to run an analysis, not learn ABI internals. Pick the situation closest to yours and follow that example.

## Where should you start?

| Your situation | Start here |
| --- | --- |
| “I want to see what ABI produces.” | Example 1: try ABI without analysis tools |
| “I have sequencing data and want to start a project.” | Example 2: treatment-vs-control RNA-seq |
| “I want an AI Agent to operate ABI for me.” | Example 3: ask an Agent to plan the analysis |
| “My analysis may run for hours.” | Example 4: submit a queued job |
| “A command failed.” | “When something goes wrong” |

## Choose the analysis that matches your question

You do not need to choose individual tools first. Choose the biological outcome; the plugin defines the workflow and ABI shows you the tools before execution.

| Your biological question | Input | Use `--type` | Main results |
| --- | --- | --- | --- |
| Which microbes are present in my 16S samples? | Paired 16S reads | `amplicon_16s` | ASVs, taxonomy, diversity |
| Which genes differ between two RNA-seq conditions? | Paired RNA-seq reads | `rnaseq_expression` | Counts, normalized expression, differential expression |
| What is the type and resistance profile of a bacterial isolate? | Isolate WGS reads | `wgs_bacteria` | Assembly, annotation, MLST, AMR calls |
| Which genes are expressed in my metatranscriptome? | Metatranscriptomic reads | `metatranscriptomics` | QC, alignment summary, gene counts |
| What organisms and functions occur in shotgun metagenomes? | Shotgun reads | `easymetagenome` | Taxonomic and functional abundance |
| Which viruses occur in my metagenome, and who are their hosts? | Metagenomic reads | `viral_viwrap` | Viral bins, quality, taxonomy, hosts |
| Which plasmids occur in my metagenome? | Reads or assemblies | `metagenomic_plasmid` | Plasmid consensus, typing, hosts, genes, abundance |

Check what is installed on your machine:

```bash
abi list-types
abi query --type rnaseq_expression --what stages
abi query --type rnaseq_expression --what tools
```

## Example 1: Try ABI without analysis tools

**Goal:** see a real execution plan, provenance bundle, standard tables, and report preview without installing STAR or downloading a reference genome.

**You need:** a source checkout of this repository and `abi-agent` installed. This example does not run biological analysis tools.

From the repository root:

```bash
abi plan \
  --type metatranscriptomics \
  --config examples/metatranscriptomics/config_demo.yaml \
  --sample-sheet examples/sample_sheet_transcriptomics.tsv \
  --outdir results/first-plan

abi dry-run \
  --type metatranscriptomics \
  --config examples/metatranscriptomics/config_demo.yaml \
  --sample-sheet examples/sample_sheet_transcriptomics.tsv \
  --outdir results/first-dry-run
```

The first command should report a three-step plan. The second should create:

```text
results/first-dry-run/
├── execution_plan.json
├── provenance/
├── tables/
└── report/
```

Open these files first:

- `execution_plan.json` — the commands, inputs, outputs, and step order ABI selected;
- `provenance/commands.tsv` — the command record;
- `provenance/config.resolved.yaml` — the effective configuration;
- `report/report.html` — the report layout your real result will use.

Validate the example result:

```bash
abi inspect --result-dir results/first-dry-run
abi validate-result --result-dir results/first-dry-run --allow-empty-tables
```

The reference paths in this fixture are placeholders. It is safe for planning and dry-run, but it must not be used for real biological execution.

## Example 2: Run a treatment-vs-control RNA-seq project

**Scenario:** you have four paired-end RNA-seq samples: two untreated controls and two treated samples. You want gene-level differential expression using STAR, featureCounts, and DESeq2.

This example becomes executable only after the FASTQ files, STAR index, annotation GTF, software environments, and compute resources exist on your machine.

### Step 1. Create the project files

```bash
abi init --type rnaseq_expression --outdir rnaseq-demo
```

ABI creates:

```text
rnaseq-demo/
├── config/rnaseq_expression.yaml
└── samples.tsv
```

### Step 2. Describe your samples

Edit `rnaseq-demo/samples.tsv`. For this example, use tab-separated values like these:

```text
sample_id	group	condition	platform	read1	read2
control_1	control	untreated	rna_seq	/data/rnaseq/control_1_R1.fastq.gz	/data/rnaseq/control_1_R2.fastq.gz
control_2	control	untreated	rna_seq	/data/rnaseq/control_2_R1.fastq.gz	/data/rnaseq/control_2_R2.fastq.gz
treated_1	treatment	treated	rna_seq	/data/rnaseq/treated_1_R1.fastq.gz	/data/rnaseq/treated_1_R2.fastq.gz
treated_2	treatment	treated	rna_seq	/data/rnaseq/treated_2_R1.fastq.gz	/data/rnaseq/treated_2_R2.fastq.gz
```

Replace `/data/rnaseq/...` with your real FASTQ paths. Keep every `sample_id` unique and make the `condition` values match the intended comparison.

### Step 3. Point ABI at your references

Edit the relevant sections of `rnaseq-demo/config/rnaseq_expression.yaml`:

```yaml
threads: 8

resources:
  genome_index: /data/references/hg38/star_index
  annotation_gtf: /data/references/hg38/gencode.annotation.gtf

differential_expression:
  comparison: treatment_vs_control
  design: "~ condition"
  alpha: 0.05
```

The paths above are examples. Use the STAR index and GTF built for the same reference assembly and annotation release.

If your experiment is paired or has a batch effect, change the design only after confirming that the required metadata columns exist in `samples.tsv`.

### Step 4. Review the plan

```bash
abi plan \
  --type rnaseq_expression \
  --config rnaseq-demo/config/rnaseq_expression.yaml \
  --sample-sheet rnaseq-demo/samples.tsv \
  --outdir rnaseq-demo/results/plan
```

Before continuing, check that:

- all four samples appear in `execution_plan.json`;
- the read pairs are assigned to the correct sample;
- the workflow contains QC, alignment, quantification, matrix construction, and differential expression;
- output paths point inside your intended project directory.

### Step 5. Check the machine and references

```bash
abi check \
  --type rnaseq_expression \
  --config rnaseq-demo/config/rnaseq_expression.yaml \
  --sample-sheet rnaseq-demo/samples.tsv

abi check-resources \
  --type rnaseq_expression \
  --config rnaseq-demo/config/rnaseq_expression.yaml
```

Do not continue while required inputs, executables, the STAR index, or the GTF are reported missing.

### Step 6. Create the reviewable dry-run

```bash
abi dry-run \
  --type rnaseq_expression \
  --config rnaseq-demo/config/rnaseq_expression.yaml \
  --sample-sheet rnaseq-demo/samples.tsv \
  --outdir rnaseq-demo/results/dry-run
```

Review `provenance/commands.tsv` and `provenance/resolved_inputs.tsv`. This is the last point where you can change inputs or parameters without spending analysis compute.

### Step 7. Run the analysis

```bash
abi run \
  --type rnaseq_expression \
  --config rnaseq-demo/config/rnaseq_expression.yaml \
  --sample-sheet rnaseq-demo/samples.tsv \
  --outdir rnaseq-demo/results/run-001 \
  --confirm-execution
```

`--confirm-execution` is required. Its presence means you reviewed this plugin, configuration, sample sheet, runtime, and output directory.

### Step 8. Validate and read the results

```bash
abi inspect --result-dir rnaseq-demo/results/run-001
abi validate-result \
  --result-dir rnaseq-demo/results/run-001 \
  --require-nonempty-tables
abi report \
  --type rnaseq_expression \
  --result-dir rnaseq-demo/results/run-001
```

Use the standard tables according to your question:

| What you want to know | File | Useful columns |
| --- | --- | --- |
| Did read quality pass? | `tables/qc_summary.tsv` | `sample_id`, `metric`, `value`, `unit` |
| Did reads align as expected? | `tables/alignment_summary.tsv` | `sample_id`, `metric`, `value` |
| What are the raw gene counts? | `tables/count_matrix.tsv` | `gene_id`, `sample_id`, `count` |
| What are the normalized values? | `tables/normalized_expression.tsv` | `gene_id`, `sample_id`, `normalized_count` |
| Which genes differ? | `tables/differential_expression.tsv` | `gene_id`, `log2_fold_change`, `padj`, `comparison` |

Start interpretation with `report/report.html`, then use the TSV tables for filtering and downstream analysis. Preserve the entire result directory so the report remains tied to its provenance.

## Example 3: Ask an Agent to plan the analysis

**Scenario:** you want Codex, Claude Code, or OpenCode to operate ABI, but you want to approve the exact plan before any bioinformatics tool runs.

Install the project integration:

```bash
pip install "abi-agent[mcp]"
abi agent install codex --scope project
abi agent doctor codex --scope project
```

Start a new Agent session and give it a request with explicit boundaries:

```text
Use ABI to plan differential-expression analysis for rnaseq-demo/samples.tsv.
Use rnaseq-demo/config/rnaseq_expression.yaml and write review files under
rnaseq-demo/results/agent-review. Query the plugin, run preflight and dry-run,
then summarize samples, stages, tools, resources, warnings, and output paths.
Do not execute abi_run until I approve that summary.
```

The Agent should call the plugin through `analysis_type: rnaseq_expression`, not create a new pipeline. It should stop after `abi_check` and `abi_dry_run` if resources are missing.

After you approve the summary, the Agent may use the full MCP profile and call `abi_run` with `confirm_execution: true`. See the [Agent Usage Guide](agent_usage.md) for the exact tool arguments.

## Example 4: Submit a long-running job

**Scenario:** the analysis may outlive your terminal or Agent session. Start the Job Service with subprocess workers:

```bash
abi job-service \
  --host 127.0.0.1 \
  --port 18791 \
  --workers 2 \
  --subprocess-workers
```

From another terminal, submit the reviewed RNA-seq run:

```bash
abi job submit \
  --command run \
  --analysis-type rnaseq_expression \
  --config-path rnaseq-demo/config/rnaseq_expression.yaml \
  --sample-sheet rnaseq-demo/samples.tsv \
  --outdir rnaseq-demo/results/job-001 \
  --confirm-execution
```

Use the returned job ID:

```bash
abi job status <JOB_ID>
abi job artifacts <JOB_ID>
abi job cancel <JOB_ID>
```

The service process must be able to read the same input, config, sample, environment, and resource paths used in the submitted request.

## The same lifecycle works for every plugin

Once your config and sample sheet are ready, only the analysis type and plugin-specific fields change:

```bash
abi init --type <analysis_type> --outdir my-project
abi plan --type <analysis_type> --config <config.yaml> --sample-sheet <samples.tsv>
abi check --type <analysis_type> --config <config.yaml> --sample-sheet <samples.tsv>
abi dry-run --type <analysis_type> --config <config.yaml> \
  --sample-sheet <samples.tsv> --outdir <dry-run-dir>
abi run --type <analysis_type> --config <config.yaml> \
  --sample-sheet <samples.tsv> --outdir <result-dir> --confirm-execution
abi validate-result --result-dir <result-dir> --require-nonempty-tables
abi report --type <analysis_type> --result-dir <result-dir>
```

Use `abi query --type <analysis_type> --what stages` before copying parameters from another plugin. Each workflow has different inputs, resources, tables, and biological limitations.

## When something goes wrong

| What you see | What it usually means | What to do next |
| --- | --- | --- |
| `unknown_analysis_type` | The plugin is not installed or the ID is wrong | Run `abi list-types` |
| `missing_input` | A FASTQ, assembly, sample sheet, or config path is wrong | Check `resolved_inputs.tsv` and the original path |
| `missing_resource` | A database, genome index, annotation, or model is absent | Run `abi check-resources` and configure the reported resource |
| `tool_not_found` | The registered executable is unavailable | Check the assigned Conda environment and `environments.yaml` |
| `contract_violation` | A tool ran but its output did not satisfy the declared contract | Read the failed step log and verify tool version and output files |
| Dry-run passes, run fails | Planning worked, but a real tool or runtime failed | Inspect `provenance/progress.jsonl` and `step_logs/` |

For machine-readable diagnostics, add `--output-json`. Check `error_code`, `diagnostic_hints`, and any inner `result.status`; a successful transport envelope can still contain a failed preflight result.

## Practical habits for trustworthy analyses

- Give every real run a new output directory such as `run-001` or a dated identifier.
- Keep source data read-only and avoid editing files inside a completed result directory.
- Save the config, sample sheet, ABI version, tool versions, and resource manifest with the result.
- Treat dry-run as planning evidence, not proof of biological correctness.
- Define biological acceptance criteria before interpreting a production result.
- Use a strict runtime lock when the environment must be reproduced or released.

Continue with the [Agent Usage Guide](agent_usage.md), [Job Service Guide](job_service.md), [Runtime Lock Guide](runtime_locks.md), or a plugin-specific guide when you need deeper settings.
