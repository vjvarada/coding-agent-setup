## Terminal output — prefix noisy commands with `rtk`

`rtk` (Rust Token Killer) filters verbose command output before it reaches the
model, cutting ~60–90% of the tokens on common dev commands with no loss of the
signal (failures, diffs, status). In Claude Code a hook applies this
automatically; **in Copilot Chat you must write `rtk` yourself** because the
Chat host does not rewrite terminal commands.

When running any of these in the terminal, prefix the command with `rtk`:

- Tests: `rtk pytest ...`, `rtk jest ...`, `rtk vitest ...`, `rtk go test ...`
- Lint/type: `rtk ruff ...`, `rtk mypy ...`, `rtk tsc ...`, `rtk eslint ...`
- VCS: `rtk git status`, `rtk git diff`, `rtk git log`
- Infra: `rtk docker ...`, `rtk kubectl ...`, `rtk psql ...`

Do **not** use `rtk` for:

- `uv run ...` — `rtk` is a standalone binary, not a uv tool; run tests as bare
  `rtk pytest ...` (or `rtk pip ...`, which auto-detects uv), never `uv run rtk`.
- Reading files — prefer the CodeGraph MCP and the editor's file tools over
  `rtk read`; they give better, symbol-aware context.

If `rtk` is not installed (`rtk --version` fails), run commands normally.

## Code intelligence — use the CodeGraph MCP

A `codegraph` MCP server is configured in `.vscode/mcp.json`. It is a pre-indexed
knowledge graph of every symbol, edge, and file. Prefer one `codegraph` query
over a grep + read loop when locating code, understanding call paths, or checking
a change's blast radius — it returns the verbatim source plus who calls it, in
far fewer round-trips.
