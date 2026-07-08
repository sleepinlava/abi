# ABI HPC 开发指南

> **状态**: 活跃维护 (2026-06-18)
> **目标读者**: 在 HPC 集群上部署 ABI 流水线的插件开发者

## 概述

ABI 流水线支持三种运行时：

```text
运行时
  ├── local        — 单机模式，基于子进程（默认）
  ├── nextflow     — 通过 ``abi export-nextflow`` 导出为 DSL2 流水线
  └── hpc          — 原生 Slurm 作业调度；兼容 PBS 脚本与依赖提交
```

## Local 运行时（当前默认）

Phase 2-5 的所有开发均使用 local 运行时。工具通过 ``GenericCommandSkill``
以子进程方式调用，并通过 conda 环境进行隔离。

### 各工具的资源需求

| 工具 | CPU | 内存 | 磁盘 I/O | 典型运行时间 |
| --- | --- | --- | --- | --- |
| fastp | 1-4 | 2 GB | 读密集型 | 5-15 分钟/样本 |
| STAR | 8-16 | 32 GB | 重度 | 30-60 分钟/样本 |
| featureCounts | 1-4 | 4 GB | 轻度 | 2-5 分钟/样本 |
| DESeq2 (R) | 1 | 4 GB | 轻度 | 1-5 分钟 |
| SPAdes | 8-16 | 64 GB | 重度 | 1-4 小时/样本 |
| Prokka | 4-8 | 8 GB | 中度 | 10-30 分钟/样本 |
| MLST | 1 | 1 GB | 轻度 | < 1 分钟/样本 |
| AMRFinderPlus | 4-8 | 8 GB | 中度 | 5-15 分钟/样本 |
| cutadapt | 1-4 | 2 GB | 读密集型 | 5-15 分钟/样本 |
| vsearch | 1-4 | 8 GB | 中度 | 10-30 分钟/步骤 |
| MetaPhlAn | 4-8 | 16 GB | 中度 | 20-60 分钟/样本 |
| HUMAnN | 8-16 | 32 GB | 重度 | 1-6 小时/样本 |

## HPC 执行策略

### Nextflow 导出

```bash
abi export-nextflow --type rnaseq_expression \
  --config config.yaml \
  --outdir nextflow_pipeline/
```

生成一个自包含的 Nextflow DSL2 流水线，可直接提交到 SLURM/PBS 集群。
每个工具转换为一个拥有独立资源声明的 Nextflow process。

### 原生 HPC 提交

ABI 的 `hpc` 运行时以 Slurm 为生产目标，并保留 PBS 脚本与依赖提交兼容性。
每个 worker 步骤生成独立 JSON 载荷和批处理脚本；driver 预检步骤在首次提交前同步执行。

```bash
# 提交前预检
abi check --type easymetagenome --config config.yaml --engine hpc

# 正式提交
abi run --type easymetagenome --config config.yaml --engine hpc \
  --scheduler slurm --partition compute --account project \
  --hpc-timeout 604800 --confirm-execution
```

Slurm 提交使用真实 `afterok` 作业依赖。运行时通过 `squeue` 监控活动作业，并用
`sacct` 获取已结束作业状态；超时作业会调用 `scancel`。每个作业以原子方式写入
`provenance/step_results/`，汇总阶段生成标准表、命令记录和 `hpc_jobs.json`。

`--resume` 仅复用非空且 SHA256 校验与 `provenance/checksums.json` 一致的输出。

生产环境以 Slurm 为主要目标；PBS 保留兼容的指令格式和依赖提交能力，但验证
覆盖面较小。

### 插件开发者的关键 HPC 注意事项

