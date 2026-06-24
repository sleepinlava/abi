# ABI 插件生产环境手动验收检查清单

本文档用于 ABI 插件在实际生产环境上线前的手动验收。检查项按以下两个环境分类：

1. **本地 IDE/普通机器验收**：验证配置、计划、命令渲染、路径解析、安全门、mock/smoke 和产物契约。
2. **HPC/生产平台验收**：验证真实工具、真实数据库、调度器、共享存储、性能、并发和故障恢复。

> 本地 `dry-run`、`--mock` 或 `--smoke` 通过，只能证明软件契约和控制流程基本正确，不能代替 HPC 上的真实生产运行，也不能证明生物学结果正确。

## 1. 验收范围

当前内置插件共 7 个：

```text
amplicon_16s
easymetagenome
metagenomic_plasmid
metatranscriptomics
rnaseq_expression
viral_viwrap
wgs_bacteria
```

建议为每个插件分别建立验收记录，至少保留以下信息：

| 字段 | 内容 |
|---|---|
| 插件 | `<analysis_type>` |
| ABI 版本 | wheel 版本、Git commit |
| 验收环境 | 本地/HPC、操作系统、节点名称 |
| 配置文件 | 路径和 SHA-256 |
| 样本表 | 路径和 SHA-256 |
| 数据库版本 | 名称、版本、日期、checksum |
| 工具版本 | 工具、环境、实际可执行文件路径、版本 |
| 执行命令 | 完整 CLI 命令 |
| 验收人员 | 姓名 |
| 验收时间 | ISO 日期时间 |
| 结果 | 通过/有条件通过/失败/阻塞 |
| 证据 | 日志、截图、输出目录、问题单 |

## 2. 验收判定规则

- **通过**：实际结果与预期完全一致，有完整证据。
- **失败**：结果错误、发生未预期副作用、错误未被检测，或产物不完整。
- **阻塞**：受外部网络、调度器、许可证、数据库权限等影响而无法执行。
- **不适用**：必须说明原因，不能直接留空。
- 任一涉及安全门、真实工具误调用、数据库误用、结果假成功的问题均按阻断缺陷处理。

---

# 第一部分：本地 IDE/普通机器验收

## 3. 基础安装与插件发现

- [ ] **L-001** 执行 `abi --help`，主命令正常显示。
- [ ] **L-002** 执行 `abi list-types`，准确返回 7 个内置插件，无重复或遗漏。
- [ ] **L-003** 执行 `abi list-types --output-json`，stdout 是可解析的纯 JSON，包含 `status=success`。
- [ ] **L-004** 在全新 Python 3.10 虚拟环境中安装构建后的 wheel，而不只验证 editable 安装。
- [ ] **L-005** wheel 安装后，`plugins/`、`config/`、`envs/`、示例和维护脚本均可找到。
- [ ] **L-006** 使用只读安装目录启动 ABI，确认运行时不会尝试修改包安装目录。
- [ ] **L-007** 未知插件 ID 返回明确错误，并列出可用插件。

对每个插件执行：

```bash
abi contract-lint --type <TYPE> --strict
abi query --type <TYPE> --what stages
abi query --type <TYPE> --what tools
abi query --type <TYPE> --what platforms
```

- [ ] **L-008** 无 DAG 循环。
- [ ] **L-009** 无断裂依赖、非法断言或工具注册不一致。

## 4. `init` 工作区初始化

```bash
abi init --type <TYPE> --outdir /tmp/abi-uat/<TYPE>
```

- [ ] **L-010** 全部 7 个插件均生成插件配置文件和 `samples.tsv` 样本表模板。
- [ ] **L-011** 文件内容与插件模板一致，路径正确。
- [ ] **L-012** 重复执行且不加 `--force` 时拒绝覆盖。
- [ ] **L-013** 加 `--force` 后可以完整覆盖。
- [ ] **L-014** 目标目录不可写时明确失败。
- [ ] **L-015** 初始化失败时不残留半初始化文件。
- [ ] **L-016** 中文、空格和长路径可正常处理。

### 当前实现状态

全部 7 个内置插件均已提供 `sample_sheet_template.tsv`。其中
`amplicon_16s`、`metagenomic_plasmid` 和 `viral_viwrap` 的模板已补齐，必须分别执行
L-010～L-016 回归，不能只抽查原有 4 个插件。

主 `abi init` 会在写入前统一检查所有源模板和覆盖冲突；任一模板缺失或写入失败时，
不得残留半初始化配置或样本表。

## 5. `plan` 验收

```bash
abi plan \
  --type <TYPE> \
  --config <CONFIG.yaml> \
  --sample-sheet <SAMPLES.tsv> \
  --profile dry_run \
  --outdir /tmp/abi-uat/<TYPE>/plan \
  --log-dir /tmp/abi-uat/<TYPE>/logs \
  --output-json
```

### 5.1 正向检查

- [ ] **L-020** 退出码为 0，生成 `execution_plan.json`。
- [ ] **L-021** `analysis_type`、项目名、样本数、线程数、模式和输出目录正确。
- [ ] **L-022** 每个步骤包含 `step_id`、`tool_id`、输入、参数、输出和命令。
- [ ] **L-023** 步骤 ID 唯一，依赖关系无环。
- [ ] **L-024** 上游输出与下游输入路径完全一致。
- [ ] **L-025** 所有输出均位于配置的 `outdir` 内，不能通过 `../` 越界。
- [ ] **L-026** 相同配置连续生成两次，除允许变化的时间字段外结果确定性一致。
- [ ] **L-027** 命令中的线程、数据库、容器和资源参数与配置一致。
- [ ] **L-028** CLI 参数覆盖配置文件参数，且优先级可预测。
- [ ] **L-029** `--check-files` 下输入存在时通过。
- [ ] **L-030** `--check-files` 下输入不存在时失败。
- [ ] **L-031** `--no-check-files` 可生成离线计划，但计划中仍保留原始输入路径。
- [ ] **L-032** `--output-json` 输出不混入日志、进度条或警告文本。

### 5.2 插件分支检查

- [ ] **L-033** `metagenomic_plasmid` 分别验证 Illumina、ONT、HiFi、Hybrid 和 assembly-only。
- [ ] **L-034** 功能开关关闭时，对应步骤不进入执行计划，并记录跳过原因。
- [ ] **L-035** 单样本、多样本、有分组、无分组产生正确分支。
- [ ] **L-036** `rnaseq_expression` 多样本时生成 count matrix 和 DESeq2 步骤。
- [ ] **L-037** `amplicon_16s` 开启/关闭 OTU clustering 时步骤正确变化。
- [ ] **L-038** `easymetagenome` taxonomy/functional preset 选择正确工具和数据库。
- [ ] **L-039** `viral_viwrap` 参数准确传递给上游 ViWrap。

### 5.3 异常输入检查

- [ ] **L-040** 缺少样本 ID 时失败。
- [ ] **L-041** 重复样本 ID 时失败。
- [ ] **L-042** 空样本表或只有表头时按插件契约处理。
- [ ] **L-043** FASTQ 配对不完整时失败。
- [ ] **L-044** 非法平台、非法模式和非法 YAML 数据类型时失败。
- [ ] **L-045** 非法线程数、内存、walltime、accelerator、容器运行时明确报错。
- [ ] **L-046** 路径含空格、中文、括号和符号链接时命令参数不会被错误拆分。
- [ ] **L-047** 输出路径越界、只读目录和无权限目录被拒绝。

## 6. 工具路径检查

工具路径预期解析顺序：

1. 明确指定的绝对路径或带目录的路径；
2. `$ABI_MAMBA_ROOT/<env>/bin`；
3. `$ABI_MAMBA_ROOT/envs/<env>/bin`；
4. 系统 `PATH`。

