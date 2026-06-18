# Metagenomic Plasmid 集成

`metagenomic_plasmid` ABI 插件使用捆绑的 `abi.autoplasm` 管线
（位于 `plugins/metagenomic_plasmid/_engine/` 中的 39 个 Python 文件，9,006 行代码）。这取代了之前由外部 `autoplasm` 包提供质粒工作流的分离开发模式。

## 公开形态

- PyPI 包：`abi-agent`
- ABI 插件 ID：`metagenomic_plasmid`
- 内部 Python 命名空间：`abi.autoplasm`
- 兼容命令：`autoplasm`
- 工具合约：67 个（质粒管线中的所有生物信息学工具，32 个带有标准化解析器）
- 引擎：`_engine/` 下的 39 个文件（pipeline、planner、DAG、parsers、normalize、report、skills 等）
- 管线 DAG：`pipeline_dag.yaml`（84 个节点，5 个平台，16 张标准表）— 唯一真相来源
- 步骤合约执行：`contracts/step_contract.py` — 输出验证、实际输出解析、断言以及校验和链式追踪

不支持顶层 `import autoplasm` API。

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

## 资源边界

该包包含小型配置、工具合约、测试 fixtures 和示例。不包含真实数据库、mamba 环境或用户结果。

使用 `resources/` 存放本地数据库，并将这些文件保持在 git 之外。

## 验证定位

metagenomic plasmid 路线现已结构化为受约束的工作流：
`pipeline_dag.yaml` 定义节点顺序、输出、合约和断言；
通用执行器写入溯源信息并在每个外部命令成功后执行合约检查。

这尚不等同于经过充分验证的生物学工作流。当前代码库提供了验证所需的控制层，而剩余工作包括固定环境、版本化数据库、整理正/负基准数据集，以及将路线级报告连接到方法引用。详见
[工作流验证与科学证据计划](workflow_validation_zh.md)。