1. **工具合约中声明资源需求**：每个 ``tool_contracts/*.yaml`` 应包含符合实际的
   ``resources:`` 块（cpu、memory、walltime），以便 HPC 调度器正确分配资源。

2. **数据库卷管理**：引用大型数据库的插件（如 Kraken2、SILVA、GTDB、MetaPhlAn、
   HUMAnN）应通过 ``abi-plugin.yaml`` 中的 resources 节来声明数据库路径，而非硬编码。

3. **断点/重启机制**：``provenance/checksums.json`` 中的校验链支持失败后恢复。
   失败的步骤可以重新运行，而无需重新计算上游步骤。

4. **多样本并行执行**：local 运行时已通过 ``--workers N`` 支持节点内并行。
   HPC 执行通过作业数组进一步扩展为跨节点并行。

## 数据库管理

### 资源清单

每次真实执行都会生成 ``provenance/resource_manifest.json``：

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

### 数据库目录约定

```text
resources/
  genomad_db/           # geNomad 标记数据库
  bakta_db/             # Bakta 注释数据库
  amrfinder_db/         # NCBI AMRFinderPlus 数据库
  kraken2_db/           # Kraken2/Bracken 索引
  silva_138/            # SILVA 16S 分类数据库
  gtdb_r207/            # GTDB 分类数据库
  metaphlan_db/         # MetaPhlAn 标记数据库
  humann_db/            # HUMAnN ChocoPhlAn + UniRef
  star_index_hg38/      # 人类 GRCh38 STAR 索引
  star_index_ecoli/     # 大肠杆菌 STAR 索引
```

### 下载与校验

```bash
# 示例：下载并校验数据库
abi setup-resources --type metagenomic_plasmid --confirm
# → 下载数据库，计算校验和，写入 resource_manifest.json
```

## 环境管理

共享 Conda 根目录由 `--mamba-root` 或环境变量 `ABI_MAMBA_ROOT` 指定。
插件工具通过 `environments.yaml` 中的 tool→env 分配来解析环境。

### 各分析类型的 Conda 环境

| 插件 | Conda 环境 | 关键依赖 |
| --- | --- | --- |
| metagenomic_plasmid | abi-qc, abi-asm, abi-annot, abi-amr | fastp, megahit, spades, bakta, prokka, amrfinderplus |
| easymetagenome | easymetagenome | fastp, megahit, quast, prokka, kraken2, metaphlan, humann |
| viral_viwrap | viral_viwrap | ViWrap 1.3.1 工具链 |
| rnaseq_expression | rnaseq | fastp, star, featurecounts, r-deseq2 |
| wgs_bacteria | rnaseq | fastp, spades, prokka, mlst, amrfinderplus |
| amplicon_16s | amplicon | cutadapt, vsearch, python-diversity |
| metatranscriptomics | abi-qc, abi-stats | fastp, star, featurecounts |

> **注意**：ViWrap 的环境集合继续通过 ``resources.conda_env_dir`` 指定。

### 容器支持

除了 conda 环境外，还可以使用 Docker/Singularity 镜像：

```yaml
execution:
  container: docker://biocontainers/fastp:v0.23.2
```

## 性能基准

### 小规模测试数据集（Phase 6 目标，local 运行时 16 核）

| 插件 | 输入 | 工具链 | 总耗时 |
| --- | --- | --- | --- |
| rnaseq_expression | 4 样本, 1M reads/样本 | fastp→STAR→featureCounts→DESeq2 | ~2 小时 |
| wgs_bacteria | 2 菌株, 1M reads/样本 | fastp→SPAdes→Prokka→MLST→AMRFinderPlus | ~6 小时 |
| amplicon_16s | 4 样本, 100K reads/样本 | cutadapt→vsearch(×3)→taxonomy→diversity | ~1 小时 |
| metatranscriptomics | 4 样本, 5M reads/样本 | fastp→STAR→featureCounts | ~3 小时 |

### 生产数据集预估（HPC，32 核 × 10 节点）

| 插件 | 样本数 | reads/样本 | 预估耗时 |
| --- | --- | --- | --- |
| rnaseq_expression | 100 | 50M | ~6 小时（STAR 占主导） |
| wgs_bacteria | 500 | 5M | ~12 小时（SPAdes 占主导） |
| amplicon_16s | 200 | 200K | ~4 小时（vsearch 占主导） |
| metatranscriptomics | 50 | 100M | ~24 小时（HUMAnN 占主导） |

## 安全注意事项

1. **路径遍历防护**：所有插件路径解析均通过 ``abi._shared._resolve_path``，
   该函数会验证路径是否被限定在项目目录内（B25 修复）。

2. **命令注入防护**：``SafeFormatDict`` 可防止通过模板参数值注入恶意命令。

3. **网络隔离**：在工具合约中标记为 ``network: false`` 的工具在运行期间不能访问
   外部网络资源。

4. **数据库完整性**：带有 SHA256 校验和的资源清单确保数据库文件未被篡改。
