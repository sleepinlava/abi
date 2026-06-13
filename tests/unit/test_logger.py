import json

from abi.autoplasm.logger import RunLogger
from abi.autoplasm.schemas import PlanStep


def test_logger_writes_json_lines(tmp_path):
    logger = RunLogger(tmp_path)
    step = PlanStep(
        step_id="s1_fastp",
        sample_id="S1",
        step_name="qc",
        tool_id="fastp",
        category="qc",
    )
    logger.log_step(step, command=["fastp", "--help"], status="dry_run")
    line = logger.log_file.read_text(encoding="utf-8").strip()
    record = json.loads(line)
    assert record["event"] == "pipeline_step"
    assert record["payload"]["tool_name"] == "fastp"
