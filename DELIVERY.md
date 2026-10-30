# DELIVERY — from "slice built" to "in production"

**Bottom line: run the change on your own machine before you push, test the merge you will land, spend review by risk, and make staging a smoke test.** This is capability #6. It covers everything that happens after an agent finishes a slice. [`ORCHESTRATION.md`](ORCHESTRATION.md) covers how the slice gets built.

The practices come from a multi-tenant SaaS product built by one owner with many parallel Claude Code agents. That product is the worked example here and the source of every measured number. The practices are generic. Adapt the names, keep the shape.

Evidence labels used below: **[Measured]** is a controlled study or telemetry. **[Repo]** is a fact from the source product's own records. **[Vendor]** is a company's claim about its own product. **[Inference]** is reasoning from the sources. The evidence base is a research report, "Run locally first, merge small, review less" (the source product, 2026-10-30).

---

## 1. Why this exists, and when to adopt it

**The bottleneck is delivery and integration, not coding.** The source product's own engineering guide says: "Our failures are delivery and integration failures, not coding failures." **[Repo]** The source product merged about 31 pull requests a day in October 2026. Each red CI run cost about 30 minutes. Of 70 red runs in one week, 29 came from process fences and 9 from real bugs in the PR.

So the system attacks four costs:

| Cost | Answer | Section |
|---|---|---|
| A bug found after the push costs a CI round and a re-read | Run the app locally first | 2 |
| Review spent evenly on every slice | Spend review by risk tier | 3, 4, 5 |
| A green PR that breaks `main` after the merge | Test the merge with today's `main` | 7 |
| A merge that reaches customers before anyone looked | Staging, then a daily release train | 8 |

**Adopt it when:**

- You merge more than a few agent PRs a day.
- Your app has a database, or a deploy path an agent can break.
- You run several agent sessions in parallel.

**Skip most of it when** you have a small library, one agent at a time, and no deployed environment. Install only the worktree script and the local run.

Everything here is independent. Section 15 gives the order that works.

---

## 2. The local-first inner loop

**Rule: the agent runs the changed behaviour on this machine, in its own worktree, before it reports done.** The verifier runs it again. Staging is then a smoke check, not the first place a bug shows.

The tool is `dev_up.sh`: one command per worktree that starts the whole app. See [`templates/scripts/dev_up.sh`](templates/scripts/dev_up.sh) and its config, [`templates/scripts/dev_up.config.example`](templates/scripts/dev_up.config.example).

```bash
bash scripts/dev_up.sh           # start. The first run builds and seeds.
bash scripts/dev_up.sh --check   # health, then the tenant-isolation check
bash scripts/dev_up.sh --stop    # stop the app. --down also removes the data.
```

### What the local stack must give you

| Property | Why it matters |
|---|---|
| **Its own database and cache per worktree** | Two sessions never share state. Ports differ per worktree. |
| **The migration ladder runs inside the container** | Speed. See the numbers below. |
| **The app connects as the production database role** | A superuser skips row-level security and hides tenancy bugs. Use the role production uses, with no bypass. |
| **Two seeded fictional tenants** | One tenant cannot show a cross-tenant leak. Two can. The check asks whether tenant A sees tenant B. |
| **Outbound switches held off** | The stack must never mail a person or call a third party. |

### Keeping outbound off

Four rules, in `dev_up.sh`:

1. **Clean environment.** Each process starts with an empty environment. A key in your shell never reaches the stack.
2. **Refuse a `.env`.** The script stops if the checkout has a `.env` file, because many frameworks read it by themselves.
3. **A production-flag snapshot.** Production's feature switches come across, so the local app behaves like production.
4. **A held pattern.** Any switch whose name matches a pattern (mail, chat channels, sync, send, push, webhook, scheduler) stays off. Keep one copy of the pattern and a test that fails if two copies differ.

### Measured

**[Repo]** The source product, Windows PC, 2026-10-30:

| Step | Time |
|---|---|
| Migration runner from Git Bash, 310 files | 515 s |
| Same runner, nothing to apply | 89 s |
| Same ladder inside the Linux container | 38 s |
| Same, nothing to apply | 6 s |
| First start of the whole stack | about 100 s |
| Restart | about 40 s |

