# 组件与架构

本文说明 ABI 由哪些组件组成、一次请求如何流经系统，以及不同类型的行为分别由哪一层负责。

## 架构概览

```text
科研人员或 AI Agent
        |
        v
CLI / JSON / MCP / HTTP / 模型工具描述
        |
        v
ABIAgentInterface
        |
        v
核心生命周期：query -> plan -> check -> dry-run -> run -> inspect -> report
        |
        v
分析插件 + 声明式 DAG + 工具注册表
        |
        v
本地 / Conda / Docker / Nextflow / HPC / 云端 worker
        |
        v
执行计划 + 溯源 + 标准表格 + 报告 + 科研图形
```

所有传输方式都调用同一个核心接口。因此，CLI 请求和 MCP 请求使用相同的规划、权限、诊断、执行确认和结果契约。

## 组件地图

| 组件 | 职责 | 主要位置 |
| --- | --- | --- |
| 入口与传输适配器 | 把用户或机器请求转换为 ABI 操作 | `src/abi/cli.py`、`src/abi/mcp/`、`src/abi/jobs/`、`src/abi/tool_descriptors.py` |
| Agent 接口 | 稳定、与传输无关的 API 和 JSON 信封 | `src/abi/agent/` |
| 工作流核心 | Schema、规划、权限、诊断、契约、溯源、表格和报告 | `src/abi/` |
| 分析插件 | 负责生物学选择、工作流配置、解析和结果解释 | `src/abi/plugins/` |
| 声明式工作流定义 | 定义 DAG 节点、工具、Schema、表格和报告元数据 | `plugins/<analysis_type>/` |
| 工具与资源层 | 解析可执行程序、Conda 环境、数据库、索引和模型 | `src/abi/tools.py`、`src/abi/resources.py`、`environments.yaml` |
| 运行时适配器 | 本地执行，或把任务转换到 Nextflow 和 HPC 后端 | `src/abi/runtimes/`、`src/abi/exporters/` |
| 结果与图形层 | 验证产物、标准化 TSV、生成报告和科研图形 | `src/abi/results.py`、`src/abi/report/`、`src/abi/sciplot/` |

## 一次请求如何执行

1. **发现。** `abi list-types` 和 `abi query` 读取插件元数据，不构建或运行工作流。
2. **解析。** ABI 合并插件、配置、样本表、运行时参数和资源覆盖项。
3. **规划。** 声明式 DAG 生成 `ExecutionPlan`，其中包含有序步骤、命令、输入、输出、依赖和契约。
4. **检查。** ABI 以只读方式检查输入路径、可执行程序、资源和运行时假设。
5. **试运行。** dry-run 写入计划、溯源骨架、标准表格和报告预览。
6. **授权。** 执行需要明确传入 `--confirm-execution` 或对应的传输字段。
7. **执行。** 运行时调用已注册工具，并强制验证步骤输出契约。
8. **发布结果。** ABI 记录校验和、溯源、表格、摘要、报告和可选的 SciPlot 图形。

## 核心设计边界

### 核心层要厚

可复用机制属于核心层：生命周期操作、权限级别、Schema、诊断、溯源、契约执行、标准表格和报告组装。

### 传输层要薄

CLI、MCP、模型工具描述、dispatch 和 HTTP Job 只负责转换请求，不应包含工作流或生物学逻辑。

### 插件要干净

插件负责分析特有的决策：工具、参数、DAG 分支、输入规则、输出解析、生物学断言和报告解释。

### Agent 调用契约，不依赖源码

Agent 发现有类型约束的操作并接收结构化响应，不需要导入 ABI 内部模块，也不需要为每次运行重新生成 Shell 流程。

## 契约与数据流

| 边界 | 输入 | 输出 |
| --- | --- | --- |
| 用户到 ABI | 分析类型、YAML 配置、TSV 样本表、运行时参数 | 已验证请求或结构化诊断 |
| 规划器到执行器 | `ExecutionPlan` 和步骤契约 | 有序且已授权的工作 |
| 工具到插件 | 文件、目录、JSON、TSV 或日志 | 已解析的工作流特有数据 |
| 插件到 ABI 结果层 | 已发布产物和标准表格行 | 稳定的结果目录和报告输入 |
| ABI 到用户或 Agent | 人类文本或 JSON 信封 | 计划、诊断、产物、报告或恢复建议 |

声明式 DAG 是依赖关系和步骤输出契约的单一事实来源；`environments.yaml` 是工具到环境映射的单一事实来源。

## 部署方式

| 方式 | 适合场景 | 入口 |
| --- | --- | --- |
| 本地 CLI | 探索、开发和单机运行 | `abi` |
| Docker | 隔离插件运行环境和可重复部署 | `docker/Dockerfile.*` |
| Nextflow 或 HPC | 调度器支持和可恢复计算 | `abi export-nextflow`、`abi run --engine hpc` |
| MCP | 使用 stdio 工具的交互式 Agent 平台 | `abi-mcp` |
| HTTP Job Service | 排队、异步或远程管理的任务 | `abi job-service`、`abi job ...` |
| 无头 dispatch | 子进程 worker 和传输适配器 | `abi dispatch` |

## 修改代码时如何选择边界

| 变更 | 所属边界 |
| --- | --- |
| 新增工作流步骤或生物学断言 | 插件 DAG 和插件测试 |
| 新增通用验证或溯源机制 | 核心模块和核心测试 |
| 新增 CLI、MCP 或 HTTP 表达 | 调用 `ABIAgentInterface` 的传输适配器 |
| 新增或迁移工具环境 | `environments.yaml` 和生成的 `envs/*.yml` |
| 修改标准结果布局 | 结果核心、插件映射、兼容性测试和文档 |
| 新增图形类型 | `abi.sciplot` Schema、渲染器、质检规则和图形测试 |

继续阅读[使用 ABI](usage_guide.md)了解标准操作流程；修改代码前，请先阅读[开发规范](development_workflow.md)。
