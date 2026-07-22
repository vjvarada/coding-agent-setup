# HARNESS-PRACTICES — harder practices for agent-developable codebases

`PLAYBOOK.md` covers the six core principles (query a symbol graph, compress tool
output, encode conventions once, verify before you trust, one shared seam,
measure the premise). This companion doc captures a second tier: practices from
harness engineering that make a codebase safe and cheap for coding agents to work
in over time. They are drawn from the
[awesome-harness-engineering](https://github.com/ai-boost/awesome-harness-engineering)
categories and proven on a real multi-agent platform.

**These are PRACTICES, not installers.** Unlike Graphify and RTK, most of these
are patterns you implement against your own stack — there is no universal binary
to drop in. Each entry says what it is, why it helps, and how to apply it.
Where a portable artifact exists, `SETUP.md` / `templates/` ship it and this doc
points there.

A note on honesty: some of the most valuable harness capabilities (a risk-aware
permission handler, durable run-trace tables, per-run credential scoping,
container isolation) are inherently coupled to your agent framework, database,
and gateway. They are described here as **practices to build**, not templates to
copy — pretending they drop into an arbitrary codebase unchanged would be a lie.

---

## 1. Tool risk annotations  *(portable convention)*

**What:** tag every tool the agent can call with a risk class —
`read_only`, `idempotent`, `destructive`, `open_world` (touches the outside
world / non-deterministic). Render the classes into the system prompt so the
agent knows what's safe to call freely, and consult them in whatever gates tool
execution. This mirrors the MCP spec's `readOnlyHint` / `destructiveHint` /
`idempotentHint` / `openWorldHint`.

**Why:** turns "the model can call anything and the harness treats it all the
same" into a system where read-only tools flow freely and destructive/outward
ones are gated. It is the precondition for a sane permission policy (§2).

**How:** keep a registry mapping tool name → risk class; emit a short
"tool risk" block into the prompt; have the permission layer branch on it. Start
by annotating the tools that write, delete, send, deploy, or spend money — those
are the ones that matter.

---

## 2. Fail-closed permissions  *(practice — build against your stack)*

**What:** replace blanket auto-approve with a policy: read-only tools approve
automatically; a **dangerous-shell denylist** (`rm -rf`, fork bombs, `curl … | sh`,
force-push to a protected branch) **fails closed**; writes outside the workspace
are denied; unknown actions approve-and-log. Support an `enforce | audit |
approve_all` mode so you can deploy in `audit` first and watch what *would* have
been blocked before enforcing.

**Why:** OWASP LLM06 (Excessive Agency). An agent that can silently run any shell
command is one bad completion away from damage. Irreversible or outward-facing
actions should return *not-confirmed* when no human is in the loop; only
explicitly-reversible actions may auto-approve non-interactively.

**How:** this is a handler you write for your runtime — there is no portable
binary. The RTK hook in `templates/claude/hooks/rtk-bash.sh` shows the *shape* of
a fail-closed allowlist (it rewrites only benign command classes and passes
everything else through); a real permission policy generalizes that idea to all
tool calls, not just Bash.

> The kit's own RTK hook embodies this: it auto-approves only an allowlist of
> benign read/test/lint/git commands, and that allowlist IS the security
> boundary. Surface such tradeoffs to the user — never bury an auto-approve.

---

## 3. Golden trajectory evals  *(practice + skeleton)*

**What:** offline tests that assert on **run behavior across components** — a tool
call produces an event, the event reaches the user, the user's input produces the
right next tool call — not just unit-level helper assertions. Make them
CI-blocking once green. Use fixtures (stable UUIDs, a `fixtures/*.json`) so they
run with no database or network.

**Why:** the expensive bug class — a confirmation gate that silently denies, a
background write that fails on every call, an async bug that breaks
human-in-the-loop — *passes unit tests* and only shows up in the live
trajectory. A green unit suite is necessary, not sufficient (this is
`PLAYBOOK.md` Principle 4, enforced in CI). Ship a golden trajectory eval
alongside any change to harness behavior.

**How:** one golden case per behavior; assert the sequence, not the internals;
keep them offline and deterministic. Start with your riskiest flows
(human-in-the-loop, stream reconnect, permission decisions, retry-after-tool-
failure).

---

## 4. Prompt-cache discipline  *(portable rules)*

**What:** keep the system-prompt prefix **byte-stable** so the provider's prompt
cache hits. Concretely:
- Split the prompt into a **stable** block (instructions, tool definitions) and a
  **dynamic** block (per-turn memory, timestamps) with an explicit seam.
- Never inject volatile content (timestamps, run IDs, per-turn memory) *before*
  the stable block — one volatile byte busts the whole cache.
- Order tool arrays deterministically.
- Provider specifics: Anthropic wants explicit `cache_control: ephemeral` on the
  stable system block and the last tool schema; OpenAI keys off `prompt_cache_key`
  and caches automatically ≥1024 tokens; some providers (e.g. DeepSeek) do
  neither — strip any cache markers so they don't leak into the prompt.

**Why:** ~90% cost reduction on the cached prefix and materially faster
time-to-first-token, on every single turn. It is the highest-ROI token practice
after not-rediscovering-things.

**How:** the *rules* above are portable; the transform that applies them is code
you write at your LLM call site. Pin per-session memory (fetch once, cache with a
TTL matching the provider's) so the memory block is stable across turns instead
of changing every turn and busting the cache.

---

## 5. Auto-compaction thresholds  *(portable rules)*

**What:** compact the conversation automatically at ~80% of the model's **real**
context window (not a guessed default), with hysteresis, **between turns only**,
sending forward only `[summary + recent turns]`.

**Why:** prevents context-overflow failures without a manual "please compact"
step, and does it at a safe point rather than mid-tool-call. The subtlety that
bites: an agent host that doesn't know a BYOK model's *true* window uses a tiny
default and trips "context length exceeded" on short conversations — always
resolve the real window first.

**How:** rules are portable; the compaction routine is host-specific. Token-count
against the resolved model, not a heuristic.

---

## 6. Tool naming and tool-surface size  *(portable practice)*

**What:** two cheap, high-leverage habits:
- **Action-verb tool names.** `run_diagnostics` gets called; `get_errors` reads
  as "list existing errors" and the model won't invoke it to *run* a check. Name
  tools for the action they perform.
- **Keep the per-agent tool surface small.** Function-calling accuracy degrades
  as the tool count grows (Berkeley Function-Calling Leaderboard); scope each
  agent to the tools it actually needs rather than exposing the whole catalog.

**Why:** naming determines whether a tool is used at all; surface size determines
whether the right one is selected. Both are free to fix and directly change
behavior.

---

## 7. Complexity / correctness CI gates  *(portable pattern)*

**What:** add two CI gates with a **grandfather-and-ratchet** threshold — set the
bar exactly where current code passes, so only *new* debt fails:
- A complexity ceiling (e.g. a cyclomatic-complexity linter).
- A correctness lint pass (e.g. undefined-name / bad-comparison rules) that
  catches real latent bugs, not just style.

**Why:** keeps a large codebase agent-developable — an agent can't safely work in
a repo whose complexity grows unchecked, and correctness lints catch the bugs
agents introduce. On one platform the correctness gate surfaced several genuine
latent bugs on the day it was added.

**Hazard to document:** **never bulk-autofix** (`ruff --fix` and friends) a repo
with re-export shims or import-for-side-effect modules — the autofixer deletes
"unused" imports that are load-bearing. Ratchet, don't sweep.

---

## 8. Observability: correlated run traces  *(practice — build against your stack)*

**What:** bind a run-context to structured (JSON) logs and persist a durable
`agent_run` trace record that outlives any short-lived cache (Redis TTL, etc.),
exposed through a small debug API so you can answer "what happened in run X"
without SSH. Gate any OTEL/OTLP export on the endpoint being configured, with a
kill-switch — telemetry that exports nowhere should never crash a run.

**Why:** self-serve debugging of "error X with agent Y" is the difference between
a five-minute fix and an afternoon. Also record per-call token + cache metrics
(`cache_read_input_tokens` etc.) — you cannot optimize caching (§4) without
measuring the hit rate.

**How:** inherently coupled to your logging, DB, and gateway. Build it; don't
expect a template.

---

## Applying this doc

Not everything here applies to every codebase. Triage by what bites first:

- **Any repo agents will edit a lot:** §4 prompt-cache discipline, §6 tool
  naming, §7 CI gates. Cheap, portable, immediate.
- **Repos where agents take real actions** (deploy, send, spend): §1 annotations
  + §2 fail-closed permissions, before anything else.
- **Harness/framework codebases:** §3 trajectory evals and §8 observability —
  these are what keep the harness itself from silently regressing.

As with the rest of the kit (`CONTRIBUTING.md`): a practice earns its place by
being proven on a real change and stated portably. When one of the
"build-against-your-stack" practices here gets generalized into an actual
installable template, promote it to `SETUP.md` + `templates/`.