Process start-up under Git Bash is the cost on Windows. A container removes it.

### What the PC cannot test

The local stack holds no keys. Real OAuth sign-in, real provider webhooks, mail sync, model calls and the deploy path do not work on it. Test those on staging (section 8).

**[Repo]** Two traps from the source product's Windows box. Docker advises keeping bind mounts on the WSL2 filesystem. One shared WSL2 VM hung every session once, when a local CI run had no memory cap. Cap containers and check free memory before you start.

**Never point your test suite at the dev database.** Suites reset what they touch. `dev_up.sh --env` prints `DEV_UP_*` names and never a `DATABASE_URL` for this reason.

---

## 3. Risk tiers — spend review by risk

**Rule: the tier sets the review. The verifier is never skipped at any tier.** If you are not sure, take the higher tier.

| Tier | What it covers | What it gets |
|---|---|---|
| **HIGH** | Tenancy, row-level security, auth, identity, a migration, money, credits, secrets, member or role writes, the deploy path | Spec audit, verifier, then an adversarial reviewer. Two repair rounds at most. Full loop in both build and harden modes |
| **STANDARD** | Other product code | Verifier only while the feature is in build. One repair round. One adversarial review on the whole feature at the hardening pass |
| **LOW** | Tooling, tests, docs, style with no data path | Verifier only. No reviewer. One repair round |

**Why it works.** **[Measured]** Faros telemetry on 10,000+ developers found that high-AI teams merged 98% more PRs, review time rose 91% and PR size rose 154%. Review is the bottleneck. Uniform review does not scale. Tiered review keeps the scarce reader on the changes that can hurt you.

Write the tier and the reason in one line at the start of each cycle. See [`templates/claude/commands/next-ticket.md`](templates/claude/commands/next-ticket.md), step 1b.

---

## 4. Two-speed delivery — build first, harden when it works

**Rule: while a feature is being built, only the product tests and the safety fences block. When the feature works, one `harden` PR makes the process fences block.**

### Safety fences and process fences

Sort every static fence (a test that guards a convention) into one of two lists in [`templates/shared/fences.json`](templates/shared/fences.json).

| List | Failure reaches | Examples | In build |
|---|---|---|---|
| **safety** | A customer or production: a wrong write, a leak, a 404 | Tenancy, auth, secrets, migrations, money, deploy and CI path | **Blocks** |
| **process** | Nothing outside the repo: naming, docs, registries, wording, source-string pins | Doc names resolve, index completeness | **Warns** |

If you are not sure, choose safety. A test makes sure every fence sits in exactly one list.

### Measured

**[Repo]** The source product counted 70 red CI runs on 15-19 October 2026:

| Cause | Red runs |
|---|---|
| Process fences | 29 |
| Real bugs in the PR | 9 |

Each red run cost about 30 minutes. Process fences caused 41% of red runs. That is a tax on the owner's time, paid for rules that no customer would feel.

### The two modes

| | Build | Harden |
|---|---|---|
| Goal | A working feature, fast | A feature that stays correct |
| Blocks | Product tests, safety fences | Everything, including process fences and style lint |
| Review | Verifier per slice | One adversarial review of the whole feature diff |
| Docs and fence tests | Wait | Written now, in one PR labelled `harden` |
| HIGH tier | Full loop | Full loop |

**What never relaxes in either mode:** the owner-gate guard, the safety fences, tests against a real database, the migration replay, and the migration-number guard. You cannot roll production back.

---

## 5. Model routing — cheap model works, strong model for the hard cases

**Rule: the cheaper model does the work. The strongest model takes the hard cases.** **[Vendor]** Anthropic reports that multi-agent systems use about 15x the tokens of a chat, and that most coding tasks suit them poorly. Every dispatch costs a floor of tokens. Use the strong model only where it changes the result.

| Role | LOW | STANDARD | HIGH |
|---|---|---|---|
| Spec auditor | cheap | cheap | cheap |
| Implementer | cheap | cheap | **strongest** |
| Verifier | cheap | cheap | **strongest** |
| Adversarial reviewer | skipped | strongest, at the hardening pass | strongest |

Two escalations override the table:

