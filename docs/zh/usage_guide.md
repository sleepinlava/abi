# 使用 ABI：从生物学问题到分析结果

这份指南面向准备实际运行分析的使用者，不要求先理解 ABI 内部实现。找到最接近你的场景，直接从对应示例开始。

## 我应该从哪里开始？

| 你的情况 | 从这里开始 |
| --- | --- |
| “我想先看看 ABI 会生成什么。” | 示例 1：不安装分析工具也能体验 ABI |
| “我已经有测序数据，准备建立项目。” | 示例 2：处理组与对照组 RNA-seq |
| “我希望由 AI Agent 操作 ABI。” | 示例 3：让 Agent 规划分析 |
| “我的分析可能运行数小时。” | 示例 4：提交队列任务 |
| “命令运行失败了。” | “遇到问题时怎么办” |

## 根据生物学问题选择分析

不必先挑选单个工具。先选择期望得到的生物学结果；插件负责定义工作流，ABI 会在执行前展示所用工具。

| 你的生物学问题 | 输入 | 使用 `--type` | 主要结果 |
| --- | --- | --- | --- |
| 16S 样本中有哪些微生物？ | 双端 16S reads | `amplicon_16s` | ASV、物种注释、多样性 |
| 两个 RNA-seq 条件间哪些基因发生变化？ | 双端 RNA-seq reads | `rnaseq_expression` | 计数、标准化表达、差异表达 |
| 细菌分离株的型别和耐药特征是什么？ | 分离株 WGS reads | `wgs_bacteria` | 组装、注释、MLST、耐药结果 |
| 宏转录组中有哪些基因正在表达？ | 宏转录组 reads | `metatranscriptomics` | 质控、比对统计、基因计数 |
| shotgun 宏基因组中有哪些物种和功能？ | shotgun reads | `easymetagenome` | 物种和功能丰度 |
| 宏基因组中有哪些病毒及其宿主？ | 宏基因组 reads | `viral_viwrap` | 病毒 bin、质量、分类、宿主 |
| 宏基因组中有哪些质粒？ | reads 或组装结果 | `metagenomic_plasmid` | 质粒共识、分型、宿主、基因、丰度 |

先检查当前机器安装了哪些插件：

```bash
abi list-types
abi query --type rnaseq_expression --what stages
abi query --type rnaseq_expression --what tools
```

## 示例 1：不安装分析工具也能体验 ABI

**目标：** 在不安装 STAR、不下载参考基因组的情况下，查看真实执行计划、溯源包、标准表格和报告预览。

**你需要：** 当前仓库的源码副本和已经安装的 `abi-agent`。本示例不会执行生物信息学分析工具。

在仓库根目录运行：

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

第一条命令应报告一个三步计划，第二条命令会生成：

```text
results/first-dry-run/
├── execution_plan.json
├── provenance/
├── tables/
└── report/
```

建议先打开这些文件：

- `execution_plan.json`：ABI 选择的命令、输入、输出和步骤顺序；
- `provenance/commands.tsv`：命令记录；
- `provenance/config.resolved.yaml`：最终生效的配置；
- `report/report.html`：真实结果将使用的报告布局。

验证示例结果：

```bash
abi inspect --result-dir results/first-dry-run
abi validate-result --result-dir results/first-dry-run --allow-empty-tables
```

该 fixture 中的参考资源路径是占位符，只适用于规划和 dry-run，不能用于真实生物学执行。

## 示例 2：运行处理组与对照组 RNA-seq 项目

**场景：** 你有 4 个双端 RNA-seq 样本，包括 2 个未处理对照和 2 个处理样本，希望使用 STAR、featureCounts 和 DESeq2 进行基因差异表达分析。

只有 FASTQ、STAR 索引、注释 GTF、软件环境和计算资源都已准备好，本示例才能进入真实执行。

### 第 1 步：创建项目文件

```bash
abi init --type rnaseq_expression --outdir rnaseq-demo
```

ABI 会创建：

```text
rnaseq-demo/
├── config/rnaseq_expression.yaml
└── samples.tsv
```

### 第 2 步：描述样本

编辑 `rnaseq-demo/samples.tsv`。本示例使用以下制表符分隔内容：

