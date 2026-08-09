# PLAYBOOK — developing complex codebases efficiently with coding agents

This is the *why* behind `SETUP.md`. It captures the methodology for working on
large, unfamiliar, or multi-runtime codebases without burning tokens or shipping
plausible-but-wrong changes. It is tool-agnostic; the specific tools in `SETUP.md`
(Graphify, RTK) are instances of these principles.

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
question in **one** call, returning the source location PLUS callers PLUS blast
radius — and it resolves cross-file call/import/inheritance edges (including
inferred indirect connections) that grep structurally cannot follow.

**The discipline that matters:** install the graph AND actually use it *first*.
The failure mode is installing Graphify and then grepping out of habit — you pay
for the index and capture none of the savings. Before reading a file to
understand or change code, query the graph. Read files only to confirm or edit
what the graph surfaced. (Graphify enforces this structurally: its installer
adds a query-first hook that nudges — or in `--strict` mode blocks — raw
source reads until the graph has been consulted.)

**Scope the index.** A symbol graph polluted with generated SQL, migrations,
minified bundles, and vendored code returns noise. Exclude those explicitly
(`.graphifyignore`). *Lesson:* an index once caught a minified worker bundle
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

This kit ships that pattern as **DOX** — `templates/shared/AGENTS.md` and
`SETUP.md §5.2`. DOX adds two disciplines on top of "write it down": *read the
whole contract chain before editing*, and *place new work in its architectural
home before building* (Principle 7). The contract is not just a place to record
conventions — it is the map that makes correct placement decidable.

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

## Principle 7 — Place work in its architectural home *before* building (attacks: *wrong-layer drift*)

The cheapest architectural mistake to prevent and the most expensive to unwind is
a feature built in the wrong place: a shared capability wedged into a leaf module,
a deployed-service concern living in a library, a tool dropped into whatever file
was already open. It compiles, it passes tests, and it quietly erodes the
boundaries that make the codebase legible — the exact property Principle 1 (symbol
graph) and Principle 3 (encode conventions) depend on. An agent reasons well only
about a structure that still means what it says.

