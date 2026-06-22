import json
import signal
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request

import pytest
from typer.testing import CliRunner

from abi.cli import _build_job_payload, app
from abi.jobs.service import (
    ABIJobService,
    ConfirmationRequiredError,
    create_http_server,
)


def _fake_nextflow(path):
    path.write_text(
        "#!/usr/bin/env sh\nprintf 'fake nextflow %s\\n' \"$*\"\n",
        encoding="utf-8",
    )
    path.chmod(0o755)
    return path


def _post_json(url, payload):
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        return response.status, json.loads(response.read().decode("utf-8"))


def _get_json(url):
    with urllib.request.urlopen(url, timeout=10) as response:
        return response.status, json.loads(response.read().decode("utf-8"))


def _create_http_server_or_skip(service):
    try:
        return create_http_server(service, host="127.0.0.1", port=0)
    except PermissionError as exc:
        pytest.skip(f"localhost sockets are unavailable in this test sandbox: {exc}")


def test_job_service_requires_confirmation_for_execution_jobs():
    service = ABIJobService()
    try:
        try:
            service.submit(
                {
                    "command": "run",
                    "arguments": {
                        "analysis_type": "metatranscriptomics",
                        "outdir": "results/unconfirmed-job",
                    },
                }
            )
        except ConfirmationRequiredError as exc:
            assert exc.payload["status"] == "confirmation_required"
            assert exc.payload["command"] == "abi_run"
        else:
            raise AssertionError("submit should require confirmation")
    finally:
        service.shutdown()


def test_job_service_can_cancel_queued_job():
    started = threading.Event()
    release = threading.Event()

    class SlowAgent:
        def dispatch(self, command, arguments):
            del command, arguments
            started.set()
            release.wait(timeout=2)
            return json.dumps({"status": "success", "command": "abi_plan", "result": {}})

    service = ABIJobService(agent=SlowAgent(), max_workers=1)
    try:
        service.submit({"command": "plan", "arguments": {"analysis_type": "metatranscriptomics"}})
        assert started.wait(timeout=2)
        queued = service.submit(
            {"command": "plan", "arguments": {"analysis_type": "metatranscriptomics"}}
        )

        cancelled = service.cancel(queued["job_id"])

        assert cancelled["status"] == "cancelled"
    finally:
        release.set()
        service.shutdown()


def test_job_service_records_running_cancel_request_after_dispatch_finishes():
    started = threading.Event()
    release = threading.Event()

    class SlowAgent:
        def dispatch(self, command, arguments):
            del command, arguments
            started.set()
            release.wait(timeout=2)
            return json.dumps({"status": "success", "command": "abi_plan", "result": {}})

    service = ABIJobService(agent=SlowAgent(), max_workers=1)
    try:
        submitted = service.submit(
            {"command": "plan", "arguments": {"analysis_type": "metatranscriptomics"}}
        )
        assert started.wait(timeout=2)

        cancelled = service.cancel(submitted["job_id"])

        assert cancelled["status"] == "cancel_requested"
        assert cancelled["cancel_requested"] is True

        release.set()
        deadline = time.time() + 2
        job = {}
        while time.time() < deadline:
            job = service.get_job(submitted["job_id"])
            if job["finished_at"] is not None:
                break
            time.sleep(0.05)

        assert job["status"] == "cancelled"
        assert job["cancel_requested"] is True
        assert job["finished_at"] is not None
    finally:
        release.set()
        service.shutdown()


