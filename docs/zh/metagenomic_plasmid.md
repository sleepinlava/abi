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
3 张 sciplot 图表。剩余的 48 个步骤大多因数据库未下载而被门控跳过 — 工具代码本身已就绪。

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
| genomad_db | ~2GB | genomad | ✅ 可用 |
| bakta_db | ~40GB | bakta | ✅ 可用 |
| amrfinder_db | ~2GB | amrfinderplus | ✅ 已修复 — `-d {database}` 参数 + DAG 链路 (2026-06-20) |
| plasmidfinder_db | ~100MB | plasmidfinder | ✅ 可用 |
| mob_suite_db | ~200MB | mob_typer | ❌ 未下载 |
| kraken2_db | ~50GB | kraken2 | ❌ 未下载 |
| metaphlan_db | ~3GB | metaphlan | ❌ 未下载 |
| checkm2_db | ~3GB | checkm2 | ❌ 未下载 |
| gtdbtk_db | ~30GB | gtdbtk | ❌ 未下载 |

## 资源边界

该包包含小型配置、工具合约、测试 fixtures 和示例。不包含真实数据库、mamba 环境或用户结果。

使用 `resources/` 存放本地数据库，并将这些文件保持在 git 之外。

## 验证定位

metagenomic plasmid 路线现已结构化为受约束的工作流：
`pipeline_dag.yaml` 定义节点顺序、输出、合约和断言；
通用执行器写入溯源信息并在每个外部命令成功后执行合约检查。

这尚不等同于经过充分验证的生物学工作流。当前代码库提供了验证所需的控制层，而剩余工作包括固定环境、版本化数据库、整理正/负基准数据集，以及将路线级报告连接到方法引用。详见
[工作流验证与科学证据计划](workflow_validation_zh.md)。