**The discipline:** before writing a new feature, module, tool, or endpoint,
decide where it belongs and confirm that home against the contract — do not default
to the current directory. Name the *kind* of thing you're adding, find the scope
that owns that kind, and reuse that scope's existing seam before adding a new one
(Principle 5's "find the seam," applied at creation time). If nothing fits, the
answer is a new scope with its own contract, not an orphan file. A feature in the
wrong layer is a defect even if it works — correct the placement first, then build.

**What makes it enforceable:** a placement rule only works if the map of "what
goes where" is written down and current. That is what DOX (Principle 3) provides —
each directory's `AGENTS.md` states what it owns, and the root's child index is the
routing table. Ship the rule *inside* the contract (`templates/shared/AGENTS.md`
carries a "Place Before Building" section) so every agent that reads the chain
before editing also reads where new work is supposed to land. Placement becomes a
step in the loop, not a thing a reviewer catches after the fact.

*Lesson:* the archetype platform kept an `apps/` split — deployed services vs
dynamically-loaded agents vs importable skills — that was load-bearing, not
cosmetic: an agent placed in the wrong group silently failed to load, and a
capability duplicated one folder over from its owner drifted from the original.
Writing the split into the contract, with a rule to consult it *before* creating
anything, turned "reviewer catches it in PR" into "the author never misplaces it."

---

## Principle 8 — Autonomy is capped by verifiability, not by model quality (attacks: *plans agents can't execute*)

The moment you point more than one agent at a project, the bottleneck stops being
how well they code and becomes whether the plan can be *executed without asking
anyone a question*. A ticket whose done-when is "works well", "looks right", or
"owner call" cannot be completed autonomously — no signal exists that would let
any agent, or any reviewer of its output, conclude it is finished. No model
improvement changes that; it is a property of the plan.

So the highest-leverage work in a multi-agent setup is not agent design. It is
**converting acceptance criteria into commands.** Every item you make checkable
converts directly into autonomous throughput; everything else is plumbing around
that one number.

The practical form is a contract each spec must satisfy before any agent may
build from it — dated status verified against code, explicit non-goals,
machine-checkable acceptance per item, file paths re-verified at dispatch,
exact verification commands, a single owning document, and a gate label per item.
An auditor agent tests the contract and refuses work that fails it.

*Lesson:* the first honest audit of a large, carefully-written spec corpus found
most workstreams only *partly* dispatchable — a buildable half plus a flag flip,
a spend, or a product decision. "Cleared, but narrowed to this half" became the
auditor's most common verdict, and splitting those rows in two was worth more
than any prompt tuning. The audit also kept finding the opposite defect: specs
claiming work was unbuilt when it had shipped, which sends an implementer to
build it a second time. Verify status against code, not against the document.

---

## Principle 9 — Durable state lives in the repo, never in an agent (attacks: *fragile long runs*)

A multi-agent run that holds its state in a conversation is one compaction, one
crash, or one context limit away from losing everything. Put the queue in a file:
a work plan that owns ordering, ownership, and dispatchability, with each spec's
status header as the completion record.

Then every cycle's last act is to **write back what shipped and what remains —
for a reader with no memory of that cycle.** This is what makes the loop
resumable rather than one long fragile session, and what makes a bad run
debuggable: the evidence is in the diff and the board, not in a transcript nobody
kept.

Two corollaries worth enforcing:

- **An agent that "remembers" instead of recording has failed**, even when its
  output was correct — the next cycle is a fresh context that can see only the repo.
- **The supervisor must not read what it delegates.** An orchestrator that reads
  specs and source itself exhausts its context in two cycles. It dispatches, keeps
  the verdicts, and discards the rest.

*Lesson:* the most easily-missed version of this is configuration. A harness
directory that is gitignored reaches no fresh clone, no worktree, and no headless
run — the loop silently degrades to a single unguarded agent, with no error to
notice. Check what is actually committed before running anything unattended.

---

## Principle 10 — Gate what agents must not do in code, not in prose (attacks: *instruction drift*)

Instructions degrade over a long unattended run; a hook does not. Anything that
is outward-facing, hard to reverse, credential-bearing, or costly — deploy,
production flag flips, force-push, publishing, destructive data operations,
spending — belongs in a `PreToolUse` guard that blocks it deterministically,
declared as data so it is reviewable and testable.

State the same gates in the agent prompts *as well*. The redundancy is
deliberate: the prompt makes the agent refuse coherently and explain what the
human needs to do; the hook makes the refusal real when the prompt is forgotten.

Two rules keep it honest:

- **A gate that exists in the plan but not in the guard config is not a gate.**
  Add both in the same change.
- **Test every gate.** An untested regex is a guess, and both failure directions
  are expensive: over-matching blocks ordinary work until someone disables the
  guard entirely; under-matching means the boundary you believe in does not exist.

The corollary for the loop's shape: stop it at **"PR opened"**. Every other
safeguard checks *correctness*, and a confident wrong change looks correct from
the inside. The human at the end is not re-checking the tests — they are the only
reader asking whether this should ship at all.

*Lesson:* a guard written this way blocked its own author's *test command* on
first run, because the test string contained a force-push pattern. Crude, and
exactly right: it failed closed on an ambiguous input rather than reasoning its
way to an exception.

The full methodology — the two loops, the seven roles, where wireframes and evals
fit, what stays human, and the cost model — is in [`ORCHESTRATION.md`](ORCHESTRATION.md).

---

## Principle 11 — Report bottom-line-up-front (attacks: *buried conclusions*)

Agent output is read by two audiences with the same bias: humans skim, and
models weight early context most. Both are best served by **BLUF** (Bottom Line
Up Front) — the conclusion, recommendation, or blocker in the first sentence;
context and evidence after, never before.

Concretely, in every response, status report, review finding, PR description,
and handover note:

- **Answer first.** The first sentence is what the reader would ask for as the
  TLDR: "Deployed and verified", "Blocked: the migration lock is held",
  "Recommendation: reuse the existing seam".
- **Cut padding.** No pleasantries, no restating the question, no "I'll now…"
  narration. What survives the cut is written in full sentences — brevity comes
  from selecting what to say, not compressing how it's said.
- **Structure for skimming.** A reader who stops after the first paragraph
  still leaves with the correct takeaway.

The same shape pays twice in *durable* prose. Specs, plan rows, and AGENTS.md
contracts written answer-first are cheaper for the next agent to consume:
the load-bearing fact lands inside the first lines the model reads, instead of
after three paragraphs of build-up it may truncate or under-weight.

The kit encodes this in the DOX root template (`templates/shared/AGENTS.md`
§Communication), so every repo it installs into gets the rule as part of the
always-loaded contract.

---

## Quick reference — the loop

1. **Orient** — read the project instructions and the DOX contract chain for the
   area you're touching; query the symbol graph (one call, not a grep sweep).
2. **Place** *(new work only)* — before creating a feature/module/tool, find its
   architectural home in the DOX child index; reuse the owning seam, don't default
   to the file you have open.
3. **Change** — edit with the blast radius in view (the graph told you the callers).
4. **Run** — tests/lint through the output compressor (`rtk pytest`, `rtk ruff`),
   never through the package runner (`uv run rtk` is broken).
5. **Review** — adversarial pass; refute findings, keep survivors.
6. **Verify** — drive the real flow, observe behavior, not just the test result.
7. **Record** — if you learned something that makes the next change faster, push
   it back to this kit (see `CONTRIBUTING.md`). Update the owning `AGENTS.md` if the
   change moved a boundary (DOX "Update After Editing"). If the work came off a
   plan, write back what shipped and what remains, for a reader with no memory of
   this session (Principle 9).

Steps 1–7 are one agent on one change. When the work is a *project* rather than a
change — a queue of features, planned and dispatched over days — that loop becomes
the inner half of a larger one: plan → wireframe → spec → audit, then dispatch →
build → verify → review → PR, with the plan itself living in the repo. See
[`ORCHESTRATION.md`](ORCHESTRATION.md).

---

## Going further

These eleven principles are the core. For the harder practices that keep a codebase
safe and cheap for agents *over time* — tool risk annotations, fail-closed
permissions, golden trajectory evals, prompt-cache discipline, auto-compaction
thresholds, tool naming, and complexity/correctness CI gates — see
[`HARNESS-PRACTICES.md`](HARNESS-PRACTICES.md). Those are drawn from the
[awesome-harness-engineering](https://github.com/ai-boost/awesome-harness-engineering)
body of work and are practices to build against your own stack, not installers.
