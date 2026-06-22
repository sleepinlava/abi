# 宏基因组质粒分析

`metagenomic_plasmid` 是 ABI 面向 Illumina、ONT、PacBio HiFi、二代+三代
混合数据和 assembly-only 项目的平台感知质粒工作流。规范拓扑位于
`plugins/metagenomic_plasmid/pipeline_dag.yaml`；Python 引擎负责解析逐样本输入、
条件节点、输出路径、provenance 和标准结果表。

## 默认路径

### Illumina

```text
FASTQ → fastp → MultiQC → 可选 Bowtie2 去宿主 → MEGAHIT → QUAST
      → geNomad → 环状/结构判定 → PlasmidFinder + MOB-typer
      → Bakta + AMRFinderPlus + ISEScan + IntegronFinder
      → MMseqs2 catalog → Bowtie2 + samtools + CoverM → 报告
```

### ONT

```text
FASTQ/POD5/BAM → 可选 Dorado 或 BAM 转 FASTQ → NanoPlot → Filtlong
               → 可选 minimap2 去宿主 → metaFlye
               → 可选 Medaka → QUAST → 共用下游路径
```

### PacBio HiFi

```text
FASTQ/BAM → 可选 BAM 转 FASTQ → NanoPlot + HiFiAdapterFilt
          → 可选 minimap2 去宿主 → hifiasm-meta → QUAST
          → 共用下游路径
```

### 二代+三代混合数据

```text
Illumina + ONT/HiFi → fastp + NanoPlot/Filtlong
                    → 按平台可选去宿主
                    → OPERA-MS → QUAST → 共用下游路径
```

`hybridSPAdes` 和 `metaSPAdes` 是显式替代方案。选择替代 assembler 时会替换平台
默认工具，不会隐式双跑多个 assembler。

## 工具策略

默认主路径保持收敛：

- geNomad 是主质粒检测工具；Platon、PLASMe、PlasX 只提供可选 consensus 证据。
  默认加权投票中 geNomad 权重为 0.60，三个辅助检测器合计为 0.40，因此辅助工具不能在
  geNomad 无支持时单独产生阳性质粒判定。
- PlasmidFinder 和 MOB-typer 是默认分型工具。
- AMRFinderPlus 是默认 AMR 路径；ABRicate 和 RGI 为可选补充。
- ISEScan 和 IntegronFinder 默认启用；eggNOG-mapper 为可选项。
- MMseqs2 用于跨样本 catalog 聚类；BLAST、MUMmer、clinker 只用于代表序列验证或展示。
- MetaBAT2、MaxBin2、CONCOCT、SemiBin 位于可选 MAG 宿主基因组分支，不属于质粒分箱。
- BWA、KneadData、Hi-C 占位节点、pMLST 和批量 Bandage 节点已从工作流 DAG 移除。

FastQC 默认关闭，因为 fastp 已输出 HTML/JSON QC 报告；只有发表附件或 QC 审计需要时
再启用。MultiQC 保持开启，用于项目级汇总。

## 跨样本条件节点

ABI 根据真实 sample sheet 计算是否满足运行条件：

| 模块 | 默认门槛 |
|---|---|
| alpha/beta 多样性 | 至少 3 个具有 reads 丰度的样本 |
| 差异丰度 | 至少 2 组，且每组至少 3 个有效重复 |
| FastSpar 网络 | 至少 20 个具有 reads 丰度的样本 |

不满足门槛时不会启动节点，原因会写入 `tables/analysis_status.tsv` 和序列化执行计划。
assembly-only 行不会被计作丰度分析重复。

满足门槛的差异分析默认使用 DESeq2 和原始 mapped counts。缺少原始 counts 时，会把
取整 coverage 明确标记为 count proxy。`internal_effect_size` 仅作为描述性回退，不输出
推断性 p value。

## 稳定结果契约

执行前会为每张声明表创建表头。因此合法的零命中运行会产生空 TSV，而不是缺文件。
核心公开结果包括：

- `sample_qc.tsv`、`assembly_qc.tsv`
- `plasmid_predictions.tsv`、`plasmid_consensus.tsv`、
  `plasmid_structure.tsv`、`plasmid_catalog.tsv`
- `plasmid_abundance.tsv`、`plasmid_annotation.tsv`、`amr_genes.tsv`、
  `mge_elements.tsv`、`plasmid_typing.tsv`
- `host_profile.tsv`、`host_plasmid_links.tsv`
- `differential_plasmids.tsv`、`network_edges.tsv`、`network_nodes.tsv`
- `analysis_status.tsv`

旧版标准化表仍保留，用于兼容已有消费者。

## 可复现性

每次运行都会写出 `provenance/resource_manifest.json`，并保留兼容文件
`provenance/resources.json`。数据库条目包含资源 ID、路径、版本、日期、来源、状态和
checksum。普通文件使用内容 SHA-256；数据库目录使用有上限的目录清单指纹，除非配置中
提供了上游发布方 checksum。

工具版本、解析后的输入、命令、日志和最终配置分别记录。以 `NOT_CONFIGURED` 结尾的
占位路径会明确标记为未配置；dry-run 通过不能证明外部工具或数据库已经安装。

## 常用命令

```bash
abi plan --type metagenomic_plasmid \
  --config examples/config_minimal.yaml --profile dry_run

abi dry-run --type metagenomic_plasmid \
  --config examples/config_minimal.yaml --profile dry_run

abi check-resources --type metagenomic_plasmid
```

生产运行前应填写数据库路径和版本、验证 sample sheet，并先执行资源与工作流检查。
