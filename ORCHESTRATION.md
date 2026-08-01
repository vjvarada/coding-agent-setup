# ORCHESTRATION — planning and building with a supervisor-worker loop

`PLAYBOOK.md` is about making *one* agent efficient on a large codebase. This
document is about making *many* agents move a project forward on their own —
from a goal, through a plan, to merged PRs — without a human driving each step
and without the plan quietly dissolving along the way.

It is the methodology behind Principles 8–10 and the templates in
`templates/claude/agents/`, `commands/`, and `templates/shared/`.

> **The honest headline:** the autonomy does not come from the agents. It comes
> from the plan being machine-checkable and the gates being code. Strong agents
> against a vague plan produce confident, unreviewable work. Ordinary agents
> against a sharp plan produce a steady queue of small, correct PRs.

---

## 1. The shape

Two loops over one shared artifact.

```
        ┌──────────────── PLAN LOOP (/plan-feature) ────────────────┐
 goal → decompose → wireframe → specify → audit → rows on the board
        └───────────────────────────────────────────────────────────┘
                                   │
                            the work plan
                       (the queue; lives in git)
                                   │
        ┌──────────────── BUILD LOOP (/next-ticket) ────────────────┐
          select → audit → branch → build → verify → review → PR
        └───────────────────────────────────────────────────────────┘
                                   │
                        human: merge, deploy
```

The board is the only thing that connects the two. Neither loop keeps state in a
conversation, so either can die mid-flight and the next run reconstructs
everything from the repo.

### The roles

| Role | Reads | Writes | Job |
|---|---|---|---|
| **supervisor** (the slash command) | the board | the board, the PR | Sequence, delegate, keep verdicts, stop at gates |
| `plan-architect` | code + board | proposals | Decompose a goal into owned, gated, verifiable rows |
| `ui-wireframer` | existing UI | a wireframe | Settle layout and *states* as an artifact, not prose |
| `spec-writer` | code | the spec | Make the work dispatchable — above all, checkable acceptance |
| `spec-auditor` | spec + code | nothing | Refuse work that is not dispatchable |
| `ws-implementer` | spec + code | the branch | Build one cleared slice, in its right home |
| `ws-verifier` | the diff | nothing | Independently prove acceptance is met |
| `diff-reviewer` | the diff | nothing | Find what green tests cannot see |

Four of the seven write nothing. That ratio is deliberate: in an unattended loop
the expensive failure is not slow work, it is confident wrong work, and the only
defence is independent readers who did not write the code.

---

## 2. The four ideas that make it work

### 2.1 Durable state lives in git, never in an agent

The board is the queue. Each spec's status header is the completion record. A
cycle's last act is to write back what shipped and what remains — *for a reader
with no memory of that cycle*.

This is what makes the loop resumable rather than one long fragile session. It is
also what makes it debuggable: when a run goes wrong, the evidence is in the diff
and the board, not in a transcript nobody kept.

The corollary is a rule: **an agent that "remembers" instead of writing it down
has failed**, even if its output was correct.

### 2.2 Enforcement is a hook, not a prompt

Instructions degrade over a long unattended run. A hook does not.

Every agent prompt in this kit states the owner gates *and*
`.claude/hooks/plan-guard.mjs` enforces them independently. The redundancy is
deliberate: the prompt makes the agent refuse coherently and explain itself; the
hook makes the refusal real. Prose is the explanation, config is the boundary.

The rule that keeps them honest: **a gate that exists in the work plan but not in
`plan-guard.config.json` is not a gate.** Add both in the same change, with a
test case — an untested regex is a guess, and both over- and under-matching are
expensive.

### 2.3 The verifier must not be the implementer

Self-reported success is the dominant failure mode of autonomous loops. An agent
that just wrote code has already concluded it works, and it will read its own
diff looking for confirmation.

So `ws-verifier` reads the diff *before* the implementer's report, re-runs the
commands the **spec** named rather than the ones the builder chose, and treats
the report as claims to check. On a host without subagents, the same effect
requires a fresh session — see `templates/copilot/orchestration-instructions.md`.

### 2.4 Autonomy is capped by verifiability

This is the load-bearing one, and it is a fact about the *plan*, not the agents.

A ticket whose done-when is "works well", "looks right", or "owner call" can
never be completed autonomously — there is no signal that would let any agent, or
any human reviewing its output, conclude it is finished. No model improvement
changes this.

So the highest-leverage work in the whole system is not agent design. It is
converting acceptance criteria into commands. Every item you make checkable
converts directly into autonomous throughput; the rest of the machinery is
plumbing around that one number.

*Lesson:* on the platform this kit came from, the first honest audit of a mature,
carefully-written spec corpus found that most workstreams were only *partly*
dispatchable — a buildable half plus a flag flip, a spend, or a product call.
`GO-NARROWED` became the auditor's most common verdict, and splitting those rows
in two was worth more than any prompt tuning.

---

## 3. Planning: what "comprehensive" actually means

A comprehensive plan is not a longer document. It is one that answers the
questions an implementer would otherwise have to ask — because there is nobody
to ask.

**Survey before you plan.** The first act of `plan-architect` is finding what is
*already built*. Half-finished capability that nobody recorded is the normal
state of a real codebase, and a plan that ignores it schedules the same work
twice. This step alone routinely changes the decomposition.

**Decompose by outcome, not by layer.** "API + UI + tests" is one workstream, not
three. Split until each row could go to a stranger holding only its spec, and
size each to a PR a human will actually read — because that PR is the last human
checkpoint, and an unreviewable one silently removes it.

**Separate the buildable from the decidable.** Most real workstreams are part
agent-safe build, part human call. Two rows, not one ambiguous row that stalls.