def test_job_service_persists_completed_jobs_and_artifact_index(tmp_path):
    store_path = tmp_path / "jobs.json"
    outdir = tmp_path / "persisted_out"
    finished = threading.Event()

    class RecordingAgent:
        def dispatch(self, command, arguments):
            outdir.mkdir(parents=True, exist_ok=True)
            (outdir / "execution_plan.json").write_text("{}\n", encoding="utf-8")
            (outdir / "provenance").mkdir(exist_ok=True)
            (outdir / "provenance" / "commands.tsv").write_text("step_id\n", encoding="utf-8")
            (outdir / "report").mkdir(exist_ok=True)
            (outdir / "report" / "report.md").write_text("# report\n", encoding="utf-8")
            finished.set()
            return json.dumps(
                {
                    "status": "success",
                    "command": command,
                    "result": {
                        "analysis_type": "metatranscriptomics",
                        "outdir": str(outdir),
                        "written_files": [str(outdir / "execution_plan.json")],
                    },
                }
            )

    service = ABIJobService(agent=RecordingAgent(), max_workers=1, store_path=store_path)
    try:
        submitted = service.submit(
            {"command": "plan", "arguments": {"analysis_type": "metatranscriptomics"}}
        )
        assert finished.wait(timeout=2)
        deadline = time.time() + 2
        while time.time() < deadline:
            job = service.get_job(submitted["job_id"])
            if job["status"] == "succeeded":
                break
            time.sleep(0.05)
        assert service.get_job(submitted["job_id"])["status"] == "succeeded"
    finally:
        service.shutdown()

    reloaded = ABIJobService(max_workers=1, store_path=store_path)
    try:
        job = reloaded.get_job(submitted["job_id"])
        assert job["status"] == "succeeded"
        artifacts = reloaded.artifacts(submitted["job_id"])["artifacts"]
        assert artifacts["outdir"] == str(outdir)
        assert artifacts["execution_plan"] == str(outdir / "execution_plan.json")
        assert artifacts["job_provenance"] == str(outdir / "provenance" / "job.json")
        assert artifacts["commands"] == str(outdir / "provenance" / "commands.tsv")
        assert artifacts["report_md"] == str(outdir / "report" / "report.md")
        assert artifacts["written_files"] == [str(outdir / "execution_plan.json")]
        job_provenance = json.loads(
            (outdir / "provenance" / "job.json").read_text(encoding="utf-8")
        )
        assert job_provenance["schema_version"] == "abi.job.provenance.v1"
        assert job_provenance["job"]["job_id"] == submitted["job_id"]
        assert job_provenance["job"]["status"] == "succeeded"
        assert job_provenance["job"]["command"] == "abi_plan"
    finally:
        reloaded.shutdown()


def test_job_service_maps_hpc_backend_to_nextflow_arguments():
    seen = []
    finished = threading.Event()

    class RecordingAgent:
        def dispatch(self, command, arguments):
            seen.append((command, dict(arguments)))
            finished.set()
            return json.dumps({"status": "success", "command": command, "result": {}})

    service = ABIJobService(agent=RecordingAgent(), max_workers=1)
    try:
        service.submit(
            {
                "command": "run",
                "backend": "hpc",
                "arguments": {
                    "analysis_type": "metatranscriptomics",
                    "outdir": "results/hpc-job",
                    "hpc_profile": "cluster",
                    "confirm_execution": True,
                },
            }
        )

        assert finished.wait(timeout=2)
        assert seen[0][0] == "abi_run"
        assert seen[0][1]["engine"] == "nextflow"
        assert seen[0][1]["executor"] == "slurm"
        assert seen[0][1]["nextflow_profile"] == "cluster"
        assert "hpc_profile" not in seen[0][1]
    finally:
        service.shutdown()


def test_job_service_maps_cloud_backend_to_nextflow_arguments():
    seen = []
    finished = threading.Event()

    class RecordingAgent:
        def dispatch(self, command, arguments):
            seen.append((command, dict(arguments)))
            finished.set()
            return json.dumps({"status": "success", "command": command, "result": {}})

    service = ABIJobService(agent=RecordingAgent(), max_workers=1)
    try:
        service.submit(
            {
                "command": "run",
                "backend": "cloud",
                "arguments": {
                    "analysis_type": "metatranscriptomics",
                    "outdir": "results/cloud-job",
                    "cloud_executor": "awsbatch",
                    "cloud_profile": "aws",
                    "confirm_execution": True,
                },
            }
        )

        assert finished.wait(timeout=2)
        assert seen[0][0] == "abi_run"
        assert seen[0][1]["engine"] == "nextflow"
        assert seen[0][1]["executor"] == "awsbatch"
        assert seen[0][1]["nextflow_profile"] == "aws"
        assert "cloud_profile" not in seen[0][1]
    finally:
        service.shutdown()


def test_job_service_dispatches_non_execution_agent_context_commands():
    seen = []
    finished = threading.Event()

    class RecordingAgent:
        def dispatch(self, command, arguments):
            seen.append((command, dict(arguments)))
            if len(seen) == 3:
                finished.set()
            return json.dumps({"status": "success", "command": command, "result": {}})

    service = ABIJobService(agent=RecordingAgent(), max_workers=1)
    try:
        service.submit(
            {
                "command": "export-agent-context",
                "arguments": {"analysis_type": "metatranscriptomics"},
            }
        )
        service.submit(
            {
                "command": "doctor-agent",
                "arguments": {"analysis_type": "metatranscriptomics"},
            }
        )
        service.submit(
            {
                "command": "validate-result",
                "arguments": {"result_dir": "results/demo"},
            }
        )

        assert finished.wait(timeout=2)
        assert [command for command, _ in seen] == [
            "abi_export_agent_context",
            "abi_doctor_agent",
            "abi_validate_result",
        ]
    finally:
        service.shutdown()


