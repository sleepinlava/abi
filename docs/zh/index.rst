ABI 文档
==========

**Agent-Bioinformatics Interface** — 一个位于 AI Agent 和生物信息学工具之间的
Python 控制平面。ABI 不是一个工作流引擎，而是一个提供标准化 JSON 信封、
溯源跟踪、工具合约和执行门控的结构化接口层，覆盖五种生物信息学分析类型。

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
   🌐 <a href="/en/">English</a> &nbsp;|&nbsp; <strong>中文</strong>
   </div>

----

安装
----

.. code-block:: bash

   pip install abi-agent

支持 Python 3.10–3.13。

.. code-block:: bash

   # 包含所有扩展的开发安装
   pip install -e ".[dev,docs,mcp]"

----

ABI 是什么？
-----------

ABI 位于 AI Agent 和生物信息学工具之间，提供**标准化接口**，使 Agent 可以在不需要编写代码或理解工具内部细节的情况下规划、执行和检查生物信息学工作流。

- **对生物信息学开发者**：将分析流程定义为带有工具合约、解析器和 DAG 的插件 — ABI 自动处理面向 Agent 的接口、溯源和执行门控。
- **对 AI Agent**：发现插件、构建执行计划、运行工具（需显式确认）并解释结果 — 全部通过类型化 JSON 信封和结构化诊断提示完成。

核心设计原则
-----------

.. list-table::
   :header-rows: 0
   :widths: 30 70

   * - **Core 要厚**
     - 生命周期、权限、诊断、溯源和标准表位于 Core 中 — 不在插件间重复。
   * - **Transport 要薄**
     - CLI、OpenAI tools、Anthropic tools、MCP、HTTP — 每个只是调用同一 ``ABIAgentInterface`` 的适配器。
   * - **Plugin 拥有生物学**
     - 工具选择、解析和报告解释是每个插件特有的；Core 处理机制：合约、DAG、溯源、执行门控。
   * - **Agent 不写代码**
     - Agent 通过 JSON 信封、工具描述符和诊断提示进行交互 — 绝不导入 Python 模块。

内置分析类型
-----------

.. list-table::
   :header-rows: 1
   :widths: 20 8 72

   * - 插件
     - 工具数
     - 说明
   * - ``amplicon_16s``
     - 8
     - 16S rRNA 微生物组：cutadapt → vsearch 合并/去冗余/去噪 → SINTAX
       分类 → MAFFT+FastTree 系统发育 → alpha/beta 多样性
   * - ``rnaseq_expression``
     - 6
     - 批量 RNA-seq：fastp → STAR → featureCounts → build_count_matrix →
       DESeq2 → clusterProfiler
   * - ``wgs_bacteria``
     - 5
     - 细菌分离株 WGS：fastp → SPAdes → Prokka → MLST → AMRFinderPlus
   * - ``metatranscriptomics``
     - 3
     - 宏转录组：fastp → STAR/HISAT2 → featureCounts
   * - ``metagenomic_plasmid``
     - 67
     - 旗舰质粒分析：QC → 组装 → 质粒检测 → 注释 → 丰度 → 统计。
       10 个 conda 环境，84 节点 DAG。

快速开始
--------

.. code-block:: bash

   # 发现可用插件
   abi list-types

   # 轻量级元数据查询
   abi query --type amplicon_16s --what stages

   # 规划工作流（不执行）
   abi plan --type amplicon_16s --sample-sheet samples.tsv --config config.yaml

   # 干运行：验证输入，写入计划和空表骨架
   abi dry-run --type amplicon_16s --sample-sheet samples.tsv --config config.yaml

   # 显式确认后执行
   abi run --type amplicon_16s --sample-sheet samples.tsv --config config.yaml \
     --confirm-execution

   # 检查结果并生成报告
   abi inspect --result-dir results/
   abi report --result-dir results/ --type amplicon_16s

   # 导出 AI Agent 工具描述符
   abi export-tools --type metagenomic_plasmid --format openai --provider openai
   abi export-tools --type metagenomic_plasmid --format anthropic
   abi export-tools --type metagenomic_plasmid --format gemini

   # 启动 MCP 服务器（Claude Desktop / Claude Code）
   abi-mcp

   # 安装 Agent 技能
   abi install-skills

所有面向 Agent 的命令均支持 ``--output-json``。

.. toctree::
   :maxdepth: 1
   :caption: 入门
   :hidden:

   development
   plugin_development_guide

.. toctree::
   :maxdepth: 1
   :caption: 插件指南
   :hidden:

   metagenomic_plasmid

.. toctree::
   :maxdepth: 1
   :caption: 核心参考
   :hidden:

   abi_spec_v0.1
   openai_interface_standard
   workflow_validation

.. toctree::
   :maxdepth: 1
   :caption: 运维
   :hidden:

   agent_usage
   job_service
   release
   development
   plugin_development_guide

快速链接
--------

- `API 参考 (英文) </en/api.html>`_ — 完整 Python API 参考（自动生成）
- :doc:`development` — 本地设置、源码树、SDK 参考
- :doc:`plugin_development_guide` — 如何添加新的分析类型
- :doc:`workflow_validation` — 生物学验证方法
- :doc:`openai_interface_standard` — 多 LLM 工具描述符导出
- :doc:`agent_usage` — Agent 集成指南（MCP、Skills、dispatch）
- :doc:`metagenomic_plasmid` — 旗舰质粒分析插件
- :doc:`job_service` — HTTP Job Service 指南
- :doc:`release` — 发布指南
- `开发日志 (英文) </en/devlog.html>`_ — 开发日志
- `开发计划 (英文) </en/next_development_plan.html>`_ — 下一步开发计划

索引和表
--------

- :ref:`genindex`
- :ref:`modindex`
