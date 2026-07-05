"""Tests for template linting."""

from __future__ import annotations

from types import SimpleNamespace

from abi.contracts.lint_template import lint_templates


class _Registry:
    def __init__(self, tools: list[dict]) -> None:
        self._tools = tools

    def list_tools(self) -> list[dict]:
        return list(self._tools)


class _Plugin:
    plugin_id = "demo"

    def __init__(self, root, tools: list[dict]) -> None:
        self.root = root
        self._registry = _Registry(tools)

    def registry(self) -> _Registry:
        return self._registry

    def build_plan(self, config, check_files: bool = False):
        return SimpleNamespace(steps=[])


def test_lint_templates_allows_registry_dag_config_and_common_fields(tmp_path) -> None:
    (tmp_path / "pipeline_dag.yaml").write_text(
        """
nodes:
  demo_node:
    tool_id: demo_tool
    inputs:
      dag_input: {type: file}
    params:
      dag_param: "{outdir}/value"
    outputs:
      result:
        path: "{outdir}/{category_dir}/{sample_id}/result.txt"
""".strip(),
        encoding="utf-8",
    )
    plugin = _Plugin(
        tmp_path,
        [
            {
                "id": "demo_tool",
                "command_template": (
                    "demo {registry_input} {dag_input} {dag_param} {threads} {alpha}"
                ),
                "inputs": ["registry_input"],
            }
        ],
    )

    result = lint_templates(
        "demo",
        {"outdir": "results", "differential_expression": {"alpha": 0.05}},
        plugin,
    )

    assert result["passed"] is True
    assert result["findings"] == []


def test_lint_templates_reports_unknown_command_field(tmp_path) -> None:
    (tmp_path / "pipeline_dag.yaml").write_text("nodes: {}\n", encoding="utf-8")
    plugin = _Plugin(
        tmp_path,
        [{"id": "bad_tool", "command_template": "bad {known} {typo}", "inputs": ["known"]}],
    )

    result = lint_templates("demo", {}, plugin)

    assert result["passed"] is False
    assert result["error_count"] == 1
    assert result["findings"][0]["location"] == "tool.bad_tool"
    assert result["findings"][0]["missing_keys"] == ["typo"]
