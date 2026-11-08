# `.claude/` — the Claude Code harness

**Scope:** hooks, subagents, slash commands and settings for Claude Code in this repo.
The parent contract is the root `AGENTS.md`. Nothing here is application code. This
folder is tracked in git on purpose: a gitignored harness reaches no fresh clone,
worktree, CI run or headless session, and the guarded loop silently degrades to an
unguarded agent.

## What lives here

| Path | Kind | Purpose |
|---|---|---|
| `settings.json` | config | Registers every hook below. Tracked: shared by every checkout |
| `skills/<name>/SKILL.md` | generated | Proxies to `.github/skills/<name>/` — written by `python .harness/harness.py sync`, never by hand |
| `hooks/session-handoff.mjs` | SessionStart hook | Injects the open `HANDOFF.md` entries. Fails open |
| `hooks/worktree-notice.mjs` | SessionStart hook | Says whether this session has its own worktree and whether its rules are behind `origin/main` |
| `hooks/plan-guard.mjs` | PreToolUse hook | Deterministic owner gates from `plan-guard.config.json` (when the loop is installed) |
| `hooks/rtk-bash.sh` | PreToolUse hook | Compresses noisy shell output (when RTK is installed) |
| `hooks/stop-children.mjs` | Stop hook | Lists long-running child processes the session left behind. Reports, never kills |
| `hooks/*.test.mjs` | tests | `node .claude/hooks/<hook>.test.mjs` — CI runs every one |
| `agents/`, `commands/` | subagents, slash commands | The planning/dispatch loop and `/handoff`, when installed |

## The three load-bearing ideas

1. **State lives in git, never in an agent.** The work plan or task board is the
   queue; `HANDOFF.md` carries actions with a Check. A session that dies part way
   through loses nothing, because the next one rebuilds its picture from the repo.
2. **Enforcement is a hook, not a prompt.** Instructions decay over a long
   unattended run; a hook does not. Agent prompts also state the gates — that
   repetition is deliberate, so an agent refuses for a reason it can name.
3. **The verifier must not be the implementer.** Self-reported success is the main
   way an unattended loop fails.

## Rules for changing this folder

- A gate changes in the work plan's owner-gate section **and** `plan-guard.config.json`
  **and** `plan-guard.test.mjs`, in the same change. A gate in prose only is not a gate.
- Every hook ships with a test, and CI runs it. Hooks that only inform fail **open**
  (exit 0 on any error); hooks that refuse fail **closed**.
- Subagents are one level deep: a worker cannot dispatch workers.
- Keep worker tool grants narrow. Read-only agents stay read-only — that is a
  correctness property, not a precaution.
- Never write `defaultMode: bypassPermissions` into a tracked settings file, and never
  let an agent grant itself permissions.
