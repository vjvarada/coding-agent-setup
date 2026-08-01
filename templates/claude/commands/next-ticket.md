---
description: Run one full supervisor cycle against the work plan — audit, build, verify, review, PR — for the next dispatchable workstream (or the one named).
argument-hint: "[<ticket-id> | 'next']"
---

You are the supervisor of the dispatch loop. Run **exactly one cycle** for one
ticket, then stop and report. Do not chain into a second ticket unless asked —
one cycle produces one reviewable PR, and that boundary is what keeps a human in
the loop.

Target: **$1** (if empty or `next`, choose the next dispatchable row yourself).

## Your posture

You orchestrate; you do not implement. Your context is the scarce resource that
has to survive the whole cycle, so delegate the reading and building and keep
only the verdicts. Do not read spec bodies or source files yourself unless a
subagent's report is ambiguous.

Everything durable goes in git — the board, the spec status headers, the branch.
Nothing that matters may live only in this conversation, because the next cycle
is a fresh context that can see only the repo.

## The cycle

**1 — Select.** Read the work plan's board only. If a ticket was named, use it.
Otherwise take the highest-leverage ready row that is not owner-gated end to end,
preferring rows that unblock others. State your pick and why, in one line.

**2 — Audit.** Dispatch `spec-auditor`.
- `NO-GO` → stop the cycle. If the blocker is documentation, *that* is the real
  next ticket: say so and offer to run `spec-writer` instead. Never proceed to
  implementation on a NO-GO — a build against an unverifiable spec produces a PR
  nobody can judge.
- `GO` / `GO-NARROWED` → carry the verdict block forward **verbatim**. It is the
  contract for every agent below.

**3 — Branch.** Confirm the tree is clean; if it is not, stop and report rather
than stashing someone's work. Then cut a branch from the default branch.

**4 — Build.** Dispatch `ws-implementer` with the auditor's verdict block pasted
in full. If it reports BLOCKED, stop and report — do not dispatch a second
implementer to route around a block.

**5 — Verify.** Dispatch `ws-verifier`.
- `FAIL` → send the findings to a *fresh* `ws-implementer` along with the
  original verdict block. **At most two repair rounds.** If it still fails, stop,
  leave the branch in place, and report what is unresolved. A loop that grinds on
  a stuck ticket burns budget and produces nothing; a human unsticks it in a
  minute.

**6 — Review.** Dispatch `diff-reviewer`.
- Any `P0` → repair round, counted against the same two-round budget.
- `P1`/`P2` → carry into the PR body as known findings; do not block.

**7 — Land.**
- Update the board row: state, plus a dated note on what shipped and what
  remains. This is the handoff to the next cycle — write it for an agent with no
  memory of this one.
- Confirm the owning spec's status header was updated; if not, do it now.
- Commit, push the branch, open a PR. The body carries: ticket id, the slice
  built, acceptance evidence, verification output, reviewer findings, and what
  was deferred.
- **Stop there.** Merging and deploying belong to the owner.

## Refusals

If any step needs an owner-gated action, stop and hand it over with the exact
action required. A guard hook enforces this independently; if it blocks you, the
block is correct — do not work around it, and do not ask a subagent to do what
you were blocked from doing.

## Report

Ten lines or fewer:

```
CYCLE:  <ticket> — <slice>
AUDIT:  GO | GO-NARROWED | NO-GO — <one line>
BUILT:  <one line>
VERIFY: PASS | FAIL — <the decisive evidence>
REVIEW: APPROVE | n findings
PR:     <url, or why none>
BOARD:  <how the row now reads>
OWNER NEEDS TO: <gated actions, or "nothing">
NEXT:   <the ticket the next cycle should take, and why>
```
