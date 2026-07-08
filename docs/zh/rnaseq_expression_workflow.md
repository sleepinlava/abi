# RNA-seq 表达量工作流 (`rnaseq_expression`)

> **插件**: `rnaseq_expression`
> **状态**: 活跃 (2026-06-18)

## 工作流

```text
FASTQ
  → fastp (QC)
  → STAR / HISAT2 (比对)
  → featureCounts (定量)
  → DESeq2 (差异表达)
  → 富集分析 (clusterProfiler, 可选)
  → 报告 + 图表
```

## 工具链

| 阶段 | 默认工具 | 替代方案 | 类别 |
| --- | --- | --- | --- |
| QC | fastp | FastQC, MultiQC | qc |
| 比对 | STAR | HISAT2 | alignment |
| 定量 | featureCounts | Salmon, Kallisto | expression |
| 差异表达 | DESeq2 | edgeR | differential_expression |
| 富集分析 | clusterProfiler | gseapy | enrichment |

## 标准表格

| 表格 | 内容 | 必需 |
| --- | --- | --- |
| `qc_summary` | Reads QC 指标 (总 reads, Q30, GC) | 是 |
| `alignment_summary` | 比对率, 唯一/多重比对 reads | 是 |
| `gene_expression` | 每个基因的原始计数 | 是 |
| `normalized_expression` | DESeq2 中位数比率归一化计数 | 是 |
| `differential_expression` | 每个基因的 log2FC, p-value, padj | 是 |
| `enrichment_results` | GO/KEGG 通路富集 | 否 |

## 图表

| 图表 | 文件 | 必需 |
| --- | --- | --- |
| QC reads 计数 | `figures/qc_read_counts.png` | 是 |
| 比对率 | `figures/mapping_rate.png` | 是 |
| PCA 表达量 | `figures/pca_expression.png` | 是 |
| 火山图 | `figures/volcano_deg.png` | 是 |
| MA 图 | `figures/ma_plot.png` | 否 |
| Top DEG 热图 | `figures/top_deg_heatmap.png` | 否 |
| 富集分析点图 | `figures/enrichment_dotplot.png` | 否 |

## 快速开始

```bash
# 计划
abi plan --type rnaseq_expression \
  --config data/examples/rnaseq_expression/config.yaml \
  --outdir results/rnaseq_example

# 干运行
abi dry-run --type rnaseq_expression \
  --config data/examples/rnaseq_expression/config.yaml \
  --outdir results/rnaseq_example

# 真实执行 (需要 STAR 索引 + GTF 注释)
abi run --type rnaseq_expression \
  --config data/examples/rnaseq_expression/config.yaml \
  --outdir results/rnaseq_example \
  --confirm-execution

# 报告
abi report --type rnaseq_expression \
  --result-dir results/rnaseq_example
```

## 配置

### 最小配置

```yaml
project_name: "rnaseq_expression_run"
mode: dry_run
threads: 4
outdir: results/rnaseq_expression
input:
  sample_sheet: sample_sheet.tsv
alignment:
  tool: star
resources:
  genome_index: /path/to/star_index
  annotation_gtf: /path/to/annotations.gtf
differential_expression:
  comparison: "treatment_vs_control"
  alpha: 0.05
```

### 样本表格式

```text
sample_id	group	condition	platform	read1	read2
sample1	treatment	treated	rna_seq	raw/s1_R1.fastq.gz	raw/s1_R2.fastq.gz
sample2	treatment	treated	rna_seq	raw/s2_R1.fastq.gz	raw/s2_R2.fastq.gz
sample3	control	untreated	rna_seq	raw/s3_R1.fastq.gz	raw/s3_R2.fastq.gz
sample4	control	untreated	rna_seq	raw/s4_R1.fastq.gz	raw/s4_R2.fastq.gz
```

必需列: `sample_id`, `read1`, `read2`。可选: `group`, `condition`, `platform`。

## 资源需求

真实执行需要：

1. **STAR 基因组索引** — 通过 `STAR --runMode genomeGenerate` 构建。
2. **GTF 注释** — GENCODE、Ensembl 或 RefSeq 格式。
3. **R + DESeq2** — `BiocManager::install("DESeq2")`。
4. **可选: R + clusterProfiler** — `BiocManager::install("clusterProfiler")`。

所有资源在真实运行后出现在 `provenance/resource_manifest.json` 中。

## 已知局限性

详见 `plugins/rnaseq_expression/limitations.yaml`。要点：

1. RNA-seq 测量的是转录本丰度，而非蛋白质水平。
2. 比对率取决于参考基因组的完整性。
3. DESeq2 假设大多数基因不差异表达。
4. 低表达基因具有膨胀的 FDR。
5. 参考基因组/注释版本会影响结果。

## 架构说明

此插件是**内联实现**（没有 `_engine/` 子包），遵循与
`metatranscriptomics` 相同的模式。解析函数存在于插件模块
本身，而非单独的 `parsers.py` 文件中。

### 插件生命周期

```
load_config()  →  build_plan()  →  run (ExternalExecutor)
  →  parse_outputs() (按步骤)  →  write_report()
```

### 解析器分发

`parse_outputs(tool_id, output_dir, sample_id)` 分发：
- `fastp` → `_parse_fastp()` → `qc_summary`
- `star` → `_parse_star()` → `alignment_summary`
- `featurecounts` → `_parse_featurecounts()` → `gene_expression`
- `deseq2` → `_parse_deseq2()` + `_parse_deseq2_normalized()` → `differential_expression` + `normalized_expression`
