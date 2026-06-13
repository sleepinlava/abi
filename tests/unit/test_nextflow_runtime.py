from abi.dag import infer_dag
from abi.exporters import NextflowExporter
from abi.plugins import get_plugin
from abi.runtimes.nextflow import (
    _command_rows,
    _remote_scheduler_jobs,
    _trace_by_process_name,
)


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
