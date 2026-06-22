"""Unit tests for abi.runtimes.hpc — HpcRuntime, _safe_name, _log_dir."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest import mock

import pytest

from abi.runtimes.base import RuntimeOptions
from abi.runtimes.hpc import HpcRuntime, _log_dir, _safe_name

# ── _safe_name ───────────────────────────────────────────────────────────


def test_safe_name_preserves_simple() -> None:
    """Simple names pass through unchanged."""
    assert _safe_name("S1_qc_fastp") == "S1_qc_fastp"


def test_safe_name_replaces_spaces() -> None:
    """Spaces are replaced with underscores."""
    assert " " not in _safe_name("S1 qc fastp")


def test_safe_name_replaces_slashes() -> None:
    """Slashes are replaced with underscores."""
    result = _safe_name("S1/qc/fastp")
    assert "/" not in result


def test_safe_name_truncates_to_50_chars() -> None:
    """Names longer than 50 characters are truncated."""
    long_name = "a" * 100
    result = _safe_name(long_name)
    assert len(result) <= 50


def test_safe_name_keeps_long_prefixes_collision_resistant() -> None:
    prefix = "sample_" + "a" * 80
    assert _safe_name(prefix + "one") != _safe_name(prefix + "two")


# ── _log_dir ─────────────────────────────────────────────────────────────


def test_log_dir_from_config() -> None:
    """Returns config value when log_dir is set."""
    assert _log_dir({"log_dir": "/var/log/abi"}) == "/var/log/abi"


def test_log_dir_default_from_outdir() -> None:
    """Derives log_dir from outdir when log_dir is not set."""
    result = _log_dir({"outdir": "/tmp/run1"})
    assert result.endswith("logs")
    assert "/tmp/run1" in result


def test_log_dir_default_fallback() -> None:
    """Falls back to /tmp/logs when neither log_dir nor outdir is set."""
    result = _log_dir({})
    assert "/tmp" in result
    assert "logs" in result


# ── HpcRuntime.__init__ ──────────────────────────────────────────────────


def test_hpc_runtime_default_options() -> None:
    """HpcRuntime creates default RuntimeOptions when none provided."""
    rt = HpcRuntime(mock.Mock())
    assert rt.options.engine == "hpc"


def test_hpc_runtime_custom_options() -> None:
    """HpcRuntime uses provided RuntimeOptions."""
    opts = RuntimeOptions(
        engine="hpc",
        scheduler="pbs",
        partition="short",
        account="myaccount",
    )
    rt = HpcRuntime(mock.Mock(), options=opts)
    assert rt.options.scheduler == "pbs"
    assert rt.options.partition == "short"


# ── HpcRuntime._scripts_dir ──────────────────────────────────────────────


def test_scripts_dir_from_config() -> None:
    """_scripts_dir returns <outdir>/provenance/hpc_scripts."""
    rt = HpcRuntime(mock.Mock())
    result = rt._scripts_dir({"outdir": "/tmp/run1"})
    assert result == Path("/tmp/run1/provenance/hpc_scripts")


def test_scripts_dir_default() -> None:
    """_scripts_dir defaults to ./provenance/hpc_scripts when no outdir."""
    rt = HpcRuntime(mock.Mock())
    result = rt._scripts_dir({})
    assert result.parts[-2:] == ("provenance", "hpc_scripts")


# ── HpcRuntime.check ─────────────────────────────────────────────────────


def test_check_slurm_found() -> None:
    """check succeeds when sbatch is on PATH."""
    with mock.patch("shutil.which", return_value="/usr/bin/sbatch"):
        rt = HpcRuntime(mock.Mock())
        rt.check()  # should not raise


def test_check_pbs_found() -> None:
    """check succeeds when qsub is on PATH for PBS scheduler."""
    opts = RuntimeOptions(engine="hpc", scheduler="pbs")
    with mock.patch("shutil.which", return_value="/usr/bin/qsub"):
        rt = HpcRuntime(mock.Mock(), options=opts)
        rt.check()  # should not raise


def test_check_not_found() -> None:
    """check raises ABIError when scheduler is not found."""
    from abi.schemas import ABIError

    with mock.patch("shutil.which", return_value=None):
        rt = HpcRuntime(mock.Mock())
        with pytest.raises(ABIError, match="not found"):
            rt.check()


# ── HpcRuntime._parse_job_id ─────────────────────────────────────────────


def test_parse_job_id_slurm() -> None:
    """Extract job ID from SLURM 'Submitted batch job 12345' output."""
    rt = HpcRuntime(mock.Mock())
    assert rt._parse_job_id("Submitted batch job 12345\n", "slurm") == "12345"


def test_parse_job_id_pbs() -> None:
    """Extract job ID from PBS '12345.scheduler.host' output."""
    rt = HpcRuntime(mock.Mock())
    assert rt._parse_job_id("12345.scheduler.host\n", "pbs") == "12345"


def test_parse_job_id_empty() -> None:
    """Returns empty string for unrecognized output."""
    rt = HpcRuntime(mock.Mock())
    assert rt._parse_job_id("", "slurm") == ""


def test_parse_job_id_no_digits() -> None:
    """Returns empty string when no digits found in SLURM output."""
    rt = HpcRuntime(mock.Mock())
    assert rt._parse_job_id("Error: submission failed\n", "slurm") == ""


# ── HpcRuntime._render_env ───────────────────────────────────────────────


def test_render_env_with_container() -> None:
    """Renders container comment when container image is set."""
    rt = HpcRuntime(mock.Mock())
    lines = rt._render_env({"env_name": "abi-base"}, container="docker://ubuntu:22.04")
    assert any("Container: docker://ubuntu:22.04" in line for line in lines)
    assert any("docker" in line for line in lines)


def test_render_env_with_mamba() -> None:
    """Renders PATH export when no container is set."""
    rt = HpcRuntime(mock.Mock())
    rt.options.mamba_root = "/opt/mamba"
    lines = rt._render_env({"env_name": "rnaseq"}, container=None)
    assert any("export PATH" in line for line in lines)
    assert any("/opt/mamba/envs/rnaseq/bin" in line for line in lines)


def test_render_env_default_mamba_root() -> None:
    """Uses default mamba_root when neither option nor config provides one."""
    rt = HpcRuntime(mock.Mock())
    rt.options.mamba_root = None
    lines = rt._render_env({}, container=None)
    assert any("export PATH" in line for line in lines)


# ── HpcRuntime._dependency_job_ids ──────────────────────────────────────


def test_dependency_job_ids_empty() -> None:
    """Returns empty list when step has no dependencies."""
    rt = HpcRuntime(mock.Mock())
    binding = mock.Mock(dependencies=[])
    from abi.dag import ABIDAG

    dag = ABIDAG(bindings=[], edges={}, roots=[], topological_order=[])
    assert rt._dependency_job_ids(binding, dag) == []


def test_dependency_job_ids_with_deps() -> None:
    """Returns placeholder job IDs for each dependency."""
    rt = HpcRuntime(mock.Mock())
    binding = mock.Mock(dependencies=["S1_trim_cutadapt", "S1_merge_vsearch"])
    from abi.dag import ABIDAG

    dag = ABIDAG(bindings=[], edges={}, roots=[], topological_order=[])
    ids = rt._dependency_job_ids(binding, dag)
    assert len(ids) == 2
    assert all("JOB_" in jid for jid in ids)


# ── HpcRuntime._cancel_jobs ──────────────────────────────────────────────


def test_cancel_jobs_slurm() -> None:
    """Uses scancel for SLURM scheduler."""
    rt = HpcRuntime(mock.Mock())
    with mock.patch("subprocess.run") as mock_run:
        rt._cancel_jobs(["12345", "12346"])
        mock_run.assert_called()
        # Last call should be scancel with the last job id
        assert mock_run.call_args_list[0][0][0][0] == "scancel"


def test_cancel_jobs_pbs() -> None:
    """Uses qdel for PBS scheduler."""
    opts = RuntimeOptions(engine="hpc", scheduler="pbs")
    rt = HpcRuntime(mock.Mock(), options=opts)
    with mock.patch("subprocess.run") as mock_run:
        rt._cancel_jobs(["12345"])
        mock_run.assert_called_once()
        assert mock_run.call_args[0][0][0] == "qdel"


# ── HpcRuntime._resolve_step_resources ───────────────────────────────────


def test_resolve_step_resources_no_overrides() -> None:
    """Returns resolved resources without CLI overrides."""
    rt = HpcRuntime(mock.Mock())
    resources = rt._resolve_step_resources("fastp", {}, {"threads": 4})
    assert resources.cpu > 0
    assert resources.memory


def test_resolve_step_resources_with_cli_overrides() -> None:
    """CLI overrides are passed through to resolve_resources."""
    opts = RuntimeOptions(
        engine="hpc",
        cpu_override=8,
        memory_override="16GB",
        walltime_override="02:00:00",
    )
    rt = HpcRuntime(mock.Mock(), options=opts)
    resources = rt._resolve_step_resources("fastp", {}, {})
    assert resources.cpu == 8
    assert resources.memory == "16GB"
    assert resources.walltime == "02:00:00"


# ── HpcRuntime._build_submit_command ─────────────────────────────────────


def test_build_submit_command_slurm() -> None:
    """Builds sbatch for-loop for SLURM."""
    rt = HpcRuntime(mock.Mock())
    cmd = rt._build_submit_command([Path("step1.sh"), Path("step2.sh")])
    assert "sbatch" in cmd
    assert "step1.sh" in cmd
    assert "step2.sh" in cmd


def test_build_submit_command_pbs() -> None:
    """Builds qsub for-loop for PBS."""
    opts = RuntimeOptions(engine="hpc", scheduler="pbs")
    rt = HpcRuntime(mock.Mock(), options=opts)
    cmd = rt._build_submit_command([Path("step.sh")])
    assert "qsub" in cmd


def test_submit_jobs_uses_actual_slurm_afterok_dependencies(tmp_path: Path) -> None:
    from abi.dag import ABIDAG, StepBinding
    from abi.schemas import PlanStep

    first = PlanStep("first", "stage", "tool", "stage", None)
    second = PlanStep("second", "stage", "tool", "stage", None)
    bindings = [
        StepBinding(first, "first", [], {}, {}),
        StepBinding(second, "second", ["first"], {}, {}),
    ]
    rt = HpcRuntime(mock.Mock())
    rt._dag = ABIDAG(bindings, {"first": [], "second": ["first"]}, ["first"], ["first", "second"])
    rt._script_by_step = {"first": tmp_path / "first.sh", "second": tmp_path / "second.sh"}
    responses = [
        subprocess.CompletedProcess([], 0, "101\n", ""),
        subprocess.CompletedProcess([], 0, "102\n", ""),
    ]

    with mock.patch("subprocess.run", side_effect=responses) as run:
        assert rt._submit_jobs(list(rt._script_by_step.values())) == {
            "first": "101",
            "second": "102",
        }

    assert "--dependency=afterok:101" in run.call_args_list[1].args[0]


def test_poll_slurm_uses_sacct_for_jobs_missing_from_squeue() -> None:
    rt = HpcRuntime(mock.Mock())
    responses = [
        subprocess.CompletedProcess([], 0, "", ""),
        subprocess.CompletedProcess([], 0, "42|COMPLETED|0:0\n", ""),
    ]

    with mock.patch("subprocess.run", side_effect=responses):
        assert rt._poll_slurm(["42"]) == {"42": "COMPLETED"}


def test_resume_requires_matching_nonempty_checksums(tmp_path: Path) -> None:
    import json

    from abi.contracts.step_contract import compute_file_checksum
    from abi.schemas import PlanStep

    outdir = tmp_path / "out"
    output = outdir / "result.tsv"
    output.parent.mkdir(parents=True)
    output.write_text("feature\tvalue\nA\t1\n", encoding="utf-8")
    provenance = outdir / "provenance"
    provenance.mkdir()
    (provenance / "checksums.json").write_text(
        json.dumps({str(output): compute_file_checksum(output)}), encoding="utf-8"
    )
    step = PlanStep(
        step_id="result",
        step_name="stage",
        tool_id="tool",
        category="stage",
        sample_id=None,
        outputs={"table": str(output), "output_dir": str(outdir)},
    )
    rt = HpcRuntime(mock.Mock())

    assert rt._step_is_resumable(step, {"outdir": str(outdir)}) is True
    output.write_text("changed\n", encoding="utf-8")
    assert rt._step_is_resumable(step, {"outdir": str(outdir)}) is False


# ── HpcRuntime dry_run ───────────────────────────────────────────────────


def test_dry_run_generates_scripts(tmp_path: Path) -> None:
    """dry_run writes SLURM scripts to provenance/hpc_scripts/."""
    from abi.dag import ABIDAG, StepBinding
    from abi.schemas import ExecutionPlan, PlanStep, SampleContext, SampleInput

    plugin = mock.Mock()
    plugin.registry.return_value.has.return_value = False
    plugin.registry.return_value.get.return_value = {}

    rt = HpcRuntime(plugin)
    outdir = tmp_path / "out"
    outdir.mkdir()

    step = PlanStep(
        step_id="S1_trim_cutadapt",
        sample_id="S1",
        step_name="primer_trimming",
        tool_id="cutadapt",
        category="qc",
        inputs={"read1": "/tmp/R1.fq"},
        outputs={"output_dir": str(outdir / "01_trimmed" / "S1")},
        params={"sample_id": "S1", "threads": 4},
    )
    sample = SampleInput(sample_id="S1", platform="illumina")
    sample_ctx = SampleContext(
        samples=[sample],
        multi_sample=False,
        has_groups=False,
        enable_sample_analysis=True,
        enable_differential_abundance=False,
    )
    plan = ExecutionPlan(
        project_name="test",
        analysis_type="amplicon_16s",
        mode="local",
        threads=4,
        outdir=str(outdir),
        log_dir=str(outdir / "logs"),
        samples=[sample],
        sample_context=sample_ctx,
        selected_tools=["cutadapt"],
        steps=[step],
    )

    # Mock infer_dag to return a valid DAG
    binding = StepBinding(
        step=step,
        process_name="S1_trim_cutadapt",
        dependencies=[],
        produced_paths={},
        consumed_paths={},
    )
    dag = ABIDAG(
        bindings=[binding],
        edges={},
        roots=["S1_trim_cutadapt"],
        topological_order=["S1_trim_cutadapt"],
    )

    config = {"outdir": str(outdir), "log_dir": str(outdir / "logs")}
    with mock.patch("abi.runtimes.hpc.infer_dag", return_value=dag):
        result = rt.dry_run(plan, config)
    assert result.status == "dry_run"
    assert result.return_code == 0
    scripts_dir = outdir / "provenance" / "hpc_scripts"
    assert scripts_dir.is_dir()
    scripts = list(scripts_dir.glob("*.sh"))
    assert len(scripts) == 1
    content = scripts[0].read_text()
    assert "#!/bin/bash" in content
    assert "S1_trim_cutadapt" in content
    assert "#SBATCH" in content


# ── HpcRuntime._write_single_script PBS variant ──────────────────────────


def test_write_single_script_pbs(tmp_path: Path) -> None:
    """Script generation for PBS scheduler uses #PBS directives."""
    from abi.dag import infer_dag
    from abi.schemas import ABIPlanStep
    from abi.tools import ResourceSpec

    opts = RuntimeOptions(engine="hpc", scheduler="pbs", partition="short")
    plugin = mock.Mock()
    plugin.registry.return_value.has.return_value = False
    plugin.registry.return_value.get.return_value = {}
    rt = HpcRuntime(plugin, options=opts)

    outdir = tmp_path / "out"
    outdir.mkdir()
    config = {"outdir": str(outdir), "log_dir": str(outdir / "logs")}
    scripts_dir = outdir / "provenance" / "hpc_scripts"
    scripts_dir.mkdir(parents=True)

    step = ABIPlanStep(
        step_id="S1_test",
        sample_id="S1",
        step_name="test",
        tool_id="fastp",
        category="qc",
        inputs={},
        outputs={"output_dir": str(outdir / "01_qc" / "S1")},
        params={},
    )
    dag = infer_dag([step], sequential_fallback=True)

    script_path = scripts_dir / "S1_test.sh"
    rt._write_single_script(
        script_path,
        step,
        dag.binding_for("S1_test"),
        ResourceSpec(cpu=2, memory="4GB", walltime="01:00:00"),
        container=None,
        config=config,
        dag=dag,
    )
    content = script_path.read_text()
    assert "#!/bin/bash" in content
    assert "#PBS" in content
    assert "#PBS -q short" in content
    assert "abi dispatch" in content


def test_write_single_script_rejects_scheduler_directive_newlines(tmp_path: Path) -> None:
    from abi.dag import infer_dag
    from abi.schemas import ABIError, ABIPlanStep
    from abi.tools import ResourceSpec

    options = RuntimeOptions(engine="hpc", partition="compute\n#SBATCH --exclusive")
    plugin = mock.Mock()
    rt = HpcRuntime(plugin, options=options)
    step = ABIPlanStep("step", "stage", "fastp", "qc", None)
    dag = infer_dag([step])

    with pytest.raises(ABIError, match="Invalid newline"):
        rt._write_single_script(
            tmp_path / "step.sh",
            step,
            dag.binding_for("step"),
            ResourceSpec(),
            None,
            {"outdir": str(tmp_path), "log_dir": str(tmp_path / "logs")},
            dag,
        )
