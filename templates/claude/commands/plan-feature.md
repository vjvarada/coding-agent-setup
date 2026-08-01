---
description: Turn a goal or feature idea into a dispatchable plan — decomposed workstreams, an owning spec with machine-checkable acceptance, and a wireframe for any UI surface.
argument-hint: "<the goal, feature, or brief>"
---

Plan this, dispatchably: **$ARGUMENTS**

You are the supervisor for the planning half of the loop. Nothing here writes
production code. The output is artifacts an autonomous implementer can execute
without asking anyone a question — because there will be nobody to ask.

Delegate the reading and writing to subagents; keep only their reports. Your
context is what has to survive the whole cycle.

## The cycle

**1 — Decompose.** Dispatch `plan-architect` with the goal.
It surveys what already exists, then proposes workstream rows with owners,
blockers, gate labels, and a one-line testable outcome each.

**Show the proposed rows to the owner and get agreement before writing them.**
Decomposition is the highest-leverage decision in the loop — everything
downstream inherits it, and correcting it here costs one message instead of four
agent-cycles. This is the one deliberate human checkpoint in the planning half.

**2 — Wireframe** *(only if a workstream has a UI surface)*.
Dispatch `ui-wireframer`. It produces a self-contained annotated HTML file
covering every screen and every state — empty, loading, populated, error,
denied. Its `⚠ OPEN` markers become open decisions in step 3.

Do this **before** the spec is finalized, so acceptance criteria can reference
the wireframe instead of describing a layout in prose.

**3 — Specify.** Dispatch `spec-writer` per workstream (in parallel where the
workstreams are independent). Each writes or upgrades the owning spec to the
seven-point contract, with machine-checkable acceptance criteria as the priority.

**4 — Gate-check.** Dispatch `spec-auditor` on each new spec.
This is a dry run of what the build loop will do on dispatch day. Any NO-GO now
is cheap; the same NO-GO discovered mid-build has already cost an implementer.
Loop back to `spec-writer` once with the blockers. If it still fails, the
workstream needs an owner decision — record it and move on.

**5 — Record.** Write the agreed rows to the work plan, with each row linking to
its owning spec. Add any new owner gates to `.claude/plan-guard.config.json`
**and a test case to `plan-guard.test.mjs`** — a gate that exists only in prose
is not a gate. Run the guard's self-test. Commit the plan, the specs, and the
wireframes together.

## Report

```
GOAL: <one line>
ALREADY BUILT: <what the survey found — often the most valuable finding here>
ROWS ADDED: <id — outcome — gate — blocked by>
SPECS: <path — auditor verdict>
WIREFRAMES: <path — screens covered>
NEW OWNER GATES: <added to plan-guard config + tested>
OWNER DECISIONS NEEDED: <question → which workstream it blocks>
READY TO DISPATCH NOW: <the rows that would pass the auditor today>
```

End by naming which row `/next-ticket` should take first, and why.
