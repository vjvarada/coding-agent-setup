---
name: self-annealing
description: >-
  Continuous self-improvement loop for this workspace (DOE framework). Capture every
  fix, gotcha, validated setting or wrong instruction as a lesson the moment it is
  learned, integrate it into its architectural home (a SKILL.md, a script plus a test,
  an AGENTS.md contract), and run the session-end gate before signing off so no
  learning is lost. Use whenever something breaks and gets fixed, whenever a skill's
  instructions turn out wrong, and ALWAYS at the end of a session that changed code,
  skills or docs.
when_to_use: "Something broke and you fixed it; a documented step was wrong; you found a better way; the session is ending."
authority: write
cost_tier: 0
audience: developer
version: 1.0.0
---

# Self-annealing

The harness is a living system. Skills and contracts encode what the agents know;
real work keeps teaching things they do not know yet. This skill turns that learning
into a loop with a hard gate, so knowledge lands in git instead of evaporating with
the session. (DOE: *errors are learning opportunities — fix it, test it, update the
directive, and the system is now stronger.*)

## The loop

1. **Capture — the moment you learn it, zero friction.**

   ```bash
   python .github/skills/self-annealing/scripts/anneal.py log \
       --title "short name" \
       --lesson "what was learned and why it matters" \
       --target <skill, module or doc that should absorb it>
   ```

   Log liberally. An un-logged lesson is a repeat mistake scheduled for the next
   session. Lessons live in `docs/lessons.md` (tracked in git — the backlog is part of
   the harness history).

2. **Integrate — same session when cheap, the next annealing pass when not.** Place
   each lesson in its architectural home *before* writing (DOX: place before building):

   | Lesson kind | Home |
   |---|---|
   | A reusable computation, API quirk handled in code, retry/backoff rule | the owning script **plus a test that fails without the fix** |
   | A process rule, gotcha, validated setting, rate limit | the owning skill's `SKILL.md` (Process / Edge Cases / Learnings) |
   | Where things go, what a directory owns | the nearest `AGENTS.md` |
   | A capability description (routing / triggers) | the SKILL.md `description` — then `python .harness/harness.py sync` updates every table and proxy |
   | A one-off fact about one run or one customer | the run's record (e.g. `outputs/<run>/`), NOT the harness |

   A lesson is integrated only when every surface that routes or describes the
   capability agrees, and a behaviour-changing lesson ships with a test — prose-only
   fixes regress silently. Then close it:

   ```bash
   python .github/skills/self-annealing/scripts/anneal.py apply L007 --note "meshing SKILL.md Edge Cases + test_retry"
   ```

   Use `defer L007 --note "why"` when it needs the user or a bigger change; add a
   `HANDOFF.md` entry if it must not be forgotten.

3. **Gate — every session end.**

   ```bash
   python .github/skills/self-annealing/scripts/anneal.py gate --run-tests
   ```

   Exit 1 means action is needed: OPEN lessons to integrate or defer, a failing
   harness check or test, or uncommitted changes. When changes are uncommitted the gate
   prints a suggested commit message — **present it to the user and ask before
   committing.** Never leave harness improvements untracked; never commit without the
   user's go-ahead.

## What counts as a lesson

- A fix to a script, with the failure that prompted it (rate limit, encoding, path with spaces)
- A documented step that was wrong, missing or slower than the path that worked
- A setting, threshold or parameter validated against real output
- An environment or platform trap (Windows paths, shell quoting, a tool's broken flag)
- A wrong assumption in a test (units, time zones, ordering)

Not lessons: one-off facts with no reuse value, and anything already documented
(check first — `anneal.py list --all` and the target SKILL.md).

## Safety rules (from the DOE framework)

- **Check before spending.** If a fix needs paid API credits, a long run, or an
  outward action to test, ask the user first.
- **Never modify credentials.** `.env` and secret stores are not yours to edit.
- **Test before trusting.** Verify the fix works before you record it as validated.
- **Record the change.** Each SKILL.md has a `## Learnings` section — append a dated
  line, so a later reader can see why the instructions say what they say.

## Scripts

| Script | Purpose |
|---|---|
| `scripts/anneal.py log` | Capture a lesson (gets the next `L###` id) |
| `scripts/anneal.py list [--all]` | Show OPEN lessons (or every lesson) |
| `scripts/anneal.py apply ID --note` / `defer ID --note` | Close or park a lesson |
| `scripts/anneal.py gate [--run-tests]` | Session-end gate: lessons + harness check (+ tests) + git status → suggested commit |

## Learnings

<!-- Dated, one line each, newest last. -->
