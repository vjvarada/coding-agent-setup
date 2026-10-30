---
description: Run one full supervisor cycle against the work plan — audit, build, verify, review by risk tier, PR, and (if granted) merge — for the next dispatchable workstream (or the one named).
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

**Task board.** If the project uses a task board (`.claude/task-board.md`), the
cycle runs inside a claim. `/work-on-task` claims the task and starts the
heartbeat, then calls this cycle. Post a short `post_agent_activity` line at
least once a minute, and before every long wait (a CI watch, a deploy watch).
At step 7, add the PR reference. End the cycle in exactly one disposition: the
task moves on, a question waits on a named member, or the task is released with
a comment. Without a board, skip these lines.

## The cycle

**1 — Select.** Read the work plan's board only. If a ticket was named, use it.
Otherwise take the highest-leverage ready row that is not owner-gated end to end,
preferring rows that unblock others. State your pick and why, in one line.

**1b — Set the risk tier.** The tier sets how much review the slice gets. Say
the tier and the reason in one line.
- **HIGH**: tenancy, auth, identity, a migration, money, secrets, a member or
  role write, or the deploy path. Verifier, then reviewer. At most two repair
  rounds.
- **STANDARD**: other product code. Verifier only while the feature is in build
  (1d). One repair round. The reviewer runs ONCE, on the whole feature, in the
  harden PR. Record each deferred guardrail in the backlog, and land the slice.
- **LOW**: tooling, tests, docs, or a style change with no data path. Verifier
  only. Skip the reviewer. One repair round.

If you are not sure, take the higher tier. The verifier is never skipped.

**1c — Pick the model for each dispatch.** Use a `fast` model for the work and a
`strong` model for the hard cases. Map the names to your host. For example
`fast` = sonnet, `strong` = opus, `small` = haiku. Pass the `model` on the
Agent call only where this table says so. Say the models in the same line as the
tier.

| Role | LOW | STANDARD | HIGH |
|---|---|---|---|
| `spec-auditor` | fast | fast | fast |
| `ws-implementer` | fast | fast | **strong** |
| `ws-verifier` | fast | fast | **strong** |
| `diff-reviewer` | skipped | **strong**, in the harden PR | **strong** |

Two escalations override the table:
- **A repair round after a FAIL on the same finding**: dispatch the next
  `ws-implementer` with the `strong` model. The `fast` one already missed it once.
- **A slice that crosses three or more services, or a concurrency, cache or
  ordering bug**: take `strong` for the implementer, at any tier.

Use the `small` model for a pure lookup with no judgement (find a file, list
callers, count rows). Never use it to build, verify or review.

**1d — Build or harden.**
- **Build** (the default): ship working slices fast. Only the product tests and
  the **safety** fences block (`fences.json`). **Process** fences and style lint
  warn. Skip the board-row note, the spec header and new process fences until
  the harden PR. Run the project's full local CI before each push.
- **Harden** (when the feature works): one PR, labelled `harden`. Make the
  process fences block for the session. Run `diff-reviewer` on the WHOLE
  feature diff. Write the deferred fences and backlog items as tasks. Update the
  spec header.
- A HIGH-tier slice keeps the full loop in both modes.

**2 — Audit.** Dispatch `spec-auditor`.
- **A small slice skips the audit.** A small slice is LOW, or STANDARD in build.
  Its task must state the acceptance criteria and must not start a new spec.
  Then quote the task text verbatim as the contract, under the line
  `AUDIT: skipped (small slice)`. A HIGH-tier slice, and the first slice of a
  spec, always get the audit.
- `NO-GO` → stop the cycle. If the blocker is documentation, *that* is the real
  next ticket: say so and offer to run `spec-writer` instead. Never proceed to
  implementation on a NO-GO — a build against an unverifiable spec produces a PR
  nobody can judge.
- `GO` / `GO-NARROWED` → carry the verdict block forward **verbatim**. It is the
  contract for every agent below.

**3 — Branch.** Confirm the tree is clean. If it is not, stop and report rather
than stashing someone's work. Then run `bash scripts/worktree.sh new <slug>`,
off the default branch. Put the task's short id in the slug. Work in the
worktree it prints. Use `worktree.sh remove <slug>` to clean up, never a bare
`git worktree remove`.

**4 — Build.** Dispatch `ws-implementer` with the contract from step 2 pasted
in full. If it reports BLOCKED, stop and report — do not dispatch a second
implementer to route around a block.
- **A slice that changes what the app does or draws runs locally first.** The
  implementer runs `bash scripts/dev_up.sh` in its worktree. It checks each
  behaviour criterion in the running app before it reports, and it leaves the
  stack up for the verifier. It reports a `LOCAL RUN:` line with the evidence.
  A slice with no running surface (docs, a pure library) writes `not run — <why>`.

