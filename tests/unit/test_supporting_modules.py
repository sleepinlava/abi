from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from urllib.error import URLError

import pytest

from abi.agent.context import build_agent_context, render_doctor_agent
from abi.agent.envelopes import error_envelope, json_dumps, success_envelope
from abi.jobs import client as jobs_client
from abi.plugins import get_plugin
from abi.report.citations import (
    CitationRegistry,
    format_citations_html,
    format_citations_markdown,
)
from abi.report.html import write_html_report
from abi.report.limitations import format_limitations_html, format_limitations_markdown
from abi.report.methods import write_methods
from abi.workflow.manifest import ResourceManifest, checksum_file


def _plan() -> dict:
    return {
        "project_name": "<unsafe>",
        "analysis_type": "test",
        "steps": [
            {
                "step_id": "S1_qc",
                "step_name": "qc",
                "tool_id": "fastp",
                "category": "qc",
                "sample_id": "S1",
            }
        ],
    }


def test_html_and_methods_reports_escape_and_include_provenance(tmp_path):
    provenance = tmp_path / "provenance"
    provenance.mkdir()
    (provenance / "tool_versions.tsv").write_text(
        "tool_id\texecutable\tenv_name\tversion\tstatus\nfastp\tfastp\tqc\t1.0\tcaptured\n",
        encoding="utf-8",
    )
    (provenance / "commands.tsv").write_text(
        "step_id\tcommand\nS1_qc\tfastp --in reads.fq\n",
        encoding="utf-8",
    )

    methods = write_methods(tmp_path, plan=_plan())
    html = write_html_report(
        tmp_path,
        plan=_plan(),
        table_summary={"qc": {"rows": 1, "path": "tables/qc.tsv"}},
        methods_md=methods.read_text(encoding="utf-8"),
        limitations_yaml=["Do not infer <causality>."],
        citations=[{"tool": "fastp", "citation": "Paper & DOI"}],
    )

    content = html.read_text(encoding="utf-8")
    assert "&lt;unsafe&gt;" in content
    assert "Do not infer &lt;causality&gt;." in content
    assert "Tool Versions" in methods.read_text(encoding="utf-8")


def test_citation_and_limitation_formatters_escape_html():
    registry = CitationRegistry(
        [
            {"tool": "tool", "stage": "qc", "citation": "A & B"},
            {"tool": "tool", "stage": "qc", "citation": "A & B"},
        ]
    )
    assert registry.unique_citations() == ["A & B"]
    assert "**tool**" in format_citations_markdown(registry.all)
    assert "A &amp; B" in format_citations_html(registry.all)
    assert "1. x < y" in format_limitations_markdown(["x < y"])
    assert "x &lt; y" in format_limitations_html(["x < y"])


def test_agent_context_and_envelopes_are_transport_safe(tmp_path):
    plugin = get_plugin("wgs_bacteria")
    context = build_agent_context(plugin)
    assert context["safe_sequence"][-1] == "report"
    assert "provenance/methods.md" in context["important_artifacts"]
    assert "abi_run" in context["unsafe_tools"]
    assert "Safe call order" in render_doctor_agent(plugin)

    success = success_envelope("test", {"path": tmp_path, 1: (Path("x"),)})
    assert success["result"]["path"] == str(tmp_path)
    assert success["result"]["1"] == ["x"]
    assert json.loads(json_dumps(success))["status"] == "success"
    error = error_envelope(
        "test",
        error="bad",
        error_type="ValueError",
        error_code="invalid_config",
        diagnostic_hints=[],
    )
    assert "error_type" not in error


def test_resource_manifest_checksum_and_validation(tmp_path):
    database = tmp_path / "db.fa"
    database.write_text(">x\nACGT\n", encoding="utf-8")
    digest = checksum_file(database)
    manifest = ResourceManifest("test")
    manifest.add_resource(id="db", path=database, checksum_sha256=digest)
    output = manifest.write(tmp_path / "provenance")

    assert output.exists()
    assert manifest.validate() == []
    database.write_text("changed\n", encoding="utf-8")
    assert "checksum mismatch" in manifest.validate()[0]


def test_job_client_wraps_connection_errors(monkeypatch):
    def fail(*args, **kwargs):
        raise URLError("offline")

    monkeypatch.setattr(jobs_client, "urlopen", fail)
    with pytest.raises(jobs_client.JobClientError) as caught:
        jobs_client.list_jobs(base_url="http://127.0.0.1:1")
    assert caught.value.status_code == 0
    assert caught.value.payload["status"] == "connection_error"


def test_plugin_report_logs_catastrophic_figure_failure(tmp_path, monkeypatch, caplog):
    from abi.report import generic_report

    root = tmp_path / "plugin"
    root.mkdir()
    (root / "figure_specs.yaml").write_text("figures: []\n", encoding="utf-8")
    (tmp_path / "result" / "tables").mkdir(parents=True)
    plugin = SimpleNamespace(
        plugin_id="test",
        root=root,
        report_title="Test",
        table_schemas=lambda: {"dummy": ["value"]},
    )
    monkeypatch.setattr(
        generic_report,
        "_render_figures_via_legacy",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("renderer crashed")),
    )
    monkeypatch.setattr(generic_report, "write_full_report", lambda *args, **kwargs: {})

    generic_report.write_plugin_report(
        plugin,
        _plan(),
        tmp_path / "result",
        use_sciplot=False,
    )

    assert "renderer crashed" in caplog.text
