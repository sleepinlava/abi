import json

from abi.agent import ABIAgentInterface


def test_agent_interface_lists_types_with_success_envelope():
    payload = json.loads(ABIAgentInterface().list_types())

    assert payload["status"] == "success"
    assert payload["command"] == "list_types"
    assert payload["result"]["count"] >= 2
    names = {row["analysis_type"] for row in payload["result"]["analysis_types"]}
    assert {"metagenomic_plasmid", "metatranscriptomics"} <= names


def test_agent_interface_plan_writes_plan_with_uniform_result(tmp_path):
    outdir = tmp_path / "agent_plan"

    payload = json.loads(
        ABIAgentInterface().plan(
            analysis_type="metatranscriptomics",
            outdir=str(outdir),
            log_dir=str(tmp_path / "log"),
        )
    )

    assert payload["status"] == "success"
    assert payload["command"] == "plan"
    assert payload["result"]["analysis_type"] == "metatranscriptomics"
    assert payload["result"]["steps"] == 3
    assert payload["result"]["written_files"] == [str(outdir / "execution_plan.json")]
    assert (outdir / "execution_plan.json").exists()


def test_agent_interface_run_requires_confirmation():
    payload = json.loads(
        ABIAgentInterface().run(
            analysis_type="metatranscriptomics",
            outdir="results/agent-confirmation-only",
            log_dir="log",
            smoke=True,
        )
    )

    assert payload["status"] == "confirmation_required"
    assert payload["command"] == "run"
    assert payload["result"]["message"].startswith("Re-run with confirm_execution=true")


def test_agent_interface_reports_invalid_json_file(tmp_path):
    result_dir = tmp_path / "bad_result"
    result_dir.mkdir()
    (result_dir / "execution_plan.json").write_text("{bad json\n", encoding="utf-8")

    payload = json.loads(ABIAgentInterface(verbose_errors=True).report(result_dir=result_dir))

    assert payload["status"] == "error"
    assert payload["error_code"] == "parse_failed"
    assert payload["error_type"] == "ABIJSONError"
    assert payload["diagnostic_hints"]
    assert "Invalid JSON in" in payload["error"]


def test_agent_interface_errors_include_diagnostics(tmp_path):
    payload = json.loads(
        ABIAgentInterface().plan(
            analysis_type="metatranscriptomics",
            sample_sheet=str(tmp_path / "missing.tsv"),
            outdir=str(tmp_path / "agent_plan"),
            log_dir=str(tmp_path / "log"),
        )
    )

    assert payload["status"] == "error"
    assert payload["error_code"] == "missing_input"
    assert payload["diagnostic_hints"][0]["code"] == "missing_input"
    assert payload["diagnostic_hints"][0]["suggested_next_action"]


def test_agent_interface_exports_agent_context():
    payload = json.loads(
        ABIAgentInterface().export_agent_context(analysis_type="metatranscriptomics")
    )

    assert payload["status"] == "success"
    assert payload["command"] == "export_agent_context"
    assert payload["result"]["analysis_type"] == "metatranscriptomics"
    assert payload["result"]["execution_requires_confirmation"] is True
    assert payload["result"]["safe_sequence"][-1] == "report"
    assert "abi_run" in payload["result"]["unsafe_tools"]
    assert "abi_run" not in payload["result"]["default_exported_tools"]
    assert "gene_expression" in payload["result"]["standard_tables"]


def test_agent_interface_doctor_agent_returns_short_guide():
    payload = json.loads(ABIAgentInterface().doctor_agent(analysis_type="metatranscriptomics"))

    assert payload["status"] == "success"
    assert payload["result"]["analysis_type"] == "metatranscriptomics"
    assert "Safe call order" in payload["result"]["text"]
    assert "run -> report" in payload["result"]["text"]


def test_agent_interface_dispatch_accepts_cli_style_tool_aliases():
    agent = ABIAgentInterface()

    context = json.loads(
        agent.dispatch("export-agent-context", {"analysis_type": "metatranscriptomics"})
    )
    doctor = json.loads(agent.dispatch("doctor-agent", {"analysis_type": "metatranscriptomics"}))
    list_types = json.loads(agent.dispatch("list-types", {}))

    assert context["status"] == "success"
    assert context["command"] == "export_agent_context"
    assert doctor["status"] == "success"
    assert doctor["command"] == "doctor_agent"
    assert list_types["status"] == "success"
    assert list_types["command"] == "list_types"


def test_agent_dispatch_enforces_execution_permission_before_handler(monkeypatch):
    agent = ABIAgentInterface()

    def unexpected_run(**kwargs):
        raise AssertionError(f"run handler should not be called: {kwargs}")

    monkeypatch.setattr(agent, "run", unexpected_run)
    payload = json.loads(agent.dispatch("run", {"analysis_type": "metatranscriptomics"}))

    assert payload["status"] == "confirmation_required"
    assert payload["result"]["tool"] == "abi_run"


def test_agent_install_skills_is_dispatchable(tmp_path):
    payload = json.loads(
        ABIAgentInterface().dispatch(
            "abi_install_skills",
            {"target": str(tmp_path / "skills")},
        )
    )

    assert payload["status"] == "success"
    assert payload["command"] == "install_skills"
    assert (tmp_path / "skills" / "README.md").is_file()
