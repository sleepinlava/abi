# ABI for OpenCode

Install ABI with MCP support first:

```bash
pip install "abi-agent[mcp]"
```

Install and verify the integration with:

```bash
abi agent install opencode --scope project
abi agent doctor opencode --scope project
```

Use `--scope user` for `~/.config/opencode`. The installer preserves unrelated
JSON settings; `opencode.example.json` remains available for manual setup.

The example starts `abi-mcp --profile safe`. Use the `full` profile only
when real workflow execution is required; ABI still requires explicit confirmation.