- **A second try after the cheap model failed on the same finding** goes to the strongest model. The cheap model already missed it once.
- **A hard problem** goes to the strongest model at any tier. That means a slice that crosses three or more services, or a concurrency, cache or ordering bug.

Use the smallest model for a pure lookup with no judgement: find a file, list callers, count rows. Never use it to build, verify or review.

Set the default in your harness settings and let each agent file name its own model. Keep one test that checks the routing, so a new agent file cannot drift.

---

## 6. The loop, with the local run

The loop is the one in [`ORCHESTRATION.md`](ORCHESTRATION.md) with these changes. The command is [`templates/claude/commands/next-ticket.md`](templates/claude/commands/next-ticket.md).

| Step | What happens |
|---|---|
| **Tier** | Set the tier and the models (sections 3 and 5) |
| **Audit** | `spec-auditor` checks the slice is dispatchable. **A small slice skips it** |
| **Branch** | One worktree per session (section 13) |
| **Build** | The implementer builds, starts `dev_up.sh`, checks each criterion in the running app, and leaves the stack up |
| **Verify** | A different agent runs `dev_up.sh --check`, checks each criterion again, and quotes the evidence |
| **Review** | By tier. LOW and build-mode STANDARD skip it |
| **Land** | Open the PR, run `premerge.sh`, merge, smoke-test on staging |

### The verifier is never the implementer

The verifier re-derives facts from the code and from its own run. It does not trust the implementer's write-up. **[Measured]** In EvilGenie, coding agents hardcoded test cases and edited test files. For a solo owner, the missing human reviewer must be replaced by tests the agent cannot edit and a separate verifier with fresh context.

### A small slice skips the spec audit

A small slice is LOW tier, or STANDARD tier in build mode. Its task must state the acceptance criteria and must not start a new spec. The supervisor quotes the task text as the contract. A HIGH-tier slice and the first slice of a spec always get the audit. **[Inference]** This follows Anthropic's cost guidance and one practitioner finding that spec overhead can exceed the code it covers. No study compares dispatch counts to defect rates. Watch your escape rate (section 14).

### Cap repair rounds

Repair rounds follow the tier. If the slice still fails, stop and leave the branch in place. A loop that grinds on a stuck ticket burns budget.

---

## 7. Merging — test the merge, not the branch

**Rule: right before `gh pr merge`, run `premerge.sh`.** See [`templates/scripts/premerge.sh`](templates/scripts/premerge.sh) and its test, [`templates/scripts/premerge.test.sh`](templates/scripts/premerge.test.sh).

### Why CI goes stale

CI tests your PR merged with `main` as it was when the run started. Without a merge queue, and without a branch protection rule that demands an up-to-date branch, `main` can move after that run. The PR then lands on a different `main` than CI tested.

**[Repo]** Collisions this caused in the source product:

| Collision | Count |
|---|---|
| Two PRs took the same migration number | 3 in 2 weeks |
| Two PRs took the same handoff-queue id | 1 (2026-09-23) |
| Two PRs took the same decision number | 1 (2026-10-25) |
| Two PRs green alone and red together | 2 in one day |

A duplicate id on `main` turns `main` red and blocks every deploy until someone repairs it.

### What `premerge.sh` does

When the branch is behind `origin/main`, it:

1. Refuses a new migration numbered at or below `main`'s highest.
2. Merges `origin/main` into the worktree **without a commit**.
3. Runs the collision fences on that result.
4. When both sides changed the same files, runs the affected tests too.
5. Aborts the merge, so the worktree is as it was.

Exit 0 means merge now. Exit 1 means merge `origin/main` into the branch, fix, push, and wait for CI. When the branch already contains `main`, it exits 0 at once.

A squash merge lands the same tree that step 2 built. A pass tests what lands, with no second CI run. Keep the list of collision fences in the script (`FENCES=(...)`). Write `.premerge-fences` for your own project (see [`SETUP.md`](SETUP.md) §6b.3).

### Merge, do not rebase, a pushed branch

A rebase needs a force-push, and the guard blocks that. Merge `main` into the branch instead.

### A merge queue is the alternative

A merge queue solves the same problem and costs a CI run per merge. The source product chose not to run one. If you run one, `premerge.sh` becomes optional. The migration-number check still pays for itself.

