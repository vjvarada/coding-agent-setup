# DOX framework

> Portable AGENTS.md hierarchy ("DOX"), shipped by coding-agent-setup (see its
> `SETUP.md §5`). It makes a codebase legible to coding agents: a small,
> always-loaded root contract that points to per-directory contracts read on
> demand. **Fill in the `<...>` placeholders below for this repo, then delete
> this quote block.** Keep the framework sections (Core Contract → Communication) intact.

- DOX is a hierarchy of AGENTS.md files that act as binding work contracts.
- Agents must follow DOX instructions across any edit in the covered subtree.

## Core Contract

- AGENTS.md files are binding contracts for their subtree.
- Work products, source, instructions, records, assets, and durable docs must stay
  understandable from the nearest applicable AGENTS.md plus every parent AGENTS.md
  above it.

## Read Before Editing

1. Read this root AGENTS.md.
2. Identify every file or folder you expect to touch.
3. Walk from the repository root to each target path.
4. Read every AGENTS.md found along each route.
5. If a parent AGENTS.md lists a child whose scope contains the path, read that child and continue.
6. Use the nearest AGENTS.md as the local contract and parent docs for repo-wide rules.
7. If docs conflict, the closer doc controls local details, but no child may weaken DOX.

Do not rely on memory. Re-read the applicable DOX chain in the current session before editing.

## Place Before Building

Every new feature, module, tool, endpoint, or asset must land in its
architecturally-correct home **before** any code is written. Convenience of the
file you happen to have open is never a reason to place work elsewhere. Before
building:

1. Name the kind of thing you're adding, and which architectural layer owns that
   kind. The directory split is load-bearing, not cosmetic — respect it.
2. Walk the Child DOX Index (below) and the nested indexes to find the scope that
   owns that kind. The nearest owning AGENTS.md is the target directory.
3. Verify the placement against this repo's Global Constraints and the local
   AGENTS.md contract before writing code.
4. Reuse the existing seam before adding a new one — extend the owning module,
   service, or package rather than duplicating its capability in a closer folder.
   If no scope fits, the right move is a new scope with its own AGENTS.md, not an
   orphan file wedged into an unrelated tree.
5. If placement is genuinely ambiguous, state the candidate homes and the
   trade-off before writing code — do not default to the current directory.

A feature in the wrong layer is a defect even if it works. Correct the placement
first, then build.

## Update After Editing

Every meaningful change requires a DOX pass before the task is done.
Update the closest owning AGENTS.md when a change affects:
- purpose, scope, ownership, or responsibilities
- durable structure, contracts, workflows, or operating rules
- required inputs, outputs, permissions, constraints, side effects, or artifacts
- user preferences about behavior, communication, process, organization, or quality
- AGENTS.md creation, deletion, move, rename, or index contents

Update parent docs when parent-level structure, ownership, workflow, or child index changes.
Update child docs when parent changes alter local rules.
Remove stale or contradictory text immediately.

## Style

- Keep docs concise, current, and operational.
- Document stable contracts, not diary entries.
- Put broad rules in parent docs and concrete details in child docs.
- Prefer direct bullets with explicit names.
- Do not duplicate rules across many files unless each scope needs a local version.
- Delete stale notes instead of explaining history.

## Communication (BLUF)

Every response to a human — answers, status reports, review findings, PR
descriptions, handover notes — leads with the bottom line up front:

1. **Answer first.** The first sentence states the conclusion, recommendation,
   result, or blocker — what the reader would ask for as the TLDR. Background,
   reasoning, and evidence follow, never precede.
2. **Cut padding.** No pleasantries, no restating the question, no "I'll now…"
   preamble. Use precise technical terms, but no jargon that a skim can't carry.
3. **Structure for skimming.** After the up-front answer, short paragraphs and
   bolded key facts; lists only for genuinely enumerable items. A reader who
   stops after the first paragraph still leaves with the correct takeaway.
4. **Outcomes before narrative.** "Deployed and verified" / "Blocked: X" comes
   before the story of how.

This also applies to durable prose (specs, plan rows, AGENTS.md updates):
answer-first text skims faster for humans and retrieves better for models,
which weight early context most.

---

# <Project Name> — Project Root

<One paragraph: what this codebase is and what it does.>

## Stack & Conventions

- Language / runtime: <e.g. Python 3.12 + uv, or Node 20 + pnpm>
- Framework(s): <e.g. FastAPI, Next.js>
- Build / test: <the one-line test command, e.g. `uv run pytest -q`>
- Data stores / infra: <e.g. Postgres + Redis>
- Code intelligence: query the Graphify knowledge graph (`graphify query` /
  `path` / `explain`) before reading files; run noisy commands through `rtk`
  (see the project instructions this kit installs).
- <Any repo-wide convention an agent cannot cheaply derive.>

## Global Constraints (Non-Negotiable)

1. <e.g. no secrets in source — config comes from the secret store>
2. <e.g. new execution paths default to the sanctioned runtime, not the ad-hoc one>
3. <add the rules that must never be violated anywhere in the tree>

## Child DOX Index

Every top-level subsystem that owns a distinct kind of work should have its own
AGENTS.md and a row here. This table is the routing map for **Place Before
Building** — an unlisted directory is a placement smell.

| Scope | Path | Covers |
|---|---|---|
| <e.g. Services>  | <apps/AGENTS.md>     | <deployed processes> |
| <e.g. Packages>  | <packages/AGENTS.md> | <shared libraries> |
| <add one row per top-level subsystem> | | |
