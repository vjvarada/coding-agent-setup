---
name: skill-authoring
description: >-
  Create or extend a skill in this workspace the DOE way: a directive (SKILL.md with
  goal, inputs, process, outputs, edge cases, definition of done) plus deterministic
  execution scripts plus tests, authored once under .github/skills/ and synced to
  every agent host. Use when a task will recur, when you catch yourself doing the
  same mechanical steps twice, when converting an SOP or a voice-dump into a
  workflow, or when porting a skill from another workspace.
when_to_use: "A workflow will recur; mechanical steps repeat; an SOP should become executable; a skill must be ported or vendored."
authority: write
cost_tier: 0
audience: developer
version: 1.0.0
---

# Skill authoring

Skills are how this workspace gets more capable over time without the model
getting any smarter: each one pushes a recurring job out of free-form reasoning
and into a directive plus deterministic code. (DOE: *if each step is 90% reliable,
five steps are 59%; reserve the LLM for judgment and let code do the mechanics.*)

## Decide what you are making

Promotion path — start at the lowest rung that works, promote on evidence:

```
one-off command or scratch script (.tmp/ or your shell)
      │  you needed it a second time
      ▼
script inside the owning skill's scripts/  (or a shared utility if 2+ skills use it)
      │  it has inputs, a process, edge cases worth writing down
      ▼
a skill: .github/skills/<name>/  = SKILL.md + scripts/ + tests/
      │  several skills chain into one outcome
      ▼
a meta-skill whose Process calls the others in order (DOE "meta-directive")
```

- **Check first.** Read the skills table in `AGENTS.md`. Extend an existing skill
  rather than adding a near-duplicate — a second implementation of an existing
  seam is a defect.
- **Not a skill:** a one-off fact (goes in the run record or a doc), a project
  rule (goes in the nearest `AGENTS.md`), a code module of the product (goes in its
  owning directory per the DOX Child Index).

## Create it

```bash
python .github/skills/skill-authoring/scripts/new_skill.py <kebab-name> \
    --description "What it does. Use when <trigger phrases a user would say>." \
    --authority read|write|external --cost-tier 0-3
```

This writes `.github/skills/<name>/{SKILL.md, scripts/main.py, tests/test_main.py}`
and runs `python .harness/harness.py sync`, which creates the Claude Code proxy in
`.claude/skills/<name>/` and refreshes every skills table. Never hand-write a proxy
and never fork a host-specific copy: one canonical skill, generated pointers.

## Write the directive (SKILL.md)

The `description` is the routing signal every host matches on: say **what** it does
and **when** to use it, with the words a user would actually type. Max 1024 chars.

The body follows the DOE directive anatomy — Goal, Inputs, Scripts, Process,
Outputs, Definition of Done, Edge Cases, Environment, Learnings. Rules:

- **Definition of Done is checkable.** "The output file exists and every row has a
  non-empty email" — not "results look good". If you cannot write it, the skill is
  not ready to be automated (PLAYBOOK Principle 8).
- **Process starts small.** Test on a small input, check, then run in full.
- **Frontmatter `authority`:** `read` (looks only) · `write` (changes the workspace)
  · `external` (sends, publishes, spends, deletes outside it). External skills
  support `--dry-run` and need the user's go-ahead for the real run.
- **Frontmatter `cost_tier`:** 0 free · 1 cheap · 2 paid API · 3 expensive or long.
  Tier 2+ asks before running at scale.
- Keep SKILL.md under ~300 lines. Put long reference material in
  `references/<topic>.md` next to it and link it — hosts load it only when needed.

## Write the execution layer (scripts/)

The script contract (the generated stub already follows it):

- One job per script; `--help` works; arguments via argparse.
- Same inputs → same outputs. Idempotent where possible (safe to re-run).
- A JSON summary on stdout; artifacts to a predictable path (e.g. `outputs/<run>/`).
- Failure = non-zero exit + a clear message on stderr. Never swallow an exception
  or return `{"error": ...}` with exit 0.
- Secrets only from environment variables (`os.environ`), documented in the
  skill's Environment section and in `.env.example`. Never in code or args.
- Anything outward-facing supports `--dry-run`.
- Code used by 2+ skills moves to the workspace's shared-utilities directory
  (named in `AGENTS.md`), not copied between skills.

## Test it — before implementing

Replace the skipped `test_behaviour` in `tests/` with a test that runs the script
on a small fixture and checks the output. Then implement until it passes. Use the
cheapest test double that exercises the logic: a fixture file, a fake API response,
a fake solver output — not the live service. Run every skill's tests with:

```bash
python .harness/harness.py test
```

## Finish — every surface that routes the capability

A capability is complete only when every place that describes or routes it agrees:

1. `SKILL.md` frontmatter description (then `python .harness/harness.py sync`).
2. The nearest `AGENTS.md` if the skill changes what a directory owns.
3. Runtime wiring, if this is a hosted agent: a tool in `agents.py`, keywords in
   `config.json` description/tags, a line in `.github/prompts/system.md`.
4. `.env.example` for any new environment variable.
5. `python .harness/harness.py check` passes.

## Porting and vendoring

- **Port from a sibling workspace:** copy the process skeleton (format tables,
  checklists, export pipelines), adapt the domain rules, and record the deltas and
  why in the skill's Learnings. Re-verify every external endpoint at port time.
- **Vendor a third-party skill** (e.g. from github.com/anthropics/skills) verbatim
  into `.github/skills/<name>/`, keep its LICENSE, and append an adoption note at
  the end of its SKILL.md: what this workspace overrides, plus "*A refresh from
  upstream removes this block. Put it back.*" Record the upstream commit.

## Learnings

<!-- Dated, one line each, newest last. -->
