ABI Documentation
==================

ABI (Agent-Bioinformatics Interface) is a Python **control plane** between AI
agents and bioinformatics tools — not a workflow engine, but a structured
interface layer that provides standardized JSON envelopes, provenance
tracking, tool contracts, and execution gating across five bioinformatics
analysis types.

.. toctree::
   :maxdepth: 3
   :caption: Contents

   self
   api
   plugin_development_guide
   workflow_validation
   hpc_development
   devlog

.. toctree::
   :maxdepth: 1
   :caption: Plugin Guides

   metagenomic_plasmid
   rnaseq_expression_workflow
   plugin_report_figure_spec

Quick Links
-----------

* :doc:`api` — Full Python API reference
* :doc:`plugin_development_guide` — How to add a new analysis type
* :doc:`workflow_validation` — Biological validation methodology
* :doc:`devlog` — Development log

Indices and Tables
------------------

* :ref:`genindex`
* :ref:`modindex`