- [ ] **L-050** 设置 `ABI_MAMBA_ROOT` 后确认其优先级最高。
- [ ] **L-051** 未设置环境变量时检查仓库 `.mamba`。
- [ ] **L-052** `.mamba` 不存在时检查兄弟目录 `abi-envs` 回退。
- [ ] **L-053** 为每个工具记录 env 名、可执行文件名和实际解析路径。
- [ ] **L-054** 实际文件存在并通过 `test -x <path>`。
- [ ] **L-055** 执行工具版本命令，版本满足生产基线。
- [ ] **L-056** 在系统 `PATH` 放置同名假工具，确认 mamba 环境内工具优先。
- [ ] **L-057** 移除环境内工具后，确认系统 `PATH` 回退行为符合预期。
- [ ] **L-058** 明确配置不存在的工具路径时必须报告 missing。
- [ ] **L-059** 文件存在但没有执行权限时必须判失败。
- [ ] **L-060** 动态库或解释器缺失时不能仅因主文件存在而判通过。
- [ ] **L-061** `provenance/tool_versions.tsv` 记录全部实际使用工具及版本状态。

`metagenomic_plasmid` 可执行：

```bash
autoplasm check-tools --config <CONFIG.yaml>
```

### 当前实现状态

全部 7 个内置插件均已实现输入、工具和资源 preflight。验收仍必须逐插件制造缺失输入、
缺失工具和缺失资源，确认返回 `fail` 和非零退出码；不得仅依据一个正常配置的 `pass`
结果判定运行环境已就绪。

显式工具路径当前主要检查文件是否存在，执行权限检查不充分，也必须通过手动检查补足。

## 7. `check` 无副作用预检

```bash
abi check \
  --type <TYPE> \
  --config <CONFIG.yaml> \
  --sample-sheet <SAMPLES.tsv> \
  --engine local \
  --output-json
```

- [ ] **L-065** 命令不创建输出、下载资源或运行分析工具。
- [ ] **L-066** 输入缺失时状态为 fail，退出码非 0。
- [ ] **L-067** 工具缺失时状态为 fail，而不是空检查 pass。
- [ ] **L-068** 数据库未配置、缺失或无权限时给出可操作建议。
- [ ] **L-069** `--no-check-runtime` 只跳过运行时检查，不跳过配置和输入检查。

## 8. `dry-run` 验收

```bash
abi dry-run \
  --type <TYPE> \
  --config <CONFIG.yaml> \
  --sample-sheet <SAMPLES.tsv> \
  --outdir /tmp/abi-uat/<TYPE>/dry-run \
  --log-dir /tmp/abi-uat/<TYPE>/logs \
  --output-json
```

- [ ] **L-070** 不调用任何真实生物信息工具。
- [ ] **L-071** 不下载数据库、不修改已有数据库。
- [ ] **L-072** 所有计划步骤状态为 `dry_run`，不能伪造为真实 `success`。
- [ ] **L-073** 命令内容完整，输入、输出和数据库路径已展开。
- [ ] **L-074** 生成 `execution_plan.json`。
- [ ] **L-075** 生成 `provenance/commands.tsv`。
- [ ] **L-076** 生成 `provenance/resolved_inputs.tsv`。
- [ ] **L-077** 生成 `provenance/tool_versions.tsv`，dry-run 下版本状态为 `not_captured`。
- [ ] **L-078** 生成 `resources.json` 和 `resource_manifest.json`。
- [ ] **L-079** 生成 `config.resolved.yaml` 和 `environment.yml`。
- [ ] **L-080** 生成 `run_summary.json`、`progress.json` 和 `progress.jsonl`。
- [ ] **L-081** 生成标准表和报告目录。
- [ ] **L-082** `run_summary.json` 中 `dry_run=true`，步骤数与计划一致。
- [ ] **L-083** `commands.tsv` 的步骤顺序与计划一致。
- [ ] **L-084** `inspect` 能识别 `NOT_CONFIGURED` 和缺失输入。
- [ ] **L-085** `validate-result --allow-empty-tables` 通过。
- [ ] **L-086** `validate-result --require-nonempty-tables` 对空 dry-run 表失败。
- [ ] **L-087** CPU、memory、walltime、accelerator 和 container 参数进入命令或导出工作流。
- [ ] **L-088** dry-run 前后比较数据库目录摘要，确认没有文件变化。

