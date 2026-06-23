"""Unit tests for contract lint — DAG validation, assertion syntax check (B18/B20/B19)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from abi.contracts.lint import (
    lint_assertion_syntax,
    lint_dag,
    lint_resource_blocks,
    lint_tool_contracts,
    run_contract_lint,
)

# ═══════════════════════════════════════════════════════════════════════════
# B18: DAG structure checks
# ═══════════════════════════════════════════════════════════════════════════


class TestLintDag:
    def test_empty_dag(self):
        findings = lint_dag({"nodes": []})
        assert any(f.check == "empty_dag" for f in findings)

    def test_clean_linear_dag(self):
        dag = {
            "nodes": [
                {"id": "A", "depends_on": []},
                {"id": "B", "depends_on": ["A"]},
                {"id": "C", "depends_on": ["B"]},
            ]
        }
        findings = lint_dag(dag)
        errors = [f for f in findings if f.severity == "error"]
        assert errors == [], f"Unexpected errors: {errors}"

    def test_broken_depends_on(self):
        """B18: depends_on references a non-existent node."""
        dag = {
            "nodes": [
                {"id": "A", "depends_on": []},
                {"id": "B", "depends_on": ["NONEXISTENT"]},
            ]
        }
        findings = lint_dag(dag)
        broken = [f for f in findings if f.check == "broken_dep"]
        assert len(broken) >= 1
        assert any("NONEXISTENT" in f.detail for f in broken)

    def test_cycle_detection(self):
        """B19: DAG with A→B→C→A cycle."""
        dag = {
            "nodes": [
                {"id": "A", "depends_on": ["C"]},
                {"id": "B", "depends_on": ["A"]},
                {"id": "C", "depends_on": ["B"]},
            ]
        }
        findings = lint_dag(dag)
        cycles = [f for f in findings if f.check == "cycle"]
        assert len(cycles) >= 1

    def test_self_loop_detection(self):
        """A node depending on itself should be detected."""
        dag = {
            "nodes": [
                {"id": "A", "depends_on": ["A"]},
            ]
        }
        findings = lint_dag(dag)
        cycles = [f for f in findings if f.check == "cycle"]
        assert len(cycles) >= 1

    def test_orphan_node_warning(self):
        dag = {
            "nodes": [
                {"id": "A", "depends_on": []},
                {"id": "B", "depends_on": ["A"]},
                {"id": "ORPHAN", "depends_on": []},
            ]
        }
        findings = lint_dag(dag)
        orphans = [f for f in findings if f.check == "orphan"]
        assert any("ORPHAN" in f.detail for f in orphans)

    def test_node_with_dependents_not_orphan(self):
        dag = {
            "nodes": [
                {"id": "A", "depends_on": []},
                {"id": "B", "depends_on": ["A"]},
            ]
        }
        findings = lint_dag(dag)
        orphans = [f for f in findings if f.check == "orphan"]
        # A has a dependent (B), so not orphan
        assert not any("A" in f.detail for f in orphans)

    def test_duplicate_id_detection(self):
        dag = {
            "nodes": [
                {"id": "A", "depends_on": []},
                {"id": "A", "depends_on": []},
            ]
        }
        findings = lint_dag(dag)
        dupes = [f for f in findings if f.check == "duplicate_id"]
        assert len(dupes) >= 1

    def test_missing_id(self):
        dag = {
            "nodes": [
                {"depends_on": []},
            ]
        }
        findings = lint_dag(dag)
        assert any(f.check == "missing_id" for f in findings)

    def test_complex_dag_no_errors(self):
        """A diamond-shaped DAG should be clean."""
        dag = {
            "nodes": [
                {"id": "A", "depends_on": []},
                {"id": "B", "depends_on": ["A"]},
                {"id": "C", "depends_on": ["A"]},
                {"id": "D", "depends_on": ["B", "C"]},
            ]
        }
        findings = lint_dag(dag)
        errors = [f for f in findings if f.severity == "error"]
        assert errors == [], f"Unexpected errors: {errors}"

    def test_misplaced_output_contract_is_rejected(self):
        dag = {
            "nodes": {
                "qc": {
                    "outputs": {
                        "report": {"type": "file", "min_size": "1KB"},
                    }
                }
            }
        }
        findings = lint_dag(dag)
        assert any(f.check == "misplaced_output_contract" for f in findings)


# ═══════════════════════════════════════════════════════════════════════════
# B20: Assertion syntax
# ═══════════════════════════════════════════════════════════════════════════


class TestLintAssertionSyntax:
    def test_valid_assertion_passes(self):
        """output_json.xxx fields resolve via _StubAttr in lint namespace."""
        dag = {
            "nodes": [
                {
                    "id": "test",
                    "assertions": ["output_json.summary.total_reads > 0"],
                }
            ]
        }
        findings = lint_assertion_syntax(dag)
        assert findings == []

    def test_valid_isclose_assertion(self):
        dag = {
            "nodes": [
                {
                    "id": "test",
                    "assertions": ["isclose(output_json.stats.q20, 0.95, rel_tol=0.01)"],
                }
            ]
        }
        findings = lint_assertion_syntax(dag)
        assert findings == []

    def test_valid_exists_assertion(self):
        dag = {
            "nodes": [
                {
                    "id": "test",
                    "assertions": ["output_files.real exists"],
                }
            ]
        }
        findings = lint_assertion_syntax(dag)
        assert findings == []

    def test_syntax_error_detected(self):
        """B20: Assertion with invalid Python syntax should be flagged."""
        dag = {
            "nodes": [
                {
                    "id": "test",
                    "assertions": ["output_json.summary.total_reads >"],  # incomplete
                }
            ]
        }
        findings = lint_assertion_syntax(dag)
        syntax_errors = [f for f in findings if f.check == "assertion_syntax"]
        assert len(syntax_errors) >= 1

    def test_undefined_variable_detected(self):
        """Unknown variable in assertion is a runtime error at lint time."""
        dag = {
            "nodes": [
                {
                    "id": "test",
                    "assertions": ["undefined_variable > 5"],
                }
            ]
        }
        findings = lint_assertion_syntax(dag)
        assert len(findings) >= 1
        assert any("undefined_variable" in f.detail for f in findings)

    def test_assertion_lint_does_not_evaluate_code(self, tmp_path):
        marker = tmp_path / "must-not-exist"
        dag = {
            "nodes": [
                {
                    "id": "test",
                    "assertions": [f"open({str(marker)!r}, 'w')"],
                }
            ]
        }
        findings = lint_assertion_syntax(dag)
        assert findings
        assert not marker.exists()

    def test_multiple_nodes_checked(self):
        dag = {
            "nodes": [
                {"id": "A", "assertions": ["return_code == 0"]},  # valid
                {"id": "B", "assertions": ["output_json.x >"]},  # syntax error
                {"id": "C", "assertions": ["output_json.x > 0"]},  # valid
            ]
        }
        findings = lint_assertion_syntax(dag)
        # Only B should have an error (syntax)
        assert len(findings) == 1
        assert findings[0].location == "B"

    def test_empty_assertions_noop(self):
        dag = {"nodes": [{"id": "A"}]}
        findings = lint_assertion_syntax(dag)
        assert findings == []


# ═══════════════════════════════════════════════════════════════════════════
# Tool contract checks
# ═══════════════════════════════════════════════════════════════════════════


class TestLintToolContracts:
    def test_valid_contract_passes(self):
        contracts = {
            "fastp": {
                "tool_id": "fastp",
                "name": "fastp",
                "category": "qc",
                "purpose": "Read trimming",
                "execution": {
                    "env_name": "abi-base",
                    "executable": "fastp",
                    "command_template": "fastp --input {read1}",
                },
            }
        }
        findings = lint_tool_contracts(contracts)
        errors = [f for f in findings if f.severity == "error"]
        assert errors == []

    def test_missing_required_field_warns(self):
        contracts = {
            "tool_x": {
                "tool_id": "tool_x",
                "name": "",
                "category": "",
                "purpose": "",
                "execution": {},
            }
        }
        findings = lint_tool_contracts(contracts)
        assert len(findings) > 0

    def test_cross_references_registry(self):
        contracts = {
            "fastp": {
                "tool_id": "fastp",
                "name": "f",
                "category": "qc",
                "purpose": "trim",
                "execution": {"env_name": "e", "executable": "f", "command_template": "f"},
            }
        }
        registry_ids = {"fastp", "star"}
        findings = lint_tool_contracts(contracts, registry_tool_ids=registry_ids)
        # star is in registry but has no contract
        missing = [f for f in findings if "star" in f.detail]
        assert len(missing) >= 1

    def test_registry_contract_command_mismatch_is_error(self):
        contracts = {
            "spades": {
                "tool_id": "spades",
                "name": "SPAdes",
                "category": "assembly",
                "purpose": "assemble",
                "execution": {
                    "executable": "spades.py",
                    "command_template": "spades.py --isolate -1 {read1}",
                },
            }
        }
        registry_tools = {
            "spades": {
                "id": "spades",
                "category": "assembly",
                "executable": "spades.py",
                "command_template": "spades.py --careful -1 {read1}",
            }
        }

        findings = lint_tool_contracts(
            contracts,
            registry_tool_ids={"spades"},
            registry_tools=registry_tools,
        )

        assert any(
            finding.severity == "error" and finding.check == "registry_contract_mismatch"
            for finding in findings
        )

    def test_registry_contract_whitespace_differences_are_ignored(self):
        contracts = {
            "fastp": {
                "tool_id": "fastp",
                "name": "fastp",
                "category": "qc",
                "purpose": "trim",
                "execution": {
                    "executable": "fastp",
                    "command_template": "fastp  -i {read1}\n-o {clean_read1}",
                },
            }
        }
        registry_tools = {
            "fastp": {
                "id": "fastp",
                "category": "qc",
                "executable": "fastp",
                "command_template": "fastp -i {read1} -o {clean_read1}",
            }
        }

        findings = lint_tool_contracts(
            contracts,
            registry_tool_ids={"fastp"},
            registry_tools=registry_tools,
        )

        assert not any(f.check == "registry_contract_mismatch" for f in findings)


# ═══════════════════════════════════════════════════════════════════════════
# Integration
# ═══════════════════════════════════════════════════════════════════════════


class TestRunContractLint:
    def test_clean_dag_passes(self):
        dag = {
            "nodes": [
                {"id": "A", "depends_on": []},
                {"id": "B", "depends_on": ["A"]},
            ]
        }
        result = run_contract_lint(dag)
        assert result["passed"] is True
        assert result["error_count"] == 0

    def test_broken_dag_fails(self):
        dag = {
            "nodes": [
                {"id": "A", "depends_on": ["MISSING"]},
            ]
        }
        result = run_contract_lint(dag)
        assert result["passed"] is False
        assert result["error_count"] >= 1

    def test_findings_are_serializable(self):
        import json

        dag = {"nodes": [{"id": "A", "depends_on": ["MISSING"]}]}
        result = run_contract_lint(dag)
        dumped = json.dumps(result)
        loaded = json.loads(dumped)
        assert loaded["passed"] is False
        assert len(loaded["findings"]) >= 1

    def test_with_contracts_and_registry(self):
        dag = {"nodes": [{"id": "A", "depends_on": []}]}
        contracts = {
            "fastp": {
                "tool_id": "fastp",
                "name": "f",
                "category": "qc",
                "purpose": "trim",
                "execution": {"env_name": "e", "executable": "f", "command_template": "f"},
            }
        }
        result = run_contract_lint(dag, contracts=contracts, registry_tool_ids={"fastp"})
        assert isinstance(result["findings"], list)

    def test_assertion_syntax_errors_included(self):
        dag = {
            "nodes": [
                {"id": "A", "assertions": ["bad syntax >>>"]},
            ]
        }
        result = run_contract_lint(dag)
        assert result["error_count"] >= 1


# ═══════════════════════════════════════════════════════════════════════════
# Resource block lint tests (Phase 1)
# ═══════════════════════════════════════════════════════════════════════════


class TestLintResourceBlocks:
    """lint_resource_blocks warns when resources blocks are missing/invalid."""

    def test_missing_resources_warns(self):
        contracts = {
            "fastp": {
                "tool_id": "fastp",
                "name": "fastp",
                "category": "qc",
                "purpose": "trim",
                "execution": {"env_name": "e", "executable": "f", "command_template": "f"},
            }
        }
        findings = lint_resource_blocks(contracts)
        assert len(findings) == 1
        assert findings[0].severity == "warning"
        assert "missing 'resources'" in findings[0].detail

    def test_valid_resources_no_findings(self):
        contracts = {
            "fastp": {
                "tool_id": "fastp",
                "name": "fastp",
                "resources": {"cpu": 4, "memory": "4GB", "walltime": "01:00:00"},
            }
        }
        findings = lint_resource_blocks(contracts)
        assert len(findings) == 0

    def test_invalid_cpu_is_error(self):
        contracts = {
            "bad": {
                "tool_id": "bad",
                "resources": {"cpu": 0, "memory": "4GB", "walltime": "01:00:00"},
            }
        }
        findings = lint_resource_blocks(contracts)
        assert any(f.severity == "error" for f in findings)

    def test_empty_walltime_warns(self):
        contracts = {
            "bad": {
                "tool_id": "bad",
                "resources": {"cpu": 4, "memory": "4GB", "walltime": ""},
            }
        }
        findings = lint_resource_blocks(contracts)
        assert any("walltime" in f.detail for f in findings)

    def test_run_contract_lint_includes_resource_findings(self):
        contracts = {
            "fastp": {
                "tool_id": "fastp",
                "name": "f",
                "category": "qc",
                "purpose": "trim",
                "execution": {"env_name": "e", "executable": "f", "command_template": "f"},
            }
        }
        dag = {"nodes": []}
        result = run_contract_lint(dag, contracts=contracts, registry_tool_ids={"fastp"})
        resource_warnings = [f for f in result["findings"] if f["check"] == "missing_resources"]
        assert len(resource_warnings) >= 1
