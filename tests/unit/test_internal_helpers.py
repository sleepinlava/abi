"""Unit tests for uncovered branches in abi.internal, abi.config, and abi.resources."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from abi.config import _resolve_project_root, env_resource_overrides, load_resource_profile
from abi.internal import _run_generic_preflight
from abi.resources import (
    _configured_or_default_resource_path,
    _is_placeholder_resource_value,
)

# --------------------------------------------------------------------------- #
#  Module 1: abi.internal  --  _run_generic_preflight
# --------------------------------------------------------------------------- #


def _mock_plugin(*, samples=(), check_resources_fn=None, check_tools_fn=None, plugin_id="test"):
    """Build a lightweight mock plugin via SimpleNamespace."""
    kwargs: dict = {
        "build_sample_context": lambda config, check_files: SimpleNamespace(samples=list(samples)),
        "plugin_id": plugin_id,
    }
    if check_resources_fn is not None:
        kwargs["check_resources"] = check_resources_fn
    if check_tools_fn is not None:
        kwargs["registry"] = lambda: SimpleNamespace(check_tools=check_tools_fn)
    return SimpleNamespace(**kwargs)


class TestPreflightSampleContext:
    def test_success_populates_sample_count(self):
        plugin = _mock_plugin(samples=["s1", "s2"])
        result = _run_generic_preflight(plugin, {}, check_runtime=False)

        inputs_check = result["checks"][0]
        assert inputs_check["name"] == "inputs"
        assert inputs_check["status"] == "pass"
        assert inputs_check["sample_count"] == 2
        assert result["status"] == "pass"

    def test_failure_records_exception(self):
        def _raise(*a, **kw):
            raise RuntimeError("sample explosion")

        plugin = SimpleNamespace(
            build_sample_context=_raise,
            plugin_id="test",
        )
        result = _run_generic_preflight(plugin, {}, check_runtime=False)

        inputs_check = result["checks"][0]
        assert inputs_check["name"] == "inputs"
        assert inputs_check["status"] == "fail"
        assert "sample explosion" in inputs_check["message"]
        assert result["status"] == "fail"


class TestPreflightResourceChecker:
    def test_maps_resource_rows_into_checks(self):
        def check_resources(config):
            return [
                {"resource_id": "db1", "status": "ok"},
                {"resource_id": "db2", "status": "missing"},
                {"resource_id": "db3", "status": "not_required"},
            ]

        plugin = _mock_plugin(check_resources_fn=check_resources)
        result = _run_generic_preflight(plugin, {}, check_runtime=False)

        resource_checks = [c for c in result["checks"] if c["name"].startswith("resource:")]
        assert len(resource_checks) == 3

        assert resource_checks[0]["status"] == "pass"  # ok
        assert resource_checks[1]["status"] == "fail"  # missing
        assert resource_checks[2]["status"] == "pass"  # not_required

    def test_exception_produces_failure_check(self):
        def check_resources(config):
            raise RuntimeError("resource checker crashed")

        plugin = _mock_plugin(check_resources_fn=check_resources)
        result = _run_generic_preflight(plugin, {}, check_runtime=False)

        resource_fail = [c for c in result["checks"] if c["name"] == "resources"]
        assert len(resource_fail) == 1
        assert resource_fail[0]["status"] == "fail"
        assert "resource checker crashed" in resource_fail[0]["message"]

    def test_absent_check_resources_is_skipped(self):
        plugin = _mock_plugin()  # no check_resources
        result = _run_generic_preflight(plugin, {}, check_runtime=False)

        resource_checks = [c for c in result["checks"] if c["name"].startswith("resource:")]
        assert len(resource_checks) == 0


class TestPreflightRuntimeCheck:
    def test_tool_rows_become_checks_when_check_runtime_is_true(self):
        def check_tools(config):
            return [
                {"tool_id": "fastp", "installed": True, "resource_status": "ok", "required": True},
                {
                    "tool_id": "bwa",
                    "installed": False,
                    "resource_status": "missing",
                    "required": True,
                },
            ]

        plugin = _mock_plugin(check_tools_fn=check_tools)
        result = _run_generic_preflight(plugin, {}, check_runtime=True)

        tool_checks = [c for c in result["checks"] if c["name"].startswith("tool:")]
        assert len(tool_checks) == 2

        assert tool_checks[0]["name"] == "tool:fastp"
        assert tool_checks[0]["status"] == "pass"

        assert tool_checks[1]["name"] == "tool:bwa"
        assert tool_checks[1]["status"] == "fail"

    def test_not_required_tool_rows_are_skipped(self):
        def check_tools(config):
            return [
                {"tool_id": "opt", "installed": False, "resource_status": "ok", "required": False},
            ]

        plugin = _mock_plugin(check_tools_fn=check_tools)
        result = _run_generic_preflight(plugin, {}, check_runtime=True)

        tool_checks = [c for c in result["checks"] if c["name"].startswith("tool:")]
        assert len(tool_checks) == 0

    def test_check_runtime_false_skips_tool_checks(self):
        def check_tools(config):
            return [
                {"tool_id": "fastp", "installed": True, "resource_status": "ok", "required": True},
            ]

        plugin = _mock_plugin(check_tools_fn=check_tools)
        result = _run_generic_preflight(plugin, {}, check_runtime=False)

        tool_checks = [c for c in result["checks"] if c["name"].startswith("tool:")]
        assert len(tool_checks) == 0

    def test_runtime_exception_produces_failure_check(self):
        def check_tools(config):
            raise RuntimeError("runtime engine missing")

        plugin = _mock_plugin(check_tools_fn=check_tools)
        result = _run_generic_preflight(plugin, {}, check_runtime=True)

        runtime_fail = [c for c in result["checks"] if c["name"] == "runtime"]
        assert len(runtime_fail) == 1
        assert runtime_fail[0]["status"] == "fail"
        assert "runtime engine missing" in runtime_fail[0]["message"]


class TestPreflightAggregate:
    def test_all_pass_yields_status_pass(self):
        plugin = _mock_plugin(samples=["s1"])
        result = _run_generic_preflight(plugin, {}, check_runtime=False)

        assert result["status"] == "pass"
        assert result["recommendations"] == []
        assert "plugin" in result

    def test_any_failure_yields_status_fail_and_recommendations(self):
        def _raise(*a, **kw):
            raise RuntimeError("boom")

        plugin = SimpleNamespace(
            build_sample_context=_raise,
            check_resources=lambda config: [
                {"resource_id": "db", "status": "missing"},
            ],
            plugin_id="doomed",
        )
        result = _run_generic_preflight(plugin, {}, check_runtime=False)

        assert result["status"] == "fail"
        assert result["checks"][0]["status"] == "fail"  # inputs
        assert result["checks"][1]["status"] == "fail"  # resource:db
        assert len(result["recommendations"]) >= 2
        # Each recommendation references the failed check name
        names = {c["name"] for c in result["checks"] if c["status"] == "fail"}
        rec_names = {rec.split(": ")[-1] for rec in result["recommendations"]}
        assert names == rec_names


# --------------------------------------------------------------------------- #
#  Module 2: abi.config
# --------------------------------------------------------------------------- #


class TestResolveProjectRoot:
    def test_returns_valid_path(self):
        root = _resolve_project_root()
        assert isinstance(root, Path)
        assert root.exists()


class TestLoadResourceProfile:
    def test_valid_profile_returns_data(self, tmp_path, monkeypatch):
        # Build the expected directory structure under tmp_path
        profiles_dir = tmp_path / "config" / "resource_profiles"
        profiles_dir.mkdir(parents=True)
        profile_file = profiles_dir / "dev_small.yaml"
        profile_file.write_text("cpu: 2\nmemory: 4GB\n", encoding="utf-8")

        monkeypatch.setattr("abi.config.PROJECT_ROOT", tmp_path)

        data = load_resource_profile("dev_small")
        assert data == {"cpu": 2, "memory": "4GB"}

    def test_not_found_returns_empty_dict(self, tmp_path, monkeypatch):
        # Point PROJECT_ROOT at an empty directory
        monkeypatch.setattr("abi.config.PROJECT_ROOT", tmp_path)

        data = load_resource_profile("nonexistent")
        assert data == {}


class TestEnvResourceOverrides:
    def test_cpu_memory_walltime(self, monkeypatch):
        monkeypatch.setenv("ABI_DEFAULT_CPU", "8")
        monkeypatch.setenv("ABI_DEFAULT_MEMORY", "32GB")
        monkeypatch.setenv("ABI_DEFAULT_WALLTIME", "04:00:00")

        overrides = env_resource_overrides()
        assert overrides["cpu"] == 8
        assert overrides["memory"] == "32GB"
        assert overrides["walltime"] == "04:00:00"

    def test_accelerator_and_containers(self, monkeypatch):
        monkeypatch.setenv("ABI_ACCELERATOR", "gpu")
        monkeypatch.setenv("ABI_CONTAINER_IMAGE", "my/image:latest")
        monkeypatch.setenv("ABI_CONTAINER_RUNTIME", "singularity")

        overrides = env_resource_overrides()
        assert overrides["accelerator"] == "gpu"
        assert overrides["container_image"] == "my/image:latest"
        assert overrides["container_runtime"] == "singularity"

    def test_invalid_cpu_is_silently_ignored(self, monkeypatch):
        monkeypatch.setenv("ABI_DEFAULT_CPU", "not_a_number")

        overrides = env_resource_overrides()
        assert "cpu" not in overrides

    def test_empty_env_returns_empty_dict(self, monkeypatch):
        for var in (
            "ABI_DEFAULT_CPU",
            "ABI_DEFAULT_MEMORY",
            "ABI_DEFAULT_WALLTIME",
            "ABI_ACCELERATOR",
            "ABI_CONTAINER_IMAGE",
            "ABI_CONTAINER_RUNTIME",
        ):
            monkeypatch.delenv(var, raising=False)

        overrides = env_resource_overrides()
        assert overrides == {}


# --------------------------------------------------------------------------- #
#  Module 3: abi.resources
# --------------------------------------------------------------------------- #


class TestIsPlaceholderResourceValue:
    def test_NOT_CONFIGURED(self):
        assert _is_placeholder_resource_value("NOT_CONFIGURED") is True

    def test_TODO(self):
        assert _is_placeholder_resource_value("TODO") is True

    def test_PLACEHOLDER(self):
        assert _is_placeholder_resource_value("PLACEHOLDER") is True

    def test_path_to_pattern(self):
        assert _is_placeholder_resource_value("/path/to/something") is True
        assert _is_placeholder_resource_value("/your/path/here") is True

    def test_windows_style_path_placeholder(self):
        assert _is_placeholder_resource_value("path\\to\\something") is True

    def test_normal_real_path_is_not_placeholder(self):
        assert _is_placeholder_resource_value("/data/actual/db.fasta") is False

    def test_relative_real_path_is_not_placeholder(self):
        assert _is_placeholder_resource_value("results/db.fasta") is False


class TestConfiguredOrDefaultResourcePath:
    def test_configured_path_takes_precedence(self):
        config = {"resources": {"mytool": "/custom/path"}}
        result = _configured_or_default_resource_path(config, "mytool")
        assert result == Path("/custom/path")

    def test_placeholder_value_falls_back_to_default(self):
        config = {"resources": {"mytool": "NOT_CONFIGURED"}, "outdir": "results"}
        result = _configured_or_default_resource_path(config, "mytool")
        assert result == Path("results") / "resources" / "mytool"

    def test_default_fallback_when_resource_not_in_config(self):
        config = {"resources": {}, "outdir": "results"}
        result = _configured_or_default_resource_path(config, "mytool")
        assert result == Path("results") / "resources" / "mytool"

    def test_default_fallback_when_resources_key_missing(self):
        config = {"outdir": "my_outdir"}
        result = _configured_or_default_resource_path(config, "mytool")
        assert result == Path("my_outdir") / "resources" / "mytool"

    def test_default_fallback_when_outdir_missing(self):
        config: dict = {}
        result = _configured_or_default_resource_path(config, "mytool")
        assert result == Path("results") / "resources" / "mytool"
