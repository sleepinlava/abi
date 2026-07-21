# <img src="figures/abi_logo.png" alt="ABI" width="36" height="36" align="top"> ABI — Agent-Bioinformatics Interface（面向 Agent 的生物信息学接口）

通过命令行或 AI Agent 运行可复现的生物信息学流程，而不是让 Agent 临时拼接分析脚本。

ABI 为所有受支持的分析提供同一套安全流程：先了解工作流、检查输入与资源、进行 dry-run，再经明确确认后执行，最后检查标准化结果与完整溯源记录。

[![PyPI](https://img.shields.io/pypi/v/abi-agent?style=flat-square&color=blue)](https://pypi.org/project/abi-agent/)
[![Python](https://img.shields.io/pypi/pyversions/abi-agent?style=flat-square)](https://pypi.org/project/abi-agent/)
[![CI](https://img.shields.io/github/actions/workflow/status/sleepinlava/abi/ci.yml?branch=master&style=flat-square)](https://github.com/sleepinlava/abi/actions/workflows/ci.yml)
[![Coverage](https://img.shields.io/badge/coverage-83%25-brightgreen?style=flat-square)](https://github.com/sleepinlava/abi/actions/workflows/ci.yml)
[![Docs](https://img.shields.io/badge/docs-Sphinx-blue?style=flat-square)](https://sleepinlava.github.io/abi/)
[![Status](https://img.shields.io/badge/status-alpha-orange?style=flat-square)](https://github.com/sleepinlava/abi)
[![License](https://img.shields.io/pypi/l/abi-agent?style=flat-square)](https://github.com/sleepinlava/abi/blob/master/LICENSE)

> :gb: [English](README.md)

## ABI 能帮你做什么

- **运行前先审查。** 在消耗计算资源前查看阶段、工具、命令、输入、输出和资源需求。
- **用一套方式操作所有流程。** 所有内置分析都遵循 `plan -> check -> dry-run -> run -> inspect -> report`。
- **让结果可追溯。** 每次运行都会记录解析后的输入、配置、命令、工具版本、资源、进度、标准表格和报告。
- **让 Agent 安全操作。** Agent 调用有类型约束的 ABI 工具，而不是生成临时 Shell 流程；真正执行仍需明确确认。
- **在不同运行环境间迁移。** 可以从本地开始，再接入 Docker、Nextflow、HPC、云端 worker 或 HTTP Job Service，而不改变工作流契约。

ABI 是工作流编排与接口层，不会替代分析所需的底层生物信息学软件、参考数据库和计算资源。

## ABI 适合谁

- **科研人员和生物信息学工程师**：希望用可预期的方式预览、运行、检查和复现分析。
- **使用 AI Agent 的团队**：需要机器可读的工具、清晰的权限边界和结构化诊断。
- **平台工程团队**：需要通过 CLI、MCP、HTTP、Nextflow、HPC 或云端基础设施提供工作流。
- **插件开发者**：希望复用 ABI 的规划、溯源、验证、标准表格和报告能力来接入新流程。

## 选择适合你的分析流程

| 如果你想…… | 使用 `--type` | 主要结果 |
| --- | --- | --- |
| 分析 16S 微生物群落 | `amplicon_16s` | ASV、物种注释、系统发育、Alpha/Beta 多样性 |
| 比较 bulk RNA-seq 表达差异 | `rnaseq_expression` | 计数矩阵、差异表达、通路富集 |
| 分析细菌分离株基因组 | `wgs_bacteria` | 组装、注释、MLST、耐药基因结果 |
| 定量宏转录组基因表达 | `metatranscriptomics` | 测序质控、比对统计、基因计数 |
| 分析宏基因组 shotgun reads | `easymetagenome` | 物种组成和功能丰度 |
| 识别并表征宏基因组病毒 | `viral_viwrap` | 病毒 bin、质量、分类、宿主和标准化丰度 |
| 重建并表征宏基因组质粒 | `metagenomic_plasmid` | 检测共识、分型、宿主、注释、丰度和群落分析 |

7 个流程均已通过软件路径验证。生物学结果仍取决于数据、参数、数据库和工具版本；投入生产前，请用代表性数据集完成自己的验收。

无需阅读源码，也可以直接了解某个流程：

```bash
abi list-types
abi query --type metagenomic_plasmid --what stages
abi query --type metagenomic_plasmid --what tools
abi query --type metagenomic_plasmid --step qc_fastp --what inputs
```

## 五分钟上手

### 1. 安装 ABI

ABI 支持 Python 3.10-3.13。

```bash
pip install abi-agent
abi --version

# 可选功能
pip install "abi-agent[mcp]"       # MCP 服务
pip install "abi-agent[report]"    # 科研图形和增强报告
```

如需运行仓库自带示例并使用源码开发：

```bash
git clone https://github.com/sleepinlava/abi.git
cd abi
python -m venv .venv
. .venv/bin/activate
pip install -e .
```

### 2. 只生成计划，不运行工具

下面的示例会解析一个三步宏转录组流程，并把完整计划写入 `results/quickstart-plan/execution_plan.json`。

```bash
abi plan \
  --type metatranscriptomics \
  --config examples/metatranscriptomics/config_demo.yaml \
  --sample-sheet examples/sample_sheet_transcriptomics.tsv \
  --outdir results/quickstart-plan
```

### 3. 生成 dry-run 结果

dry-run 不会执行 STAR、HISAT2、featureCounts 或其他分析工具。它会先生成可供检查的溯源包、标准表格骨架和报告预览。

```bash
abi dry-run \
  --type metatranscriptomics \
  --config examples/metatranscriptomics/config_demo.yaml \
  --sample-sheet examples/sample_sheet_transcriptomics.tsv \
  --outdir results/quickstart-dry-run
```

所有结果目录都遵循相近的结构：

```text
results/quickstart-dry-run/
├── execution_plan.json
├── provenance/          # 解析后的输入、配置、命令、资源和版本
├── tables/              # 当前工作流的标准 TSV 表格
└── report/              # Markdown 和 HTML 报告预览
```

### 4. 检查真实运行环境

正式运行前，请在配置中填写真实数据和参考资源，再以只读方式检查文件、可执行程序和数据库。

```bash
abi check \
  --type metatranscriptomics \
  --config path/to/config.yaml \
  --sample-sheet path/to/samples.tsv

abi check-resources \
  --type metatranscriptomics \
  --config path/to/config.yaml
```

部分插件支持托管资源安装。先预览安装计划，确认路径和下载内容无误后再明确授权。

```bash
abi setup-resources --type metagenomic_plasmid --dry-run
abi setup-resources --type metagenomic_plasmid --confirm
```

### 5. 审查后再执行

没有 `--confirm-execution` 时，`abi run` 不会执行分析。这为用户和 Agent 提供了清晰的授权边界。

```bash
abi run \
  --type metatranscriptomics \
  --config path/to/config.yaml \
  --sample-sheet path/to/samples.tsv \
  --outdir results/my-run \
  --confirm-execution

abi inspect --result-dir results/my-run
abi report --result-dir results/my-run --type metatranscriptomics
```

所有面向 Agent 的命令都支持 `--output-json`，方便结构化自动化调用。

## 每一步会发生什么

| 命令 | 你会得到什么 | 是否执行分析工具 |
| --- | --- | --- |
| `abi query` | 来自 DAG 和工具注册表的轻量级流程信息 | 否 |
| `abi plan` | 解析后的步骤、命令、输入、输出和依赖关系 | 否 |
| `abi check` | 输入、资源、可执行程序和运行环境诊断 | 否 |
| `abi dry-run` | 执行计划、溯源包、表格骨架和报告预览 | 否 |
| `abi run` | 完整执行结果和记录的产物 | 是，需明确确认 |
| `abi inspect` | 对已有结果目录的验证和摘要 | 否 |
| `abi report` | 重新生成 Markdown 和 HTML 报告 | 不执行分析工具 |

## 在你的运行环境中使用 ABI

### 本地与 Conda 环境

ABI 通过 `environments.yaml` 把已注册工具映射到 18 个 Conda 环境。默认从仓库内的 `.mamba/envs/<env_name>/bin` 解析工具。

可以设置 `ABI_MAMBA_ROOT` 使用其他根目录；`AUTOPLASM_MAMBA_ROOT` 继续用于向后兼容。

### Docker

项目为 16S、RNA-seq、细菌 WGS、宏转录组和质粒分析提供 Dockerfile。EasyMetagenome 与 ViWrap 目前使用托管的本地环境。

```bash
docker build -f docker/Dockerfile.amplicon -t abi-amplicon .

docker run --rm -v "$PWD:/data" abi-amplicon \
  abi plan --type amplicon_16s --outdir /data/results

docker compose -f docker/docker-compose.yml up -d
```

镜像大小约为：16S 1.5 GB，RNA-seq、WGS 和宏转录组 2-2.5 GB，质粒分析 15 GB。

### Nextflow、HPC、云端与队列任务

当本地前台进程无法满足需求时，可以导出 Nextflow 工作流、选择 HPC 执行器，或通过带队列的 Job Service 提交任务。

```bash
abi export-nextflow --type metatranscriptomics --output workflow.nf

abi job-service --host 127.0.0.1 --port 18791 --workers 2 --subprocess-workers
abi job submit --command run --analysis-type metatranscriptomics --confirm-execution
abi job status <JOB_ID>
abi job artifacts <JOB_ID>
abi job cancel <JOB_ID>
```

子进程 worker 支持先发出 SIGTERM、宽限期后再 SIGKILL 的强制取消。详见 [Job Service 指南](docs/zh/job_service.md)和 [HPC 指南](docs/zh/hpc_development.md)。

## 与 AI Agent 一起使用

ABI 通过 JSON CLI 响应、不同模型厂商的工具描述、MCP、无头调度器和 HTTP 任务提供同一组核心操作。

```bash
# 安装仓库级 Agent 集成并进行诊断
abi agent install codex --scope project
abi agent doctor codex --scope project

# 启动安全的 MCP stdio 配置
abi-mcp

# 为模型厂商导出工具描述
abi export-tools --type metatranscriptomics --format openai --provider openai
abi export-tools --type metatranscriptomics --format anthropic
abi export-tools --type metatranscriptomics --format gemini

# 从 worker 进程调用 ABI 命令
abi dispatch --command list-types --arguments '{}'
```

默认 MCP `safe` 配置不会暴露执行和管理工具。`abi-mcp --profile full` 会增加仍受确认门保护的执行能力。可直接使用的 Claude Code、OpenCode 和 Codex 配置位于 `integrations/`。

系统提示词或程序也可以直接获取 ABI 的操作说明：

```python
import abi

print(abi.get_agent_guide())
print(abi.list_plugins_summary())
```

模型厂商配置和权限说明请参考 [Agent 使用指南](docs/zh/agent_usage.md)。

## 从结果生成科研图形

`abi-sciplot` 使用声明式图形规范，经过验证后输出可发表的 PDF、SVG、PNG 或 TIFF。它支持 15 种图形、3 套主题、图形质检和 SHA-256 溯源。

```bash
abi-sciplot validate --spec figure.yaml
abi-sciplot render --spec figure.yaml
abi-sciplot lint --spec figure.yaml
abi-sciplot list-plot-types
```

详见 [SciPlot 设计与使用指南](docs/zh/abi_sciplot_design.md)。

## 复现生产运行环境

普通运行时锁是一份审计快照。严格运行时锁会验证 Conda 包、声明的工具、数据库、主机环境、ABI 版本、Git 提交和发布范围内的就绪状态。

```bash
abi lock-runtime \
  --output-dir locks/candidate \
  --prefix abi-production \
  --mamba-root /path/to/mamba \
  --resource-root /path/to/resources \
  --db-profile full \
  --strict
```

如果发布环境不完整或代码身份不干净，严格模式会直接失败。只有需要认证全部可选工具时，才应增加 `--require-all-tools`。

资源目录、不可变锁策略和托管云端流程请参考[可发布运行时锁说明](docs/zh/runtime_locks.md)。

## 项目状态与使用预期

ABI 目前仍处于 alpha 阶段。核心契约、内置规划路径、dry-run、打包和适配器都有测试覆盖，但能否用于生产仍取决于底层工具和你的验证数据。

生产使用前，请固定 ABI 版本、生成严格运行时锁、核对工具和数据库版本，并为代表性样本定义生物学验收标准。

质粒流程已通过一个包含 3 条质粒的 RefSeq 数据集 assembly 模式验证。其他声明和各流程的验证证据记录在[工作流验证指南](docs/zh/workflow_validation.md)中。

## 扩展 ABI 或参与开发

与传输无关的行为位于 `src/abi/`；CLI、MCP、HTTP 和模型厂商集成保持为薄适配层。内置流程由 `src/abi/plugins/` 中的 Python 适配器和 `plugins/<analysis_type>/` 中的声明式定义共同组成。

第三方插件通过 `abi.plugins` entry-point 组注册：

```toml
[project.entry-points."abi.plugins"]
my_analysis = "my_package.plugins:MyPlugin"
```

分享插件前，请验证声明式 DAG 和工作流契约：

```bash
abi contract-lint --type my_analysis
abi contract-lint --type my_analysis --strict
```

本地开发与检查：

```bash
pip install -e ".[dev]"

ruff check src/ tests/
ruff format --check src/ tests/
mypy src/abi/ --ignore-missing-imports
pytest tests/ -v --tb=short
python -m build
```

建议从[开发指南](docs/zh/development.md)、[插件开发指南](docs/zh/plugin_development_guide.md)和 [API 参考](docs/en/api.rst)开始。

## 深入阅读

- [组件与架构](docs/zh/components_and_architecture.md)
- [使用 ABI：生命周期与示例](docs/zh/usage_guide.md)
- [全流程开发规范](docs/zh/development_workflow.md)
- [ABI 规范](docs/zh/abi_spec_v0.1.md)
- [Agent 使用指南](docs/zh/agent_usage.md)
- [插件开发指南](docs/zh/plugin_development_guide.md)
- [工作流验证](docs/zh/workflow_validation.md)
- [运行时锁](docs/zh/runtime_locks.md)
- [Job Service](docs/zh/job_service.md)
- [HPC 开发](docs/zh/hpc_development.md)
- [RNA-seq 工作流](docs/zh/rnaseq_expression_workflow.md)
- [宏基因组质粒工作流](docs/zh/metagenomic_plasmid.md)
- [发布指南](docs/zh/release.md)
- [在线文档](https://sleepinlava.github.io/abi/)

## 许可证

ABI 使用 MIT License，详见 [LICENSE](LICENSE)。