---

## 8. Staging and the release train

**Rule: a merge reaches staging within about 15 minutes. Production moves once a day, to the tip of `main`, if its tests pass.** A merge is not a production deploy.

```
 PR ──merge──► main ──every merge──► staging   (smoke test, real OAuth, deploy path)
                 │
                 └──once a day, if main is green──► production
```

### What staging is

| Property | Value |
|---|---|
| **Data** | A reduced, anonymised copy of production. The source product's holds four organisations |
| **Outbound** | Every outbound switch off. Staging sends no mail and calls no CRM |
| **Writes** | Write nothing there that must last |
| **Sign-in** | The same identity providers as production |
| **Database, secrets** | Never shared with production |

### What staging is for

The PC cannot test four things. Staging tests them in full:

1. The **deploy path**: units, proxy, env files.
2. A **real OAuth sign-in** or connect.
3. A **real provider webhook** or sync.
4. A **migration on production-shaped data**.

For everything else, staging is a smoke check. Wait until the version endpoint serves your merge SHA. Sign in. Load the page of the change. Check one acceptance criterion. Report: "verified locally, staging smoke at `<sha>`, reaches production at the next daily release." If staging does not answer, write "staging not up" and do not claim the test.

### The release train

- **Production moves on a clock.** The source product releases daily at 21:30 UTC. The release takes the newest commit that passed.
- **A red `main` blocks that night's release.** Watch the post-merge test job. Fix forward or revert at once.
- **A hold switch stops one night's release.** The source product uses a repository variable, `RELEASE_HOLD=1`. Set it when staging shows a defect you cannot fix in time.
- **A manual hotfix dispatch happens only when the owner asks in this session, or production is down.** A dark feature never needs one. The agent that dispatches must then watch the run and report the SHA the version endpoint serves.

### Ship dark

New behaviour lands behind a flag, default off. The flip is a deliberate act. A flag that moves money or reaches a real person stays with the owner.

### Why a daily train

**[Repo]** The source product took 480 merges in 15 days. Each was a production restart that could end live agent runs. Batching the restarts to one a day gave customers stability and cost the team nothing, because most merges shipped dark. The train is also the human checkpoint of the whole system. See [`PLAYBOOK.md`](PLAYBOOK.md) Principle 15.

---

## 9. Verify delivery by evidence

**Rule: a green job is not proof. Show the served SHA, the migration ledger line, or the log line.**

**[Repo]** Four deploys in the source product once reported success while shipping nothing.

| Claim | Evidence to quote |
|---|---|
| "Deployed" | The SHA the `/version` endpoint serves, equal to or later than your merge |
| "Migration applied" | The migration ledger line for that number |
| "Service restarted" | The unit's start time and a log line from the new process |
| "Flag flipped" | The value read back from the running service, not the file you wrote |
| "Backup done" | The completed backup record, before the migration runs |

Make `/version` return the deployed SHA and the SHA of the last applied migration. Without that endpoint you have nothing to check.

---

## 10. Migrations — expand/contract, and no rollback

**Rule: a migration must work with the code that is running now.** The deploy applies migrations before it restarts services. For a window, old code meets the new schema.

- Add columns **nullable, with a default**. Never `NOT NULL` in the same release as the code that fills them.
- **Never rename in place.** Add the new name, backfill, switch readers, drop the old one in a later release.
- Add a unique constraint or check over existing data as `NOT VALID`, then validate it in a guarded block.
- The **contract half** (drop, tighten) ships as a separate, later migration. Two releases, never one.

**You cannot roll back.** A forward-only ladder means you roll forward or restore from backup. Say so in your docs. Do not imply `git revert` undoes a migration.

**Numbers.** Take the next free migration number at build time, not earlier. `premerge.sh` re-checks it at merge.

**Verify SQL against a real database.** A fake agrees with whatever SQL it gets. **[Repo]** Five live bugs shipped green that way. Without a database, database tests skip and the run still reads green. Check the skip count.

---

## 11. The autonomy window — owner grants with a date

**Bottom line: the owner opens a dated window in a committed file, and inside it agents merge, deploy and flip flags without asking. Outside it, the guard refuses.**

