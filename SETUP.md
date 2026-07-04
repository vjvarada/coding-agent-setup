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
| 1 | **CodeGraph** (MCP) | Sub-ms symbol lookup + call paths + blast radius. Replaces the grep→read→re-read loop that burns the most tokens on large repos. | Claude Code, VS Code Copilot, any MCP host |
| 2 | **RTK** (Rust Token Killer) | 60–90% fewer tokens on noisy shell output (tests, lint, git, docker). | Claude Code (transparent hook), Copilot (agent prefixes `rtk`) |
| 3 | **Review + verify skills** | Adversarial code review + end-to-end verification before commit. Catches the expensive class of bug: plausible-but-wrong. | Any agent (methodology + optional slash commands) |
| 4 | **Project instructions** | A `CLAUDE.md` / `copilot-instructions.md` that encodes the repo's conventions so the agent stops rediscovering them each session. | Both |

The single biggest token win on a large codebase is **#1 (CodeGraph)** — a
grep/read exploration is dozens of tool calls; a CodeGraph query is one. #2 is
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

## 2. Install CodeGraph (capability #1)

CodeGraph is a local knowledge graph of every symbol/edge/file, exposed as an
MCP server. Reads are sub-millisecond and it follows dynamic-dispatch edges
(callbacks, JSX children, re-renders) that grep cannot.

**Install the CLI** (Node ≥ 18 required):

```bash
npm install -g @colbymchenry/codegraph
codegraph --version   # expect 1.2.0 or newer
```

**Build the index at the repo root:**

```bash
codegraph init .      # initializes .codegraph/ and builds the initial index
codegraph status .    # verify: prints symbol/file counts
```

**Register it as an MCP server** so the agent host can query it. Config shape
differs per host (this is the single most common setup mistake):

- **Claude Code** — `.mcp.json` at repo root, key `mcpServers`:
  ```json
  { "mcpServers": { "codegraph": { "type": "stdio", "command": "codegraph", "args": ["serve", "--mcp"] } } }
  ```
- **VS Code Copilot** — `.vscode/mcp.json`, key `servers` (NOT `mcpServers`):
  ```json
  { "servers": { "codegraph": { "type": "stdio", "command": "codegraph", "args": ["serve", "--mcp"] } } }
  ```

Copy templates from `coding-agent-setup/templates/` rather than hand-typing.

**Scope the index** to the source agents actually edit — drop generated files,
migrations, vendored code, and huge minified blobs, or they pollute symbol
search. Copy `templates/shared/codegraph.json` to the repo root and edit the
`exclude` list for this repo. (Real example excludes: generated SQL schemas,
`**/migrations/**`, `**/*.min.js` AND `**/*.min.mjs`, vendored `reference/**`.)

**Then USE it.** Before reading a file to understand or change code, query
CodeGraph first — one call returns the verbatim source plus callers plus blast
radius. This is where the token savings actually happen; installing it and then
grepping anyway wastes the investment.

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
  CodeGraph/Read). The wrapper is a strict allowlist that skips both.

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
and prefer CodeGraph/native Read over `rtk read` for files.

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

## 5. Write project instructions (capability #4)

Encode the repo's non-obvious conventions once so every session starts informed:

- **Claude Code:** `CLAUDE.md` at repo root.
- **VS Code Copilot:** `.github/copilot-instructions.md` (+ glob-scoped
  `.github/instructions/*.instructions.md` with `applyTo` frontmatter).

Both should state: the stack + package manager, the build/test command, where
the architecture docs live, "query CodeGraph before reading files," and the RTK
rule. Start from `templates/*/` and fill in the repo specifics.

---

## 6. Verify (do this — report real numbers)

```bash
# CodeGraph answers a real question about THIS repo in one call:
codegraph explore "where is the main entry point"     # expect source + call paths

# RTK actually reduces tokens (run on a real diff in this repo):
rtk gain                                               # after a few rtk commands, shows % saved
```

Report back: CodeGraph index symbol count, and the RTK reduction % on a real
command. If either is zero or errors, debug it before declaring setup complete —
a tool installed but unused delivers nothing.

---

## 7. Host support matrix (what to skip where)

| Capability | Claude Code | VS Code Copilot Chat | Copilot CLI | Cursor / other MCP host |
|---|---|---|---|---|
| CodeGraph MCP | ✅ `.mcp.json` | ✅ `.vscode/mcp.json` | ✅ | ✅ (host's MCP config) |
| RTK transparent hook | ✅ | ❌ (use nudge) | ✅ | depends on hook support |
| RTK instruction nudge | ✅ (fallback) | ✅ | ✅ | ✅ |
| Review / verify | ✅ skills | ✅ methodology | ✅ | ✅ methodology |
| Project instructions | ✅ CLAUDE.md | ✅ copilot-instructions.md | ✅ | host-specific |

If a capability is unsupported, skip it and note it in your setup summary. Do not
fail the whole setup because one host lacks one feature.
