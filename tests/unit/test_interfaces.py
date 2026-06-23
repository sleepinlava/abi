from __future__ import annotations

from pathlib import Path

from abi.interfaces import (
    ABIDryRunPlugin,
    ABIInitializablePlugin,
    ABIPlugin,
    ABIResourcePlugin,
    ABIResultValidationPlugin,
)


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


class ResourcePlugin(CompletePlugin):
    def check_resources(self, config, *, resource_ids=None):
        return []

    def setup_resources(self, config, *, resource_ids=None, dry_run=False, mock=False):
        return []


class ResultValidationPlugin(CompletePlugin):
    def validate_result_dir(self, result_dir, *, allow_empty_tables=True):
        return {"valid": True}


def test_base_plugin_protocol_is_structural_and_runtime_checkable():
    assert isinstance(CompletePlugin(), ABIPlugin)
    assert not isinstance(object(), ABIPlugin)


def test_dry_run_protocol_requires_dedicated_method():
    assert isinstance(DryRunPlugin(), ABIDryRunPlugin)
    assert not isinstance(CompletePlugin(), ABIDryRunPlugin)


def test_initializable_protocol_requires_root_attribute():
    assert isinstance(InitializablePlugin(), ABIInitializablePlugin)
    assert not isinstance(CompletePlugin(), ABIInitializablePlugin)


def test_resource_protocol_requires_check_and_setup_methods():
    assert isinstance(ResourcePlugin(), ABIResourcePlugin)
    assert not isinstance(CompletePlugin(), ABIResourcePlugin)


def test_result_validation_protocol_is_optional():
    assert isinstance(ResultValidationPlugin(), ABIResultValidationPlugin)
    assert not isinstance(CompletePlugin(), ABIResultValidationPlugin)