## 9. 数据库路径侦测与使用

```bash
abi check-resources \
  --type <TYPE> \
  --config <CONFIG.yaml>
```

### 9.1 通用状态

- [ ] **L-100** `NOT_CONFIGURED`、`TODO`、`PLACEHOLDER` 返回 `not_configured`。
- [ ] **L-101** 不存在路径返回 `missing`。
- [ ] **L-102** 空目录不能被误判为完整数据库。
- [ ] **L-103** 路径有内容但结构不完整时返回 `incomplete` 或 `invalid`。
- [ ] **L-104** 完整数据库返回 `ok`。
- [ ] **L-105** 相对路径、绝对路径和符号链接解析正确。
- [ ] **L-106** 路径存在但当前用户不可读时失败。
- [ ] **L-107** 自定义路径同时出现在 `execution_plan.json`、`commands.tsv` 和资源 provenance 中。
- [ ] **L-108** 计划路径与实际工具命令使用路径一致。
- [ ] **L-109** 数据库版本、日期、来源和 checksum/fingerprint 被记录。
- [ ] **L-110** `--resource <ID>` 只返回指定资源。

### 9.2 插件资源矩阵

| 插件 | 必查资源 | 内容级检查 |
|---|---|---|
| `amplicon_16s` | `taxonomy_db`、`phylogeny_tree`、`diversity_script` | taxonomy FASTA 必须有 `;tax=` 注释 |
| `easymetagenome` | `host_db`、`kraken2_db`、HUMAnN nucleotide/protein、MetaPhlAn DB | 运行上游数据库检查命令 |
| `metagenomic_plasmid` | 30 个数据库、模型和外部工具资源 | provider 文件结构、ready sentinel、版本元数据 |
| `metatranscriptomics` | STAR `genome_index`、`annotation_gtf` | STAR 索引结构、GTF 可读性 |
| `rnaseq_expression` | `genome_index`、`annotation_gtf`、Rscript/DESeq2 | `library(DESeq2)` 成功并记录版本 |
| `viral_viwrap` | `db_dir`、`conda_env_dir`、ViWrap executable | ViWrap 上游完整环境检查 |
| `wgs_bacteria` | `amrfinder_db` | AMRFinderPlus 数据库结构和版本 |

`metagenomic_plasmid` 当前资源分类：

- `check-resources` 应报告全部 30 个资源。
- 默认 `setup-resources --dry-run` 只包含 14 个自动资源。
- Level 2 资源只有显式指定 `--resource` 时才应进入安装计划。

## 10. 数据库下载与安装安全门

```bash
abi setup-resources \
  --type <TYPE> \
  --config <CONFIG.yaml> \
  --resource <RESOURCE_ID> \
  --dry-run

abi setup-resources \
  --type <TYPE> \
  --config <CONFIG.yaml> \
  --resource <RESOURCE_ID> \
  --mock \
  --dry-run
```

- [ ] **L-120** dry-run 返回 `planned`、目标路径、来源和完整命令。
- [ ] **L-121** dry-run 不创建下载目录或 ready sentinel。
- [ ] **L-122** 不带 `--confirm` 的真实安装退出码为 2。
- [ ] **L-123** `--resource` 只处理指定资源。
- [ ] **L-124** `--mock` 输出包含布尔字段 `mock: true`；普通 dry-run 包含
  `mock: false`。`--mock --dry-run` 不得创建资源，并且必须可通过该字段与真实资源 dry-run
  明确区分。
