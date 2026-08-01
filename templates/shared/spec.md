# <Feature / workstream name>

**Status:** <not started | in progress | shipped> · **Verified against code:** <YYYY-MM-DD>
**Owner:** WS-<n> · **Board:** `<path to work plan>`

> **Fill in every `<...>` and delete this quote block.**
> This spec is what an autonomous implementer gets *instead of* a conversation.
> It must answer every question a stranger would ask, because there is nobody to
> ask. `spec-auditor` tests it against the seven-point contract before any agent
> is allowed to build from it.
>
> The status line above must describe what is true **today**, checked against the
> code — not what this document hopes for. A spec claiming "not built" for
> shipped work sends an implementer to build it twice.

---

## 1. Scope

<What this workstream delivers, in a few sentences. The outcome, not the tasks.>

### Non-goals

- <What this deliberately does not do — and where that work lives instead.>

Non-goals are load-bearing. They are what stops an unattended implementer from
widening a reviewable diff into an unreviewable one.

---

## 2. Current state

<What exists in the code right now, verified on the date in the header. Name the
files. If part of this is already built, say exactly which part — this is the
single most valuable section for anyone dispatching against this spec.>

---

## 3. Design

<How it works. Data model, the seam it extends, the flow. Name the
architectural home for each new piece and the `AGENTS.md` scope that owns it —
placement decided here is placement the implementer cannot get wrong.>

**Reuses:** <the existing seam this extends, rather than a parallel one.>

---

## 4. UI surface

<Delete this section if there is none.>

**Wireframe:** `docs/wireframes/<feature>.html` — the authoritative layout.
Do not restate the layout in prose here; prose layouts get reinterpreted
differently by every agent that reads them.

States that must be built (all of them, not just the populated one):
empty · loading · populated · error · <permission-denied, if gateable>

---

## 5. Items and acceptance

Each item is independently dispatchable. **Acceptance must be checkable by a
command or an observable state** — this is the point that decides whether the
item can ever be built autonomously.

### <n>.1 — <item name>  ·  **AGENT-SAFE**

<One paragraph: what changes.>

**Done when:**
- `<exact command>` passes
- <observable state: an endpoint returns X; the DB row has Y; the wireframe's
  empty state renders>

### <n>.2 — <item name>  ·  **OWNER-GATE**

<What it is, and *why* it is gated: reaches production / spends money / touches
credentials / is publicly visible / needs a product decision.>

**Owner must:** <the exact action a human has to take.>

---

## 6. Verification

The exact commands that prove this workstream is done. Run them yourself before
writing them here — a command that does not exist fails the audit.

```bash
<test command scoped to this feature>
<the project's full test suite>
<lint / typecheck>
```

<Anything CI will not cover — a language the pipeline skips, a package it does
not build, a suite that runs only on the default branch. Name it, so the
verifier covers it locally.>

---

## 7. Open decisions

| # | Question | Blocks | Owner |
|---|---|---|---|
| 1 | <what genuinely needs a human call> | <item> | <who> |

An open decision is a legitimate output. What is *not* legitimate is an
implementer inventing the answer mid-build — list it here so it gets settled
once, deliberately.

---

## 8. Changelog

- **<YYYY-MM-DD>** — <what shipped, and the PR. Updated in the same PR (R4).>
