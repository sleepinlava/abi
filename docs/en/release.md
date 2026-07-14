# Release Guide

`abi-agent` is the only PyPI distribution produced from this repository.

## Pre-Release Checks

Run the consolidated release check before tagging or publishing:

```bash
scripts/release_check.sh
```

Before pushing a release candidate, confirm `CHANGELOG.md` has a section for
the exact `project.version` in `pyproject.toml`; CI enforces this with
`scripts/check_release_identity.py`. The same check requires the Claude Code and
Codex plugin manifest versions to equal `project.version`.

Choose a version that is absent from both PyPI and remote Git tags. Tags and
PyPI versions are immutable identities: never move or reuse a tag after it has
been pushed. If a tag points to mismatched package metadata, abandon that
version and increment again. Version `1.5.4` was not published because its tag
was created against `1.5.3` metadata; the next valid release is `1.5.5`.

The script creates a POSIX temporary directory under `/tmp` by default and
exports `TMPDIR`, `TMP`, and `TEMP` before running tests. This keeps
permission-sensitive checks off WSL/Windows-mounted temporary directories. Use
`ABI_RELEASE_TMPDIR` or `ABI_RELEASE_TMP_ROOT` to override the location.

The script runs the same quality gate expected by CI:

```bash
ruff check src/ tests/
ruff format --check src/ tests/
mypy src/abi/ --ignore-missing-imports
python -m pytest tests/ src/abi/sciplot/tests/ -v --tb=short \
  --strict-markers -m "not requires_tools" --capture=no \
  --cov=src/abi --cov-branch --cov-report=term-missing:skip-covered \
  --cov-report=xml --cov-report=json:coverage.json --cov-fail-under=75
python scripts/check_module_coverage.py --coverage coverage.json

python -m build
abi query --type metagenomic_plasmid --what stages
```

After building a wheel, install it with its `[mcp]` extra and smoke-test the
installed commands in a clean environment when possible:

```bash
abi list-types
abi query --type metagenomic_plasmid --what stages
abi query --type rnaseq_expression --what tools
autoplasm --help
abi dry-run --type metagenomic_plasmid --config examples/config_minimal.yaml --profile dry_run
abi doctor-agent --type metatranscriptomics
abi export-openai-tools --type metatranscriptomics --format json
abi install-skills --target /tmp/abi-smoke-skills
abi-mcp --help 2>/dev/null || python -m abi.mcp.server --help 2>/dev/null || true
for platform in claude-code opencode codex; do
  abi agent install "$platform" --scope project --project-dir "/tmp/abi-release-agent-$platform"
  abi agent doctor "$platform" --scope project --project-dir "/tmp/abi-release-agent-$platform"
done
```

Run this with the clean wheel environment's `bin` directory on `PATH`, because
the doctor verifies the installed `abi-mcp` entry point. `integrations/` is a
release input: it must be present in both distributions and every Docker `/app`
context, and a change to it must exercise the Docker workflow.

## GitHub Actions

- `ci.yml` runs lint, format check, mypy, tests, and a build check.
- `docker.yml` builds and smoke-tests plugin images on relevant PRs. It pushes
  images with provenance and SBOM only for tags or approved manual dispatches;
  local PR image loads intentionally disable attestations. Published images are
  multi-platform except RNA-seq, which remains `linux/amd64`-only until its
  R/DESeq2 environment passes a native arm64 build and smoke test.
- `release.yml` builds distributions, creates a GitHub Release for `v*` tags,
  and emits the published event.
- `publish-pypi.yml` downloads those exact Release artifacts and publishes
  them through PyPI Trusted Publishing. PyPI binds the OIDC identity to this
  filename, so it remains required.

No optional bot or duplicate publishing workflow belongs in `.github/workflows/`.
The required workflow set is exactly `ci.yml`, `docker.yml`, `release.yml`, and
`publish-pypi.yml`.

The canonical automatic chain is:

```text
verified master commit → v<version> tag → reusable CI quality gate
→ build and smoke-test wheel/sdist → GitHub Release with exact artifacts
→ top-level release.published event starts publish-pypi.yml
→ download Release artifacts → PyPI Trusted Publishing
```

Do not call `publish-pypi.yml` as a reusable workflow: PyPI does not support the
parent workflow's OIDC Build Config URI. `release.published` is the single
automatic publication trigger. Recovery uses `workflow_dispatch` with the
existing GitHub Release tag and never rebuilds locally. Renaming the publisher
requires updating the trusted publisher configuration on PyPI first.

Before merging packaging or container changes, require a successful default
sdist-to-wheel build and all applicable Docker matrix jobs. The PR Docker gate
must cover build, local load, and `abi list-types`; a successful BuildKit setup
or Conda solve alone is not sufficient. The plasmid image is intentionally
excluded from automatic PR builds because of its size and must be validated by
manual workflow dispatch before a container release that affects it.

## Post-Release Verification

After publication, verify the GitHub Release and PyPI version, confirm Trusted
Publishing provenance and file hashes, install the wheel in a clean environment,
and run `abi list-types`, `autoplasm --help`, and representative plugin dry-runs.
For container tags, verify the GHCR image can be pulled and runs
`abi list-types`. Record links to the Release, PyPI project, release workflow,
publish job, and container workflow in the release handoff.
