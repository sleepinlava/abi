from __future__ import annotations

import importlib

import pytest


@pytest.mark.parametrize(
    "module_name",
    [
        "abi",
        "abi.schemas",
        "abi.openai_contracts",
        "abi.tool_descriptors",
        "abi.diagnostics",
        "abi.permissions",
        "abi.contracts",
        "abi.jobs",
        "abi.sciplot",
    ],
)
def test_every_public_export_exists(module_name):
    module = importlib.import_module(module_name)
    missing = [name for name in module.__all__ if not hasattr(module, name)]
    assert missing == []
