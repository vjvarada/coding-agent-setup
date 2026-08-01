# Work plan — the dispatch board

**Status:** Active · **Updated:** <YYYY-MM-DD> · **Owner:** <name>

> **Fill in the `<...>` placeholders and delete this quote block.**
> This document is the queue an autonomous dispatch loop reads. It owns
> **ordering, ownership, and dispatchability** — nothing else. What to build and
> how belongs in the owning spec; this board links to it and never restates it.
>
> **Authority:** for *what and how*, the owning spec wins. For *what order and
> who owns it*, this doc wins. When another doc disagrees with the owner named
> in §3, that doc is stale by definition — fix it.
>
> Keep it honest. A board that lies about state is worse than no board: agents
> dispatch from it without asking, and a wrong row costs a whole cycle.

---

## 1. The dispatchable-spec contract

A workstream may be handed to an autonomous agent only when its owning spec
carries all seven points. `spec-auditor` tests each one and refuses otherwise.

1. **Status header** — dated, and verified against the code on that date. A
   header contradicting the body is worse than none.
2. **Scope and non-goals** — both, explicitly. Non-goals are what keep an
   implementer from quietly widening the work.
3. **Acceptance per item** — a "done when" that can be *tested*, naming a
   command, an assertion, or an observable state. "Owner call", "works well" and
   "looks right" all fail. **This point is the ceiling on how much of the project
   can ever be autonomous** — every item you make checkable converts directly
   into throughput.
4. **Current file paths** — re-verified at dispatch, not trusted from authoring
   time.
5. **Verification commands** — the exact, runnable commands.
6. **Single owner** — one owning spec; every other doc linking here and adding
   nothing.
7. **Gate labels** — every item marked **AGENT-SAFE** or **OWNER-GATE**. An
   agent must refuse owner-gated work and say so.

**Standing rules** (bind every spec):

- **R1 — no absolute future identifiers.** Never write a migration number,
  version, or sequence id that does not exist yet; write "next free at build
  time". Stale forward references are the most common broken anchor.
- **R2 — no id reuse across docs.** "Phase 2" meaning three different things in
  three specs makes dispatch ambiguous. New work uses the ids on this board.
- **R3 — one name per concept.** <state the project's naming conventions>.
- **R4 — status changes propagate.** A PR that ships spec'd work updates the
  owning spec's status header *in the same PR*.

---

## 2. The board

States: 🟢 ready to dispatch · 🟡 dispatchable after the named gate ·
🔴 blocked on an owner decision · ✅ done.

| WS | Workstream | Owning spec | State | Gate | Next / notes |
|---|---|---|---|---|---|
| WS-1 | <name> | `<path>` | 🟢 | AGENT-SAFE | <what remains, one line> |
| WS-2 | <name> | `<path>` | 🟡 WS-1 | mixed | <buildable half vs gated half> |
| WS-3 | <name> | `<path>` | 🔴 | OWNER-GATE | <the decision it waits on> |

Each row's note is written **for an agent with no memory of the last cycle**.
Say what shipped, what remains, and what was learned — not "in progress".

---

## 3. Single-owner registry

When two specs describe the same capability, one owns it and the rest are
mirrors. Duplicated ownership is how capability gets built twice and drifts.

| Capability | Owner | Mirrors (link-only) |
|---|---|---|
| <capability> | **WS-n** | <docs that must link here and add nothing> |

---

## 4. Decisions recorded

Cross-cutting calls, so they are made once rather than re-litigated per ticket.

- **D1 — <decision>.** <the resolution, and which workstream owns it.>

---

## 5. Owner-gate registry — agents must refuse these

Anything here stops at a human, whatever the agent's reasoning. Keep this list
**in sync with `.claude/plan-guard.config.json`**: prose is the explanation, the
config is the enforcement, and a gate that exists only here is not a gate.

- Deploying to any live environment
- Flipping a production feature flag: <list them by name>
- Credential creation, rotation, or exposure
- Force-push, history rewrite, remote branch deletion
- Destructive data operations (drop, truncate, reset)
- Publishing anything public (package, release, announcement)
- Spending money, or provisioning anything billable
- Creating external accounts or completing third-party reviews
- <project-specific gates>

---

## 6. Remediation backlog

Documentation defects that block dispatch — stale status headers, missing
acceptance criteria, broken anchors, duplicate ownership. Work these *before*
the workstreams they block; a NO-GO found here is far cheaper than one found
mid-build.

1. <spec> — <what is wrong, and which workstream it blocks>
