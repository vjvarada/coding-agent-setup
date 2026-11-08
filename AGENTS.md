# coding-agent-setup — kit contract

**If you were sent here to set up a project, you are in the wrong file:** new or empty
folder → [`SCAFFOLD.md`](SCAFFOLD.md); existing codebase → [`SETUP.md`](SETUP.md).
This file is for agents **changing the kit itself**.

## Purpose

A kit that scaffolds new projects and custom agents, and retrofits existing
codebases, for agent-driven development. Its products are *other people's
workspaces*, so every change here is multiplied: a bug in a template lands in every
project scaffolded after it.

## Layout

| Path | Owns |
|---|---|
| `SCAFFOLD.md`, `SETUP.md` | Agent-facing playbooks (directives for the scaffolding agent) |
| `DOE.md`, `PLAYBOOK.md`, `ORCHESTRATION.md`, `DELIVERY.md`, `HARNESS-PRACTICES.md` | Method and principles |
| `scaffold/scaffold.py` | The generator: `list`, `intake-template`, `check-intake`, `new`, `install`, `upgrade` |
| `scaffold/catalog/` | Archetypes and stack recipes (data, not code) |
| `scaffold/tests/` | Kit tests — every archetype must scaffold and pass its own check |
| `templates/project/` | Base layer for every scaffolded project (`*.tmpl` rendered; `_*` fragments composed by code; the rest copied verbatim and kit-owned) |
| `templates/skills/` | Core skills shipped into every project |
| `templates/agent/`, `templates/agent-commandcenter/` | DOE agent archetype and its CommandCenter runtime |
| `templates/claude/`, `templates/copilot/`, `templates/shared/`, `templates/scripts/` | Host config, hooks, subagents, commands; DOX/plan/spec/handoff templates; delivery scripts — shared by the scaffolder and the installers |
| `install.sh`, `install.ps1` | Capability installers (retrofit, and `scaffold.py install`) |

## Rules for changing the kit

1. **Run the tests before and after.** `python -m unittest discover -s scaffold/tests`,
   every `node templates/claude/hooks/*.test.mjs`, and `bash templates/scripts/premerge.test.sh`.
   CI (`.github/workflows/kit.yml`) runs them on every push.
2. **The generator emits what the validator requires.** A new required file goes into
   `build_plan()`'s `required` list *and* is emitted for every archetype that needs it;
   the every-archetype test enforces this.
3. **One source per fact.** The DOX framework text lives only in
   `templates/shared/AGENTS.md`; hook registrations only in `templates/claude/settings*.json`;
   the lessons header only in `anneal.py`. Compose from them; never paste a copy.
4. **Templates render or fail.** `{{key}}` tokens must exist in `build_context()`;
   `${{ ... }}` (GitHub Actions) is left alone. A new key needs a value for every archetype.
5. **Unfinished-work markers are deliberate.** Use `TODO(scaffold): <what to fill>`
   only where the scaffolding agent must supply judgment; `harness.py check --strict`
   lists them. Never write that marker in prose that is not a request.
6. **Kit-owned files are upgradable; rendered files are the project's.** Changing a
   verbatim template reaches existing projects through `scaffold.py upgrade` (only where
   the project has not edited the file). Keep those files generic.
7. **Installers stay idempotent and non-destructive** — run twice, second run a no-op;
   merge, never overwrite. Keep `install.sh` and `install.ps1` in step.
8. **Hooks:** informational hooks fail open; refusing hooks fail closed; every hook ships
   with a `*.test.mjs`. A gate changes in `plan-guard.config.json` and its test together.
9. **Nothing in `templates/` may be gitignored by the kit's own `.gitignore`** (an
   unanchored `.claude/` once hid `templates/project/.claude/`). A kit test enforces it.
10. **Provenance.** A learning carries the case that taught it (`CONTRIBUTING.md`).

## Communication

Bottom line up front in every response, report, PR description and commit message.
