# Development Guide

This repository publishes one Python distribution: `abi-agent`.

The source tree has two layers:

- `src/abi`: public ABI SDK, CLI, plugin registry, transports, runtimes, and built-in plugins.
- `src/abi/autoplasm`: bundled metagenomic plasmid pipeline used by the
  `metagenomic_plasmid` plugin and the `autoplasm` compatibility CLI.

Do not add a top-level Python package named `autoplasm`. Code should import the
bundled pipeline as `abi.autoplasm`.

## Local Setup

```bash
pip install -e ".[dev]"
```

Useful checks:

```bash
ruff check src/ tests/
ruff format --check src/ tests/
mypy src/abi/ --ignore-missing-imports
pytest tests/ -v --tb=short
```

`mypy` is intentionally scoped to `src/abi/`; the bundled pipeline is covered by
runtime tests and ruff first, with stricter typing left for later hardening.

## Runtime Assets

Small source assets are tracked:

- `config/`
- `envs/`
- `skills/`
- `plugins/`
- `examples/`
- `data/examples/`
- `scripts/`

Large or generated runtime state is ignored:

- `.mamba/`
- `resources/`
- `results/`
- `log/`
- Nextflow work directories

Tool execution resolves environments from `.mamba/envs/<env_name>/bin` by
default. Override with `ABI_MAMBA_ROOT`; `AUTOPLASM_MAMBA_ROOT` is still
accepted for compatibility.

## Agent Interfaces

`ABIAgentInterface` is the transport-neutral boundary. Keep CLI JSON, MCP,
OpenAI descriptors, and Job Service behavior aligned with it.

Execution must remain gated: `abi run`, `abi_run`, and Job Service execution
submissions should return `confirmation_required` unless explicit confirmation
is passed.
