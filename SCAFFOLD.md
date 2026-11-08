# SCAFFOLD — set up a new project or a custom agent from an empty folder

> **You are a coding agent in a new (or nearly empty) folder, and the user pointed you
> at this kit. Execute this file top to bottom.** The result is a complete, agent-ready
> workspace: the project's code skeleton (from its stack's own generator), the DOX
> architecture contract, the DOE skill harness (directives + deterministic scripts +
> self-annealing), session hooks, owner gates, CI, and the kit's token and delivery
> tools. Every step says how to verify it. Report real output, never "should work".
>
> Retrofitting an **existing** codebase instead? `SETUP.md` is the shorter path. The
> scaffold also works there (it never overwrites; it composes existing `AGENTS.md`,
> `CLAUDE.md` and `README.md`) — skip step 3 if you use it.

**How the work splits (DOE):** you do the judgment — the interview, the stack choice,
the scopes, the prose that needs thought. `scaffold/scaffold.py` does the mechanics,
the same way every time. Do not hand-write files the script writes; if the script is
wrong, fix the script (and tell the user — see `CONTRIBUTING.md`).

## Ground rules for this session

- **Bottom line first** in every message to the user.
- **Ask before anything outward or hard to undo:** installing system tools, the first
  commit, creating a remote, pushing. Everything else in this file is local and
  reversible — do it.
- **Never overwrite** a file you did not create in this session. The script already
  refuses to.
- **Finish guard and CI edits in this session.** The kit's owner gates (`plan-guard`)
  load at session start, so they are not live yet. From the next session on, agents
  cannot edit `.claude/settings.json`, `.claude/plan-guard.config.json`,
  `.github/workflows/` or `.env*` — the owner does. Leave those files finished.

---

## 1. Get the kit (outside the project)

Clone the kit to a temporary folder **outside** the project, so none of it is
committed by accident:

```bash
# macOS / Linux / Git-Bash
git clone --depth 1 https://github.com/vjvarada/coding-agent-setup "${TMPDIR:-/tmp}/coding-agent-setup"
```
```powershell
# Windows PowerShell
git clone --depth 1 https://github.com/vjvarada/coding-agent-setup "$env:TEMP\coding-agent-setup"
```

Call that path **`$KIT`** below. Then check the prerequisites and the menu:

```bash
python --version          # need 3.9+ (python3 on some systems)
git --version
node --version            # needed for the Claude Code hooks; warn the user if missing
python $KIT/scaffold/scaffold.py list
```

`list` prints the archetypes (web-app, api-service, cli, library, data-pipeline,
**agent**, mobile-app, desktop-app, firmware, monorepo, other) and the stack recipes.
If the folder is not a git repository yet, run `git init` now.

## 2. Intake interview (judgment — the most important step)

Get just enough from the user to fill an intake. Infer what you can, offer a
recommendation for every choice, and never ask what has a sensible default. Use the
host's structured-question tool if it has one (max ~4 questions per round). Write
down every assumption you make; you will show them in step 2.4.

**2.1 Round one — what and how (always):**

1. *What are we building, and who uses it?* (one or two sentences)
2. *Is it a program/app, or an agent that does a specific job?* → propose the
   archetype. "An agent that …" → `agent`. Unsure → `other` is a valid answer.
3. *Stack?* Recommend one from the archetype's `suggested_stacks` with a one-line
   reason; accept the user's preference, including stacks not in the catalog
   (use `"stack": {"id": "custom", ...}` with your own commands).
4. *Which coding agents will work on it?* Default: Claude Code + GitHub Copilot.

**2.2 Round two — the brief (always):** the problem today; the success criteria —
**each one checkable by a command, a metric or a demo** (push back on "works well":
an unverifiable goal caps how much agents can do unattended); explicit non-goals;
known risks; who owns scope decisions.

**2.3 Round three — depends on the archetype:**

- **Agent:** the jobs it does → one **skill** each (`name` in kebab-case, a
  `description` that says what it does *and when to use it*, in the words a user
  would type; `authority` read / write / external; `cost_tier` 0–3); the systems it
  touches and the credentials that implies (`integrations`, `env`); the runtime —
  `ide` (Claude Code / Copilot in this workspace; the default) or `commandcenter`
  (the MAF agent contract: `agents.py` + `config.json`); its persona in one sentence;
  what it must never do on its own (→ `gates`).
