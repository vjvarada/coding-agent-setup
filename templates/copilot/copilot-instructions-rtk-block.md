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
- Reading files — prefer Graphify queries and the editor's file tools over
  `rtk read`; they give better, symbol-aware context.

If `rtk` is not installed (`rtk --version` fails), run commands normally.

## Code intelligence — query the Graphify graph

This repo has a Graphify knowledge graph (`graphify-out/graph.json`): every
symbol, call/import/inherit edge, and file, pre-indexed with tree-sitter.
Prefer one graph query over a grep + read loop when locating code,
understanding call paths, or checking a change's blast radius:

- `graphify query "<plain-language question>"` — scoped subgraph with source locations
- `graphify path <A> <B>` — how two symbols/concepts connect
- `graphify explain <symbol>` — source line plus every caller/callee edge

If a `graphify` MCP server is configured in `.vscode/mcp.json`, use its tools
(`query_graph`, `get_node`, `get_neighbors`, `shortest_path`) instead of the
terminal. If the graph is stale or missing, rebuild with
`graphify extract . --code-only`.
