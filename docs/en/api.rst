API Reference
=============

.. automodule:: abi
   :members: get_agent_guide, list_plugins_summary
   :undoc-members:
   :exclude-members: __version__

Core Modules
------------

Agent Interface
~~~~~~~~~~~~~~~

.. automodule:: abi.agent
   :members:
   :undoc-members:

Plugins
~~~~~~~

.. automodule:: abi.plugins
   :members: list_plugins, get_plugin

.. automodule:: abi.interfaces
   :members:
   :undoc-members:

Schemas
~~~~~~~

.. automodule:: abi.schemas
   :members:
   :undoc-members:
   :exclude-members: model_computed_fields, model_config, model_fields

Tools & Registry
~~~~~~~~~~~~~~~~

.. automodule:: abi.tools
   :members: ToolRegistry, ToolSkill, GenericCommandSkill, RunResult
   :undoc-members:

Provenance
~~~~~~~~~~

.. automodule:: abi.provenance
   :members: RunLogger, PipelineProgressRecorder
   :undoc-members:

.. automodule:: abi.json_utils
   :members:
   :undoc-members:

Contracts & DAG
~~~~~~~~~~~~~~~

.. automodule:: abi.contracts
   :members:
   :undoc-members:

.. automodule:: abi.dag
   :members: infer_dag, ABIDAG, StepBinding
   :undoc-members:

Diagnostics & Permissions
~~~~~~~~~~~~~~~~~~~~~~~~~

.. automodule:: abi.diagnostics
   :members:
   :undoc-members:

.. automodule:: abi.permissions
   :members:
   :undoc-members:

Execution & Workflow
~~~~~~~~~~~~~~~~~~~~

.. automodule:: abi.executor
   :members:
   :undoc-members:

.. automodule:: abi.workflow.validation
   :members:
   :undoc-members:

Report & Figures
~~~~~~~~~~~~~~~~

.. automodule:: abi.report
   :members:
   :undoc-members:

.. automodule:: abi.figures
   :members:
   :undoc-members:

Shared Utilities
~~~~~~~~~~~~~~~~

.. automodule:: abi._shared
   :members:
   :undoc-members:

Testing Utilities
~~~~~~~~~~~~~~~~~

.. automodule:: abi.testing
   :members:
   :undoc-members:

Plugin API Reference
--------------------

Each plugin implements the :class:`abi.interfaces.ABIPlugin` protocol.

.. automodule:: abi.plugins.rnaseq_expression
   :members:
   :undoc-members:

.. automodule:: abi.plugins.wgs_bacteria
   :members:
   :undoc-members:

.. automodule:: abi.plugins.amplicon_16s
   :members:
   :undoc-members:

.. automodule:: abi.plugins.metatranscriptomics
   :members:
   :undoc-members:
