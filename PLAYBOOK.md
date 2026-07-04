# PLAYBOOK — developing complex codebases efficiently with coding agents

This is the *why* behind `SETUP.md`. It captures the methodology for working on
large, unfamiliar, or multi-runtime codebases without burning tokens or shipping
plausible-but-wrong changes. It is tool-agnostic; the specific tools in `SETUP.md`
(CodeGraph, RTK) are instances of these principles.

**The archetype these lessons came from:** a large multi-agent platform (a
web/API backend + vector-store-backed memory + an event bus + a web frontend)
that runs two different agent runtimes side by side. It is the kind of codebase
where naive exploration is ruinously expensive and where the same capability is
easy to build twice and let drift — which is what made these lessons concrete.
The lessons generalize to any complex codebase; the "*lesson:*" callouts below
describe the situation abstractly rather than any one product's internals.

---

## The core problem: tokens are spent on *rediscovery*, not *thinking*

On a large codebase, most tokens an agent burns are not spent reasoning about the
change — they are spent re-deriving things that are already knowable:

- **Where code lives** (grep → read → "not here" → grep again).
- **What calls what** (reading a function, then hunting its callers by hand).
- **What noisy commands printed** (200 lines of passing-test output to find 1 failure).
- **The repo's conventions** (rediscovering the stack, the test command, the layout every session).

Every principle below attacks one of these four rediscovery costs.

---

## Principle 1 — Query a symbol graph instead of grepping (attacks: *where / what-calls-what*)

A grep+read exploration of "how does X work" is dozens of tool calls and reads
whole files to find the relevant lines. A pre-built symbol graph answers the same
question in **one** call, returning the verbatim source PLUS callers PLUS blast
radius — and it follows dynamic-dispatch edges (callbacks, event handlers, JSX
children, framework re-renders) that grep structurally cannot.

**The discipline that matters:** install the graph AND actually use it *first*.
The failure mode is installing CodeGraph and then grepping out of habit — you pay
for the index and capture none of the savings. Before reading a file to
understand or change code, query the graph. Read files only to confirm or edit
what the graph surfaced.

**Scope the index.** A symbol graph polluted with generated SQL, migrations,
minified bundles, and vendored code returns noise. Exclude those explicitly
(`codegraph.json`). *Lesson:* an index once caught a minified worker bundle
because the exclude list had `*.min.js` but not `*.min.mjs` — one missing glob
poisoned symbol search for common words. Be exhaustive with minified/generated
globs (`*.min.js`, `*.min.mjs`, `*.generated.*`, and friends).

**Delegate the search, keep the conclusion.** When a lookup is broad, hand it to
a sub-agent/search tool and keep only the answer — do not pull dozens of file
dumps into your own context. (And do not delegate a lookup the symbol graph
already answers in one call; that repeats work.)

---

## Principle 2 — Compress tool *output*, not tool *instructions* (attacks: *noisy command output*)

Shell commands flood context with output that is 90% noise: progress bars,
passing-test detail, full diffs when you needed the changed lines, `ls` of a
thousand files. Filter that output *before* it lands in context. RTK does this
per-command (dedup repeated lines, failures-only tests, tree-ified listings) with
a tee-to-disk safety net so nothing is truly lost.

**Know exactly what to compress and what to leave alone** — this is the whole
game, and getting it wrong is worse than not compressing:

- ✅ Compress: test runners, linters/type-checkers, `git diff`/`status`/`log`,
  `docker`, `kubectl`, `psql`, directory listings. Deterministic, high-noise,
  meaning-preserving to filter.
- ❌ Do NOT compress **file reads** — a symbol-aware Read/graph gives better
  context than heuristic filtering. (*Lesson:* the stock RTK hook rewrote
  `cat` → `rtk read`; block it, because a symbol graph / native Read win.)
- ❌ Do NOT compress **instruction / skill / prompt text** with a lossy
  (LLMLingua-style "semantic") compressor. That text must be followed verbatim;
  dropping "low-information" tokens changes behavior on the exact files where
  precision matters, and it breaks prompt caching. (*Lesson:* when measured, the
  always-injected instructions on one platform were only a few thousand tokens
  and cache-friendly as-is; compressing them was all downside — see Principle 6.)
- ❌ Do NOT wrap the package-manager runner. `uv run rtk pytest` is broken; run
  `rtk pytest` directly. Same class of bug exists for any `<runner> run <x>` shape.

**Match the mechanism to the host.** Transparent command rewriting (a hook that
silently swaps `git status` → `rtk git status`) works in some agent hosts and is
*ignored* by others (VS Code Copilot Chat is the notable case). Where it is
ignored, fall back to an instruction that tells the agent to type `rtk` itself.
Verify which one your host honors rather than assuming.

**The auto-approve tradeoff is real.** A rewrite hook that takes effect must tell
the host to allow the rewritten command, which bypasses the normal per-command
prompt. Scope it with a strict allowlist (only benign read/test/lint/git
commands) and surface the tradeoff to the user — do not bury it.

---

## Principle 3 — Encode conventions once (attacks: *rediscovering the repo*)

An agent that relearns the stack, the build command, the directory layout, and
the "read the architecture doc first" rule every session pays that cost every
session. Write it down once where the host auto-loads it:

- Claude Code: `CLAUDE.md`. VS Code Copilot: `.github/copilot-instructions.md`
  (+ glob-scoped `*.instructions.md` with `applyTo` frontmatter).
- Keep it to non-obvious facts the agent cannot cheaply derive: the package
  manager, the one-line test command, where the design system / architecture
  docs live, the "query the symbol graph before reading" rule, the RTK rule.
- Point at deeper docs rather than inlining them (a "read `AGENTS.md` first"
  chain), so the always-injected prefix stays small and cache-friendly.

*A pattern that works well:* a root `AGENTS.md` (or `CLAUDE.md`) with global
constraints that points to per-directory `AGENTS.md` files, read on demand as the
agent descends into a subsystem. The always-loaded top stays tiny; depth is
pulled only when the agent is actually working in that area.

---

## Principle 4 — Verify before you trust (attacks: *the expensive bug class*)

The costliest bug on a large codebase is the change that looks right, passes a
shallow check, and is wrong. Two habits prevent it:

**Adversarial review.** Review the diff for correctness AND for
reuse/simplification/efficiency. On anything non-trivial, run a second pass whose
job is to *refute* each finding, not confirm it — keep only what survives.
Independent skeptics catch plausible-but-wrong findings that a single confirming
pass waves through. Scale the effort to the change: a few finders for a small
diff; a broader pool with majority-vote verification for a risky one.

**End-to-end verification.** A green test suite is necessary, not sufficient.
Drive the actual affected flow and observe the behavior — the real request, the
real UI path, the real job. Skip this only for pure test/doc/config changes with
no runtime surface.

*Lesson:* on one platform, several of the most damaging bugs — a
confirmation gate that silently denied instead of asking; a background
write-back that failed on every call due to a misrouted request; an async
context bug that broke human-in-the-loop prompts — all *passed unit tests* and
were only caught by exercising the live path. Trajectory-level evals that assert
on real run behavior — not just unit assertions — became the contract.

---

## Principle 5 — Serve every runtime from one shared seam (attacks: *drift & double-maintenance*)

When a codebase runs multiple agent runtimes (or multiple hosts), the trap is
building a capability twice and letting the copies drift. Find the shared choke
point and hook it once.

*Lesson:* a platform running two agent runtimes that *looked* divergent turned
out to converge on two shared seams — a single function that built every
request's input, and one call site where all traffic reached the LLM. Context
assembly and prompt caching were implemented once at those seams and served both
runtimes for free. The inverse lesson, from the same codebase: a skill was
mirrored by hand into two per-host directory trees (one per agent host) and
*drifted* — a file existed in one and not the other. Before duplicating, look for
the seam; if you must duplicate, guard the copies with a drift check.

---

## Principle 6 — Measure the premise before optimizing it

Before adding machinery to "reduce tokens," measure where the tokens actually go.
The intuition is often wrong.

*Lesson:* a request to add semantic compression to "reduce the token cost of
skills and tools" dissolved on measurement — skills loaded per-host (one copy
each, not doubled at runtime), the always-injected text was small and
cache-friendly, and the big skill files loaded only on demand. The real issues
that surfaced were *duplication/drift* and *one oversized monolith*, neither of
which compression fixes. The few minutes spent measuring saved building the wrong
system. Always `wc`/token-count the suspected sink first; act on the number.

---

## Quick reference — the loop

1. **Orient** — read the project instructions; query the symbol graph for the
   area you're touching (one call, not a grep sweep).
2. **Change** — edit with the blast radius in view (the graph told you the callers).
3. **Run** — tests/lint through the output compressor (`rtk pytest`, `rtk ruff`),
   never through the package runner (`uv run rtk` is broken).
4. **Review** — adversarial pass; refute findings, keep survivors.
5. **Verify** — drive the real flow, observe behavior, not just the test result.
6. **Record** — if you learned something that makes the next change faster, push
   it back to this kit (see `CONTRIBUTING.md`).

---

## Going further

These six principles are the core. For the harder practices that keep a codebase
safe and cheap for agents *over time* — tool risk annotations, fail-closed
permissions, golden trajectory evals, prompt-cache discipline, auto-compaction
thresholds, tool naming, and complexity/correctness CI gates — see
[`HARNESS-PRACTICES.md`](HARNESS-PRACTICES.md). Those are drawn from the
[awesome-harness-engineering](https://github.com/ai-boost/awesome-harness-engineering)
body of work and are practices to build against your own stack, not installers.
