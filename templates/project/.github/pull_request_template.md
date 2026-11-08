## What changed and why

<!-- Bottom line first: one sentence a reviewer could stop after. Then the why. -->

## Risk tier

<!-- HIGH (auth, money, secrets, migrations, tenancy, deploy path) · MEDIUM (product code) · LOW (docs, tooling). HIGH gets the full review loop. -->

## Verification

<!-- CI requires a line that starts "Verified:". Name the command you ran and what it
showed — a test run, a request and its response, a screenshot path. A green CI job
is not evidence on its own. Example:
Verified: `pnpm test` 142 passed; `curl localhost:3000/api/health` → 200 {"ok":true}
-->

Verified: <command and what it showed>

## Task / plan row

<!-- A link to the task, or the work-plan row this closes. Write PR links as URLs, not #N. -->

## Checklist

- [ ] Placed per the DOX Child Index (no orphan files, no second implementation of an existing seam)
- [ ] Owning `AGENTS.md` / `SKILL.md` updated if a boundary, rule or capability changed
- [ ] Lessons learned logged (`anneal.py log`) and `HANDOFF.md` updated for anything handed over
