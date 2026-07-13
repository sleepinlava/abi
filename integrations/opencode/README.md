# ABI for OpenCode

Install ABI with MCP support first:

```bash
pip install "abi-agent[mcp]"
```

Copy `opencode.example.json` to the appropriate OpenCode configuration and
install `skills/abi/SKILL.md` under `.opencode/skills/abi/SKILL.md` for a
project or `~/.config/opencode/skills/abi/SKILL.md` for the current user.

The example starts `abi-mcp --profile safe`. Use the `full` profile only
when real workflow execution is required; ABI still requires explicit confirmation.
