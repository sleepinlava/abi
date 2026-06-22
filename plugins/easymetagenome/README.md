# EasyMetagenome-style ABI Plugin

This is an ABI-owned structural reimplementation of the EasyMetagenome P0
workflow: manifest validation, SeqKit statistics, fastp QC, KneadData host
removal, Kraken2 classification, Bracken abundance estimation, table merging,
diversity, and reporting. It does not vendor or invoke EasyMetagenome's GPLv3
Shell source.

The standard ABI entry point is the `easymetagenome` analysis type. The
document-format loader is available as `P0Workflow`; its `dry_run()` expands
every sample and P/G/S Bracken node, while `run()` enforces fail-fast execution,
non-empty output checks, and node-level resume.