- [ ] **L-125** production 配置不能接受 mock/synthetic 资源。
- [ ] **L-126** 已完成资源再次安装时显示跳过，不重复下载。
- [ ] **L-127** 不完整目录不能被覆盖，应返回 `incomplete`。
- [ ] **L-128** 下载超时、断网、磁盘不足时返回 failed/error。
- [ ] **L-129** 失败下载不能写 ready sentinel。
- [ ] **L-130** 下载成功后执行内容级 ready check，而不只检查目录存在。
- [ ] **L-131** `GTDBTK_DATA_PATH`、`CHECKM2DB` 等环境变量指向配置路径。
- [ ] **L-132** 资源清单记录版本、来源、日期、checksum 和文件数量。
- [ ] **L-133** 小型资源真实下载后可重复检查和复用。

### 当前实现状态与已知风险

资源 setup 返回行已统一包含 `mock` 布尔字段；`metagenomic_plasmid` 的
`ResourceStatus` 和资源清单也记录该字段。L-124 必须覆盖全部 7 个插件，并同时比较执行前后
目标路径，确认 `--mock --dry-run` 没有写入目录或 sentinel。

16S RDP 下载失败时，当前实现可能生成 synthetic fallback。生产验收必须将 `fallback` 判为失败，不能将合成数据库用于真实分析。

部分通用资源检查目前主要验证 `Path.exists()`。目录存在不代表数据库完整、可读或能被工具使用，因此必须在 HPC 上执行真实最小查询。

## 11. 本地 smoke run

先验证执行确认门：

```bash
abi run --type <TYPE> --config <CONFIG.yaml> --smoke
```

- [ ] **L-140** 未带 `--confirm-execution` 时退出码为 2。
- [ ] **L-141** 返回 `confirmation_required`。
- [ ] **L-142** 不调用工具、不产生真实分析结果。

确认后执行：

```bash
abi run \
  --type <TYPE> \
  --config <CONFIG.yaml> \
  --smoke \
  --confirm-execution \
  --outdir /tmp/abi-uat/<TYPE>/smoke
```

- [ ] **L-143** smoke 运行成功且不调用真实工具。
- [ ] **L-144** `commands.tsv`、标准表、报告和 summary 齐全。
- [ ] **L-145** `inspect` 无 failed steps。
- [ ] **L-146** `validate-result --allow-empty-tables` 通过。
- [ ] **L-147** 删除一个必需产物后 validation 失败。
- [ ] **L-148** 修改标准表表头后 schema validation 失败。
- [ ] **L-149** `report` 可从已有结果重新生成 Markdown/HTML。
- [ ] **L-150** `export-nextflow --smoke` 生成可运行 DSL2。
- [ ] **L-151** `run --engine nextflow --smoke` 在本地 Nextflow 环境通过。
- [ ] **L-152** 无效 engine 返回 `runtime_not_supported` 或等价明确错误。

## 12. 本地结果与辅助功能

- [ ] **L-160** `abi inspect --result-dir <OUT>` 正确汇总失败、跳过和缺失输入。
- [ ] **L-161** `abi report --type <TYPE> --result-dir <OUT>` 可重复生成报告。
- [ ] **L-162** `abi validate-result` 不修改结果目录。
- [ ] **L-163** `--allow-empty-tables` 与 `--require-nonempty-tables` 行为符合说明。
- [ ] **L-164** `abi export-nextflow` 输出包含 DSL2、步骤依赖和资源参数。
- [ ] **L-165** `abi export-agent-context` 内容与插件能力一致。
- [ ] **L-166** 所有 agent/JSON 接口统一返回 success、confirmation_required 或 error 信封。
- [ ] **L-167** 同一运行重新生成报告不会修改原始结果表和 provenance。

---

# 第二部分：HPC/生产平台验收

## 13. 平台与共享文件系统

