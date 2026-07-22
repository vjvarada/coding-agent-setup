# SETUP — agent-facing auto-install playbook

> **You are a coding agent. Read this file top-to-bottom and execute it.**
> It sets up a complex codebase for token-efficient, high-velocity development.
> Everything here has been validated on a real large multi-agent platform
> (see the archetype and lessons in `PLAYBOOK.md`). When a step says
> "verify," actually run the verification and report the number — do not assume.

---

## 0. What you are installing and why

Four capabilities, in priority order. Each is independent; install what the host
supports and skip the rest without failing.

| # | Capability | What it buys you | Works in |
|---|---|---|---|
| 1 | **Graphify** (code knowledge graph) | Local tree-sitter symbol/call graph queried by plain-language questions, path tracing, and per-symbol explain. Replaces the grep→read→re-read loop that burns the most tokens on large repos. | Claude Code, Copilot (Chat + CLI), Cursor, Codex, Gemini CLI, 15+ hosts; optional MCP server |
| 2 | **RTK** (Rust Token Killer) | 60–90% fewer tokens on noisy shell output (tests, lint, git, docker). | Claude Code (transparent hook), Copilot (agent prefixes `rtk`) |
| 3 | **Review + verify skills** | Adversarial code review + end-to-end verification before commit. Catches the expensive class of bug: plausible-but-wrong. | Any agent (methodology + optional slash commands) |
| 4 | **Project instructions + DOX contract** | A root `AGENTS.md`/`CLAUDE.md` that encodes conventions once, plus a hierarchy of per-directory `AGENTS.md` contracts with a *place-before-building* rule — so the agent stops rediscovering the repo AND puts new features in the right architectural layer instead of wherever a file was open. | Any host (plain markdown) |

The single biggest token win on a large codebase is **#1 (Graphify)** — a
grep/read exploration is dozens of tool calls; a `graphify query` is one. #2 is
the cheap, immediate win. Do both first.

---

## 1. Fast path — run the installer

If you have shell access, run the installer for the platform and stop reading
until it finishes; it does steps 2–5 for you and prints what it skipped.

```bash
# macOS / Linux / Git-Bash on Windows
bash coding-agent-setup/install.sh

# Windows PowerShell
pwsh coding-agent-setup/install.ps1
```

The installer is **idempotent** and **non-destructive**: it merges into existing
config files (never overwrites), and no-ops any tool that is already present.
After it runs, jump to **§6 Verify**.

If you do **not** have shell access, or the installer fails, do the manual steps
below.

---

## 2. Install Graphify (capability #1)