```text
sample_id	group	condition	platform	read1	read2
control_1	control	untreated	rna_seq	/data/rnaseq/control_1_R1.fastq.gz	/data/rnaseq/control_1_R2.fastq.gz
control_2	control	untreated	rna_seq	/data/rnaseq/control_2_R1.fastq.gz	/data/rnaseq/control_2_R2.fastq.gz
treated_1	treatment	treated	rna_seq	/data/rnaseq/treated_1_R1.fastq.gz	/data/rnaseq/treated_1_R2.fastq.gz
treated_2	treatment	treated	rna_seq	/data/rnaseq/treated_2_R1.fastq.gz	/data/rnaseq/treated_2_R2.fastq.gz
```

把 `/data/rnaseq/...` 替换为真实 FASTQ 路径。每个 `sample_id` 必须唯一，`condition` 的取值必须与计划比较的条件一致。

### 第 3 步：配置参考资源

编辑 `rnaseq-demo/config/rnaseq_expression.yaml` 中的相关部分：

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

以上路径只是示例。STAR 索引和 GTF 必须来自同一套参考基因组与注释版本。

如果实验存在配对设计或批次效应，只有在 `samples.tsv` 包含对应元数据列后才能修改 design。

### 第 4 步：审查执行计划

```bash
abi plan \
  --type rnaseq_expression \
  --config rnaseq-demo/config/rnaseq_expression.yaml \
  --sample-sheet rnaseq-demo/samples.tsv \
  --outdir rnaseq-demo/results/plan
```

继续之前，请确认：

- `execution_plan.json` 包含全部 4 个样本；
- 双端 reads 分配到了正确样本；
- 工作流包含质控、比对、定量、计数矩阵和差异表达；
- 输出路径位于预期的项目目录中。

### 第 5 步：检查机器和参考资源

```bash
abi check \
  --type rnaseq_expression \
  --config rnaseq-demo/config/rnaseq_expression.yaml \
  --sample-sheet rnaseq-demo/samples.tsv

abi check-resources \
  --type rnaseq_expression \
  --config rnaseq-demo/config/rnaseq_expression.yaml
```

如果必需输入、可执行程序、STAR 索引或 GTF 仍显示缺失，不要继续执行。

### 第 6 步：生成可审查的 dry-run

```bash
abi dry-run \
  --type rnaseq_expression \
  --config rnaseq-demo/config/rnaseq_expression.yaml \
  --sample-sheet rnaseq-demo/samples.tsv \
  --outdir rnaseq-demo/results/dry-run
```

检查 `provenance/commands.tsv` 和 `provenance/resolved_inputs.tsv`。这是消耗分析计算资源之前，修改输入或参数的最后检查点。

### 第 7 步：执行分析

```bash
abi run \
  --type rnaseq_expression \
  --config rnaseq-demo/config/rnaseq_expression.yaml \
  --sample-sheet rnaseq-demo/samples.tsv \
  --outdir rnaseq-demo/results/run-001 \
  --confirm-execution
```

`--confirm-execution` 是必需参数，表示你已经审查了本次使用的插件、配置、样本表、运行环境和输出目录。

### 第 8 步：验证并阅读结果

```bash
abi inspect --result-dir rnaseq-demo/results/run-001
abi validate-result \
  --result-dir rnaseq-demo/results/run-001 \
  --require-nonempty-tables
abi report \
  --type rnaseq_expression \
  --result-dir rnaseq-demo/results/run-001
```

根据问题选择标准表格：

| 你想了解什么 | 文件 | 常用列 |
| --- | --- | --- |
| reads 质量是否合格？ | `tables/qc_summary.tsv` | `sample_id`、`metric`、`value`、`unit` |
| reads 比对是否符合预期？ | `tables/alignment_summary.tsv` | `sample_id`、`metric`、`value` |
| 原始基因计数是多少？ | `tables/count_matrix.tsv` | `gene_id`、`sample_id`、`count` |
| 标准化表达值是多少？ | `tables/normalized_expression.tsv` | `gene_id`、`sample_id`、`normalized_count` |
| 哪些基因存在差异？ | `tables/differential_expression.tsv` | `gene_id`、`log2_fold_change`、`padj`、`comparison` |

先从 `report/report.html` 开始解释，再使用 TSV 进行筛选和下游分析。保留完整结果目录，使报告始终与对应溯源记录绑定。

