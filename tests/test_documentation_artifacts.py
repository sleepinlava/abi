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
        # Core English docs (moved to docs/en/ in v1.3.0)
        "docs/en/abi_spec_v0.1.md",
        "docs/en/plugin_development_guide.md",
        "docs/en/openai_interface_standard.md",
        "docs/en/job_service.md",
        "docs/en/agent_usage.md",
        "docs/en/workflow_validation.md",
        "docs/en/hpc_development.md",
        "docs/en/development.md",
        "docs/en/release.md",
        "docs/en/devlog.md",
        # Core Chinese docs
        "docs/zh/abi_spec_v0.1.md",
        "docs/zh/agent_usage.md",
        "docs/zh/development.md",
        "docs/zh/job_service.md",
        "docs/zh/metagenomic_plasmid.md",
        "docs/zh/openai_interface_standard.md",
        "docs/zh/plugin_development_guide.md",
        "docs/zh/release.md",
        "docs/zh/workflow_validation.md",
        # Docs build infrastructure
        "docs/_base.py",
        "docs/build_docs.sh",
        "docs/index.html",
        "docs/en/conf.py",
        "docs/zh/conf.py",
        "docs/en/index.rst",
        "docs/zh/index.rst",
        # Repo-level artifacts
        "demo_artifacts/README.md",
        "baseline_comparison/README.md",
        "figures/README.md",
        "metrics.tsv",
    ]

    missing = [path for path in required if not (root / path).exists()]

    assert missing == []


def test_release_workflow_uses_full_gate_and_clean_wheel_smoke() -> None:
    root = Path(__file__).resolve().parents[1]
    release_workflow = (root / ".github/workflows/release.yml").read_text(encoding="utf-8")

    assert "uses: ./.github/workflows/ci.yml" in release_workflow
    assert "pages: write" in release_workflow
    assert "id-token: write" in release_workflow
    assert "needs: quality-gate" in release_workflow
    assert "scripts/check_release_identity.py --tag" in release_workflow
    assert "python -m venv /tmp/abi-wheel-smoke" in release_workflow
    assert "/tmp/abi-wheel-smoke/bin/abi dry-run" in release_workflow
    assert "--type metagenomic_plasmid" in release_workflow
    assert "--config examples/config_minimal.yaml" in release_workflow
    assert "uses: ./.github/workflows/publish-pypi.yml" in release_workflow
    assert "needs: release" in release_workflow
    for plugin in (
        "rnaseq_expression",
        "wgs_bacteria",
        "amplicon_16s",
        "metatranscriptomics",
        "easymetagenome",
        "viral_viwrap",
    ):
        assert plugin in release_workflow


def test_ci_treats_sciplot_docs_and_dry_runs_as_required_gates() -> None:
    root = Path(__file__).resolve().parents[1]
    ci_workflow = (root / ".github/workflows/ci.yml").read_text(encoding="utf-8")

    assert "src/abi/sciplot/tests/" in ci_workflow
    assert "--cov-branch" in ci_workflow
    assert "--cov-fail-under=75" in ci_workflow
    assert "--cov-report=json:coverage.json" in ci_workflow
    assert "python scripts/check_module_coverage.py" in ci_workflow
    assert "scripts/check_release_identity.py" in ci_workflow
    assert "|| echo" not in ci_workflow


def test_pypi_publishes_the_github_release_artifacts_without_rebuilding() -> None:
    root = Path(__file__).resolve().parents[1]
    workflow = (root / ".github/workflows/publish-pypi.yml").read_text(encoding="utf-8")

    assert "gh release download" in workflow
    assert "python -m twine check dist/*" in workflow
    assert "python -m build" not in workflow
    assert "workflow_call:" in workflow
    assert "repository_dispatch:" in workflow
    assert "github.event.client_payload.tag" in workflow
    assert '"pypi-v*"' in workflow
    assert 'RELEASE_TAG="${REQUESTED_TAG#pypi-}"' in workflow


def test_ci_includes_github_pages_deployment() -> None:
    root = Path(__file__).resolve().parents[1]
    ci_workflow = (root / ".github/workflows/ci.yml").read_text(encoding="utf-8")

    assert "actions/deploy-pages@v4" in ci_workflow
    assert "actions/upload-pages-artifact@v3" in ci_workflow
    assert ".nojekyll" in ci_workflow
