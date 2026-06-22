from __future__ import annotations

from pathlib import Path

from abi.interfaces import ABIDryRunPlugin, ABIInitializablePlugin, ABIPlugin


class CompletePlugin:
    plugin_id = "complete"
    display_name = "Complete"
    description = "Complete protocol implementation"
    report_title = "Complete Report"

    def load_config(self, config_path=None, *, profile=None, overrides=None):
        return {}

    def build_plan(self, config, *, check_files=True):
        return object()

    def registry(self):
        return object()

    def table_schemas(self):
        return {}

    def parse_outputs(self, tool_id, output_dir, sample_id):
        return {}

    def write_report(self, plan, result_dir):
        return {}


class DryRunPlugin(CompletePlugin):
    def execute_dry_run(self, plan, config):
        return {}


class InitializablePlugin(CompletePlugin):
    root = Path("/tmp/plugin")


def test_base_plugin_protocol_is_structural_and_runtime_checkable():
    assert isinstance(CompletePlugin(), ABIPlugin)
    assert not isinstance(object(), ABIPlugin)


def test_dry_run_protocol_requires_dedicated_method():
    assert isinstance(DryRunPlugin(), ABIDryRunPlugin)
    assert not isinstance(CompletePlugin(), ABIDryRunPlugin)


def test_initializable_protocol_requires_root_attribute():
    assert isinstance(InitializablePlugin(), ABIInitializablePlugin)
    assert not isinstance(CompletePlugin(), ABIInitializablePlugin)