- [ ] **H-001** 使用与发布版本相同的 wheel、Git commit 和配置版本。
- [ ] **H-002** 登录节点和计算节点均能运行 `abi --help`。
- [ ] **H-003** `ABI_MAMBA_ROOT` 位于计算节点可访问路径。
- [ ] **H-004** 输入、数据库、工作目录和日志目录均为共享路径。
- [ ] **H-005** 计算节点拥有数据库读取权限和输出写权限。
- [ ] **H-006** 检查磁盘容量、inode、用户配额和临时空间。
- [ ] **H-007** 配置不依赖登录节点本地 `/tmp` 或仅登录节点可见的本地磁盘。
- [ ] **H-008** 多节点同时读取数据库时无锁冲突和文件损坏。
- [ ] **H-009** NFS/Lustre/GPFS 等共享存储路径和性能满足要求。

## 14. 调度器验收

Slurm 示例：

```bash
abi run \
  --engine hpc \
  --scheduler slurm \
  --type <TYPE> \
  --config <PROD_CONFIG.yaml> \
  --partition <PARTITION> \
  --account <ACCOUNT> \
  --qos <QOS> \
  --confirm-execution
```

PBS 环境替换为 `--scheduler pbs`。

- [ ] **H-010** Slurm 的 `sbatch`、`squeue`、`sacct`、`scancel` 可用。
- [ ] **H-011** PBS 的 `qsub`、`qstat`、`qdel` 可用。
- [ ] **H-012** 每个 DAG 步骤生成独立调度脚本。
- [ ] **H-013** CPU、memory、walltime、GPU 正确写入调度指令。
- [ ] **H-014** DAG 依赖转换为正确的 scheduler dependency。
- [ ] **H-015** 上游失败后，依赖下游不会执行。
- [ ] **H-016** scheduler job ID 写入 `commands.tsv` 和 summary。
- [ ] **H-017** 调度器超时映射为 timeout/failed。
- [ ] **H-018** OOM、preempt、node failure 和 cancelled 状态正确映射。
- [ ] **H-019** 用户取消后停止未启动的后续作业，并保留已完成步骤 provenance。
- [ ] **H-020** partition/account/qos 等参数不能造成 shell 或调度指令注入。
- [ ] **H-021** 调度脚本包含 `set -euo pipefail` 或等价严格错误处理。

### 当前已知限制

`HpcRuntime.dry_run()` 已实现 HPC 脚本生成，但主 `abi dry-run` 当前未暴露 `--engine hpc`。CLI 用户不能直接预览完整 HPC 脚本，应作为验收缺口记录。

## 15. 计算节点工具路径

必须在真实计算节点内检查，不能只在登录节点检查。

- [ ] **H-030** 每个计划使用的工具在计算节点上可解析。
- [ ] **H-031** 工具来自预期 mamba 环境，而不是系统同名旧版本。
- [ ] **H-032** 可执行文件有执行权限。
- [ ] **H-033** 动态库、Perl、R、Python 包和辅助脚本依赖完整。
- [ ] **H-034** `PYTHONPATH` 不污染隔离环境。
- [ ] **H-035** OpenMP、BLAS 和工具线程配置合理。
- [ ] **H-036** 全部实际工具版本写入 `tool_versions.tsv`。
- [ ] **H-037** 容器模式下镜像可拉取或已缓存。
- [ ] **H-038** Singularity/Apptainer bind 路径包含输入、数据库、工作和输出目录。
- [ ] **H-039** 登录节点与计算节点解析到相同版本的 ABI CLI。

## 16. 真实数据库下载

大型数据库应逐个下载，不建议一次安装全部资源：

```bash
abi setup-resources \
  --type metagenomic_plasmid \
  --config <PROD_CONFIG.yaml> \
  --resource genomad \
  --confirm
```

- [ ] **H-040** 下载节点符合组织的外网访问和安全策略。
- [ ] **H-041** 下载目标是最终共享路径。
- [ ] **H-042** 下载前检查预计大小、剩余空间和配额。
- [ ] **H-043** 下载中断后不会把半成品标记为 ready。
- [ ] **H-044** 重跑不会覆盖已验证的完整数据库。
- [ ] **H-045** 校验 provider checksum 或目录 fingerprint。
- [ ] **H-046** 记录数据库版本、下载日期、来源 URL 和许可证。
- [ ] **H-047** 在计算节点执行数据库工具最小查询，不只检查文件存在。
- [ ] **H-048** geNomad、Bakta、Kraken2、GTDB-Tk、CheckM2 等分别执行真实 smoke query。
- [ ] **H-049** 数据库升级后保留旧版本并支持回滚。
- [ ] **H-050** 多作业同时启动时不会并发重复下载同一数据库。
- [ ] **H-051** 数据库路径在 provenance 中记录为最终解析后的规范路径。

