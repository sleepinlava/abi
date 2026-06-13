"""Annotation wrappers use GenericCommandSkill through the registry."""

from abi.plugins.metagenomic_plasmid._engine.skills.base import GenericCommandSkill, RunResult, ToolSkill

__all__ = ["GenericCommandSkill", "RunResult", "ToolSkill"]
