"""Repository deliverable checks from Rebuild.md."""

from __future__ import annotations

from pathlib import Path


def test_pypi_distribution_excludes_runtime_artifacts() -> None:
    root = Path(__file__).resolve().parents[1]
    pyproject = (root / "pyproject.toml").read_text(encoding="utf-8")
    forbidden_entries = [
        '".mamba"',
        '"resources"',
        '"results"',
        '"log"',
        '"work"',
        '".nextflow"',
        '"nextflow_work"',
        '"nf_work"',
    ]

    included_forbidden_entries = [entry for entry in forbidden_entries if entry in pyproject]

    assert included_forbidden_entries == []


def test_rebuild_documentation_deliverables_exist() -> None:
    root = Path(__file__).resolve().parents[1]
    required = [
        "docs/abi_spec_v0.1.md",
        "docs/next_development_plan.md",
        "docs/plugin_development_guide.md",
        "docs/openai_interface_standard.md",
        "docs/job_service.md",
        "docs/agent_usage.md",
        "docs/workflow_validation.md",
        "docs/hpc_development.md",
        "docs/development.md",
        "docs/release.md",
        "docs/devlog.md",
        "demo_artifacts/README.md",
        "baseline_comparison/README.md",
        "figures/README.md",
        "metrics.tsv",
    ]

    missing = [path for path in required if not (root / path).exists()]

    assert missing == []


def test_release_workflow_smoke_tests_installed_demo_dry_runs() -> None:
    root = Path(__file__).resolve().parents[1]
    release_workflow = (root / ".github/workflows/release.yml").read_text(encoding="utf-8")

    assert "abi dry-run" in release_workflow
    assert "--type metagenomic_plasmid" in release_workflow
    assert "--config examples/config_minimal.yaml" in release_workflow
    assert "--type metatranscriptomics" in release_workflow


def test_ci_includes_github_pages_deployment() -> None:
    root = Path(__file__).resolve().parents[1]
    ci_workflow = (root / ".github/workflows/ci.yml").read_text(encoding="utf-8")

    assert "actions/deploy-pages@v4" in ci_workflow
    assert "actions/upload-pages-artifact@v3" in ci_workflow
    assert ".nojekyll" in ci_workflow
