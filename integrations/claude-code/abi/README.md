# ABI for Claude Code

Install ABI with MCP support first:

```bash
pip install "abi-agent[mcp]"
```

Validate and load this plugin during development:

```bash
claude plugin validate integrations/claude-code/abi --strict
claude --plugin-dir integrations/claude-code/abi
```

The plugin starts `abi-mcp --profile safe`. Use the `full` profile only when
real workflow execution is required; ABI still requires explicit confirmation.