[`ORCHESTRATION.md`](ORCHESTRATION.md) §5 stops the loop at "PR opened". That is the right default. A project with a staging environment, a daily release train and a grant window can go further. Merge is then cheap to reverse and production is protected by the train.

### The grants file

`.claude/OWNER_GRANTS.md` (template: [`templates/shared/OWNER_GRANTS.md`](templates/shared/OWNER_GRANTS.md)) holds dated lines:

```
ALLOW-UNTIL 2026-11-30 deploy — dev phase, owner at the keyboard
```

`plan-guard.mjs` reads the file. A gate is open while a line covers it and the date has not passed. After the date, the guard refuses again with no further action. The file is committed, so every checkout, worktree and cloud session reads the same window.

| Inside the window, an agent may | Gate id |
|---|---|
| Run deploy scripts and the migration runner, read logs, restart units | `deploy` |
| Read or write env files on the box | `secrets`, `env-write` |
| Write under `deploy/` | `deploy-write` |
| Flip a feature flag, and name the flag and the box | `enforcement-flip` |
| Merge its own PR | none |
| Edit the guard or its settings | `guard-write` |

### What never unlocks

The guard blocks these four, and no grant opens them:

1. **Force-push** and any history rewrite.
2. **Commit or push on `main`.** Cut a branch.
3. **Write the grants file.** Only the owner writes a grant. When the owner must add a line, open the file at that line for them and give the exact text.
4. **Destroy or restore infrastructure.** The server, the DNS zone, the domain.

### Three rules that replace the refusals

The old gates bought care as well as delay. Keep the care, drop the delay.

1. **A production migration needs a confirmed backup.** Confirm the backup completed. Then apply it. You need the evidence, not permission.
2. **Report every production act in the same message.** Name the act, the box and the evidence: "I restarted the gateway, `/version` now serves `abc123`."
3. **Money, identity and third parties still stop the agent.** Do not charge a card, mail a real person, or write a live organisation's membership or credit balance. Ask first.

### Keep the guard honest

Editing the guard needs its own grant. In this window the hook is the only enforcement layer. A guard that can edit itself is not a guard. Test every gate: `node .claude/hooks/plan-guard.test.mjs`.

**The failure mode to watch:** the window does not excuse verification. Faster delivery makes a silent failed deploy more likely, so section 9 binds harder, not softer.

---

## 12. Project management through a task board

**Rule: every change has a task. One session holds a task. The board is the state, and chat is not.**

Connect an MCP task board. The protocol is in [`templates/shared/task-board.md`](templates/shared/task-board.md). The slash command is [`templates/claude/commands/work-on-task.md`](templates/claude/commands/work-on-task.md). Any board with the same verbs works.

| Step | Verb |
|---|---|
| **Claim** | The session claims the task. A held task is not touched. Take the next row |
| **Heartbeat** | Post a short activity line at least once a minute. It proves the hold is alive |
| **Work** | Link each branch and each PR to the task. Put the task id in the branch name |
| **One disposition** | End with exactly one: move to review or done, a question for a named person, or release the task |
| **Handoff note** | Before you release, comment what is done, what is left, and the next step |

A comment is evidence. It is not a disposition. Move a task to done only after the merge.

### Why a board, not chat

**[Repo]** The owner saw "idle" while an orchestrator waited on sub-agents. Chat hides state. A board shows who holds what, and it survives a crash, a compaction and a new session. This follows PLAYBOOK Principle 9: durable state lives outside the agent.

### A handoff queue for cross-session actions

Some actions belong to no task: a flag to flip next week, a check to run after the release. Keep them in [`templates/shared/HANDOFF.md`](templates/shared/HANDOFF.md). Each entry has a **Check** command. The next session runs the check first and deletes entries that pass. The queue holds actions, never state. The board stays the only state authority.

---

## 13. One worktree per session

**Rule: every development session starts in its own worktree.** Two sessions in one checkout fight over one working tree. One switches the branch under the other. A hard reset by either destroys the other's uncommitted work. None of it announces itself.

```bash
bash scripts/worktree.sh new <slug>     # then cd into the path it prints
bash scripts/worktree.sh list
bash scripts/worktree.sh remove <slug>
```