## 示例 3：让 Agent 规划分析

**场景：** 你希望 Codex、Claude Code 或 OpenCode 操作 ABI，但任何生物信息学工具运行前都必须由你审查并批准计划。

安装项目级集成：

```bash
pip install "abi-agent[mcp]"
abi agent install codex --scope project
abi agent doctor codex --scope project
```

开启新的 Agent 会话，并给出边界明确的请求：

```text
使用 ABI 为 rnaseq-demo/samples.tsv 规划差异表达分析。
使用 rnaseq-demo/config/rnaseq_expression.yaml，并把审查文件写入
rnaseq-demo/results/agent-review。查询插件，运行预检和 dry-run，
然后汇总样本、阶段、工具、资源、警告和输出路径。
在我批准摘要之前，不要执行 abi_run。
```

Agent 应通过 `analysis_type: rnaseq_expression` 调用已有插件，而不是重新生成一套管线。资源缺失时，应在 `abi_check` 或 `abi_dry_run` 后停止。

你批准摘要后，Agent 才能使用 full MCP profile，并传入 `confirm_execution: true` 调用 `abi_run`。准确工具参数详见 [Agent 使用指南](agent_usage.md)。

## 示例 4：提交长时间运行的任务

**场景：** 分析可能超过终端或 Agent 会话的生命周期。先使用子进程 worker 启动 Job Service：

```bash
abi job-service \
  --host 127.0.0.1 \
  --port 18791 \
  --workers 2 \
  --subprocess-workers
```

在另一个终端提交已经审查的 RNA-seq 任务：

```bash
abi job submit \
  --command run \
  --analysis-type rnaseq_expression \
  --config-path rnaseq-demo/config/rnaseq_expression.yaml \
  --sample-sheet rnaseq-demo/samples.tsv \
  --outdir rnaseq-demo/results/job-001 \
  --confirm-execution
```

使用返回的 Job ID：

```bash
abi job status <JOB_ID>
abi job artifacts <JOB_ID>
abi job cancel <JOB_ID>
```

Job Service 进程必须能读取请求中使用的输入、配置、样本表、软件环境和资源路径。

## 所有插件都使用相同生命周期

配置和样本表准备完成后，只有分析类型和插件特有字段会变化：

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

从另一个插件复制参数前，先运行 `abi query --type <analysis_type> --what stages`。每个工作流的输入、资源、表格和生物学局限都不同。

## 遇到问题时怎么办

| 你看到的错误 | 常见原因 | 下一步 |
| --- | --- | --- |
| `unknown_analysis_type` | 插件未安装或 ID 错误 | 运行 `abi list-types` |
| `missing_input` | FASTQ、组装、样本表或配置路径错误 | 检查 `resolved_inputs.tsv` 和原始路径 |
| `missing_resource` | 缺少数据库、基因组索引、注释或模型 | 运行 `abi check-resources` 并配置报告的资源 |
| `tool_not_found` | 已注册可执行程序不可用 | 检查对应 Conda 环境和 `environments.yaml` |
| `contract_violation` | 工具已运行，但输出不满足声明契约 | 阅读失败步骤日志并核对工具版本和输出文件 |
| dry-run 成功、run 失败 | 规划有效，但真实工具或运行环境失败 | 检查 `provenance/progress.jsonl` 和 `step_logs/` |

需要机器可读诊断时增加 `--output-json`。同时检查 `error_code`、`diagnostic_hints` 和内部 `result.status`；传输信封为 success 时，预检结果仍可能失败。

## 让分析更可信的实用习惯

- 每次真实执行使用新的输出目录，例如 `run-001` 或带日期的标识。
- 保持源数据只读，不要修改已完成结果目录中的文件。
- 与结果一起保存配置、样本表、ABI 版本、工具版本和资源清单。
- 把 dry-run 视为规划证据，而不是生物学正确性的证明。
- 解释生产结果前，先定义生物学验收标准。
- 需要复现或正式发布环境时，生成严格运行时锁。

需要更深入的设置时，请继续阅读 [Agent 使用指南](agent_usage.md)、[Job Service 指南](job_service.md)、[运行时锁指南](runtime_locks.md)或对应插件指南。
