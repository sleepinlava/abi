import json

from typer.testing import CliRunner

from abi.cli import app


def _fake_nextflow(path):
    path.write_text(
        """#!/usr/bin/env sh
trace=""
while [ "$#" -gt 0 ]; do
  if [ "$1" = "-with-trace" ]; then
    shift
    trace="$1"
  fi
  shift || break
done
if [ -n "$trace" ]; then
  mkdir -p "$(dirname "$trace")"
  printf 'task_id\tname\tstatus\texit\tnative_id\texecutor\n' > "$trace"
  printf '1\tRNA1_QC_FASTP (RNA1_qc_fastp)\tCOMPLETED\t0\tlocal-1\tlocal\n' >> "$trace"
fi
printf 'fake nextflow %s\n' "$*"
""",
        encoding="utf-8",
    )
    path.chmod(0o755)
    return path


def _assert_nextflow_smoke_artifacts(outdir):
    summary = json.loads((outdir / "provenance" / "run_summary.json").read_text(encoding="utf-8"))
    assert summary["engine"] == "nextflow"
    assert summary["smoke"] is True
    assert summary["status"] == "success"
    assert summary["dag"]["edges"]["RNA1_alignment_star"] == ["RNA1_qc_fastp"]
    assert summary["remote_scheduler_jobs"][0]["scheduler_job_id"] == "local-1"
    commands = (outdir / "provenance" / "commands.tsv").read_text(encoding="utf-8")
    assert "abi-nextflow-smoke" in commands
    assert "remote_scheduler_job_id" in commands
    assert "local-1" in commands
    assert "\tsuccess\t0\t" in commands
    resolved_inputs = (outdir / "provenance" / "resolved_inputs.tsv").read_text(encoding="utf-8")
    assert "NOT_CONFIGURED" not in resolved_inputs
    assert (outdir / "tables" / "gene_expression.tsv").exists()
    assert (outdir / "report" / "report.md").exists()
    assert (outdir / "nextflow" / "workflow.nf").exists()


def test_abi_metatranscriptomics_dry_run_writes_portability_artifacts(tmp_path):
    outdir = tmp_path / "abi_transcriptomics"
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "dry-run",
            "--type",
            "metatranscriptomics",
            "--outdir",
            str(outdir),
            "--log-dir",
            str(tmp_path / "log"),
            "--no-progress",
        ],
    )

    assert result.exit_code == 0, result.output
    commands = (outdir / "provenance" / "commands.tsv").read_text(encoding="utf-8")
    assert "fastp" in commands
    assert "STAR" in commands
    assert "featureCounts" in commands
    assert (outdir / "tables" / "gene_expression.tsv").exists()
    resolved_inputs = (outdir / "provenance" / "resolved_inputs.tsv").read_text(encoding="utf-8")
    assert "GENOME_INDEX_NOT_CONFIGURED" in resolved_inputs
    assert "ANNOTATION_GTF_NOT_CONFIGURED" in resolved_inputs
    progress_events = outdir / "provenance" / "progress.jsonl"
    progress_snapshot = outdir / "provenance" / "progress.json"
    assert progress_events.exists()
    assert progress_snapshot.exists()
    summary = json.loads((outdir / "provenance" / "run_summary.json").read_text(encoding="utf-8"))
    assert summary["progress_events"] == str(progress_events)
    events = [json.loads(line) for line in progress_events.read_text(encoding="utf-8").splitlines()]
    assert [event["event"] for event in events] == ["run_started", "run_completed"]


def test_abi_inspect_reports_placeholder_inputs(tmp_path):
    outdir = tmp_path / "abi_transcriptomics"
    runner = CliRunner()
    dry_run = runner.invoke(
        app,
        [
            "dry-run",
            "--type",
            "metatranscriptomics",
            "--outdir",
            str(outdir),
            "--log-dir",
            str(tmp_path / "log"),
            "--no-progress",
        ],
    )
    assert dry_run.exit_code == 0, dry_run.output

    result = runner.invoke(app, ["inspect", "--result-dir", str(outdir)])

    assert result.exit_code == 0, result.output
    assert "missing_or_placeholder_inputs" in result.output
    assert "GENOME_INDEX_NOT_CONFIGURED" in result.output


def test_abi_report_regenerates_transcriptomics_report(tmp_path):
    outdir = tmp_path / "abi_transcriptomics"
    runner = CliRunner()
    dry_run = runner.invoke(
        app,
        [
            "dry-run",
            "--type",
            "metatranscriptomics",
            "--outdir",
            str(outdir),
            "--log-dir",
            str(tmp_path / "log"),
            "--no-progress",
        ],
    )
    assert dry_run.exit_code == 0, dry_run.output

    result = runner.invoke(
        app,
        ["report", "--type", "metatranscriptomics", "--result-dir", str(outdir)],
    )

    assert result.exit_code == 0, result.output
    assert (outdir / "report" / "report.md").exists()
    assert (outdir / "report" / "report.html").exists()