**Wireframe every UI surface, before the spec is final.** A prose layout is
ambiguous by construction — three agents will build three different screens from
the same paragraph. One self-contained annotated HTML file settles it, and makes
"matches the wireframe" a checkable criterion instead of an opinion.

The states are most of the value: **empty, loading, populated, error, denied.**
Implementers reliably build the populated state from prose and skip the rest, and
tests rarely cover them. Writing real copy for the empty state is often where a
team discovers nobody had decided what the feature says when it has nothing to
show.

**Get human agreement on the decomposition, and only there.** It is the one
checkpoint worth stopping for: everything downstream inherits it, and correcting
it costs one message now versus four agent-cycles later.

---

## 4. Tests and evals between the stages

Every handoff in the loop is gated by something a machine can check. That is what
lets a stage fail loudly instead of passing a plausible artifact downstream.

| Handoff | Gate | Catches |
|---|---|---|
| plan → spec | seven-point contract | vague scope, no owner |
| spec → build | `spec-auditor`, run before dispatch | uncheckable acceptance, stale anchors, status drift, gated work |
| build → review | spec's own commands + full suite + lint | ordinary regressions |
| verify → PR | independent re-run + acceptance-by-command | self-reported success |
| review → PR | adversarial diff read | silent no-ops, contract breaks, fail-open, leaks |
| PR → merge | CI, then a human | everything above, again, plus judgement |

**Unit tests are necessary and not sufficient**, which is `PLAYBOOK.md`
Principle 4 applied inside the loop. The expensive defects — a confirmation gate
that denies instead of asking, a write-back that fails on every call, wiring that
nothing reads — pass unit tests and are only caught by exercising the real path.
Where your project has trajectory or end-to-end evals, they belong in the
verifier's command list, not in a separate manual step. See
`HARNESS-PRACTICES.md` for building those.

**Cover the CI gap explicitly.** Every pipeline has one — a language it skips, a
package it does not build, a suite that only runs on the default branch. The
verifier's job includes finding that gap and covering it locally, because nothing
downstream will.

---

## 5. What stays human

The loop stops at **"PR opened"**. Deliberately.

- **Merge** — the reviewable diff is the product of the whole loop. Consuming it
  is the human's part.
- **Deploy** — outward-facing and often irreversible. A deploy that auto-applies
  migrations is not something the agent that broke it can unbreak.
- **Production flag flips** — the code can ship dark; turning it on is a
  judgement about users.
- **Spending, publishing, credentials, external accounts.**
- **The decomposition** — the one planning checkpoint (§3).

Everything in that list belongs in both the work plan's owner-gate section and
`plan-guard.config.json`.

A tempting mistake is to extend the loop through merge and deploy once it has run
well for a few days. The reason not to: every other safeguard here is a check on
*correctness*, and correctness is exactly what a confident wrong change looks
like from the inside. The human at the end is not reviewing whether the tests
passed — they are the only reader asking whether this should ship at all.

---

## 6. Cost, and when not to use this

A full build cycle is four subagents, each paying its own tool-schema and
instruction floor before doing any work. On the platform this came from, that
floor measured **~12–19k tokens per agent** — the number was more than double the
first estimate, which is Principle 6 in miniature: measure your own.

So:

- **Use the loop** for planned, spec'd work of real size — the queue you would
  otherwise grind through by hand.
- **Do not use it** for a typo, a one-line fix, or exploration. A single agent is
  cheaper and better. The loop's overhead buys independence, and there is nothing
  to be independent about in a three-line diff.
- **Narrow every worker's tool grants.** Four of the seven roles are read-only,
  which is a correctness property first and a cost saving second.

---

## 7. Failure modes seen in practice

- **The spec that lies.** A status header claiming work is unbuilt when it
  shipped sends an implementer to build it twice. Hence the auditor's
  reality-check step, and R4 (status updates land in the same PR as the work).
- **The grinding ticket.** Verifier fails, implementer repairs, verifier fails
  again, forever. Cap repair rounds at two and stop with the branch intact — a
  human unsticks it in a minute.
- **Scope creep in an unattended run.** Nobody is watching, the implementer
  notices adjacent work, and a 200-line PR becomes 2,000. Hence a *narrowed*
  scope in the verdict block, and the verifier checking for anything outside it.
- **The gate that only exists in prose.** Someone writes "agents must not deploy"
  in the plan and never adds the pattern to the guard. The rule in §2.2 exists
  because this is the easiest mistake in the system to make.
- **Config the loop cannot see.** If the harness directory is gitignored, none of
  it reaches a fresh clone, a worktree, or an unattended run — the loop silently
  degrades to an unguarded agent. Check this before running headless.
- **Supervisor context exhaustion.** A supervisor that reads specs and source
  itself runs out of room after two cycles. It must delegate the reading and keep
  only verdicts.

---

## 8. Adoption path

Do not build all seven roles on day one. The order that works:

1. **Write the board and one spec by hand** (`templates/shared/`). If you cannot
   write checkable acceptance criteria for one real ticket, no amount of agent
   machinery will help — and you have learned that for the price of an afternoon.
2. **Install `plan-guard` and its config**, and run the self-test. The boundary
   comes before the autonomy, not after.
3. **Add `spec-auditor` alone** and run it over your existing plan. Its NO-GO
   list *is* your remediation backlog, and it is usually longer than expected.
   This step pays for itself before a single line is built.
4. **Add the build trio** and run `/next-ticket` on one small, self-verifying
   ticket — watch it interactively. Do not walk away from cycle one.
5. **Add the planning trio** once the build loop is landing PRs you would have
   merged anyway.
6. **Only then run it unattended** — headless, on a schedule. Same agents, same
   hooks, no window open.

Each step is useful alone. If you stop after step 3, you still got the most
valuable thing in this document: an honest measure of how dispatchable your plan
actually is.
