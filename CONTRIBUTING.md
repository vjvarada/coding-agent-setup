# Contributing — how learnings land in this kit

This is a **living kit**. The rule is simple:

> Whenever we learn something that makes development faster, better, stronger,
> more effective, or cheaper on tokens — we push it here.

That includes: a new tool worth adopting, a sharper way to use an existing one, a
setup gotcha and its fix, a host-compatibility fact, or a methodology principle
proven on a real change.

## What belongs here

- **Tools** that reduce rediscovery cost (symbol graphs, output compressors,
  indexers) or catch expensive bugs (review/verify harnesses).
- **Configuration** that makes a tool work correctly on a real codebase —
  especially the non-obvious parts (scoping an index, the `uv run` gotcha, the
  auto-approve tradeoff, per-host mechanism differences).
- **Principles** — a lesson general enough to apply beyond the repo it came from.
  Add it to `PLAYBOOK.md` with the concrete case that taught it.

## What does NOT belong here

- Anything specific to one product's business logic. Keep this kit about the
  *act of developing*, not any one codebase's features.
- Unmeasured optimizations. Before adding machinery to "save tokens," measure the
  sink first (see `PLAYBOOK.md` Principle 6). Land the number alongside the change.
- Secrets, tokens, or machine-specific paths. Templates use placeholders.

## How to contribute

1. **Prove it on a real change.** A learning earns its place by being applied,
   not proposed. Include the before/after (token count, tool-call count, or the
   bug it caught).
2. **Update the right file:**
   - New/changed tool or setup step → `SETUP.md` (and `install.sh` +
     `install.ps1` if it should auto-install, and `templates/` if it ships config).
   - A general lesson → `PLAYBOOK.md`, as a principle + the case that taught it.
   - Something about planning, agent roles, or the dispatch loop →
     `ORCHESTRATION.md` (and the affected agent prompt in
     `templates/claude/agents/`). Changing a role's prompt is changing an
     interface: state what its report must still contain, because the supervisor
     and the downstream agents parse it.
   - A new owner gate → `templates/claude/plan-guard.config.json` **and** a case
     in `plan-guard.test.mjs`. An untested gate is a guess; ship both or neither.
3. **Keep the installers idempotent and non-destructive.** They must merge into
   existing config, never overwrite, and no-op what's already present. Test a
   re-run: running twice must be a clean no-op.
4. **Keep host-agnostic.** State per-host differences explicitly (Claude Code vs
   Copilot Chat vs Copilot CLI vs other MCP hosts) rather than assuming one.
5. **Open a PR** with the evidence from step 1 in the description.

## Provenance

Each substantive learning should carry a one-line note of where it came from — a
real bug, a measured win, a platform quirk. `PLAYBOOK.md`'s "*lesson:*" callouts
are the model. Provenance is what lets the next reader trust the advice.
