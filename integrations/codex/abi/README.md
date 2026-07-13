# ABI for Codex

This Codex plugin bundles the platform-neutral ABI skill and a local `abi-mcp`
server using the default `safe` tool profile.

Install ABI first:

```bash
pip install -e ".[mcp]"
```

For a direct user installation, run:

```bash
abi agent install codex --scope user
abi agent doctor codex --scope user
```

The direct installer writes the skill to `~/.agents/skills/abi` and safely adds
the ABI server to `~/.codex/config.toml`. The plugin directory can also be
published through a Codex marketplace when team-wide plugin distribution is
preferred.
