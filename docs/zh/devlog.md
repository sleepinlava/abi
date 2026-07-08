# ABI 开发日志

> **注意**：完整英文开发日志请见 [`docs/en/devlog.md`](../en/devlog.md)（~1200 行）。
> 本文档为中文摘要索引，列出关键版本和里程碑条目。

## 2026-07-07 — v1.5.3: 发布质量门禁与 DAG 修复

- 新增 `scripts/release_check.sh` 统一发布验证入口
- 新增 paper-evaluation 任务包（基准任务定义、指标 schema、双语评估笔记）
- 合约 lint 扩展至 DAG 模板参数检查
- 修复 DAG `source: config.*` 输入解析、FASTA 导出、Matplotlib boxplot 兼容性

## 2026-07-09 — v1.5.4-pre: RefSeq 质粒验证与 Bug 修复

- **Assembly 模式全流程验证**：3 个 RefSeq 质粒（NC_002127.1 3.3kb、NC_011977.1 7.6kb、NC_002483.1 99kb F 质粒）在 AutoDL 128 核云服务器上运行 39/39 DAG 步骤全部通过
- **Bug 修复**：修复 cross-sample path propagation（executor 向所有样本泄漏首个样本的 assembly 路径）、platon `--db` 标志缺失、genomad 解析器重复读取结果
- **Consensus table 修复**：`plasmid_consensus.tsv` 在 `abi run` 流程中始终为空 — 根因是 `write_consensus_table()` 仅在 `PipelineRunner` 路径中调用，`ABIExecutor`（`abi run` 使用）从未调用。在 `write_report()` 中增加调用，并在 `ExecutionPlan` 中新增 `plasmid_strategy` 字段
- **WGS bacteria 验证**：合成 MG1655 样本完成 fastp → SPAdes → Prokka → MLST（ST10 正确）→ AMRFinderPlus（0 获得性 / 11 固有）全流程
- **SciPlot 图表**：3/9 figure specs 成功渲染（assembly_metrics_by_sample、plasmid_length_distribution、plasmid_score_vs_length）；barplot 新增 auto-count 模式
- **CLI 新增**：`abi --version` / `abi -V` 显示版本号

## 2026-06-23 — v1.5.1-1.5.2: 发布身份与规划器清理

- `pyproject.toml` `project.version` 成为单一版本来源
- 移除旧手写质粒规划器，全部 7 个插件使用声明式 `pipeline_dag.yaml`
- 覆盖率门禁提升至 75%，加入按模块风险分级门禁
- 修复 wheel 安装配置发现、PBS 任务 ID 验证、资源选择过滤等

## 2026-06-23 — v1.5.0: HPC 运行时 + 新插件

- HPC 运行时全面重构（SLURM/PBS）
- 新增 `easymetagenome`（P0 猎枪宏基因组）和 `viral_viwrap`（ViWrap 包装）插件
- SciPlot 扩展至 15 种生物图形类型
- `environments.yaml` 统一 tool→env 声明，扩展多平台支持

## 2026-06-21 — 三维工程修复：环境、图表、并行执行

- **环境修复**：metaPhlAn/kraken2 `autoplasm-stats` → `stats`，新增 mmseqs2 ResourceSpec
- **图表迁移**：旧 FigureEngine → abi-sciplot（8 张科学图表，PDF+SVG+PNG）
- **并行执行**：`GenericABIExecutor` 支持 ThreadPoolExecutor 样本级并行
- **CoverM 解析器修复**：`_get_contains()` 处理动态列名

## 2026-06-21 — 真实流水线执行：Bug 修复 + 组装流水线验证

- 对 RefSeq 质粒数据运行 metagenomic_plasmid（assembly 平台）
- 修复 5 个 bug：AMRFinderPlus makeblastdb、Bakta 输出目录冲突、geNomad 路径合约等
- 3 个样本全部 19/19 步骤通过

## 2026-06-20 — v1.4.0: 科学图形编译器升级

- SciPlot 从 9 种图形扩展至 15 种（PCoA、火山图、堆叠柱状图、热图、系统发育热图等）
- 新增 plotnine（ggplot2 语法）+ seaborn 后端
- 12 个 DAG `enable_condition` 修复，geNomad 解析器通配符修复
- 5 个插件端到端验证（4/5 零失败）

## 2026-06-18 — Direction E: Token 优化 + 基准数据

- v1.3.0：计划摘要（~5K→250 tokens）、`abi query` 轻量查询、错误信封无 traceback 模式
- 全部 5 个插件完成基准数据集（`data/benchmarks/<plugin>/`）

## 2026-06-18 — ABI "uv-ification": 声明式 DAG 规划器

- `dag_planner.py`（~630 行）— UniversalDAG，从 `pipeline_dag.yaml` 声明式生成执行计划
- `tsv_mapping.py`（~230 行）— YAML 驱动 TSV 列映射，替换 ~14 个手写解析器
- 全部 5 个插件接入 `use_dag` 开关和 `TSVMapper`

## 2026-06-18 — Direction D-F: 基准数据集 + Docker + DAG 迁移

- Direction D：基准数据集 + 端到端真实执行测试
- Direction C：全部 5 个插件 Docker 镜像 + docker-compose
- Direction F：质粒 DAG 从 PipelineDAG 迁移至 UniversalDAG

## 2026-06-18 — Direction A-B: 扩增子多样性 + 工程基础设施

- Direction A：扩增子多样性脚本（781 行纯 Python）、AMRFinderPlus 解析器修复、系统发育树步骤
- Direction B：Sphinx API 文档 + ReadTheDocs、README 徽章、pre-commit 版本升级

---

更多历史详情请参阅[完整英文开发日志](../en/devlog.md)。
