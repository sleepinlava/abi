from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from abi.agent import ABIAgentInterface


@pytest.mark.smoke
@pytest.mark.requires_tools
@pytest.mark.parametrize(
    ("analysis_type", "config_env"),
    [
        ("wgs_bacteria", "ABI_REAL_WGS_CONFIG"),
        ("metatranscriptomics", "ABI_REAL_METATRANSCRIPTOMICS_CONFIG"),
        ("metagenomic_plasmid", "ABI_REAL_PLASMID_CONFIG"),
    ],
)
def test_real_plugin_end_to_end_from_config(analysis_type, config_env):
    """Run a real end-to-end workflow when its site-specific config is supplied."""
    config_value = os.environ.get(config_env)
    if not config_value:
        pytest.skip(f"set {config_env} to a real-tool config to enable this smoke test")
    config = Path(config_value)
    if not config.is_file():
        pytest.fail(f"{config_env} does not point to a file: {config}")

    response = json.loads(
        ABIAgentInterface().run(
            analysis_type=analysis_type,
            config_path=config,
            profile="real",
            confirm_execution=True,
            smoke=False,
        )
    )

    assert response["status"] == "success", response
    assert response["result"]["return_code"] == 0