def test_abi_validate_result_accepts_transcriptomics_dry_run(tmp_path):
    outdir = tmp_path / "abi_transcriptomics"
    runner = CliRunner()
    dry_run = runner.invoke(
        app,
        [
            "dry-run",
            "--type",
            "metatranscriptomics",
            "--outdir",
            str(outdir),
            "--log-dir",
            str(tmp_path / "log"),
            "--no-progress",
        ],
    )
    assert dry_run.exit_code == 0, dry_run.output

    result = runner.invoke(
        app,
        [
            "validate-result",
            "--result-dir",
            str(outdir),
            "--allow-empty-tables",
            "--output-json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["status"] == "success"
    assert payload["command"] == "abi_validate_result"
    assert payload["result"]["valid"] is True
    assert payload["result"]["analysis_type"] == "metatranscriptomics"
    assert payload["result"]["tables"]["gene_expression"]["exists"] is True
    assert payload["result"]["artifacts"]["provenance/progress.jsonl"]["exists"] is True


def test_abi_export_nextflow_writes_dsl2_script(tmp_path):
    outdir = tmp_path / "abi_transcriptomics"
    workflow = tmp_path / "workflow.nf"
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "export-nextflow",
            "--type",
            "metatranscriptomics",
            "--outdir",
            str(outdir),
            "--log-dir",
            str(tmp_path / "log"),
            "--output",
            str(workflow),
        ],
    )

    assert result.exit_code == 0, result.output
    script = workflow.read_text(encoding="utf-8")
    assert "nextflow.enable.dsl=2" in script
    assert "process RNA1_QC_FASTP" in script
    assert "workflow" in script


def test_abi_export_nextflow_smoke_writes_runnable_smoke_script(tmp_path):
    outdir = tmp_path / "abi_transcriptomics"
    workflow = tmp_path / "workflow.nf"
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "export-nextflow",
            "--type",
            "metatranscriptomics",
            "--outdir",
            str(outdir),
            "--log-dir",
            str(tmp_path / "log"),
            "--output",
            str(workflow),
            "--smoke",
        ],
    )

    assert result.exit_code == 0, result.output
    script = workflow.read_text(encoding="utf-8")
    assert "// Export mode: smoke" in script
    assert "ABI Nextflow smoke step" in script
    assert "fastp -i" not in script


def test_abi_run_engine_nextflow_smoke_writes_abi_artifacts_with_fake_nextflow(
    tmp_path,
):
    outdir = tmp_path / "abi_transcriptomics"
    nextflow = _fake_nextflow(tmp_path / "nextflow")
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "run",
            "--engine",
            "nextflow",
            "--type",
            "metatranscriptomics",
            "--outdir",
            str(outdir),
            "--log-dir",
            str(tmp_path / "log"),
            "--nextflow-bin",
            str(nextflow),
            "--smoke",
            "--confirm-execution",
        ],
    )

    assert result.exit_code == 0, result.output
    _assert_nextflow_smoke_artifacts(outdir)


def test_abi_run_plain_cli_requires_confirmation(tmp_path):
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "run",
            "--engine",
            "nextflow",
            "--type",
            "metatranscriptomics",
            "--outdir",
            str(tmp_path / "unconfirmed_run"),
            "--log-dir",
            str(tmp_path / "log"),
            "--smoke",
        ],
    )

    assert result.exit_code == 2, result.output
    payload = json.loads(result.output)
    assert payload["status"] == "confirmation_required"
    assert payload["command"] == "run"


def test_abi_run_nextflow_alias_uses_runtime_layer(tmp_path):
    outdir = tmp_path / "abi_transcriptomics"
    nextflow = _fake_nextflow(tmp_path / "nextflow")
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "run-nextflow",
            "--type",
            "metatranscriptomics",
            "--outdir",
            str(outdir),
            "--log-dir",
            str(tmp_path / "log"),
            "--nextflow-bin",
            str(nextflow),
            "--confirm-execution",
        ],
    )

    assert result.exit_code == 0, result.output
    _assert_nextflow_smoke_artifacts(outdir)


def test_abi_metagenomic_plasmid_adapter_plan_keeps_autoplasm_route(tmp_path):
    outdir = tmp_path / "abi_plasmid"
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "plan",
            "--type",
            "metagenomic_plasmid",
            "--config",
            "examples/config_minimal.yaml",
            "--profile",
            "dry_run",
            "--outdir",
            str(outdir),
            "--log-dir",
            str(tmp_path / "log"),
        ],
    )

    assert result.exit_code == 0, result.output
    plan = (outdir / "execution_plan.json").read_text(encoding="utf-8")
    assert '"analysis_type": "metagenomic_plasmid"' in plan
    assert "genomad" in plan