def test_abi_job_payload_builder_maps_runtime_options(tmp_path):
    payload = _build_job_payload(
        command="run",
        payload_path=None,
        arguments_json=None,
        backend="hpc",
        analysis_type="metatranscriptomics",
        config_path=tmp_path / "config.yaml",
        sample_sheet=tmp_path / "samples.tsv",
        profile="cluster",
        mode="rna",
        threads=8,
        outdir=str(tmp_path / "out"),
        log_dir=str(tmp_path / "log"),
        engine="nextflow",
        workflow=tmp_path / "workflow.nf",
        nextflow_bin=tmp_path / "nextflow",
        nextflow_profile="slurm_profile",
        executor="slurm",
        work_dir=tmp_path / "work",
        nxf_home=tmp_path / "nxf_home",
        mamba_root=tmp_path / ".mamba",
        resume=True,
        smoke=True,
        confirm_execution=True,
        check_files=False,
    )

    arguments = payload["arguments"]
    assert payload["backend"] == "hpc"
    assert arguments["analysis_type"] == "metatranscriptomics"
    assert arguments["config_path"] == str(tmp_path / "config.yaml")
    assert arguments["sample_sheet"] == str(tmp_path / "samples.tsv")
    assert arguments["profile"] == "cluster"
    assert arguments["mode"] == "rna"
    assert arguments["threads"] == 8
    assert arguments["outdir"] == str(tmp_path / "out")
    assert arguments["log_dir"] == str(tmp_path / "log")
    assert arguments["engine"] == "nextflow"
    assert arguments["workflow"] == str(tmp_path / "workflow.nf")
    assert arguments["nextflow_bin"] == str(tmp_path / "nextflow")
    assert arguments["nextflow_profile"] == "slurm_profile"
    assert arguments["executor"] == "slurm"
    assert arguments["work_dir"] == str(tmp_path / "work")
    assert arguments["nxf_home"] == str(tmp_path / "nxf_home")
    assert arguments["mamba_root"] == str(tmp_path / ".mamba")
    assert arguments["resume"] is True
    assert arguments["smoke"] is True
    assert arguments["confirm_execution"] is True
    assert arguments["check_files"] is False


def test_job_service_http_run_nextflow_smoke_returns_status_and_artifacts(tmp_path):
    service = ABIJobService(max_workers=1)
    server = _create_http_server_or_skip(service)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"
    outdir = tmp_path / "abi_job_nextflow"
    nextflow = _fake_nextflow(tmp_path / "nextflow")

    try:
        status, submitted = _post_json(
            f"{base_url}/jobs",
            {
                "command": "run",
                "arguments": {
                    "analysis_type": "metatranscriptomics",
                    "engine": "nextflow",
                    "outdir": str(outdir),
                    "log_dir": str(tmp_path / "log"),
                    "nextflow_bin": str(nextflow),
                    "smoke": True,
                    "confirm_execution": True,
                },
            },
        )
        assert status == 202
        job_id = submitted["job"]["job_id"]

        deadline = time.time() + 10
        job = {}
        while time.time() < deadline:
            _, job = _get_json(f"{base_url}/jobs/{job_id}")
            if job["status"] in {"succeeded", "failed", "cancelled"}:
                break
            time.sleep(0.05)

        assert job["status"] == "succeeded", job
        _, artifacts = _get_json(f"{base_url}/jobs/{job_id}/artifacts")
        assert artifacts["status"] == "succeeded"
        assert artifacts["artifacts"]["outputs"]["workflow"] == str(
            outdir / "nextflow" / "workflow.nf"
        )
    finally:
        server.shutdown()
        server.server_close()
        service.shutdown()
        thread.join(timeout=2)


def test_job_service_http_returns_409_for_unconfirmed_run():
    service = ABIJobService(max_workers=1)
    server = _create_http_server_or_skip(service)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"

    try:
        try:
            _post_json(
                f"{base_url}/jobs",
                {
                    "command": "run",
                    "arguments": {
                        "analysis_type": "metatranscriptomics",
                        "outdir": "results/unconfirmed-http-job",
                    },
                },
            )
        except urllib.error.HTTPError as exc:
            assert exc.code == 409
            payload = json.loads(exc.read().decode("utf-8"))
            assert payload["status"] == "confirmation_required"
            assert payload["command"] == "abi_run"
        else:
            raise AssertionError("HTTP submission should require confirmation")
    finally:
        server.shutdown()
        server.server_close()
        service.shutdown()
        thread.join(timeout=2)


