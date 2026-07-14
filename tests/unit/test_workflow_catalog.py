from __future__ import annotations

import pytest

from abi.workflow import WorkflowCatalog, WorkflowPresetError


def test_catalog_lists_presets_in_declared_order():
    catalog = WorkflowCatalog.for_plugin("easymetagenome")

    assert catalog.preset_ids == ("p0_taxonomy", "p1_humann4", "full_read_based")


def test_catalog_resolves_easymetagenome_functional_selection():
    preset = WorkflowCatalog.for_plugin("easymetagenome").resolve("p1_humann4")

    assert preset.include_nodes == (
        "validate_manifest",
        "seqkit_stat_raw",
        "fastp_qc",
        "kneaddata_host_removal",
        "fastp_summary",
        "kneaddata_summary",
        "concat_dehost_reads",
        "humann4_profile",
        "humann_join_genefamilies",
        "humann_renorm_genefamilies",
        "humann_regroup_ko",
        "humann_split_ko",
        "humann_join_pathabundance",
        "humann_renorm_pathabundance",
        "humann_split_pathabundance",
        "functional_report",
    )


def test_catalog_exposes_preset_capabilities_and_resources():
    preset = WorkflowCatalog.for_plugin("easymetagenome").resolve("full_read_based")

    assert (preset.capabilities, preset.required_resources) == (
        frozenset({"taxonomy", "functional"}),
        (
            "host_db",
            "kraken2_db",
            "humann_nucleotide_db",
            "humann_protein_db",
            "metaphlan_db",
        ),
    )


def test_catalog_resolves_viwrap_compatibility_workflow():
    preset = WorkflowCatalog.for_plugin("viral_viwrap").resolve("viwrap_compat")

    assert (preset.include_nodes, preset.capabilities) == ((), frozenset({"compatibility"}))


def test_catalog_rejects_unknown_preset_with_declared_choices():
    catalog = WorkflowCatalog.for_plugin("viral_viwrap")

    with pytest.raises(
        WorkflowPresetError,
        match="Unknown viral_viwrap workflow preset 'viral_native'.*viwrap_compat",
    ):
        catalog.resolve("viral_native")
