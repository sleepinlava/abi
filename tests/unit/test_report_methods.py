"""Unit tests for abi.report.methods — write_methods (Resources & Databases section)."""

from __future__ import annotations

from pathlib import Path

from abi.report.methods import write_methods

# ── write_methods: Resources & Databases ──────────────────────────────────


def test_write_methods_with_resource_manifest(tmp_path: Path) -> None:
    """L128-145: Resources & Databases section with resource_manifest."""
    result_dir = tmp_path
    prov_dir = result_dir / "provenance"
    prov_dir.mkdir(parents=True)
    tables_dir = result_dir / "tables"
    tables_dir.mkdir(parents=True)

    # Write required provenance files so write_methods doesn't crash on _read_tsv
    (prov_dir / "tool_versions.tsv").write_text(
        "tool_id\texecutable\tenv_name\tversion\tstatus\n"
        "fastp\t/usr/bin/fastp\trnaseq\t0.23.4\tok\n",
        encoding="utf-8",
    )
    (prov_dir / "commands.tsv").write_text(
        "step_id\tsample_id\tstep_name\ttool_id\tcategory\tcommand\tstatus\t"
        "return_code\tremote_scheduler_job_id\treason\tparsed_status\tstandard_tables\n"
        "S1_qc\tS1\tqc\tfastp\tqc\tfastp -i in.fq\tsuccess\t0\t\t\tok\t\n",
        encoding="utf-8",
    )

    resource_manifest = {
        "resources": [
            {
                "id": "SILVA_138",
                "version": "138.1",
                "path": "/db/silva_138",
                "checksum_sha256": (
                    "abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890"
                ),
            },
            {
                "id": "uniprot",
                "version": "2024_01",
                "path": "/db/uniprot",
                "checksum_sha256": "1234",
            },
            {
                "id": "NoneDB",
                "version": "",
                "path": "/db/none",
                "checksum_sha256": "",
            },
        ]
    }

    class FakePlan:
        def to_dict(self):
            return {
                "analysis_type": "rnaseq",
                "project_name": "test-project",
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

    path = write_methods(
        result_dir,
        plan=FakePlan(),
        resource_manifest=resource_manifest,
    )

    assert path.exists()
    content = path.read_text(encoding="utf-8")
    assert "## Resources & Databases" in content
    assert "SILVA_138" in content
    assert "138.1" in content

    # L143: checksum truncation >12 chars → "abcdef123456..."
    assert "abcdef123456..." in content

    # checksum always shown with "..." suffix
    assert "| 1234..." in content

    # Empty checksum → empty cell (produces "|  |" due to format padding)
    assert "|  |" in content


def test_write_methods_no_resource_manifest(tmp_path: Path) -> None:
    """resource_manifest is None → no Resources section."""
    result_dir = tmp_path
    prov_dir = result_dir / "provenance"
    prov_dir.mkdir(parents=True)
    tables_dir = result_dir / "tables"
    tables_dir.mkdir(parents=True)

    (prov_dir / "tool_versions.tsv").write_text("tool_id\tversion\n", encoding="utf-8")
    (prov_dir / "commands.tsv").write_text("step_id\tcommand\n", encoding="utf-8")

    class FakePlan:
        def to_dict(self):
            return {"analysis_type": "rnaseq", "project_name": "test"}

    path = write_methods(result_dir, plan=FakePlan())
    content = path.read_text(encoding="utf-8")
    assert "## Resources & Databases" not in content


def test_write_methods_resource_manifest_empty_resources(tmp_path: Path) -> None:
    """resource_manifest with empty resources list → no Resources section."""
    result_dir = tmp_path
    prov_dir = result_dir / "provenance"
    prov_dir.mkdir(parents=True)
    tables_dir = result_dir / "tables"
    tables_dir.mkdir(parents=True)

    (prov_dir / "tool_versions.tsv").write_text("tool_id\tversion\n", encoding="utf-8")
    (prov_dir / "commands.tsv").write_text("step_id\tcommand\n", encoding="utf-8")

    class FakePlan:
        def to_dict(self):
            return {"analysis_type": "rnaseq", "project_name": "test"}

    path = write_methods(
        result_dir,
        plan=FakePlan(),
        resource_manifest={"resources": []},
    )
    content = path.read_text(encoding="utf-8")
    assert "## Resources & Databases" not in content


# ── write_methods: Citations section ──────────────────────────────────────


def test_write_methods_with_citations(tmp_path: Path) -> None:
    """L148-162: Literature Citations section."""
    result_dir = tmp_path
    (result_dir / "provenance").mkdir(parents=True)
    (result_dir / "tables").mkdir(parents=True)
    (result_dir / "provenance" / "tool_versions.tsv").write_text(
        "tool_id\tversion\n",
        encoding="utf-8",
    )
    (result_dir / "provenance" / "commands.tsv").write_text(
        "step_id\tcommand\n",
        encoding="utf-8",
    )

    class FakePlan:
        def to_dict(self):
            return {
                "analysis_type": "rnaseq",
                "project_name": "test-project",
                "steps": [],
            }

    citations = [
        {"tool": "fastp", "stage": "qc", "citation": "Chen et al. 2018"},
    ]
    path = write_methods(result_dir, plan=FakePlan(), citations=citations)
    content = path.read_text(encoding="utf-8")
    assert "## Literature Citations" in content
    assert "fastp" in content
    assert "Chen et al. 2018" in content


# ── write_methods: Limitations section ────────────────────────────────────


def test_write_methods_with_limitations(tmp_path: Path) -> None:
    """L165-174: Known Limitations section."""
    result_dir = tmp_path
    (result_dir / "provenance").mkdir(parents=True)
    (result_dir / "tables").mkdir(parents=True)
    (result_dir / "provenance" / "tool_versions.tsv").write_text(
        "tool_id\tversion\n",
        encoding="utf-8",
    )
    (result_dir / "provenance" / "commands.tsv").write_text(
        "step_id\tcommand\n",
        encoding="utf-8",
    )

    class FakePlan:
        def to_dict(self):
            return {
                "analysis_type": "rnaseq",
                "project_name": "test-project",
                "steps": [],
            }

    limitations = ["Limitation A", "Limitation B"]
    path = write_methods(result_dir, plan=FakePlan(), limitations=limitations)
    content = path.read_text(encoding="utf-8")
    assert "## Known Limitations" in content
    assert "1. Limitation A" in content
    assert "2. Limitation B" in content


# ── write_methods: Empty steps / no plan steps ─────────────────────────────


def test_write_methods_no_steps(tmp_path: Path) -> None:
    """Empty steps list → no steps table (but provenance section still written)."""
    result_dir = tmp_path
    (result_dir / "provenance").mkdir(parents=True)
    (result_dir / "tables").mkdir(parents=True)
    (result_dir / "provenance" / "tool_versions.tsv").write_text(
        "tool_id\tversion\n",
        encoding="utf-8",
    )
    (result_dir / "provenance" / "commands.tsv").write_text(
        "step_id\tcommand\n",
        encoding="utf-8",
    )

    class FakePlan:
        def to_dict(self):
            return {
                "analysis_type": "rnaseq",
                "project_name": "no-steps",
                "steps": [],
            }

    path = write_methods(result_dir, plan=FakePlan())
    content = path.read_text(encoding="utf-8")
    assert "## Pipeline Steps" in content
    assert "## Provenance" in content