def test_abi_job_cli_submit_status_and_artifacts(tmp_path):
    service = ABIJobService(max_workers=1)
    server = _create_http_server_or_skip(service)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"
    outdir = tmp_path / "abi_job_cli_nextflow"
    nextflow = _fake_nextflow(tmp_path / "nextflow")
    runner = CliRunner()

    try:
        submit = runner.invoke(
            app,
            [
                "job",
                "submit",
                "--service-url",
                base_url,
                "--command",
                "run",
                "--analysis-type",
                "metatranscriptomics",
                "--engine",
                "nextflow",
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
        assert submit.exit_code == 0, submit.output
        job_id = json.loads(submit.output)["job"]["job_id"]

        deadline = time.time() + 10
        status_payload = {}
        while time.time() < deadline:
            status = runner.invoke(app, ["job", "status", job_id, "--service-url", base_url])
            assert status.exit_code == 0, status.output
            status_payload = json.loads(status.output)
            if status_payload["status"] in {"succeeded", "failed", "cancelled"}:
                break
            time.sleep(0.05)

        assert status_payload["status"] == "succeeded", status_payload
        artifacts = runner.invoke(app, ["job", "artifacts", job_id, "--service-url", base_url])
        assert artifacts.exit_code == 0, artifacts.output
        artifact_payload = json.loads(artifacts.output)
        assert artifact_payload["artifacts"]["outputs"]["workflow"] == str(
            outdir / "nextflow" / "workflow.nf"
        )
        assert artifact_payload["artifacts"]["job_provenance"] == str(
            outdir / "provenance" / "job.json"
        )
        job_provenance = json.loads(
            (outdir / "provenance" / "job.json").read_text(encoding="utf-8")
        )
        assert job_provenance["job"]["job_id"] == job_id
        assert job_provenance["job"]["backend"] == "nextflow"
    finally:
        server.shutdown()
        server.server_close()
        service.shutdown()
        thread.join(timeout=2)


def test_abi_job_cli_submit_maps_runtime_options(tmp_path):
    seen = []
    finished = threading.Event()

    class RecordingAgent:
        def dispatch(self, command, arguments):
            seen.append((command, dict(arguments)))
            finished.set()
            return json.dumps({"status": "success", "command": command, "result": {}})

    service = ABIJobService(agent=RecordingAgent(), max_workers=1)
    server = _create_http_server_or_skip(service)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"
    runner = CliRunner()

    try:
        result = runner.invoke(
            app,
            [
                "job",
                "submit",
                "--service-url",
                base_url,
                "--command",
                "run",
                "--analysis-type",
                "metatranscriptomics",
                "--profile",
                "cluster",
                "--mode",
                "rna",
                "--threads",
                "8",
                "--engine",
                "nextflow",
                "--workflow",
                str(tmp_path / "workflow.nf"),
                "--work-dir",
                str(tmp_path / "work"),
                "--nxf-home",
                str(tmp_path / "nxf_home"),
                "--mamba-root",
                str(tmp_path / ".mamba"),
                "--nextflow-profile",
                "slurm_profile",
                "--executor",
                "slurm",
                "--resume",
                "--smoke",
                "--confirm-execution",
            ],
        )

        assert result.exit_code == 0, result.output
        assert finished.wait(timeout=2)
        assert seen[0][0] == "abi_run"
        arguments = seen[0][1]
        assert arguments["analysis_type"] == "metatranscriptomics"
        assert arguments["profile"] == "cluster"
        assert arguments["mode"] == "rna"
        assert arguments["threads"] == 8
        assert arguments["engine"] == "nextflow"
        assert arguments["workflow"] == str(tmp_path / "workflow.nf")
        assert arguments["work_dir"] == str(tmp_path / "work")
        assert arguments["nxf_home"] == str(tmp_path / "nxf_home")
        assert arguments["mamba_root"] == str(tmp_path / ".mamba")
        assert arguments["nextflow_profile"] == "slurm_profile"
        assert arguments["executor"] == "slurm"
        assert arguments["resume"] is True
        assert arguments["smoke"] is True
        assert arguments["confirm_execution"] is True
    finally:
        server.shutdown()
        server.server_close()
        service.shutdown()
        thread.join(timeout=2)


def test_abi_job_cli_unconfirmed_run_returns_confirmation_required():
    service = ABIJobService(max_workers=1)
    server = _create_http_server_or_skip(service)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"
    runner = CliRunner()

    try:
        result = runner.invoke(
            app,
            [
                "job",
                "submit",
                "--service-url",
                base_url,
                "--command",
                "run",
                "--analysis-type",
                "metatranscriptomics",
                "--outdir",
                "results/unconfirmed-cli-job",
            ],
        )

        assert result.exit_code == 2, result.output
        payload = json.loads(result.output)
        assert payload["status"] == "confirmation_required"
        assert payload["command"] == "abi_run"
    finally:
        server.shutdown()
        server.server_close()
        service.shutdown()
        thread.join(timeout=2)


def test_job_service_remote_scheduler_job_id_extracted_from_result():
    finished = threading.Event()

    class HpcAgent:
        def dispatch(self, command, arguments):
            del command, arguments
            finished.set()
            return json.dumps(
                {
                    "status": "success",
                    "command": "abi_run",
                    "result": {
                        "analysis_type": "metatranscriptomics",
                        "outdir": "results/hpc-job",
                        "remote_scheduler_job_id": "slurm-12345",
                    },
                }
            )

    service = ABIJobService(agent=HpcAgent(), max_workers=1)
    try:
        submitted = service.submit(
            {
                "command": "run",
                "arguments": {
                    "analysis_type": "metatranscriptomics",
                    "outdir": "results/hpc-job",
                    "confirm_execution": True,
                },
            }
        )
        assert finished.wait(timeout=2)
        deadline = time.time() + 2
        while time.time() < deadline:
            job = service.get_job(submitted["job_id"])
            if job["status"] == "succeeded":
                break
            time.sleep(0.05)
        assert job["remote_scheduler_job_id"] == "slurm-12345"
    finally:
        service.shutdown()


def test_job_service_subprocess_workers_flag():
    finished = threading.Event()

    class FastAgent:
        def dispatch(self, command, arguments):
            del command, arguments
            finished.set()
            return json.dumps({"status": "success", "command": "abi_plan", "result": {}})

    service = ABIJobService(agent=FastAgent(), max_workers=1, subprocess_workers=False)
    try:
        assert service._subprocess_workers is False
        submitted = service.submit(
            {"command": "plan", "arguments": {"analysis_type": "metatranscriptomics"}}
        )
        assert finished.wait(timeout=2)
        deadline = time.time() + 2
        while time.time() < deadline:
            job = service.get_job(submitted["job_id"])
            if job["status"] == "succeeded":
                break
            time.sleep(0.05)
        assert job["status"] == "succeeded"
    finally:
        service.shutdown()


def test_kill_process_escalates_to_sigkill_for_term_ignoring_child(monkeypatch):
    import abi.jobs.service as service_module

    monkeypatch.setattr(service_module, "PROCESS_TERMINATE_GRACE_SECONDS", 0.1)
    monkeypatch.setattr(service_module, "PROCESS_KILL_WAIT_SECONDS", 1.0)
    process = subprocess.Popen(
        [
            sys.executable,
            "-c",
            (
                "import signal,time; "
                "signal.signal(signal.SIGTERM, signal.SIG_IGN); "
                "print('ready', flush=True); time.sleep(60)"
            ),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert process.stdout is not None
    assert process.stdout.readline().strip() == "ready"

    service_module._kill_process(process, process.pid)

    assert process.returncode == -signal.SIGKILL


def test_job_service_persists_remote_scheduler_job_id(tmp_path):
    store_path = tmp_path / "jobs.json"
    finished = threading.Event()

    class FullAgent:
        def dispatch(self, command, arguments):
            del command, arguments
            finished.set()
            return json.dumps(
                {
                    "status": "success",
                    "command": "abi_run",
                    "result": {
                        "outdir": str(tmp_path),
                        "remote_scheduler_job_id": "nxflow-abc",
                    },
                }
            )

    service = ABIJobService(agent=FullAgent(), max_workers=1, store_path=store_path)
    try:
        submitted = service.submit(
            {
                "command": "run",
                "backend": "nextflow",
                "arguments": {
                    "analysis_type": "metatranscriptomics",
                    "outdir": str(tmp_path),
                    "confirm_execution": True,
                },
            }
        )
        assert finished.wait(timeout=2)
        deadline = time.time() + 2
        while time.time() < deadline:
            job = service.get_job(submitted["job_id"])
            if job["status"] == "succeeded":
                break
            time.sleep(0.05)
        assert job["remote_scheduler_job_id"] == "nxflow-abc"
    finally:
        service.shutdown()

    reloaded = ABIJobService(max_workers=1, store_path=store_path)
    try:
        job = reloaded.get_job(submitted["job_id"])
        assert job["status"] == "succeeded"
        assert job["remote_scheduler_job_id"] == "nxflow-abc"
    finally:
        reloaded.shutdown()
