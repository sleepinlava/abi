from abi.dag import infer_dag
from abi.exporters import NextflowExporter
from abi.plugins import get_plugin
from abi.runtimes.base import RuntimeOptions
from abi.runtimes.hpc import _safe_name
from abi.runtimes.nextflow import (
    NextflowRuntime,
    _command_rows,
    _remote_scheduler_jobs,
    _trace_by_process_name,
)
from abi.tools import ResourceSpec


def test_trace_rows_are_indexed_by_process_and_tag():
    row = {
        "name": "RNA1_ALIGNMENT_STAR (RNA1_alignment_star)",
        "status": "COMPLETED",
        "exit": "0",
    }

    indexed = _trace_by_process_name([row])

    assert indexed["RNA1_ALIGNMENT_STAR"] == row


def test_remote_scheduler_jobs_are_extracted_from_nextflow_trace_fields():
    rows = [
        {
            "name": "RNA1_ALIGNMENT_STAR (RNA1_alignment_star)",
            "native_id": "12345.cluster",
            "status": "COMPLETED",
            "executor": "slurm",
        },
        {
            "process": "RNA1_EXPRESSION_FEATURECOUNTS",
            "job id": "67890",
            "status": "COMPLETED",
        },
    ]

    jobs = _remote_scheduler_jobs(rows)

    assert jobs == [
        {
            "scheduler_job_id": "12345.cluster",
            "process": "RNA1_ALIGNMENT_STAR (RNA1_alignment_star)",
            "task_id": "",
            "status": "COMPLETED",
            "executor": "slurm",
        },
        {
            "scheduler_job_id": "67890",
            "process": "RNA1_EXPRESSION_FEATURECOUNTS",
            "task_id": "",
            "status": "COMPLETED",
            "executor": "",
        },
    ]


def test_nextflow_command_rows_include_remote_scheduler_job_id(tmp_path):
    plugin = get_plugin("metatranscriptomics")
    config = plugin.load_config(overrides={"outdir": str(tmp_path / "results")})
    plan = plugin.build_plan(config)
    dag = infer_dag(plan.steps, sequential_fallback=True)
    rows = _command_rows(
        plan,
        plugin.registry(),
        NextflowExporter(),
        dag=dag,
        return_code=0,
        smoke=True,
        trace_rows=[
            {
                "name": "RNA1_ALIGNMENT_STAR (RNA1_alignment_star)",
                "native_id": "12345.cluster",
                "status": "COMPLETED",
                "exit": "0",
            }
        ],
        dry_run=False,
    )

    rows_by_step = {row["step_id"]: row for row in rows}

    assert rows_by_step["RNA1_alignment_star"]["remote_scheduler_job_id"] == "12345.cluster"
    assert rows_by_step["RNA1_qc_fastp"]["remote_scheduler_job_id"] == ""


def test_runtime_forwards_resource_and_container_options_to_exporter(tmp_path):
    plugin = get_plugin("metatranscriptomics")
    config = plugin.load_config(overrides={"outdir": str(tmp_path / "results")})
    plan = plugin.build_plan(config)
    options = RuntimeOptions(
        engine="nextflow",
        smoke=True,
        cpu_override=7,
        memory_override="23GB",
        walltime_override="05:00:00",
        accelerator_override="gpu",
        resource_profile=None,
        container_image="docker://example/tool:1",
    )
    runtime = NextflowRuntime(plugin, options=options)

    result = runtime.dry_run(plan, config)
    script = result.outputs["workflow"].read_text(encoding="utf-8")

    assert "cpus 7" in script
    assert "memory '23.GB'" in script
    assert "time '05:00:00'" in script
    assert "accelerator gpu" in script
    assert "container 'docker://example/tool:1'" in script


# ═══════════════════════════════════════════════════════════════════════════
# HPC Runtime tests (Phase 3)
# ═══════════════════════════════════════════════════════════════════════════


class TestHpcRuntime:
    """Unit tests for HpcRuntime script generation and parsing."""

    def test_safe_name_sanitizes(self):
        assert _safe_name("RNA1_alignment_star") == "RNA1_alignment_star"
        assert " " not in _safe_name("step with spaces")
        assert len(_safe_name("a" * 100)) <= 50

    def test_resource_to_slurm_directives_in_hpc_context(self):
        spec = ResourceSpec(cpu=8, memory="16GB", walltime="04:00:00")
        dirs = spec.to_slurm_directives()
        assert "#SBATCH --cpus-per-task=8" in dirs
        assert "#SBATCH --mem=16G" in dirs
        assert "#SBATCH --time=04:00:00" in dirs

    def test_resource_to_pbs_directives_in_hpc_context(self):
        spec = ResourceSpec(cpu=16, memory="32GB", walltime="08:00:00")
        dirs = spec.to_pbs_directives()
        assert any("#PBS -l nodes=1:ppn=16" in d for d in dirs)
        assert any("mem=32g" in d.lower() for d in dirs)

    def test_hpc_runtime_imports(self):
        """HpcRuntime is importable and follows the ABIRuntime protocol."""
        from abi.runtimes import HpcRuntime

        assert hasattr(HpcRuntime, "check")
        assert hasattr(HpcRuntime, "dry_run")
        assert hasattr(HpcRuntime, "run")
