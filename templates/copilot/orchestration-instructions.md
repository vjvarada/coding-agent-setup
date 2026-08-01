## Planning and dispatch loop (no-subagent hosts)

This project plans and builds through a supervisor-worker loop. Where the host
supports subagents (Claude Code), each role below runs as its own agent with its
own tool grants. **In this host there are no subagents**, so you play the roles
yourself, sequentially — and the discipline that the roles are *separate* has to
come from you.

Full methodology: `coding-agent-setup/ORCHESTRATION.md`.
The queue: `<path to work plan>`. The gates: `.claude/plan-guard.config.json`.

### The rule that makes it work without subagents

**Never verify your own work in the same breath as writing it.** The value of a
separate verifier is that it does not already believe the code works. When you
play both roles, you must deliberately reset: re-read the diff from scratch,
re-run the spec's commands rather than the ones you remember choosing, and treat
your own earlier report as a claim to check rather than a finding.

Where the host supports it, start a **fresh session** for the verify and review
passes and give it only the branch name and the spec. That restores most of the
independence a separate agent would have provided.

### Planning a feature

1. **Decompose** — survey what already exists first, then split the goal into
   workstreams: one owner, one outcome, independently verifiable, sized to a
   reviewable PR. Label each AGENT-SAFE or OWNER-GATE. **Show the decomposition
   to the owner before writing it to the board.**
2. **Wireframe** any UI surface — one self-contained annotated HTML file at
   `docs/wireframes/<feature>.html`, covering *every state*: empty, loading,
   populated, error, denied. Real copy, no lorem ipsum. Grey boxes, not visual
   design.
3. **Specify** — write the owning spec to the seven-point contract in the work
   plan §1. Acceptance criteria must be checkable by a command; that point is
   the ceiling on how much can ever be automated.
4. **Audit** — test the spec against the contract *before* building. A NO-GO
   found now is cheap.

### Building a ticket

1. **Audit** the spec against the seven-point contract. If acceptance is not
   checkable, stop: the next task is fixing the spec, not writing code.
2. **Branch** from the default branch. Never commit on a protected branch.
3. **Build** only the cleared slice. Walk the `AGENTS.md` chain first; place new
   work in its architectural home before writing it.
4. **Verify** — re-read the diff cold, re-run the spec's commands, check each
   acceptance criterion yourself, and cover whatever CI does not.
5. **Review** — adversarially. Hunt silent no-ops (new wiring nothing reads),
   contract breaks, fail-open error handling, missing tenancy scoping,
   wrong-layer placement.
6. **Land** — update the board row and the spec's status header in the same
   change, then open a PR. **Stop there**: merge and deploy belong to the owner.

### Owner gates — refuse these

Deploy · production flag flips · credentials · force-push or history rewrite ·
destructive data operations · publishing · spending money · external accounts.

If you hit one, stop and write down the exact action the owner must take. Do not
find another route to the same effect.