**5 — Verify.** Dispatch `ws-verifier`. It checks each behaviour criterion on the
local stack itself (`bash scripts/dev_up.sh --check`, then the criterion through
the API or a capture), and quotes the evidence on a `LOCAL:` line. It never runs
`--down` or `--reset` on a stack it did not start.
- `FAIL` → send the findings to a *fresh* `ws-implementer` along with the
  original contract. **The tier (1b) sets the repair rounds.** For a STANDARD or
  LOW slice, land it if no remaining finding can reach a customer, and record
  those findings in `HANDOFF.md`. If it still fails, stop, leave the branch in
  place, and report what is unresolved. A loop that grinds on a stuck ticket
  burns budget and produces nothing; a human unsticks it in a minute.

**6 — Review.** Skip this step for a LOW slice, and for a STANDARD slice in
build. Otherwise dispatch `diff-reviewer`.
- Any `P0` → repair round, counted against the same tier budget.
- `P1`/`P2` → carry into the PR body as known findings; do not block.

**7 — Land.**
- Update the board row: state, plus a dated note on what shipped and what
  remains. In build, a short note is enough. This is the handoff to the next
  cycle — write it for an agent with no memory of this one.
- Confirm the owning spec's status header was updated (in harden; in build it
  can wait). If it is due, do it now.
- Commit, push the branch, open a PR. The body carries: ticket id, the task URL
  (if a board is in use), the slice built, acceptance evidence, verification
  output, reviewer findings, and what was deferred. Add the task reference for
  the branch and the PR, and move the task to its review status.
- **Merge only if the owner has granted it.** Read `.claude/OWNER_GRANTS.md`.
  - **No `merge` grant in date** (the kit default): **stop at PR opened.**
    Merging and deploying belong to the owner. Say so in the report.
  - **A `merge` grant in date:** run
    `bash scripts/premerge.sh && gh pr merge <n> --squash`. Never merge
    without the script. If `premerge.sh` exits 1, the branch is behind or
    stale: merge the default branch into your branch, fix the conflicts, push,
    wait for CI, and run it again. Never rebase a pushed branch.
  - Watch the deploy run that the merge starts. A green run is not proof. Wait
    until the served version endpoint (or the log line, or the migration
    ledger) shows your merge SHA or a later one.
  - **Smoke-test staging** when the served SHA arrives: load the page of the
    change and check one acceptance criterion. Steps 4 and 5 already tested the
    behaviour locally.
  - **Test in full on staging only what the PC cannot:** the deploy path
    (units, proxy, env files), a real OAuth sign-in, a real provider webhook or
    sync, and a migration on production-shaped data.
  - If staging does not answer, write "staging not up". Do not claim the test.
  - If the project promotes to production on a schedule, report "verified
    locally, staging smoke at `<sha>`, reaches production at the next release".
    Do not dispatch production unless the owner asks in this session.
  - Move the task to done after the merge.

## Refusals

Check `.claude/OWNER_GRANTS.md` first. If a dated line covers the gate id, do
the work, report the act in the same message (what, where, evidence), and do not
ask again. If no line covers it, stop and hand it over with the exact gate id.

Four acts stay refused, and no grant unlocks them: force-push or history
rewrite, a commit or push on a protected branch, writing the grant file, and
destroying infrastructure or data. Money, identity and third parties also need
the owner's word first.

A guard hook enforces this independently. If it blocks you, the block is
correct — do not work around it, and do not ask a subagent to do what you were
blocked from doing.

## Report

Twelve lines or fewer:

```
CYCLE:  <ticket> — <slice>
AUDIT:  GO | GO-NARROWED | NO-GO | skipped (small slice) — <one line>
TIER:   HIGH | STANDARD | LOW — <one line why> — models: <fast/strong per role>
BUILT:  <one line>
LOCAL:  <app URL + criteria checked, or "not run — <why>">
VERIFY: PASS | FAIL — <the decisive evidence>
REVIEW: APPROVE | n findings | skipped (LOW, or STANDARD in build)
PR:     <url, or why none>
MERGED/STAGING: merged <sha>, staging smoke at <sha> | not merged (no grant) | staging not up
BOARD:  <how the row now reads>
OWNER NEEDS TO: <gated actions, or "nothing">
NEXT:   <the ticket the next cycle should take, and why>
```
