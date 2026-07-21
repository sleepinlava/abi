# Components and Architecture

This page explains what ABI is made of, how a request moves through the system, and which boundary owns each kind of behavior.

## Architecture at a glance

```text
Researcher or AI agent
        |
        v
CLI / JSON / MCP / HTTP / provider tool descriptors
        |
        v
ABIAgentInterface
        |
        v
Core lifecycle: query -> plan -> check -> dry-run -> run -> inspect -> report
        |
        v
Analysis plugin + declarative DAG + tool registry
        |
        v
Local / Conda / Docker / Nextflow / HPC / cloud worker
        |
        v
Execution plan + provenance + standard tables + reports + figures
```

Every transport calls the same core interface. A CLI request and an MCP request therefore use the same planning, permissions, diagnostics, execution gate, and result contract.

## Component map

| Component | Responsibility | Main location |
| --- | --- | --- |
| Entry points and transports | Adapt human or machine requests into ABI operations | `src/abi/cli.py`, `src/abi/mcp/`, `src/abi/jobs/`, `src/abi/tool_descriptors.py` |
| Agent interface | Stable, transport-neutral API and JSON envelopes | `src/abi/agent/` |
| Workflow core | Schemas, planning, permissions, diagnostics, contracts, provenance, tables, and reports | `src/abi/` |
| Analysis plugins | Own biological choices, workflow configuration, parsing, and interpretation | `src/abi/plugins/` |
| Declarative workflow definitions | Define DAG nodes, tools, schemas, tables, and report metadata | `plugins/<analysis_type>/` |
| Tool and resource layer | Resolve executables, Conda environments, databases, indexes, and models | `src/abi/tools.py`, `src/abi/resources.py`, `environments.yaml` |
| Runtime adapters | Execute locally or translate work to Nextflow and HPC backends | `src/abi/runtimes/`, `src/abi/exporters/` |
| Result and figure layer | Validate artifacts, normalize TSV tables, build reports, and render figures | `src/abi/results.py`, `src/abi/report/`, `src/abi/sciplot/` |

## How a request is processed

1. **Discover.** `abi list-types` and `abi query` read installed plugin metadata without building or running a workflow.
2. **Resolve.** ABI combines the plugin, configuration, sample sheet, runtime options, and resource overrides.
3. **Plan.** The declarative DAG becomes an `ExecutionPlan` containing ordered steps, commands, inputs, outputs, dependencies, and contracts.
4. **Check.** ABI validates input paths, executables, resources, and runtime assumptions without executing analysis tools.
5. **Dry-run.** ABI writes the plan, provenance skeleton, standard tables, and report preview.
6. **Authorize.** Execution requires an explicit `--confirm-execution` or equivalent transport field.
7. **Execute.** The runtime invokes registered tools and enforces step output contracts.
8. **Publish results.** ABI records checksums, provenance, tables, summaries, reports, and optional SciPlot figures.

## Core design boundaries

### Thick core

Reusable mechanisms belong in the core: lifecycle operations, permission levels, schemas, diagnostics, provenance, contract enforcement, tables, and report assembly.

### Thin transports

CLI, MCP, provider descriptors, dispatch, and HTTP jobs translate requests. They should not contain workflow or biology logic.

### Clean plugins

A plugin owns analysis-specific decisions: tools, parameters, DAG branches, input rules, output parsing, biological assertions, and report interpretation.

### Agents call contracts, not source code

Agents discover typed operations and receive structured responses. They do not need to import ABI internals or generate a new shell pipeline for each run.

## Contracts and data flow

| Boundary | Input | Output |
| --- | --- | --- |
| User to ABI | Analysis type, YAML config, TSV sample sheet, runtime options | Validated request or structured diagnostic |
| Planner to executor | `ExecutionPlan` and step contracts | Ordered, authorized work |
| Tool to plugin | Files, directories, JSON, TSV, or logs | Parsed workflow-specific values |
| Plugin to ABI result | Published outputs and standard table rows | Stable result directory and report inputs |
| ABI to user or agent | Human text or JSON envelope | Plan, diagnostics, artifacts, report, or recovery hint |

The declarative DAG is the source of truth for dependencies and step output contracts. `environments.yaml` is the source of truth for tool-to-environment assignments.

## Deployment patterns

| Pattern | Best for | Entry point |
| --- | --- | --- |
| Local CLI | Exploration, development, and single-host runs | `abi` |
| Docker | Isolated plugin runtimes and repeatable deployment | `docker/Dockerfile.*` |
| Nextflow or HPC | Scheduler-backed and resumable compute | `abi export-nextflow`, `abi run --engine hpc` |
| MCP | Interactive agent platforms using stdio tools | `abi-mcp` |
| HTTP Job Service | Queued, asynchronous, or remotely managed work | `abi job-service`, `abi job ...` |
| Headless dispatch | Subprocess workers and transport adapters | `abi dispatch` |

## Where to make a change

| Change | Owning boundary |
| --- | --- |
| Add a workflow step or biological assertion | Plugin DAG and plugin tests |
| Add a reusable validation or provenance mechanism | Core module and core tests |
| Add a CLI, MCP, or HTTP representation | Transport adapter calling `ABIAgentInterface` |
| Add or move a tool environment | `environments.yaml` and generated `envs/*.yml` |
| Change standard result layout | Result core, plugin mappings, compatibility tests, and docs |
| Add a plot type | `abi.sciplot` schema, renderer, lint rules, and figure tests |

Continue with [Using ABI](usage_guide.md) for the operating lifecycle or [Development Standards](development_workflow.md) before changing the codebase.
