ABI 文档
==============================

ABI 让科研人员和 AI Agent 通过统一、可预期且受确认门保护的接口运行可复现生物信息学流程。先选择目标，再从只读发现逐步进入经过审查的正式执行。

.. image:: https://img.shields.io/pypi/v/abi-agent?style=flat-square&color=1e6fba
   :target: https://pypi.org/project/abi-agent/
   :alt: PyPI
.. image:: https://img.shields.io/pypi/pyversions/abi-agent?style=flat-square
   :target: https://pypi.org/project/abi-agent/
   :alt: Python
.. image:: https://img.shields.io/github/actions/workflow/status/sleepinlava/abi/ci.yml?branch=master&style=flat-square
   :target: https://github.com/sleepinlava/abi/actions/workflows/ci.yml
   :alt: CI
.. image:: https://img.shields.io/badge/docs-Furo-blue?style=flat-square
   :target: https://sleepinlava.github.io/abi/
   :alt: Docs

.. raw:: html

   <div style="margin: 1rem 0; padding: 0.8rem 1rem; background: var(--color-admonition-background); border-radius: 8px; font-size: 0.95rem;">
   🌐 <a href="../en/">English</a> &nbsp;|&nbsp; <strong>中文</strong>
   </div>

从这里开始
------------------------------

.. list-table::
   :header-rows: 1
   :widths: 34 66

   * - 你的目标
     - 建议先阅读
   * - 理解组件和请求流
     - :doc:`components_and_architecture`
   * - 安全运行一次分析
     - :doc:`usage_guide`
   * - 连接 AI Agent
     - :doc:`agent_usage`
   * - 新增或修改工作流
     - :doc:`development_workflow` 和 :doc:`plugin_development_guide`
   * - 部署队列任务或生产环境
     - :doc:`job_service`、:doc:`hpc_development` 和 :doc:`runtime_locks`

安装
------------------------------

ABI 支持 Python 3.10–3.13。

.. code-block:: bash

   pip install abi-agent
   abi --version

按需安装可选能力：

.. code-block:: bash

   pip install "abi-agent[mcp]"       # MCP 服务
   pip install "abi-agent[report]"    # 科研图形和增强报告

五分钟示例
------------------------------

在源码仓库根目录中，内置宏转录组 fixture 无需安装分析工具和参考索引，即可生成执行计划与 dry-run 结果。

.. code-block:: bash

   abi list-types
   abi query --type metatranscriptomics --what stages

   abi plan \
     --type metatranscriptomics \
     --config examples/metatranscriptomics/config_demo.yaml \
     --sample-sheet examples/sample_sheet_transcriptomics.tsv \
     --outdir results/docs-plan

   abi dry-run \
     --type metatranscriptomics \
     --config examples/metatranscriptomics/config_demo.yaml \
     --sample-sheet examples/sample_sheet_transcriptomics.tsv \
     --outdir results/docs-dry-run

该 fixture 包含参考资源占位路径，只用于演示规划和 dry-run，不是可直接执行的生物学配置。准备真实配置请继续阅读 :doc:`usage_guide`。

理解 ABI
------------------------------

ABI 把传输、通用工作流机制、生物学插件、运行时执行和结果发布分开，使所有 Agent 集成都保持轻量，并共享相同的安全与结果契约。

.. toctree::
   :maxdepth: 1
   :caption: 组件与架构

   components_and_architecture
   abi_spec_v0.1
   openai_interface_standard
   abi_sciplot_design

使用 ABI
------------------------------

标准生命周期为 ``query -> plan -> check -> dry-run -> run -> inspect -> report``，真实执行必须得到明确确认。

.. toctree::
   :maxdepth: 1
   :caption: 使用方法与示例

   usage_guide
   agent_usage
   job_service
   hpc_development
   metagenomic_plasmid
   rnaseq_expression_workflow

开发 ABI
------------------------------

从验收标准开始，选择正确的架构边界，添加回归测试，并运行与受影响发布表面相匹配的质量门禁。

.. toctree::
   :maxdepth: 1
   :caption: 开发规范

   development_workflow
   development
   plugin_development_guide
   plugin_report_figure_spec
   testing
   workflow_validation
   real_data_validation_datasets
   production_manual_acceptance_checklist

运维与发布
------------------------------

生产使用需要固定版本、验证工具和数据库、定义代表性生物学验收标准，并生成严格运行时锁。

.. toctree::
   :maxdepth: 1
   :caption: 运维与发布

   runtime_locks
   release
   devlog

组件摘要
------------------------------

.. list-table::
   :header-rows: 1
   :widths: 26 74

   * - 层级
     - 面向用户的职责
   * - 传输层
     - CLI、JSON、MCP、模型工具描述、dispatch 和 HTTP Job
   * - 核心层
     - 规划、权限、诊断、契约、溯源、表格和报告
   * - 插件层
     - 分析特有工具、DAG 分支、解析器、断言和结果解释
   * - 运行时
     - 本地、Conda、Docker、Nextflow、HPC 和云端执行
   * - 结果层
     - 执行计划、溯源、标准 TSV、报告和科研图形

所有面向 Agent 的命令都支持 ``--output-json``。当前环境的权威插件列表以 ``abi list-types --output-json`` 为准。

索引与表
------------------------------

* :ref:`genindex`
* :ref:`modindex`
