# DOE — Directive, Orchestration, Execution

**Every workspace this kit scaffolds runs on DOE: natural-language directives say
*what*, the LLM orchestrates and judges, and deterministic scripts do the work.** That
holds for an ordinary software project (where the skills are the team's recurring
workflows) and for a custom agent (where the skills *are* the product). This file is
the method behind [`SCAFFOLD.md`](SCAFFOLD.md); `PLAYBOOK.md` Principles 16–18
state it as rules.

Source: the [DOE Framework for Agentic AI](https://github.com/vjvarada/DOE-Framework-Agentic-AI)
(its README, `AGENTS.md`, the agent-creator generator, `agent_repo_compatibility.md`
v6.0, and its skill-observation log), merged with the harness disciplines of a large
production platform (Metorite) and this kit's own PLAYBOOK.

---

## 1. Why: errors compound, code does not

An LLM step is probabilistic. At 90% per step, five chained steps succeed 59% of the
time and ten steps 35%. And a business does not feel a 5% error rate as 5%: one wrong
invoice costs the customer's trust.

The fix is architectural, not a better prompt: **shorten the stretches where errors
can accumulate.** Put a deterministic node between the important steps. Reserve the
model for what only it can do — routing, interpretation, judgment, recovery — and let
code do everything mechanical, where it is 10,000× faster, essentially free, and the
same every time.

| Layer | Is | Lives in | Strength |
|---|---|---|---|
| **Directive** | An SOP in Markdown: goal, inputs, process, outputs, edge cases, definition of done | `.github/skills/<name>/SKILL.md`, and the rules in `AGENTS.md` | Readable and editable by anyone; flexible |
| **Orchestration** | The LLM: reads the directive, decides, calls tools, judges results, recovers | The agent host (Claude Code, Copilot, CommandCenter) steered by `AGENTS.md` | Handles ambiguity |
| **Execution** | Scripts that do one job each and fail loudly | `.github/skills/<name>/scripts/`, shared code, `harness.py`, hooks | Reliable, fast, testable |

The kit eats its own cooking: `scaffold.py`, `harness.py`, `anneal.py`, `new_skill.py`
and the hooks are the execution layer of *setting up and maintaining* a workspace;
`SCAFFOLD.md` and the SKILL.md files are its directives; you are the orchestrator.

## 2. The skill: one package, three layers

A **skill** is the unit of capability — DOE "v2", where the directive and its
execution live together:

```
.github/skills/<kebab-name>/
├── SKILL.md        directive: front matter (name, description, authority, cost_tier) + the SOP
├── scripts/        execution: one job per script, --help, JSON on stdout, loud failure
├── tests/          the behaviour test, written before the implementation
└── references/     optional long material, loaded only when needed
```

- **The description is the routing signal.** Every host matches on it, so it says
  what the skill does *and when to use it*, in the user's words.
- **The directive anatomy** — Goal · Inputs · Scripts · Process · Outputs · Definition
  of Done · Edge Cases · Environment · Learnings. The Definition of Done is checkable;
  the Learnings section is where self-annealing writes.
- **`authority`** (read / write / external) and **`cost_tier`** (0–3) are risk
  annotations (HARNESS-PRACTICES §1): external or tier 2+ means `--dry-run` first and
  the user's go-ahead.
- **Promotion path:** a one-off command → a script in the owning skill (or a shared
  utility once two skills need it) → a skill → a *meta-skill* whose Process chains
  others. Start low; promote on evidence.
- **Create with** `new_skill.py` (the `skill-authoring` skill). It writes the package
  and runs `harness.py sync`.

Three core skills ship in every workspace: **`self-annealing`** (the learning loop),
**`skill-authoring`** (how to add capability), and **`run-and-verify`** (how to run
*this* project and prove a change works — rendered with the project's own commands,
and the skill Claude Code's `/run` and `/verify` look for).

## 3. One harness, many hosts

Skills and rules are authored **once**; every host reads them through its own entry
point. Never fork a host-specific copy — the platform this came from had a skill
mirrored by hand into two host trees, and the copies drifted.

| Host | Entry point | Skills |
|---|---|---|
| Claude Code / Agent SDK | `CLAUDE.md` → `AGENTS.md` | `.claude/skills/<name>/SKILL.md` — **generated proxies** |
| GitHub Copilot (Chat, CLI, custom agent) | `.github/copilot-instructions.md`, `.github/agents/<slug>.agent.md` | `.github/skills/` natively |
| Cursor, Codex, other AGENTS.md-aware hosts | `AGENTS.md` | the skills table in `AGENTS.md` |
| Hosted runtime (CommandCenter) | `agents.py` → `.github/prompts/system.md` | runtime SKILL.md files appended to the prompt |

`python .harness/harness.py sync` writes the proxies and every skills table (between
`<!-- harness:skills:start/end -->` markers); `harness.py check` fails when they
drift, and CI runs the check.

## 4. Self-annealing: errors are lessons

```
something breaks → read the error → fix the script → test the fix
   → update the directive (SKILL.md Edge Cases / Learnings) → log the lesson
   → the system is now stronger
```

The kit turns the DOE loop into a backlog with a gate (`self-annealing` skill):

1. **Capture** the moment you learn it: `anneal.py log --title --lesson --target`.
   Lessons live in `docs/lessons.md`, tracked in git.
2. **Integrate** each lesson into its architectural home: a script fix ships with a
   test; a process rule goes to the SKILL.md; a placement rule to the nearest
   `AGENTS.md`; a capability description to the SKILL.md front matter (then `sync`).
   A capability is integrated only when *every* surface that routes or describes it
   agrees — code, skill, contracts, runtime wiring, tests.
3. **Gate** every session: `anneal.py gate` fails on OPEN lessons, a failing harness
   check or tests, or uncommitted work, and prints a suggested commit — for the
   user to approve, never auto-committed.

Safety rules from DOE: ask before a test that spends money; never touch credentials;
test before recording a fix as validated; keep a dated Learnings line so the next
reader knows why an instruction says what it says.

Lessons that would help **every** project go upstream into this kit
(`CONTRIBUTING.md`), and reach existing projects through `scaffold.py upgrade`.

## 5. Memory: what persists, and where

DOE treats memory as one of an agent's five components (planning, tools, memory,
reflection, orchestration). The kit keeps durable memory **in the repo, as files**
(PLAYBOOK Principle 9) — a fresh session, a worktree and a CI run can all read it:

| What | Where | Lifetime |
|---|---|---|
| Rules and architecture | `AGENTS.md` chain | Until the architecture changes |
| Technique (how to do X) | `SKILL.md` + scripts | Grows with every lesson |
| Learning backlog | `docs/lessons.md` | Until integrated |
| Actions the next session owes | `HANDOFF.md` (each with a Check) | Until the Check passes |
| Work state (what's next, who owns it) | Work plan or task board | The project |
| What an agent did on each run | `outputs/<run>/` via `run_store.py` (agents) | Permanent; searchable |

The DOE repo's SQLite memory (`execution/memory_db.py`: short- and long-term memory
with full-text and semantic search) is the upgrade for a hosted agent whose recall
needs outgrow `run_store.py search`. Port it as a shared utility plus a skill when a
measured need appears (PLAYBOOK Principle 6), not by default.

## 6. The agent archetype

An agent workspace is a DOE harness that does one job well:

```
AGENTS.md                      persona, DOE layers, operating principles, data flow
.github/prompts/system.md      runtime prompt (hosted runs)
.github/agents/<slug>.agent.md VS Code Copilot Chat agent
.github/skills/<capability>/   one per job the agent does
.tmp/scripts/                  shared execution code (run_store.py) — tracked; rest of .tmp/ is scratch
inputs/<project>/              what the user provides — read-only
agent-data/ + INDEX.md         permanent reference data — every asset listed
outputs/<run>/                 one record per run: run.json + step files + deliverables
```

Operating principles baked into its contract: check for an existing skill first;
**never fabricate** — report only what scripts and sources returned; small run first;
dry-run and ask before external or costly actions; every run leaves a record; past
runs are searched before work is repeated; self-anneal.

**Runtimes:**

- **`ide`** (default) — the agent is Claude Code or Copilot running in the workspace,
  interactively or headless (`claude -p "<task>"`). No runtime code to maintain.
- **`commandcenter`** — the MAF agent-repo contract (`agent_repo_compatibility.md`
  v6.0 in the DOE repo): `agents.py` with a synchronous `build_agents()`, one
  `async def` tool per skill script, `config.json` (bare slug name,
  `max_mutation_attempts: 1`), `instructions.md`, `tests/test_agents.py` as the CI
  gate. `harness.py check` validates the contract; developer-only skills
  (`audience: developer`) stay out of the runtime prompt.

To embed an agent in another application later, the Claude Agent SDK can load the same
project settings and skills; add it as a runtime when there is a concrete need.

## 7. Lessons the DOE framework paid for, now executable defaults

From the DOE repo's skill-observation log and agent builds — each became code or a
test here, not advice:

| Lesson | Became |
|---|---|
| A generator that does not emit everything its own spec requires makes every new workspace start non-compliant | `scaffold/tests`: every archetype is scaffolded and must pass its own `harness.py check` |
| A bare `*.tmp` in `.gitignore` matched the `.tmp/` directory and silently untracked all shared utilities | The template uses `?*.tmp` plus `!.tmp/scripts/**`; `harness.py check` runs `git check-ignore` over every harness file |
| A "successful" first push was missing files the project cannot run without | SCAFFOLD.md step 7: verify the staged manifest before the first commit |
| Extending an agent touched four layers; a missed doc surface left the agent unaware of its own capability | `sync` regenerates every skills table and proxy; the skill-authoring "every surface" checklist |
| First-run setup was fragmented across manual steps | One command each: `scaffold.py new`, `scaffold.py install`, `harness.py check` / `test` |
| Porting a standard from a sibling workspace needs adaptation, not copying | skill-authoring § Porting and vendoring |

## 8. Provenance

| Piece | From |
|---|---|
| Directive / orchestration / execution, the compound-error argument, directive anatomy, self-annealing, promotion path, meta-directives, inputs/outputs/agent-data layout, CommandCenter contract | DOE Framework repo |
| Canonical skills + generated proxies + drift test; `self_annealing` with a session-end gate | DOE agent builds (the CFD/FEA agent workspace) |
| Session-handoff, worktree/stale-rules and stop-children hooks; `/handoff`; `.claude/AGENTS.md`; review-reminder workflow; gitleaks PR-range scan; "Verified:" PR line; engineering rules (name the fence, verifier ≠ implementer, ship dark, clean up after yourself) | Metorite |
| DOX contracts, place-before-building, BLUF, Graphify, RTK, the planning/dispatch loop, plan-guard, Delivery | This kit (`PLAYBOOK.md`, `ORCHESTRATION.md`, `DELIVERY.md`) |

Not ported (yet), on purpose: Metorite's Simplified Technical English linter (a strong
writing discipline, but tuned to one codebase's vocabulary — a candidate opt-in pack),
its CI sharding and deploy workflows (project-specific), and third-party design skills
(vendor them per project with the adoption-note convention in `skill-authoring`).
