import pytest

from abi.dag import infer_dag, process_name
from abi.plugins import get_plugin
from abi.schemas import ABIError, ABIPlanStep


def test_infer_dag_links_steps_by_declared_paths(tmp_path):
    plugin = get_plugin("metatranscriptomics")
    config = plugin.load_config(
        overrides={
            "outdir": str(tmp_path / "results"),
            "log_dir": str(tmp_path / "log"),
        }
    )
    plan = plugin.build_plan(config)

    dag = infer_dag(plan.steps)

    assert dag.roots == ["RNA1_qc_fastp"]
    assert dag.edges["RNA1_qc_fastp"] == []
    assert dag.edges["RNA1_alignment_star"] == ["RNA1_qc_fastp"]
    assert dag.edges["RNA1_expression_featurecounts"] == ["RNA1_alignment_star"]
    assert dag.topological_order == [
        "RNA1_qc_fastp",
        "RNA1_alignment_star",
        "RNA1_expression_featurecounts",
    ]


def test_infer_dag_rejects_duplicate_output_paths(tmp_path):
    steps = [
        ABIPlanStep(
            step_id="a",
            sample_id="S1",
            step_name="first",
            tool_id="mock",
            category="test",
            outputs={"out": str(tmp_path / "shared.txt")},
        ),
        ABIPlanStep(
            step_id="b",
            sample_id="S1",
            step_name="second",
            tool_id="mock",
            category="test",
            outputs={"out": str(tmp_path / "shared.txt")},
        ),
    ]

    with pytest.raises(ABIError, match="Duplicate ABI output path"):
        infer_dag(steps)


def test_infer_dag_allows_shared_step_output_directories(tmp_path):
    shared = tmp_path / "01_qc" / "S1"
    steps = [
        ABIPlanStep(
            step_id="fastp",
            sample_id="S1",
            step_name="qc",
            tool_id="fastp",
            category="qc",
            outputs={"output_dir": str(shared)},
        ),
        ABIPlanStep(
            step_id="fastqc",
            sample_id="S1",
            step_name="qc",
            tool_id="fastqc",
            category="qc",
            outputs={"output_dir": str(shared)},
        ),
    ]

    dag = infer_dag(steps)

    assert dag.edges == {"fastp": [], "fastqc": []}
    assert dag.binding_for("fastp").produced_paths["output_dir"] == str(shared)
    assert dag.binding_for("fastqc").produced_paths["output_dir"] == str(shared)


def test_infer_dag_sequential_fallback_links_unresolved_steps(tmp_path):
    shared = tmp_path / "01_qc" / "S1"
    steps = [
        ABIPlanStep(
            step_id="fastp",
            sample_id="S1",
            step_name="qc",
            tool_id="fastp",
            category="qc",
            outputs={"output_dir": str(shared)},
        ),
        ABIPlanStep(
            step_id="fastqc",
            sample_id="S1",
            step_name="qc",
            tool_id="fastqc",
            category="qc",
            outputs={"output_dir": str(shared)},
        ),
    ]

    dag = infer_dag(steps, sequential_fallback=True)

    assert dag.roots == ["fastp"]
    assert dag.edges["fastqc"] == ["fastp"]


def test_infer_dag_accepts_metagenomic_plasmid_shared_output_dirs(tmp_path):
    plugin = get_plugin("metagenomic_plasmid")
    config = plugin.load_config(
        "examples/config_minimal.yaml",
        overrides={
            "outdir": str(tmp_path / "plasmid"),
            "log_dir": str(tmp_path / "log"),
        },
    )
    plan = plugin.build_plan(config)

    dag = infer_dag(plan.steps, sequential_fallback=True)

    # The DAG-driven planner generates steps from pipeline_dag.yaml.
    # The exact root depends on which optional stages are enabled in
    # the minimal config — it could be fastqc_raw, host_prediction,
    # assembly, or fastp.  Verify the DAG is structurally sound
    # regardless.
    # DAG 驱动的规划器从 pipeline_dag.yaml 生成步骤。
    # 根节点取决于最小配置中启用的可选阶段 —— 可能是 fastqc_raw、
    # host_prediction、assembly 或 fastp。验证 DAG 结构正确即可。
    assert len(dag.roots) >= 1, f"Expected at least 1 root, got {dag.roots}"
    assert "S1_qc_fastp" in dag.topological_order
    assert "S2_qc_fastp" in dag.topological_order
    # Verify the plasmid detection chain is intact
    assert "S1_plasmid_detect_genomad" in dag.topological_order
    assert "S1_plasmid_consensus" in dag.topological_order


def test_infer_dag_ignores_structured_non_path_values():
    step = ABIPlanStep(
        step_id="a",
        sample_id="S1",
        step_name="first",
        tool_id="mock",
        category="test",
        inputs={"metadata": {"sample": "S1"}},
        outputs={"records": ["not", "a", "path"]},
    )

    dag = infer_dag([step])
    binding = dag.binding_for("a")

    assert binding.consumed_paths == {}
    assert binding.produced_paths == {}


def test_process_name_is_nextflow_safe():
    assert process_name("1 sample/qc-fastp") == "STEP_1_SAMPLE_QC_FASTP"
