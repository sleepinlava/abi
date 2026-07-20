# ABI Development Standards

Use this workflow for every behavior, plugin, transport, documentation, packaging, Docker, or release change. The goal is a traceable path from acceptance criteria to verified artifacts.

## 1. Define behavior and acceptance criteria

Before editing code, write down:

- the user or system behavior that must change;
- inputs, outputs, errors, and compatibility expectations;
- the owning architectural boundary;
- the smallest test that proves the change;
- affected docs, plugins, runtimes, and release surfaces.

Do not combine an unrelated refactor with a behavior change. If the new behavior needs a refactor, isolate and verify the structural change first.

## 2. Choose the owning boundary

| Concern | Owner |
| --- | --- |
| Schemas, permissions, diagnostics, provenance, contracts, tables | ABI core |
| CLI, MCP, HTTP, provider descriptors | Thin transport adapter |
| Biological choices, workflow steps, parsers, assertions | Analysis plugin |
| Tool-to-Conda mapping | `environments.yaml` and generated `envs/*.yml` |
| Docker and CI packaging | Dockerfiles, workflows, package metadata, build context |
| Scientific plot behavior | `abi.sciplot` schema, renderer, lint, and tests |

Preserve the architecture rule: thick core, thin transport, clean plugin.

## 3. Implement the smallest coherent change

- Keep public APIs typed and compatible unless the change explicitly introduces a migration.
- Prefer declarative DAG, contract, schema, and table metadata over plugin-specific boilerplate.
- Keep transport adapters free of business and biology logic.
- Preserve deterministic paths, ordering, diagnostics, and serialized output.
- Do not edit generated Conda YAMLs without updating their source in `environments.yaml`.
- Do not embed machine-specific resource paths in reusable plugin definitions.

## 4. Add regression coverage

| Test layer | Use it for |
| --- | --- |
| `tests/unit/` | Fast, isolated behavior and regressions |
| `tests/integration/` | Cross-component contracts and adapter/core interaction |
| `tests/smoke/` | Installed tools, real runtimes, or representative workflows |
| `src/abi/sciplot/tests/` | Figure schema, rendering, export, and lint behavior |

Name files `test_<feature>.py` and tests `test_<behavior>`. Mark real-tool tests with `smoke` and/or `requires_tools`.

Every behavior fix needs a regression test that fails before the fix and passes after it. Avoid assertions that only prove a function returned without checking the user-visible result.

## 5. Run proportional quality gates

### Python or core changes

```bash
ruff check src/ tests/
ruff format --check src/ tests/
mypy src/abi/ --ignore-missing-imports
pytest tests/unit/test_affected_feature.py -q
pytest tests/ -v --tb=short
```

Run the affected integration tests after the focused unit test. The repository CI coverage floor is 75%; project policy requires total coverage to remain at least 60%.

### Plugin changes

```bash
abi contract-lint --type <analysis_type> --strict
abi plan --type <analysis_type> --config <config.yaml> --sample-sheet <samples.tsv>
abi dry-run --type <analysis_type> --config <config.yaml> --sample-sheet <samples.tsv>
pytest tests/smoke/ -m "smoke and not requires_tools" -q
```

Also run plugin contract tests, parser tests, result validation, and the relevant real-tool smoke or benchmark when tools are available.

### Docker, package, or CI changes

Treat CI workflows, Dockerfiles, `.dockerignore`, `pyproject.toml`, `environments.yaml`, and `envs/*.yml` as one release surface.

```bash
pytest tests/unit/test_docker_configuration.py -q
docker compose -f docker/docker-compose.yml config --quiet
python -m build
python -m twine check dist/*
```

Build a representative image and run `abi list-types` inside it. The default sdist-to-wheel build path must succeed because forced wheel inputs must also exist in the sdist and Docker context.

### Documentation changes

```bash
bash docs/build_docs.sh
```

Keep English and Chinese navigation, terminology, commands, and behavior descriptions aligned. Add screenshots or generated artifacts when a visual or report change needs review.

### Release changes

Before tagging, update `project.version` and add the exact version heading to `CHANGELOG.md`. Then run the full CI gate, package checks, clean-wheel smoke test, and release identity validation.

Never reuse or move a published or remotely visible version tag. See the [Release Guide](release.md) for the Trusted Publishing workflow and post-release verification.

## 6. Validate runtime and data contracts

For execution changes, verify the full chain:

1. Planned input and output paths are deterministic.
2. The tool command uses registered executables and environment mappings.
3. Actual outputs resolve to the planned contract.
4. Checksums and assertions are recorded.
5. Standard tables contain the expected schema and row identity.
6. Reports and figures use published, validated results.

For release runtime certification, use strict locks. A normal runtime lock is an audit snapshot, not a release artifact.

## 7. Keep documentation and examples executable

- Prefer commands that can be copied from the repository root.
- Mark placeholder paths clearly and do not present a dry-run fixture as a production configuration.
- Link to the owning deep reference instead of duplicating unstable implementation detail.
- Update both languages when a public workflow, command, configuration, or policy changes.
- Run the documented quick-start plan and dry-run when changing their examples.

## 8. Prepare the commit and pull request

Use concise imperative commit subjects with a scope such as `feat:`, `fix:`, or `docs:`. Keep each commit focused and reviewable.

A pull request should state:

- the user-visible problem and solution;
- affected architecture and compatibility boundaries;
- validation commands and results;
- linked issues and migration notes;
- checks that could not run and their residual risk;
- screenshots or artifacts for report, docs, or figure changes.

## 9. Definition of done

A change is complete when:

- acceptance criteria are implemented;
- regression coverage exists at the correct layer;
- focused and proportional quality gates pass;
- generated environments and build inputs remain synchronized;
- English and Chinese documentation are aligned;
- runtime, result, and compatibility risks are stated;
- the pull request records exact commands and results.

See [Components and Architecture](components_and_architecture.md), the [Development Guide](development.md), [Plugin Development Guide](plugin_development_guide.md), and [Testing Guide](testing.md) for deeper reference material.
