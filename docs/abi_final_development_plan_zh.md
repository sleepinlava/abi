# ABI 最终开发计划

本文档是源自 `Rebuild.md` 的仓库本地固化计划。
它保持实现边界清晰，以防未来工作偏离回单一的 AutoPlasm CLI 封装。

## 产品形态

ABI 以以下形式交付：

- ABI 核心
- 面向 Agent 的工具层
- 插件 SDK
- HTTP Job Service
- PyPI 包：`abi-agent`

Python 导入包保持为 `abi`，主命令保持为 `abi`。

## 架构规则

- 核心要厚：插件发现、schema、权限、诊断、溯源、标准表、合约、执行规划和报告均位于 `src/abi` 下。
- 传输层要薄：CLI JSON、OpenAI 描述符、MCP 和 HTTP 作业均调用 `ABIAgentInterface`，而非重新实现业务逻辑。
- 插件要清晰：生物学规划、解析、工具合约、标准表和报告属于各分析插件。
- Agent 不需要导入 Python 类。它们调用 CLI JSON、描述符、MCP 工具或 HTTP 作业。

## 内置插件

- `metagenomic_plasmid`：AutoPlasm 适配器及复杂的主要案例。
- `metatranscriptomics`：轻量级可移植性演示，使用 fastp、STAR/HISAT2 和 featureCounts。

## 必备检查项

当环境提供所需工具时，仓库应保持以下检查项通过：

```bash
pytest
ruff check src/abi tests
ruff format --check src/abi tests
mypy src/abi/ --ignore-missing-imports
python -m build
python -m twine check dist/*
```

## 证据产物

- Golden agent trace 存放在 `golden_traces/` 中。
- 插件清单和工具合约位于 `plugins/*/` 中。
- 实验脚手架位于 `docs/experiments/` 中。
- Demo 输出必须包含 `execution_plan.json`、`provenance/`、`tables/` 和 `report/`。

## 下一步开发路线图

下一阶段是将 ABI 从强控制平面推进为经过验证的、有文献支持的科学工作流。

### 1. 合约完整性

- 扩展运行时合约，在执行前验证输入大小、扩展名、目录文件数量以及可选/必需输入的语义。
- 为 `pipeline_dag.yaml`、`tool_registry.yaml` 和 `tool_contracts/*.yaml` 添加 contract-lint 命令。
- 将合约违规提升为稳定的面向 Agent 的诊断代码。

### 2. 可复现性清单

- 通过逐工具版本探测记录真实工具版本。
- 添加数据库/模型清单，包含来源、版本、校验和、许可证说明以及验证日期。
- 为冒烟测试路线支持固定的 conda-lock 文件或容器。

### 3. 生物学验证

- 为默认路线添加小型正/负基准数据集。
- 在标准表中定义预期行数和阈值，而非仅检查原始文件。
- 追踪宿主预测、质粒分箱、丰度以及相关网络解释的已知局限性。

### 4. 基于文献的报告

- 维护按工具 ID 和工作流阶段索引的引用注册表。
- 将方法、版本、数据库清单和引用输出到报告中。
- 根据 fixture 覆盖度和文献审查，将可选工具标记为 `validated`、`available` 或 `experimental`。

详细的验收标准和初始证据映射见
[工作流验证与科学证据计划](workflow_validation_zh.md)。
