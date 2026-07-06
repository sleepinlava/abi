"""Tests for context_resolver.py."""

from __future__ import annotations

from abi.plugins.metagenomic_plasmid._engine.context_resolver import (
    DATA_PROFILE_BY_PLATFORM,
    PlasmidContextResolver,
    _annotation_tools,
    _category_enabled,
    _data_profile_dag,
    _default_tools_for_category,
    _enable_state,
    _is_isolate_profile,
    _requested,
    config_for_sample,
)
from abi.schemas import SampleContext, SampleInput


def _mk(**kw) -> SampleInput:
    d = dict(platform="illumina", sample_id="S1", read1="data/R1.fq", read2="data/R2.fq")
    d.update(kw)
    return SampleInput(**d)


def _ctx(samps=None, **kw) -> SampleContext:
    s = samps or [_mk()]
    m = kw.pop("multi_sample", len(s) > 1)
    h = kw.pop("has_groups", len({x.group for x in s if x.group}) >= 2)
    return SampleContext(samples=s, multi_sample=m, has_groups=h, **kw)


def _cfg(**kw):
    c = {
        "workflow": {"data_profile": "illumina_short"},
        "input": {"read1": "d/R1.fq", "read2": "d/R2.fq"},
    }
    c.update(kw)
    return c


class TestRequested:
    def test_bool_true(self):
        assert _requested(True)

    def test_bool_false(self):
        assert not _requested(False)

    def test_str_false(self):
        assert not _requested("false")

    def test_str_no(self):
        assert not _requested("no")

    def test_str_off(self):
        assert not _requested("off")

    def test_str_auto(self):
        assert _requested("auto")

    def test_int_0(self):
        assert _requested(0)

    def test_none(self):
        assert _requested(None)


class TestEnableState:
    def test_true(self):
        assert _enable_state({"x": {"enable": True}}, "x")

    def test_false(self):
        assert not _enable_state({"x": {"enable": False}}, "x")

    def test_missing(self):
        assert _enable_state({}, "x")

    def test_custom_default(self):
        assert not _enable_state({}, "x", default=False)

    def test_none_block(self):
        assert not _enable_state({"x": None}, "x", default=False)


class TestIsIsolateProfile:
    def test_isolate(self):
        assert _is_isolate_profile("isolate")

    def test_isolate_plasmid(self):
        assert _is_isolate_profile("isolate_plasmid")

    def test_suffix(self):
        assert _is_isolate_profile("x_isolate")

    def test_default(self):
        assert not _is_isolate_profile("default")

    def test_upper_no_suffix(self):
        assert not _is_isolate_profile("ISOLATE")


class TestDataProfileByPlatform:
    def test_values(self):
        assert DATA_PROFILE_BY_PLATFORM["illumina"] == "illumina_short"
        assert DATA_PROFILE_BY_PLATFORM["ont"] == "ont_long"


class TestDefaultToolsForCategory:
    def test_detection(self):
        assert _default_tools_for_category("plasmid_detection", "x") == ["genomad"]

    def test_binning(self):
        assert _default_tools_for_category("plasmid_binning", "x") == ["gplas2"]

    def test_typing_isolate(self):
        assert len(_default_tools_for_category("typing", "isolate")) == 2

    def test_typing_non_isolate(self):
        assert _default_tools_for_category("typing", "d") == []

    def test_host_short(self):
        assert _default_tools_for_category("host_prediction", "illumina_short") == ["metaphlan"]


class TestAnnotationTools:
    def test_bakta(self):
        tools = _annotation_tools(_cfg(annotation={"general_annotator": "bakta"}), "x")
        assert "bakta" in tools

    def test_none_skipped(self):
        tools = _annotation_tools(_cfg(annotation={"general_annotator": "none"}), "x")
        assert len(tools) == 0

    def test_arg_tools(self):
        tools = _annotation_tools(
            _cfg(annotation={"general_annotator": "bakta", "arg_tools": ["abr"]}), "x"
        )
        assert "abr" in tools

    def test_isolate_adds_mob_suite(self):
        tools = _annotation_tools(_cfg(annotation={"general_annotator": "bakta"}), "isolate")
        assert "mob_suite" in tools

    def test_non_mapping(self):
        assert _annotation_tools(_cfg(annotation="x"), "x") == []


class TestDataProfileDag:
    def test_workflow(self):
        assert _data_profile_dag(_mk(), _cfg(workflow={"data_profile": "dp"})) == "dp"

    def test_fallback_to_input(self):
        c = _cfg()
        c.pop("workflow")
        c["input"] = {"data_profile": "dp2"}
        assert _data_profile_dag(_mk(), c) == "dp2"

    def test_platform_map(self):
        c = _cfg()
        c.pop("workflow")
        assert _data_profile_dag(_mk(platform="ont"), c) == "ont_long"

    def test_unknown_platform(self):
        c = _cfg()
        c.pop("workflow")
        assert _data_profile_dag(_mk(platform="generic"), c) == "generic"


class TestCategoryEnabled:
    def test_false(self):
        assert not _category_enabled({"a": {"enable": False}}, "a", "x", _mk())

    def test_true(self):
        assert _category_enabled({"a": {"enable": True}}, "a", "x", _mk())

    def test_auto_abundance(self):
        assert _category_enabled({"a": {"enable": "auto"}}, "a", "x", _mk())

    def test_auto_typing_isolate(self):
        assert _category_enabled({"t": {"enable": "auto"}}, "typing", "isolate", _mk())

    def test_comparative_false(self):
        assert not _category_enabled(
            {"comparative_genomics": {"enable": "auto"}}, "comparative_genomics", "x", _mk()
        )


class TestConfigForSample:
    def test_returns_dict(self):
        assert isinstance(config_for_sample(_cfg(), _mk()), dict)

    def test_deep_copies(self):
        o = _cfg()
        c = config_for_sample(o, _mk())
        c["x"] = 1
        assert "x" not in o

    def test_long_reads(self):
        c = config_for_sample(
            _cfg(), _mk(platform="ont", read1=None, read2=None, long_reads="lr.fq")
        )
        assert c["input"]["long_reads"] == "lr.fq"

    def test_host_ref(self):
        c = config_for_sample(_cfg(), _mk(host_reference="hg38.fa"))
        assert c["host_removal"]["host_reference"] == "hg38.fa"


class TestResolver:
    def test_resolve_returns_dict(self):
        r = PlasmidContextResolver(_cfg(), _ctx()).resolve()
        assert isinstance(r, dict)
        assert "sample_analysis" in r

    def test_resolve_no_abundance(self):
        r = PlasmidContextResolver(
            _cfg(workflow={"data_profile": "assembly_only"}),
            _ctx([_mk(platform="assembly", read1=None, read2=None)]),
        ).resolve()
        assert not r["sample_analysis"]["run_diversity"]

    def test_resolve_multi(self):
        s = [_mk(sample_id=f"S{i}") for i in range(1, 5)]
        r = PlasmidContextResolver(_cfg(), _ctx(s)).resolve()
        assert isinstance(r, dict)

    def test_eligibility_keys(self):
        pcr = PlasmidContextResolver(_cfg(), _ctx())
        pcr.resolve()
        e = pcr.eligibility()
        for k in ("diversity", "differential_abundance", "network", "host_plasmid_coabundance"):
            assert k in e
            assert "run" in e[k]
            assert "sample_count" in e[k]

    def test_eligibility_count(self):
        pcr = PlasmidContextResolver(_cfg(), _ctx())
        pcr.resolve()
        assert pcr.eligibility()["diversity"]["sample_count"] == 1
