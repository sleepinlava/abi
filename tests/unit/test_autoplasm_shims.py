from __future__ import annotations


def test_autoplasm_shims_reexport_canonical_engine_objects():
    from abi.autoplasm.config import load_config as shim_load_config
    from abi.autoplasm.parsers import parse_standard_outputs as shim_parse
    from abi.autoplasm.planner import build_plan_from_dag as shim_build_plan
    from abi.plugins.metagenomic_plasmid._engine.config import load_config
    from abi.plugins.metagenomic_plasmid._engine.parsers import parse_standard_outputs
    from abi.plugins.metagenomic_plasmid import build_plan_from_dag as new_build_plan

    assert shim_load_config is load_config
    assert shim_parse is parse_standard_outputs
    assert shim_build_plan is new_build_plan
