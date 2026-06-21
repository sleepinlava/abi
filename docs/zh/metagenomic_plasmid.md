# Metagenomic Plasmid 集成

`metagenomic_plasmid` ABI 插件使用捆绑的 `abi.autoplasm` 管线
（位于 `plugins/metagenomic_plasmid/_engine/` 中的 40 个 Python 文件）。这是 ABI 的旗舰质粒分析工作流，
支持从原始测序数据到群落分析可视化的完整分析链路。此插件取代了之前由外部 `autoplasm` 包提供质粒工作流的分离开发模式。

## 公开形态

- PyPI 包：`abi-agent`
- ABI 插件 ID：`metagenomic_plasmid`
- 内部 Python 命名空间：`abi.autoplasm`
- 兼容命令：`autoplasm`
- 工具合约：67 个（质粒管线中的所有生物信息学工具，涵盖 11 个分析类别）
- 引擎：`_engine/` 下的 40 个文件（pipeline、planner、DAG、parsers、normalize、report、statistics、skills 等）
- 管线 DAG：`pipeline_dag.yaml`（84+ 节点，5 个平台，16 张标准表）— 唯一真相来源
- 步骤合约执行：`contracts/step_contract.py` — 输出验证、实际输出解析、断言以及校验和链式追踪
- 10 个 conda 环境：qc, assembly, plasmid_detection, plasmid_binning, annotation, typing, abundance, comparative_genomics, visualization, statistics

## 完整分析链路

```
QC（fastp/FastQC/MultiQC）
  → 组装（MEGAHIT/SPAdes/Canu）
    → 组装质控（QUAST/Bandage）
      → 质粒检测（geNomad/Plasme/PlasX/Platon）
        → 质粒分箱（MetaBAT2/MaxBin2/CONCOCT/SemiBin）
          → 质粒共识（plasmid_consensus）
            → 注释（Bakta/Prodigal/AMRFinder/ISEScan）
              → 分型（PlasmidFinder/MOB-typer）
                → 丰度计算（bowtie2/coverm）
                  → 群落分析（alpha/beta 多样性 + 差异丰度）
                    → 比较基因组学（BLAST/MUMmer/MMseqs2/clinker）
                      → 可视化（pyCirclize/DNA Features Viewer/pyvis）
                        → 共现网络（FastSpar）
                          → 报告生成（Markdown + sciplot 图表）
```

## 高性能服务器运行

在配备 16 核 CPU、1TB RAM 的服务器上，metagenomic_plasmid 插件可在 16 线程下稳定运行。
核心流程（QC → 组装 → 质粒检测 → 注释 → 丰度 → 群落分析 → 可视化）已通过真实数据验证。

当前产出 16 张标准表（含 `sample_diversity`, `differential_abundance`, `network_edges` 等群落分析表），
8 张 sciplot 图表（barplot × 3, scatterplot, stacked_barplot, heatmap × 5），使用 `abi_nature` 主题 +
`colorblind_safe` 调色板。10 个数据库可用；24/24 个 default_enabled 工具已确认可正常工作。
支持通过 `config.execution.parallel` 实现样本级并行执行。

## 常用命令

```bash
abi plan --type metagenomic_plasmid \
  --config examples/config_minimal.yaml \
  --profile dry_run

abi dry-run --type metagenomic_plasmid \
  --config examples/config_minimal.yaml \
  --profile dry_run

autoplasm dry-run \
  --config examples/config_minimal.yaml \
  --profile dry_run
```

对于真实执行，请先准备仓库本地的 mamba 环境和所需数据库。Dry-run 输出是规划证据，而非外部生物信息学工具或数据库已可投入生产的证明。

## 数据库依赖

| 数据库 | 大小 | 依赖工具 | 状态 |
|--------|------|---------|:---:|
| genomad_db | 2.9 GB | geNomad | ✅ 可用 |
| bakta_db | 4.2 GB | Bakta | ✅ 可用（light DB，--skip-sorf 绕过） |
| amrfinder_db | 251 MB | AMRFinderPlus | ✅ 可用（+ BLAST 索引自动构建） |
| plasmidfinder_db | ~1 MB | PlasmidFinder | ✅ 可用 |
| mob_suite_db | 3.0 GB | MOB-suite | ✅ 可用 |
| platon_db | 55 MB | PLaton | ✅ 可用 |
| macsyfinder_db | 180 MB | MacSyFinder | ✅ 可用（pip install） |
| metaphlan_db | 34 GB | MetaPhlAn | ✅ 可用 |
| mmseqs2_db | 1.6 GB | MMseqs2 | ✅ 可用（从 mob_suite 构建） |
| kraken2_db | ~50 GB | Kraken2 | 🔄 待下载（S3） |
| blast_db | ~10 GB | BLAST+ | ❌ 未构建 |
| checkm2_db | ~100 GB | CheckM2 | ❌ 未下载（环境版本冲突） |
| gtdbtk_db | ~100 GB | GTDB-Tk | ❌ 未下载（环境版本冲突） |

**工具可用性**：24/24 个 `default_enabled: true` 工具已确认在其 conda 环境中可正常工作。
11 个 `default_enabled: false` 工具（PlasmidHostFinder、pMLST、gplas2、Recycler、scapp、
COPLA、conjscan、PLASMe、PlasX、plasmaag、plasmidhostfinder）缺少 git-clone 安装 —
这些是第三梯队（实验性/非主流）工具，用于小众分析场景。

## 资源边界

该包包含小型配置、工具合约、测试 fixtures 和示例。不包含真实数据库、mamba 环境或用户结果。

使用 `resources/` 存放本地数据库，并将这些文件保持在 git 之外。

## 验证定位

metagenomic plasmid 路线现已结构化为受约束的工作流：
`pipeline_dag.yaml` 定义节点顺序、输出、合约和断言；
通用执行器写入溯源信息并在每个外部命令成功后执行合约检查。

这尚不等同于经过充分验证的生物学工作流。当前代码库提供了验证所需的控制层，而剩余工作包括固定环境、版本化数据库、整理正/负基准数据集，以及将路线级报告连接到方法引用。详见
[工作流验证与科学证据计划](workflow_validation_zh.md)。
