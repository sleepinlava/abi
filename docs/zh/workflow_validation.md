# 工作流验证与科学证据计划

本文档追踪 ABI 能否成为一个受约束、可验证且可复现的工作流，其生物学路线有已发表方法作为支撑。

## 当前评估

ABI 已是一个强大的工作流控制层：

- **受约束**：计划由插件 schema 和 metagenomic plasmid DAG 生成；外部执行有确认门控；步骤合约强制执行输出存在性、大小、扩展名、目录内容、文件数量、FASTA contig 数量、JSON 必需键、JSON schema 字段、断言以及校验和链式追踪。
- **可验证**：运行写入 `execution_plan.json`、`provenance/commands.tsv`、`resolved_inputs.tsv`、`tool_versions.tsv`、`resources.json`、`run_summary.json`、步骤日志、标准表和报告。
- **结构上可复现**：相同的配置/样本表应生成相同的计划和规范的产物布局；校验和保留下游文件身份。
- **文献对齐**：核心路线阶段使用具有已发表方法论文的成熟生物信息学工具。

该代码库**尚不应**被描述为经过充分验证的科学工作流。已发表的组件工具支持该路线，但系统级可靠性仍需固定的环境、数据库清单、基准数据集、预期的生物学输出以及文档化的验收阈值。

## 证据主干

下表是默认 metagenomic plasmid 路线的初始证据主干。它有意保持保守：每个参考文献支持一个组件方法，而非将完整的 ABI 工作流作为一项集成的科学声明。

| 工作流阶段 | ABI 工具 | 文献证据 | 支持内容 | 剩余 ABI 验证工作 |
| --- | --- | --- | --- | --- |
| 读段 QC 与修剪 | `fastp` | Chen et al., 2018, Bioinformatics, DOI: [10.1093/bioinformatics/bty560](https://doi.org/10.1093/bioinformatics/bty560) | FASTQ 预处理、接头修剪、质量过滤、JSON/HTML QC 报告 | 固定 fastp 版本，在基准 FASTQ 上断言修剪前后的读段数量不变量。 |
| 跨样本 QC 报告 | `multiqc` | Ewels et al., 2016, Bioinformatics, DOI: [10.1093/bioinformatics/btw354](https://doi.org/10.1093/bioinformatics/btw354) | 跨工具和样本的聚合 QC 报告 | 在启用 MultiQC 时添加预期的 MultiQC 产物检查。 |
| 短读段宏基因组组装 | `megahit` | Li et al., 2015, Bioinformatics, DOI: [10.1093/bioinformatics/btv033](https://doi.org/10.1093/bioinformatics/btv033) | 使用简洁 de Bruijn 图进行大规模复杂宏基因组组装 | 维护带有最低 N50/contig 数量阈值的组装基准 fixtures。 |
| 可移动遗传元件检测 | `genomad` | Camargo et al., 2023, Nature Biotechnology, DOI: [10.1038/s41587-023-01953-y](https://doi.org/10.1038/s41587-023-01953-y) | 质粒、病毒和其他可移动遗传元件的鉴定 | 版本化 geNomad 数据库，在冒烟数据集上断言已知阳性质粒/病毒命中。 |
| 细菌基因组注释 | `bakta` | Schwengers et al., 2021, Microbial Genomics, DOI: [10.1099/mgen.0.000685](https://doi.org/10.1099/mgen.0.000685) | 快速标准化的细菌基因组注释和结构化输出 | 对已知参考质粒添加注释验收检查。 |
| 基因预测子任务 | `prodigal` | Hyatt et al., 2010, BMC Bioinformatics, DOI: [10.1186/1471-2105-11-119](https://doi.org/10.1186/1471-2105-11-119) | 原核生物编码序列预测 | 在启用时要求生成 GFF/FAA/FFN 文件和最低编码序列计数。 |

## 最终状态验收标准

当以下所有条件满足时，ABI 可被称为受约束、可验证且稳定可复现的工作流：

1. 每条生产路线都有版本化的 DAG、经过 schema 验证的配置，以及为每个馈入下游生物学声明的步骤提供输出合约。
2. 工具环境通过精确的包版本或容器固定，且 `tool_versions.tsv` 记录真实的可执行文件版本，而不仅仅是状态。
3. 每个数据库/模型/参考都有一个清单，包含路径、版本、来源 URL、校验和、许可证说明以及最后验证日期。
4. 每条路线至少有一个小型基准数据集，包含预期的标准表行和生物学断言，在 CI 或可复现的本地测试中进行检查。
5. 报告包含方法溯源：工具版本、数据库版本、参数、引用和已知的解释限制。
6. Golden agent trace 覆盖 plan、dry-run、inspect、run 阻止、故障恢复、report 以及结果验证路径。
7. Nextflow/local 运行时对相同 fixture 输入产生可比较的标准产物。

## 验证路线图

### 第 0 阶段：控制层加固

- 将合约验证扩展到输入，而非仅限于输出和校验和链式追踪。
- 将合约违规提升为 JSON 信封中稳定的诊断错误码。
- 为 `pipeline_dag.yaml` 和 `tool_contracts/*.yaml` 添加 contract-lint 命令。
- 在每次变更中保持 `pytest`、`ruff check`、`ruff format --check` 和 `mypy src/abi/` 通过。

### 第 1 阶段：可复现性清单

- 在可用的情况下通过真实的 `--version` 探测生成 `provenance/tool_versions.tsv`。
- 添加带有数据库/模型校验和的 `provenance/resource_manifest.json`。
- 通过显式的 conda lock 文件或容器固定冒烟测试环境。
- 以机器可读形式记录命令模板和解析后的命令令牌。

### 第 2 阶段：生物学基准

- 添加精心策划的小型阳性对照：已知质粒参考、阴性染色体对照以及混合样本。
- 定义质粒调用、注释、丰度行以及报告内容的标准表验收检查。
- 附加预期失败案例：缺失数据库、格式错误的样本表、空输出、交换的 R1/R2 以及不兼容的平台/输入组合。

### 第 3 阶段：文献与报告

- 添加按工具 ID 和工作流阶段索引的引用注册表。
- 将引用和方法限制输出到 `report/methods.md`。
- 将 `pipeline_dag.yaml` 中的每条默认路线链接到证据条目和验证 fixtures。
- 逐一审查质粒特定的可选工具，并在文档中将每个标记为 `validated`、`available` 或 `experimental`。
