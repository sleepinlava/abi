ABI Documentation
==================

**Agent-Bioinformatics Interface** — a Python control plane between AI agents
and bioinformatics tools.  Not a workflow engine, but a structured interface
layer that provides standardized JSON envelopes, provenance tracking, tool
contracts, and execution gating across seven bioinformatics analysis types.

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

----

Install
-------

.. code-block:: bash

   pip install abi-agent

Python 3.10–3.13 is supported.

.. code-block:: bash

   # Development install with all extras
   pip install -e ".[dev,docs,mcp]"

----

What is ABI?
------------

ABI sits between AI agents and bioinformatics tools, providing a **standardized
interface** so agents can plan, execute, and inspect bioinformatics workflows
without needing to write code or understand tool internals.

- **For bioinformaticians**: define analysis pipelines as plugins with tool
  contracts, parsers, and DAGs — ABI handles the agent-facing interface,
  provenance, and execution gating automatically.
- **For AI agents**: discover plugins, build execution plans, run tools (with
  explicit confirmation), and interpret results — all through typed JSON
  envelopes and structured diagnostic hints.

Key Design Principles
---------------------

.. list-table::
   :header-rows: 0
   :widths: 30 70

   * - **Thick Core**
     - Lifecycle, permissions, diagnostics, provenance, and standard tables
       live in Core — not duplicated across plugins.
   * - **Thin Transport**
     - CLI, OpenAI tools, Anthropic tools, MCP, HTTP — each is just an adapter
       calling the same ``ABIAgentInterface``.
   * - **Plugin owns biology**
     - Tool selection, parsing, and report interpretation are per-plugin; Core
       handles mechanism: contracts, DAGs, provenance, execution gating.
   * - **Agent never codes**
     - Agents interact through JSON envelopes, tool descriptors, and
       diagnostic hints — never by importing Python modules.

Built-In Analysis Types
-----------------------

.. list-table::
   :header-rows: 1
   :widths: 25 75

   * - Plugin
     - Description
   * - ``amplicon_16s``
     - 16S rRNA microbiome: cutadapt → vsearch merge/derep/denoise → SINTAX
       taxonomy → MAFFT+FastTree phylogeny → diversity (alpha/beta)
   * - ``rnaseq_expression``
     - Bulk RNA-seq: fastp → STAR → featureCounts → build_count_matrix →
       DESeq2 → clusterProfiler
   * - ``wgs_bacteria``
     - Bacterial isolate WGS: fastp → SPAdes → Prokka → MLST → AMRFinderPlus
   * - ``metatranscriptomics``
     - Metatranscriptomics: fastp → STAR/HISAT2 → featureCounts
   * - ``metagenomic_plasmid``
     - Flagship plasmid analysis: QC → assembly → plasmid detection →
       annotation → abundance → statistics. DAG-driven planning (UniversalDAG),
       parallel execution, standardized tables, and SciPlot figures.
   * - ``easymetagenome``
     - P0 shotgun metagenomics: fastp → kneaddata → kraken2 → bracken →
       HUMAnN utilities → seqkit. Includes taxonomy, functional profiling,
       manifest validation, and schema-driven reports.
   * - ``viral_viwrap``
     - Viral metagenomics via ViWrap 1.3.1: binning → taxonomy → host
       prediction → quality filtering. Managed external CLI plugin with
       custom ToolSkill, environment checker, and artifact mapper.

Run ``abi list-types --output-json`` for the authoritative installed plugin list.

Quick Start
-----------

.. code-block:: bash

   # Discover available plugins
   abi list-types

   # Lightweight metadata query (~50ms, reads DAG + tool registry)
   abi query --type metagenomic_plasmid --what stages
   abi query --type metagenomic_plasmid --what tools
   abi query --type metagenomic_plasmid --step qc_fastp --what inputs

   # Plan a workflow (no execution) — includes summary for token-efficient AI agents
   abi plan --type amplicon_16s --sample-sheet samples.tsv --config config.yaml

   # Dry-run: validate inputs, write plan + table skeletons
   abi dry-run --type amplicon_16s --sample-sheet samples.tsv --config config.yaml

   # Execute with explicit confirmation
   abi run --type amplicon_16s --sample-sheet samples.tsv --config config.yaml \
     --confirm-execution

   # Inspect results + generate report
   abi inspect --result-dir results/
   abi report --result-dir results/ --type amplicon_16s

   # Export tool descriptors for AI agents
   abi export-tools --type metagenomic_plasmid --format openai --provider openai
   abi export-tools --type metagenomic_plasmid --format anthropic
   abi export-tools --type metagenomic_plasmid --format gemini

   # Start MCP server for Claude Desktop / Claude Code
   abi-mcp

   # Install agent skills
   abi install-skills

All agent-facing commands support ``--output-json``.

.. toctree::
   :maxdepth: 1
   :caption: Getting Started
   :hidden:

   development
   plugin_development_guide
   testing

.. toctree::
   :maxdepth: 1
   :caption: Plugin Guides
   :hidden:

   metagenomic_plasmid
   rnaseq_expression_workflow
   plugin_report_figure_spec

.. toctree::
   :maxdepth: 1
   :caption: Core Reference
   :hidden:

   api
   abi_spec_v0.1
   abi_sciplot_design
   openai_interface_standard
   workflow_validation
   hpc_development

.. toctree::
   :maxdepth: 1
   :caption: Operations
   :hidden:

   agent_usage
   job_service
   runtime_locks
   release
   devlog
   paper_execution_plan

Quick Links
-----------

- :doc:`api` — Full Python API reference (auto-generated)
- :doc:`abi_sciplot_design` — Scientific figure compiler design
- :doc:`development` — Local setup, source tree, SDK reference
- :doc:`plugin_development_guide` — How to add a new analysis type
- :doc:`runtime_locks` — Release-ready runtime lock generation and validation
- :doc:`workflow_validation` — Biological validation methodology
- :doc:`openai_interface_standard` — Multi-LLM tool descriptor export
- :doc:`agent_usage` — Agent integration guide (MCP, Skills, dispatch)
- :doc:`devlog` — Development log
- :doc:`paper_execution_plan` — Paper execution stratification and verification

Indices and Tables
------------------

- :ref:`genindex`
- :ref:`modindex`
