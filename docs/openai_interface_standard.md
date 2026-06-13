# OpenAI-Compatible Interface Standard

ABI exports provider-neutral descriptors for agent platforms with:

```bash
abi export-openai-tools --type metagenomic_plasmid --format responses
abi export-openai-tools --type metagenomic_plasmid --format apps-sdk
abi export-openai-tools --type metagenomic_plasmid --format json
```

## Default Tools

Default exports include:

- `abi_list_types`
- `abi_plan`
- `abi_dry_run`
- `abi_inspect`
- `abi_report`
- `abi_export_nextflow`
- `abi_export_agent_context`
- `abi_doctor_agent`
- `abi_validate_result`

`abi_run` is omitted unless `--include-execution` is passed.

## Schema Rules

- Descriptor input schemas use `additionalProperties: false`.
- Responses descriptors set `strict: true`.
- Apps SDK descriptors include `readOnlyHint` where appropriate.
- JSON descriptors include `permission` and `requires_confirmation`.

## Agent Context

Agents can fetch compact operating context:

```bash
abi export-agent-context --type metagenomic_plasmid --format json
abi doctor-agent --type metagenomic_plasmid
```

The context lists safe call order, standard tables, important artifacts, error
codes, and recovery rules.