[Graphify](https://github.com/Graphify-Labs/graphify) turns the repo into a
local knowledge graph: tree-sitter AST parsing (deterministic, no LLM, nothing
leaves the machine for code) resolves `calls` / `imports` / `inherits` edges
across ~40 languages, with every edge tagged `EXTRACTED` (explicit in source)
or `INFERRED` (resolved, with a confidence score). You query the graph instead
of grepping: `graphify query "<question>"`, `graphify path A B`,
`graphify explain <symbol>`.

**Install the CLI** (Python ≥ 3.10 required; the package is `graphifyy` — two
y's — the command is `graphify`):

```bash
uv tool install graphifyy   # or: pipx install graphifyy
graphify --version
```

**Register it with the host** — one command per host; Graphify writes the
`/graphify` skill plus a query-first hook or instruction file as appropriate:

```bash
graphify install --project                       # Claude Code (repo-scoped)
graphify install --project --platform copilot    # GitHub Copilot CLI
graphify vscode install                          # VS Code Copilot Chat
graphify cursor install                          # Cursor
```

On Claude Code the default install adds a `PreToolUse` hook that *nudges* the
agent to run `graphify query` before raw file reads; add `--strict` to block
the first raw source read of a session and redirect it to the graph. This is
built-in enforcement of the "use the graph first" discipline (`PLAYBOOK.md`
Principle 1).

**Build the graph at the repo root:**

```bash
graphify extract . --code-only   # headless, fully offline, no API key needed
```

or run `/graphify .` inside the assistant — this also maps docs/PDFs/SQL into
the same graph using the IDE session's model (only the docs pass costs tokens;
the code pass is always free and local). Output lands in `graphify-out/`
(`graph.json` + `GRAPH_REPORT.md` + an HTML viz); upstream recommends
committing it so the whole team starts with the map.

**Keep it fresh:** `graphify hook install` rebuilds the code graph on every
git commit (AST only, no API cost) and adds a merge driver so `graph.json`
never gets conflict markers. `/graphify . --update` re-extracts only changed
files; `/graphify . --watch` auto-syncs in a background terminal.

**Scope the graph** to the source agents actually edit. `.gitignore` is
respected automatically; add a `.graphifyignore` (same syntax, including `!`
negation) for anything git tracks but agents shouldn't index — generated
files, migrations, vendored code, minified blobs. Copy
`templates/shared/.graphifyignore` to the repo root and edit it. (Real example
excludes: generated SQL schemas, `**/migrations/**`, `*.min.js` AND
`*.min.mjs`, vendored `reference/**`.)

**Optional — MCP server** for structured tool-call access (`query_graph`,
`get_node`, `get_neighbors`, `shortest_path`) instead of shelling out to the
CLI. Needs the `mcp` extra importable from `python` (e.g.
`pip install "graphifyy[mcp]"` in the project venv — an isolated
`uv tool` / `pipx` install is not importable from a plain `python`). Config
shape differs per host (this is the single most common setup mistake):

- **Claude Code** — `.mcp.json` at repo root, key `mcpServers`:
  ```json
  { "mcpServers": { "graphify": { "type": "stdio", "command": "python", "args": ["-m", "graphify.serve", "graphify-out/graph.json"] } } }
  ```
- **VS Code Copilot** — `.vscode/mcp.json`, key `servers` (NOT `mcpServers`):
  ```json
  { "servers": { "graphify": { "type": "stdio", "command": "python", "args": ["-m", "graphify.serve", "graphify-out/graph.json"] } } }
  ```

Copy templates from `coding-agent-setup/templates/` rather than hand-typing.
A team can instead share one HTTP server:
`python -m graphify.serve graphify-out/graph.json --transport http --port 8080`.

**Then USE it.** Before reading a file to understand or change code, query the
graph first — `graphify query` returns a scoped subgraph for a plain-language
question; `graphify explain` returns a symbol's source location plus every
caller/callee edge. This is where the token savings actually happen;
installing it and then grepping anyway wastes the investment (the query-first
hook exists to prevent exactly that).

---

## 3. Install RTK — Rust Token Killer (capability #2)

RTK filters verbose command **output** (test runs, lint, `git diff`, `docker`,
`ls`) before it reaches your context — typically 60–90% smaller with no loss of
the signal (failures, diffs, status). It tees full output to disk on failure so
nothing is truly lost.

**Install:**
```bash
# Windows
winget install rtk-ai.rtk
# macOS / Linux
brew install rtk-ai/tap/rtk   # or: cargo install --git https://github.com/rtk-ai/rtk
rtk --version                 # expect 0.43.0 or newer
```

**Wire it — the mechanism differs by host, and this matters:**

- **Claude Code (transparent):** a `PreToolUse` Bash hook rewrites covered
  commands to their `rtk` form automatically. Use the **scoped** wrapper in
  `templates/claude/hooks/rtk-bash.sh` + the `.claude/settings.json` block —
  NOT the stock `rtk init`, which mis-handles `uv run` (produces the broken
  `uv run rtk ...`) and hijacks file reads (`cat`→`rtk read`, worse than
  Graphify/Read). The wrapper is a strict allowlist that skips both.

  > ⚠️ The hook returns `permissionDecision:"allow"` so the rewrite takes effect,
  > which auto-approves the rewritten command. The allowlist (git/pytest/ruff/
  > mypy/docker/psql only) IS the security boundary. Surface this to the user;
  > it is a deliberate, scoped tradeoff.

- **VS Code Copilot Chat (instruction nudge):** Copilot Chat **cannot** rewrite
  a command from a hook (`updatedInput` is ignored — confirmed platform bug). So
  instead, the project instructions tell the agent to type `rtk` itself:
  `rtk pytest`, `rtk git diff`. Copy the RTK block from
  `templates/copilot/copilot-instructions.md`. (Copilot **CLI** — not Chat —
  *does* support the real hook via `rtk init --global --copilot`.)

**Never** `rtk` a `uv run` command (rtk is a standalone binary, not a uv tool),
and prefer Graphify queries/native Read over `rtk read` for files.

---

## 4. Set up review + verify discipline (capability #3)

The most expensive bugs on a big codebase are plausible-but-wrong changes that
pass a shallow check. Two habits prevent them:

1. **Adversarial review before commit** — review the diff for correctness bugs
   AND for reuse/simplification/efficiency. On non-trivial changes, have a
   second pass *try to refute* each finding rather than confirm it; keep only
   what survives. If the host has a `/code-review` skill, use it; otherwise do
   it inline with that adversarial framing.
2. **Verify end-to-end, not just tests** — drive the actual affected flow and
   observe behavior. A green test suite is necessary, not sufficient. If the host
   has a `/verify` skill, use it.

These are methodology, not installs — they work in any agent. See
`PLAYBOOK.md §Review` for the full loop.

---

## 5. Project instructions + DOX architecture contract (capability #4)

### 5.1 Write project instructions

Encode the repo's non-obvious conventions once so every session starts informed:

- **Claude Code:** `CLAUDE.md` at repo root.
- **VS Code Copilot:** `.github/copilot-instructions.md` (+ glob-scoped
  `.github/instructions/*.instructions.md` with `applyTo` frontmatter).

Both should state: the stack + package manager, the build/test command, where
the architecture docs live, "run `graphify query` before reading files," and
the RTK rule. Start from `templates/*/` and fill in the repo specifics.
(`graphify install --project` writes much of this automatically — the
query-first hook for Claude Code, `.cursor/rules/` for Cursor, `AGENTS.md`
for Codex/OpenCode.)

### 5.2 Install the DOX architecture contract

**DOX** is a hierarchy of `AGENTS.md` files: a small root contract, read every
session, that points to per-directory contracts read on demand as the agent
descends into a subsystem. The always-loaded top stays tiny (cache-friendly); the
depth is pulled only where the agent is actually working. This is
`PLAYBOOK.md` Principle 3 made concrete and Principle 7 (*place before building*)
made enforceable.

The installer seeds it for you: if the repo has **no** root `AGENTS.md`, it copies
`templates/shared/AGENTS.md` (non-destructive — it never touches an existing one).
To do it by hand, copy that template to `AGENTS.md`, fill in the `<...>`
placeholders (purpose, stack, global constraints, and the **Child DOX Index**),
and delete the guidance quote block. For each top-level subsystem, copy
`templates/shared/AGENTS.child.md` to `<subsystem>/AGENTS.md` and add a row to the
root's Child DOX Index.

The template ships two disciplines the agent must follow — do not strip them:

- **Read Before Editing** — walk the root → target `AGENTS.md` chain and obey the
  nearest contract before touching a file. Don't rely on memory; re-read in-session.
- **Place Before Building** — before creating any new feature/module/tool/endpoint,
  find its architectural home in the Child DOX Index and reuse the owning seam.
  A feature in the wrong layer is a defect even if it works.

If your host only auto-loads `CLAUDE.md`/`copilot-instructions.md` (not
`AGENTS.md`), add a one-line pointer there — "read `AGENTS.md` first, and follow
its Read-Before-Editing and Place-Before-Building rules" — so the chain is entered
every session.

---

## 6. Verify (do this — report real numbers)

```bash
# Graphify answers a real question about THIS repo in one call:
graphify query "where is the main entry point"   # expect a scoped subgraph with source locations
graphify explain "<a real symbol in this repo>"  # expect source line + caller/callee edges

# RTK actually reduces tokens (run on a real diff in this repo):
rtk gain                                          # after a few rtk commands, shows % saved
```

Report back: the node/edge counts from the graph build (printed by
`graphify extract` / `/graphify .`, or visible in `graphify-out/GRAPH_REPORT.md`),
and the RTK reduction % on a real command. If either is zero or errors, debug it
before declaring setup complete — a tool installed but unused delivers nothing.

---

## 7. Host support matrix (what to skip where)

| Capability | Claude Code | VS Code Copilot Chat | Copilot CLI | Cursor / other MCP host |
|---|---|---|---|---|
| Graphify skill + query-first hook | ✅ `graphify install --project` | ✅ `graphify vscode install` | ✅ `--platform copilot` | ✅ `graphify cursor install` / 15+ hosts |
| Graphify MCP (optional) | ✅ `.mcp.json` | ✅ `.vscode/mcp.json` | ✅ | ✅ (host's MCP config) |
| RTK transparent hook | ✅ | ❌ (use nudge) | ✅ | depends on hook support |
| RTK instruction nudge | ✅ (fallback) | ✅ | ✅ | ✅ |
| Review / verify | ✅ skills | ✅ methodology | ✅ | ✅ methodology |
| Project instructions | ✅ CLAUDE.md | ✅ copilot-instructions.md | ✅ | host-specific |
| DOX architecture contract | ✅ AGENTS.md | ✅ AGENTS.md | ✅ | ✅ (plain markdown) |

If a capability is unsupported, skip it and note it in your setup summary. Do not
fail the whole setup because one host lacks one feature.
