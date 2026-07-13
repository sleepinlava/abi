Stable API Reference
====================

ABI exposes one transport-neutral lifecycle through the CLI, MCP server, HTTP
jobs, and Python. Agent integrations should prefer JSON envelopes and must not
parse human-readable terminal output.

Agent Boundary
--------------

Every agent-facing operation returns one of three statuses:

``success``
   The ``result`` field contains the structured payload.
``confirmation_required``
   Execution is waiting for explicit user approval.
``error``
   Inspect ``error_code`` and ``diagnostic_hints`` before retrying.

The safe lifecycle is ``list-types`` → ``plan`` → ``dry-run`` → ``inspect`` →
``run`` → ``report``. All CLI lifecycle commands accept ``--output-json``.
See :doc:`agent_usage` for MCP configuration, exported tool descriptors,
permissions, examples, and recovery rules.

Python Entry Points
-------------------

The supported Python package entry points are:

``abi.get_agent_guide()``
   Return a compact operating guide suitable for an Agent system prompt.
``abi.list_plugins_summary()``
   Return installed plugin metadata without starting a workflow.
``abi.agent.ABIAgentInterface``
   Transport-neutral implementation behind CLI JSON, MCP, and HTTP adapters.
``abi.plugins.list_plugins()`` and ``abi.plugins.get_plugin()``
   Discover or load registered analysis plugins.

Example:

.. code-block:: python

   import json

   from abi.agent import ABIAgentInterface

   interface = ABIAgentInterface()
   envelope = json.loads(interface.list_types())
   if envelope["status"] == "success":
       print(envelope["result"])

Execution methods require the same explicit confirmation as the CLI. Do not
bypass the lifecycle or call plugin internals from an Agent integration.

Developer Interfaces
--------------------

Plugin authors implement the protocols in ``abi.interfaces`` and declare tools,
DAGs, schemas, and report metadata in their plugin directory. The maintained
contracts and examples live in:

- :doc:`plugin_development_guide` — plugin protocols, manifests, and tests.
- :doc:`workflow_validation` — biological and software validation boundaries.
- :doc:`runtime_locks` — release-ready tools and resource certification.
- :doc:`abi_sciplot_design` — validated scientific figure specifications.
- :doc:`openai_interface_standard` — provider descriptor export formats.

The source repository remains authoritative for concrete Python signatures.
Use the version shown in the documentation announcement when selecting source
for a deployed documentation build.