## 17. 真实端到端运行

每个插件至少准备一个可人工判断的 gold/small-real 数据集。

- [ ] **H-060** 使用真实模式和 `--confirm-execution`，不得带 `--smoke`。
- [ ] **H-061** 所有外部步骤真实执行且 return code 为 0。
- [ ] **H-062** 所有必需输出文件存在且非空。
- [ ] **H-063** 标准表不只包含表头。
- [ ] **H-064** 解析后的样本 ID、数值范围和分类字段正确。
- [ ] **H-065** 报告中的方法、工具版本和数据库与实际运行一致。
- [ ] **H-066** `inspect` 无 failed steps，无生产资源占位符。
- [ ] **H-067** `validate-result --require-nonempty-tables` 通过。
- [ ] **H-068** 与已知基线比较，核心指标在允许误差内。
- [ ] **H-069** 由领域人员抽查生物学合理性。
- [ ] **H-070** 对无命中、低质量和极端输入返回合理空结果，而不是崩溃或假阳性。

## 18. 输入平台覆盖

- [ ] **H-075** Illumina paired-end 真实运行。
- [ ] **H-076** ONT 真实运行。
- [ ] **H-077** PacBio HiFi 真实运行。
- [ ] **H-078** Hybrid 真实运行。
- [ ] **H-079** assembly-only 真实运行。
- [ ] **H-080** 单样本和多样本均运行。
- [ ] **H-081** 有分组和无分组场景均运行。
- [ ] **H-082** 可选工具启用和禁用路径均验证。

仅需对插件实际支持的平台执行，不适用项必须在验收记录中注明。

## 19. 并发、恢复与故障注入

- [ ] **H-090** 多样本并行时无输出目录覆盖。
- [ ] **H-091** 相同样本 ID 被提前拒绝。
- [ ] **H-092** `--resume` 只跳过输出完整且 checksum 一致的步骤。
- [ ] **H-093** 手工修改已完成输出后，resume 重新执行该步骤。
- [ ] **H-094** 删除中间文件后从正确步骤恢复。
- [ ] **H-095** 人为终止一个工具，失败原因写入 step log。
- [ ] **H-096** 数据库临时不可读时快速失败，不产生假成功。
- [ ] **H-097** scheduler 中断后 provenance 仍可解析。
- [ ] **H-098** 同一 outdir 重跑时旧 provenance 不污染新运行。
- [ ] **H-099** Nextflow `-resume` 与 ABI resume 行为一致。
- [ ] **H-100** 失败、取消和超时后无长期残留作业。
- [ ] **H-101** 一个计算节点故障时最终状态和失败原因正确。
- [ ] **H-102** 部分标准表解析失败时不能把整体结果误报为成功。

## 20. Nextflow 生产验收

```bash
abi run \
  --engine nextflow \
  --type <TYPE> \
  --config <PROD_CONFIG.yaml> \
  --executor slurm \
  --nextflow-profile <PROFILE> \
  --resume \
  --confirm-execution
```

- [ ] **H-110** 生成的 `workflow.nf` 是有效 DSL2。
- [ ] **H-111** Nextflow executor、profile 和工作目录正确。
- [ ] **H-112** trace、timeline、stdout 和 stderr 文件生成。
- [ ] **H-113** trace 中任务状态和退出码映射到 ABI provenance。
- [ ] **H-114** 远程 scheduler job ID 被记录。
- [ ] **H-115** `-resume` 不重复执行已缓存任务。
- [ ] **H-116** Nextflow 失败时 ABI CLI 退出码非 0，并指出 stderr 路径。
- [ ] **H-117** Nextflow work 和 cache 清理策略明确。

## 21. 性能与容量

- [ ] **H-120** 记录 plan、提交、排队、运行和报告耗时。
- [ ] **H-121** 记录单样本和多样本峰值内存。
- [ ] **H-122** 记录临时文件和最终结果磁盘使用量。
- [ ] **H-123** 100 样本计划生成时间满足 SLA。
- [ ] **H-124** 大型 DAG 不造成 scheduler 提交风暴。
- [ ] **H-125** 数据库共享读取不是不可接受的 I/O 瓶颈。
- [ ] **H-126** 日志、progress JSON/JSONL 在长任务中不会异常增长。
- [ ] **H-127** 报告生成时间和内存满足要求。
- [ ] **H-128** 并发 worker 数与节点 CPU/内存匹配。
- [ ] **H-129** 超大样本或超长路径不会导致命令行、文件名或调度脚本失败。

## 22. 可追溯性与结果归档

- [ ] **H-130** `execution_plan.json` 与实际执行配置一致。
- [ ] **H-131** `commands.tsv` 包含所有步骤及最终状态。
- [ ] **H-132** `resolved_inputs.tsv` 中生产输入均存在，无 `NOT_CONFIGURED`。
- [ ] **H-133** `tool_versions.tsv` 中必需工具版本均成功捕获。
- [ ] **H-134** `resources.json` 记录数据库版本和路径。
- [ ] **H-135** `checksums.json` 或资源 fingerprint 可用于完整性检查。
- [ ] **H-136** `run_summary.json` 与实际 scheduler 状态一致。
- [ ] **H-137** `progress.jsonl` 可重放主要运行事件。
- [ ] **H-138** 每个失败步骤有 stdout/stderr 或等价日志。
- [ ] **H-139** 报告、标准表和 provenance 一起归档。
- [ ] **H-140** 归档后在另一台机器可执行只读 `inspect` 和 `validate-result`。

---

# 第三部分：生产放行与缺陷管理

## 23. 生产放行门槛

只有同时满足以下条件，才能判定插件可用于生产：

- [ ] 本地清单无阻断项。
- [ ] HPC 真实端到端运行通过。
- [ ] 结果中不存在 `NOT_CONFIGURED`、mock、synthetic 或 fallback 生产资源。
- [ ] 真实工具版本和数据库版本完整可追溯。
- [ ] `validate-result --require-nonempty-tables` 通过。
- [ ] 失败、超时、取消和 resume 至少各验证一次。
- [ ] 真实结果通过基线或领域专家审查。
- [ ] 已知限制、运行成本、数据库许可证和运维流程有正式文档。

## 24. 当前修复状态与建议优先处理的问题

已完成并需要持续回归：

1. 全部 7 个插件均已实现完整 preflight，不再允许空检查假通过。
2. 全部 7 个插件均已提供 `init` 所需样本模板。
3. `setup-resources` 输出已显式区分 mock 与真实资源预览，mock dry-run 不写入资源。

仍建议优先处理：

1. 部分通用数据库检查只验证路径存在，尚未完整验证内容、权限和结构。
2. 16S 数据库下载失败后的 synthetic fallback 必须禁止进入生产运行。
3. 显式工具路径检查应补充执行权限和版本探测。
4. 主 CLI 应提供 HPC dry-run/调度脚本预览入口。

## 25. 单项验收记录模板

```markdown
### 检查项：L-070 dry-run 不调用真实工具

- 插件：metagenomic_plasmid
- 环境：本地/HPC
- ABI 版本：
- 配置文件：
- 输入文件：
- 执行命令：
- 预期结果：不启动任何真实外部工具，不修改数据库目录
- 实际结果：
- 退出码：
- 证据路径：
- 判定：通过/失败/阻塞/不适用
- 缺陷编号：
- 验收人：
- 时间：
```