- **Everything else:** where it will run (→ whether the Delivery capability is on);
  what must never happen without the owner (→ `gates`: migrations against shared
  databases, publishing, sending to customers, spending); team or solo (solo + no
  server → Delivery off).

**2.4 Write and confirm the intake.** Start from the template, fill it, validate it:

```bash
python $KIT/scaffold/scaffold.py intake-template --archetype <archetype> --out "$KIT/../intake.json"
# edit the file …
python $KIT/scaffold/scaffold.py check-intake --intake "$KIT/../intake.json"
```

Worked examples: `$KIT/scaffold/examples/intake.agent.json`,
`$KIT/scaffold/examples/intake.web-app.json`. Field reference: the `_doc` keys in
`$KIT/scaffold/catalog/*.json`. Show the user a short summary — name, archetype,
stack, skills or scopes, gates, capabilities, and your assumptions — and get **one**
confirmation before generating anything.

## 3. Generate the code skeleton with the stack's own tool

Skip this step for `agent` (the kit's DOE layer *is* its skeleton) and for an
existing codebase.

- Take the recipe's `init` commands from `check-intake`'s stack (or your custom
  stack). **Run `<tool> --help` first**: generators change their flags. Use
  non-interactive flags; generate into the project root (`.`).
- Install dependencies and run its sample test once, so you know the test command
  works before the harness records it.
- **Now look at the tree it produced and set the intake's `scopes`** to match it:
  one scope per top-level area that owns a distinct kind of work, with `covers`,
  `not_owns`, and two or three `rules` each (where new files of each kind go, the
  local test command). This is what Place Before Building routes on — make it true.
  Re-run `check-intake`.

## 4. Scaffold the harness (mechanical)

```bash
python $KIT/scaffold/scaffold.py new --intake "$KIT/../intake.json" --target . --dry-run   # look first
python $KIT/scaffold/scaffold.py new --intake "$KIT/../intake.json" --target .
```

It writes (never overwriting; composing `AGENTS.md`/`CLAUDE.md`/`README.md` if the
generator made them): the DOX root `AGENTS.md` with your constraints, gates, scopes
and a harness map; one `AGENTS.md` per scope; `CLAUDE.md` and
`.github/copilot-instructions.md` pointing at it; the core skills
(`self-annealing`, `skill-authoring`, `run-and-verify`) and one skill package per
intake skill under `.github/skills/` with generated Claude Code proxies; `.harness/`
(`project.json`, `harness.py`, a manifest for upgrades); `docs/brief.md`,
`docs/lessons.md`; `HANDOFF.md` with the follow-ups as checkable entries; session
hooks and `/handoff`; CI (`.github/workflows/harness.yml`, review reminder), a PR
template and a gitleaks config; for agents, the DOE layout (`.github/prompts/system.md`,
`.github/agents/<slug>.agent.md`, `.tmp/scripts/run_store.py`, `inputs/`,
`outputs/`, `agent-data/`) and, for `commandcenter`, `agents.py`, `config.json`,
`instructions.md`, `pyproject.toml`, `tests/test_agents.py`.

Verify: `python .harness/harness.py check` → `PASS` (warnings about unfinished
markers are expected until step 6).

## 5. Install the capability tools

```bash
python $KIT/scaffold/scaffold.py install --target .
```

This runs the kit installer (`install.sh`, or `install.ps1` on Windows) with the
intake's toggles: **Graphify** (code knowledge graph), **RTK** (output compression),
the **planning/dispatch loop** (subagents, `/plan-feature`, `/next-ticket`,
`plan-guard`), and **Delivery** (`dev_up.sh`, `premerge.sh`, `worktree.sh`). It
installs system tools (uv/pipx, winget/brew) — **ask the user first**. Tell them
about the RTK auto-approve tradeoff (`SETUP.md §3`). A tool that fails to install is
reported and skipped, not fatal. Details per capability: `SETUP.md` §2–§6b.

## 6. Finish the judgment work

```bash
python .harness/harness.py check --strict     # lists every unfinished marker, file:line
```

Resolve each one with real content — run the command before you write it down:

- **`run-and-verify` smoke check** — start the thing, find the one observable check
  that proves it is up (a URL and expected text, a CLI line, an agent run record),
  and write that.
- **Scope contracts** (`<scope>/AGENTS.md`) — the local conventions, if the intake
  gave none.
- **`docs/brief.md`** — any field the interview missed: ask the user.
- **Carried-over notes** in `AGENTS.md`/`CLAUDE.md` — merge them into the right
  section, then delete the notes section.
- **CI project tests** — if there was no test command, set up the toolchain step.

Then work the `HANDOFF.md` queue the scaffolder wrote — each entry has a Check:

- **Owner gates (loop installed):** turn every line of `AGENTS.md § Owner Gates` that
  a command can express into `pathGates` / `commandGates` in
  `.claude/plan-guard.config.json`, replace the `prod-flag-flip` placeholder, and add a
  case per gate to `.claude/hooks/plan-guard.test.mjs`. Run
  `node .claude/hooks/plan-guard.test.mjs`. (This session only — see the ground rules.)
- **First plan (loop installed):** with the user, copy `$KIT/templates/shared/work-plan.md`
  to `docs/plan/work-plan.md` and `$KIT/templates/shared/spec.md` to
  `docs/specs/<first-workstream>.md`, and fill them from the brief. Acceptance
  criteria are commands. If the user is not available, leave the entry.
- **Delivery:** `cp scripts/dev_up.config.example scripts/dev_up.config`, fill it, and
  run `bash scripts/dev_up.sh --check`.
- **Agent skills:** do not implement them all now. Fill each SKILL.md's Goal, Inputs,
  Process, Outputs and Definition of Done from the interview; implementing them
  test-first is the first work item (`/plan-feature` or the `skill-authoring` skill).

Delete every `HANDOFF.md` entry whose Check now passes. Leave the rest — they are
the next session's queue.

## 7. Verify — and report the numbers

```bash
python .harness/harness.py check --strict     # expect PASS
python .harness/harness.py test               # expect PASS (stub skills show skipped=1)
for t in .claude/hooks/*.test.mjs; do node "$t"; done          # every hook passes
<the project test command from AGENTS.md>     # the generator's sample test passes
git add -A && git status --short | head -50   # staged manifest: .claude/, .harness/, .github/skills/ present
python .harness/harness.py check              # ignore traps clean after staging
```

Also run the `run-and-verify` smoke check if anything is runnable, and report the
Graphify node/edge counts and the RTK version if those were installed. **The staged
manifest check is not optional:** a gitignore rule that drops `.claude/`, `.harness/`
or `.tmp/scripts/` produces a "successful" commit of a workspace that does not work
on any other machine.

## 8. Hand over

1. **Ask the user before the first commit.** The root commit goes on `main` (there is
   nothing to review against yet); from then on, work happens on branches — the
   guard refuses commits on `main` from the next session.
   Suggested message: `Scaffold <name> (<archetype>, <stack>) with coding-agent-setup <version>`.
2. Ask before creating a remote or pushing.
3. Report, bottom line first: what was created; the check/test results with real
   output; what is left (the open `HANDOFF.md` entries, one line each); and the next
   command — usually `/plan-feature <first goal>` (or `/next-ticket` if a plan exists).
4. Delete the temporary kit clone.

---

## Later: keeping the workspace current

- **Kit improvements** reach a scaffolded project through
  `python <kit>/scaffold/scaffold.py upgrade --target .` — it refreshes kit-owned files
  the project never edited, adds new ones, and lists edited ones for a manual merge.
  It merges into `.claude/settings.json` (a guard file), so run it when the owner asks.
- **The project improves itself** through the `self-annealing` skill: lessons are
  logged as they happen, integrated into skills and contracts, and gated at session
  end. A lesson that would help *every* project belongs in this kit — see
  `CONTRIBUTING.md`.
- **New capabilities** are new skills: `python .github/skills/skill-authoring/scripts/new_skill.py <name> --description "..."`.

The method behind all of this — what DOE is and why the harness is shaped this way —
is in [`DOE.md`](DOE.md). The engineering principles are in [`PLAYBOOK.md`](PLAYBOOK.md).