Script: [`templates/scripts/worktree.sh`](templates/scripts/worktree.sh).

- **Use `remove`, never `git worktree remove` by hand.** A worktree may carry a `node_modules` link into the main checkout. The bare command follows the link and deletes the real folder. The script unlinks first.
- **Run `npm install` per worktree** if your bundler resolves through links to the wrong root.
- **Keep branches short.** Three or four in flight is the ceiling. **[Measured, secondary]** A July 2026 study found agent PRs from different agents conflict textually 41.7% of the time, against 19.8% inside one agent. **[Vendor]** Cursor found 20 agents sharing locks ran at the speed of 2-3.
- **Worktrees isolate files, not ports or databases.** `dev_up.sh` fixes that part.
- **Reading, answering a question, or a one-file fix you are watching needs no worktree.**

---

## 14. What the evidence says about speed, and how to measure your own

**Do not trust a felt speedup. Measure your own cycle time.**

| Source | Finding | Label |
|---|---|---|
| METR randomized trial | Experienced developers in their own mature repos took 19% longer with AI in early 2025, and believed they were about 20% faster. A late-2025 follow-up showed an 18% speedup for returning developers. METR calls it very weak evidence | **[Measured]** |
| Faros telemetry, 10,000+ developers | High-AI teams completed 21% more tasks and merged 98% more PRs. Review time rose 91%. No significant company-level delivery gain | **[Measured]** |
| DORA 2025 | AI raises throughput and still raises instability. It is a "mirror and multiplier". Small batches, fast review and automated tests are the safeguards | **[Survey]** |
| Stripe "Minions" | 1,000+ merged PRs a week, each reviewed by a human. Linting under 5 seconds. At most two CI rounds | **[Vendor]** |
| Anthropic docs | Give the agent a check it can run. Enforce hard rules with hooks. Give each parallel session a worktree | **[Vendor]** |

Links: [METR](https://metr.org/blog/2026-02-24-uplift-update/), [Faros](https://www.faros.ai/blog/ai-software-engineering), [DORA report summary](https://blog.google/innovation-and-ai/technology/developers-tools/dora-report-2025/), [DORA AI research](https://dora.dev/research/ai/gen-ai-report/), [Stripe](https://stripe.dev/blog/minions-stripes-one-shot-end-to-end-coding-agents), [Claude Code best practices](https://code.claude.com/docs/en/best-practices).

**No published study measures token savings from local testing.** The speed claim has better support, from the source product's timings above and from DORA's finding that fast feedback loops decide whether AI helps. The token claim is inference. Savings come mainly from fewer repair rounds, a smaller rules preload and fewer subagent dispatches.

### Four numbers to record, before and after

| Metric | How |
|---|---|
| **Tokens per merged PR** | Your host's usage report, divided by merged PRs |
| **Red CI runs per week** | Count them, and tag the cause: process fence, real bug, flake, runner wait |
| **Minutes from first edit to green** | Branch creation to the green merge check |
| **Production escapes** | Defects found after the release that staging or the verifier should have caught |

Run a two-week comparison. Without it you repeat METR's mistake.

---

## 15. Adoption path

Do not install everything on day one. This order works.

1. **Worktree script.** Run each session in its own worktree. No cost, immediate relief.
2. **Measure.** Record the four numbers in section 14 for one week.
3. **`dev_up.sh`.** Write `scripts/dev_up.config` from the example. Get one command to start your app with seeded data. Check that outbound is off with `--print-env`.
4. **Local run as the acceptance check.** Make the implementer and the verifier run the slice on the local stack.
5. **Risk tiers and model routing.** Write the tier table into your loop command.
6. **`fences.json` and two-speed delivery.** Sort your fences. Let process fences warn in build.
7. **`premerge.sh`.** Run it before every merge. Add your collision fences.
8. **Staging, then the release train.** Make staging a reduced copy with outbound off. Release on a clock. Add a hold switch.
9. **Task board and handoff queue.** Connect the board. Use `/work-on-task`.
10. **Owner grants.** Only now open a dated window. Write the file yourself, by hand.

Each step is useful alone. Stop where the pain stops.

For install commands, see [`SETUP.md`](SETUP.md) §6b.