def test_abi_metagenomic_plasmid_no_progress_writes_progress_artifacts(tmp_path):
    outdir = tmp_path / "abi_plasmid"
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "dry-run",
            "--type",
            "metagenomic_plasmid",
            "--config",
            "examples/config_minimal.yaml",
            "--profile",
            "dry_run",
            "--outdir",
            str(outdir),
            "--log-dir",
            str(tmp_path / "log"),
            "--no-progress",
            "--output-json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    progress_events = outdir / "provenance" / "progress.jsonl"
    progress_snapshot = outdir / "provenance" / "progress.json"
    assert payload["result"]["outputs"]["progress_events"] == str(progress_events)
    assert progress_events.exists()
    assert progress_snapshot.exists()
    snapshot = json.loads(progress_snapshot.read_text(encoding="utf-8"))
    assert snapshot["status"] == "success"
    assert snapshot["record_progress"] is False
    plan = json.loads((outdir / "execution_plan.json").read_text(encoding="utf-8"))
    assert plan["analysis_type"] == "metagenomic_plasmid"

    validation = runner.invoke(
        app,
        [
            "validate-result",
            "--result-dir",
            str(outdir),
            "--allow-empty-tables",
            "--output-json",
        ],
    )

    assert validation.exit_code == 0, validation.output
    validation_payload = json.loads(validation.output)
    assert validation_payload["result"]["valid"] is True
    assert validation_payload["result"]["analysis_type"] == "metagenomic_plasmid"


def test_abi_cli_output_json_wraps_plan_result(tmp_path):
    outdir = tmp_path / "abi_transcriptomics_json"
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "plan",
            "--type",
            "metatranscriptomics",
            "--outdir",
            str(outdir),
            "--log-dir",
            str(tmp_path / "log"),
            "--output-json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["status"] == "success"
    assert payload["command"] == "plan"
    assert payload["result"]["analysis_type"] == "metatranscriptomics"
    assert payload["result"]["plan_path"] == str(outdir / "execution_plan.json")


def test_abi_cli_output_json_run_requires_confirmation(tmp_path):
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "run",
            "--type",
            "metatranscriptomics",
            "--outdir",
            str(tmp_path / "run_requires_confirmation"),
            "--log-dir",
            str(tmp_path / "log"),
            "--smoke",
            "--output-json",
        ],
    )

    assert result.exit_code == 2, result.output
    payload = json.loads(result.output)
    assert payload["status"] == "confirmation_required"
    assert payload["command"] == "run"


def test_abi_cli_output_json_run_executes_after_confirmation(tmp_path):
    outdir = tmp_path / "abi_transcriptomics_json_run"
    nextflow = _fake_nextflow(tmp_path / "nextflow")
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "run",
            "--engine",
            "nextflow",
            "--type",
            "metatranscriptomics",
            "--outdir",
            str(outdir),
            "--log-dir",
            str(tmp_path / "log"),
            "--nextflow-bin",
            str(nextflow),
            "--smoke",
            "--confirm-execution",
            "--output-json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["status"] == "success"
    assert payload["command"] == "run"
    assert payload["result"]["engine"] == "nextflow"
    _assert_nextflow_smoke_artifacts(outdir)


def test_abi_export_agent_context_outputs_machine_readable_guidance():
    runner = CliRunner()

    result = runner.invoke(
        app,
        ["export-agent-context", "--type", "metatranscriptomics", "--format", "json"],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["analysis_type"] == "metatranscriptomics"
    assert payload["safe_sequence"] == [
        "list_types",
        "plan",
        "dry_run",
        "inspect",
        "run",
        "report",
    ]
    assert payload["execution_requires_confirmation"] is True
    assert "abi_run" in payload["unsafe_tools"]
    assert "abi_run" not in payload["default_exported_tools"]
    assert "gene_expression" in payload["standard_tables"]


def test_abi_doctor_agent_outputs_short_operating_guide():
    runner = CliRunner()

    result = runner.invoke(app, ["doctor-agent", "--type", "metatranscriptomics"])

    assert result.exit_code == 0, result.output
    assert "ABI agent guide for metatranscriptomics" in result.output
    assert "Safe call order" in result.output
    assert "gene_expression" in result.output


def test_abi_check_resources_reports_generic_plugin_placeholders():
    runner = CliRunner()

    result = runner.invoke(app, ["check-resources", "--type", "metatranscriptomics"])

    assert result.exit_code == 0, result.output
    rows = json.loads(result.output)
    by_id = {row["resource_id"]: row for row in rows}
    assert by_id["genome_index"]["status"] == "not_configured"
    assert by_id["annotation_gtf"]["status"] == "not_configured"


def test_abi_setup_resources_dry_run_uses_metagenomic_resource_manager():
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "setup-resources",
            "--type",
            "metagenomic_plasmid",
            "--config",
            "examples/config_minimal.yaml",
            "--profile",
            "dry_run",
            "--resource",
            "genomad",
            "--dry-run",
        ],
    )

    assert result.exit_code == 0, result.output
    rows = json.loads(result.output)
    assert rows[0]["resource_id"] == "genomad"
    assert rows[0]["status"] == "planned"
    assert rows[0]["command"][0] == "genomad"
