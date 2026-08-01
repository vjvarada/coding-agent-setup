# coding-agent-setup

**A portable, self-installing kit that sets up any complex codebase for
token-efficient, high-velocity development by coding agents.**

Point a coding agent (Claude Code, GitHub Copilot, Cursor, or any MCP-capable
host) at [`SETUP.md`](SETUP.md) and it installs and wires up the systems that
make large, unfamiliar codebases cheap and fast to work on:

- **[Graphify](https://github.com/Graphify-Labs/graphify)** — a local
  tree-sitter code knowledge graph (with an optional MCP server). One
  `graphify query` replaces the grep→read→re-read loop that burns the most
  tokens on big repos.
- **RTK (Rust Token Killer)** — filters noisy shell output (tests, lint, git,
  docker) by 60–90% before it reaches the model's context.
- **Review + verify discipline** — adversarial review and end-to-end
  verification that catch the plausible-but-wrong changes shallow checks miss.
- **Project instructions + DOX contract** — encode the repo's conventions once,
  then a hierarchy of per-directory `AGENTS.md` contracts that tells the agent
  what each directory owns and *where a new feature belongs* — so work lands in
  the right architectural layer instead of wherever a file was already open.
- **Planning + multi-agent orchestration** — a supervisor-worker loop that takes a
  goal to merged PRs: decompose → wireframe → spec → audit, then dispatch →
  build → verify → review. The plan lives in the repo as a dispatch board, the
  owner gates live in a hook that enforces them deterministically, and the loop
  stops at "PR opened" so merge and deploy stay human.

## Quickstart

**For an agent:** read [`SETUP.md`](SETUP.md) and execute it.

**For a human:**
```bash
# from your target repo's root
bash /path/to/coding-agent-setup/install.sh       # macOS / Linux / Git-Bash
pwsh /path/to/coding-agent-setup/install.ps1       # Windows PowerShell
```
The installers are idempotent and non-destructive — they merge into existing
config, never overwrite, and no-op anything already installed.

## What's here

| File | Purpose |
|---|---|
| [`SETUP.md`](SETUP.md) | **Agent-facing** step-by-step auto-install playbook |
| [`PLAYBOOK.md`](PLAYBOOK.md) | The **methodology** — why these tools, the principles behind them, hard-won lessons |
| [`ORCHESTRATION.md`](ORCHESTRATION.md) | **Multi-agent planning + dispatch** — the two loops, the seven roles, where wireframes and evals fit, what stays human, and what it costs |
| [`HARNESS-PRACTICES.md`](HARNESS-PRACTICES.md) | Harder harness practices (tool risk annotations, fail-closed permissions, trajectory evals, prompt-cache discipline, CI gates) for keeping a codebase agent-developable over time |
| [`install.sh`](install.sh) / [`install.ps1`](install.ps1) | Runnable installers (Unix / Windows) |
| [`templates/`](templates/) | Ready-to-copy config for Claude Code + VS Code Copilot |
| [`CONTRIBUTING.md`](CONTRIBUTING.md) | How we push new learnings back into this kit |

## Host support

Works across Claude Code, VS Code GitHub Copilot (Chat + CLI), Cursor, and other
MCP hosts. Each capability degrades gracefully where a host lacks it — see the
support matrix in [`SETUP.md §8`](SETUP.md). Two platform gaps worth knowing:
VS Code Copilot **Chat** cannot transparently rewrite shell commands from a hook,
so RTK there works via an instruction nudge instead of a silent rewrite; and
hosts without subagents run the orchestration loop as sequential roles in fresh
sessions rather than as parallel agents.

## Origin

Distilled from real work on a large multi-agent platform running two agent
runtimes side by side — the kind of codebase where naive exploration is
ruinously expensive. Every principle in `PLAYBOOK.md` was learned by hitting the
problem it solves. This kit is a living document: as we learn things that make
development faster, better, or cheaper, they land here.

## License

MIT — see [`LICENSE`](LICENSE).
