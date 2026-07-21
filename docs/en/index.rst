ABI Documentation
=================

ABI lets researchers and AI agents run reproducible bioinformatics workflows
through one predictable, confirmation-gated interface. Start by choosing your
goal, then move from read-only discovery to a reviewed execution plan.

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

Start here
----------

.. list-table::
   :header-rows: 1
   :widths: 34 66

   * - Your goal
     - Start with
   * - Understand the components and request flow
     - :doc:`components_and_architecture`
   * - Run an analysis safely
     - :doc:`usage_guide`
   * - Connect an AI agent
     - :doc:`agent_usage`
   * - Add or change a workflow
     - :doc:`development_workflow` and :doc:`plugin_development_guide`
   * - Deploy queued or production work
     - :doc:`job_service`, :doc:`hpc_development`, and :doc:`runtime_locks`

Install
-------

ABI supports Python 3.10–3.13.

.. code-block:: bash

   pip install abi-agent
   abi --version

Install optional capabilities only when needed:

.. code-block:: bash

   pip install "abi-agent[mcp]"       # MCP server
   pip install "abi-agent[report]"    # Scientific figures and richer reports

Five-minute example
-------------------

From a source checkout, the bundled metatranscriptomics fixture can build a
plan and dry-run without installing analysis tools or a reference index.

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

The fixture contains placeholder reference paths. It demonstrates planning and
dry-run output, not real biological execution. Continue with
:doc:`usage_guide` to prepare a real configuration.

Understand ABI
--------------

ABI separates transport, reusable workflow mechanics, biological plugins,
runtime execution, and result publication. This keeps agent integrations thin
and makes every transport use the same safety and result contracts.

.. toctree::
   :maxdepth: 1
   :caption: Components and Architecture

   components_and_architecture
   abi_spec_v0.1
   api
   openai_interface_standard
   abi_sciplot_design

Use ABI
-------

The standard lifecycle is ``query -> plan -> check -> dry-run -> run -> inspect
-> report``. Real execution requires explicit confirmation.

.. toctree::
   :maxdepth: 1
   :caption: Usage and Examples

   usage_guide
   agent_usage
   job_service
   hpc_development
   metagenomic_plasmid
   rnaseq_expression_workflow

Develop ABI
-----------

Start from acceptance criteria, choose the owning architectural boundary, add
a regression test, and run checks proportional to the affected release surface.

.. toctree::
   :maxdepth: 1
   :caption: Development Standards

   development_workflow
   development
   plugin_development_guide
   plugin_report_figure_spec
   testing
   workflow_validation
   production_manual_acceptance_checklist

Operate and release
-------------------

Production use requires pinned versions, verified tools and databases,
representative biological acceptance criteria, and a strict runtime lock.

.. toctree::
   :maxdepth: 1
   :caption: Operations and Release

   runtime_locks
   release
   devlog
   paper_execution_plan

Component summary
-----------------

.. list-table::
   :header-rows: 1
   :widths: 26 74

   * - Layer
     - User-visible role
   * - Transports
     - CLI, JSON, MCP, provider descriptors, dispatch, and HTTP jobs
   * - Core
     - Planning, permissions, diagnostics, contracts, provenance, tables, reports
   * - Plugins
     - Analysis-specific tools, DAG branches, parsers, assertions, interpretation
   * - Runtimes
     - Local, Conda, Docker, Nextflow, HPC, and cloud execution
   * - Results
     - Execution plan, provenance, standard TSV tables, reports, and figures

All agent-facing commands support ``--output-json``. Use ``abi list-types
--output-json`` for the authoritative plugin list in the current environment.

Indices and tables
------------------

* :ref:`genindex`
* :ref:`modindex`
