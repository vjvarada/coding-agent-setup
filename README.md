# coding-agent-setup

**A self-installing kit that scaffolds any new software project or custom agent as an
agent-ready workspace — or retrofits an existing codebase — so coding agents can build
it fast, cheaply and safely.**

> **Agent, start here.** The user gave you this repo's link:
> - **Empty or new folder** (a new project, or "create an agent that …") → read
>   [`SCAFFOLD.md`](SCAFFOLD.md) and execute it.
> - **Existing codebase** → read [`SETUP.md`](SETUP.md) and execute it.
>
> Clone this kit to a temporary folder *outside* the project; never commit it into
> the project.

## What you get

A scaffolded workspace is built on **DOE** — *directives* (SOPs as `SKILL.md`) say
what, the *orchestrating* LLM judges and routes, *execution* scripts do the work — and
on the engineering disciplines in [`PLAYBOOK.md`](PLAYBOOK.md):

- **The project's own skeleton**, from its stack's official generator (Next.js, Vite,
  uv, Cargo, Go, .NET, Flutter, Expo, Tauri, PlatformIO, …) — or the DOE agent layout
  for an agent.
- **A DOX architecture contract** — a root `AGENTS.md` every agent host reads, with
  constraints, owner gates, a skills table and a child index, plus one `AGENTS.md` per
  scope, so new work lands in the right layer (*place before building*).
- **A skill harness** — canonical skills in `.github/skills/` (directive + scripts +
  tests), generated proxies for Claude Code, and three core skills in every project:
  `self-annealing` (lessons → skills, with a session-end gate), `skill-authoring`
  (add capability the DOE way), `run-and-verify` (run *this* project and prove a
  change works).
- **A custom-agent archetype** — persona, runtime system prompt, Copilot agent,
  `inputs/` → `outputs/<run>/` run records, "never fabricate" and dry-run-before-
  external rules; optional CommandCenter runtime (`agents.py` + `config.json`).
- **Session continuity** — `HANDOFF.md` with a Check per entry, injected at session
  start; a stale-rules and worktree notice; a leftover-process report at stop.
- **Guardrails and CI** — owner gates enforced by a hook (`plan-guard`), harness CI
  (contracts, skills, proxies, ignore traps, hook tests), a secret scan of new
  commits, a PR template that requires verification evidence, a review-cadence
  reminder.
- **The token and delivery tools** — Graphify (code knowledge graph), RTK (output
  compression), the planning/dispatch loop (plan → spec → audit → build → verify →
  review → PR), and Delivery (one-command local stack, premerge, worktrees).
- **A way to stay current** — `scaffold.py upgrade` brings kit improvements into a
  project without touching the files it has edited.

## Quickstart

**For an agent:** follow [`SCAFFOLD.md`](SCAFFOLD.md) (new) or [`SETUP.md`](SETUP.md) (existing).

**For a human:**

```bash
git clone --depth 1 https://github.com/vjvarada/coding-agent-setup /tmp/coding-agent-setup
python /tmp/coding-agent-setup/scaffold/scaffold.py list                      # archetypes and stacks
python /tmp/coding-agent-setup/scaffold/scaffold.py intake-template --archetype agent --out intake.json
#   … fill in intake.json …
python /tmp/coding-agent-setup/scaffold/scaffold.py new --intake intake.json --target my-project
python /tmp/coding-agent-setup/scaffold/scaffold.py install --target my-project   # Graphify, RTK, loop, delivery
python my-project/.harness/harness.py check --strict
```

The intake interview is the part an agent does best — the fastest path is to open a
coding agent in an empty folder and say: *"Use https://github.com/vjvarada/coding-agent-setup
to scaffold this project: <one sentence>."*

Retrofit an existing repo instead: `bash install.sh` / `pwsh install.ps1` from its root.

## What's here

| Path | Purpose |
|---|---|
| [`SCAFFOLD.md`](SCAFFOLD.md) | **Agent-facing**: scaffold a new project or custom agent from an empty folder |
| [`SETUP.md`](SETUP.md) | **Agent-facing**: retrofit an existing codebase |
| [`DOE.md`](DOE.md) | The **DOE method** — skills, one harness for many hosts, self-annealing, memory, the agent archetype, provenance |
| [`PLAYBOOK.md`](PLAYBOOK.md) | The **principles** — why these tools and disciplines, with the cases that taught them |
| [`ORCHESTRATION.md`](ORCHESTRATION.md) | Multi-agent planning and dispatch: the two loops, the seven roles, what stays human |
| [`DELIVERY.md`](DELIVERY.md) | From "slice built" to "in production": local stack, premerge, staging, release train, task board |
| [`HARNESS-PRACTICES.md`](HARNESS-PRACTICES.md) | Harder practices: risk annotations, fail-closed permissions, trajectory evals, cache discipline |
| [`scaffold/`](scaffold/) | `scaffold.py` (new · install · upgrade), the archetype and stack catalogs, example intakes, kit tests |
| [`templates/`](templates/) | Everything the scaffolder and installers lay down: `project/` (base harness), `skills/` (core skills), `agent/` + `agent-commandcenter/` (DOE agent), `claude/` + `copilot/` (host config, hooks, subagents), `shared/` (DOX, plan, spec, handoff), `scripts/` (delivery) |
| [`install.sh`](install.sh) / [`install.ps1`](install.ps1) | Capability installers (Unix / Windows), idempotent and non-destructive |
| [`CONTRIBUTING.md`](CONTRIBUTING.md) | How learnings land in this kit |

## Host support

Works across Claude Code, VS Code GitHub Copilot (Chat + CLI), Cursor, Codex and other
AGENTS.md-aware hosts. Each capability degrades gracefully where a host lacks it — see
[`SETUP.md §8`](SETUP.md). Hooks, subagents and slash commands need Claude Code; on
other hosts the same skills and contracts apply, and the loop runs as sequential roles.

## Origin

Distilled from three sources of hard-won practice: the DOE Framework for Agentic AI
(agent workspaces that self-anneal), a large multi-agent production platform with two
agent runtimes (where naive exploration is ruinously expensive), and this kit's own
use. Every principle in `PLAYBOOK.md` was learned by hitting the problem it solves.
This kit is a living document: when we learn something that makes development faster,
better or cheaper, it lands here — and `scaffold.py upgrade` carries it into existing
projects.

## License

MIT — see [`LICENSE`](LICENSE).
