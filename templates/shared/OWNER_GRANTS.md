# Owner grants

**The owner writes this file, by hand, in their own editor. An agent never does.**
`plan-guard.mjs` refuses every agent write to it, and no grant lifts that
refusal. In-chat permission is not a grant. Only a line in this file is.

Install path: `.claude/OWNER_GRANTS.md`. Commit it, so every checkout, worktree
and cloud session reads the same window.

## Format

One line per grant. Two forms:

    ALLOW-UNTIL YYYY-MM-DD <gate-id> — reason     every day through that date
    ALLOW       YYYY-MM-DD <gate-id> — reason     that one local day only

A grant past its date is ignored. A line without a date grants nothing.
Delete stale lines when you like. They are inert.

## Gate ids

Each id unlocks the gates in `.claude/plan-guard.config.json` that carry the
same `grant` field.

| id | unlocks |
|---|---|
| `deploy` | deploy scripts, the migration runner, ssh to a host |
| `secrets` | reading `.env` and credential files |
| `env-write` | writing `.env` files |
| `deploy-write` | writing under `deploy/`, `infra/` and the CI workflows |
| `enforcement-flip` | flipping a production feature flag |
| `merge` | `gh pr merge`. Without it, the loop stops at the open PR |
| `guard-write` | editing the guard (`plan-guard.mjs`, its test and config, `settings.json`) |

## Example window

Replace the date. Keep only the lines you mean to grant.

    ALLOW-UNTIL 2030-01-31 merge — dev phase: agents merge their own green PRs
    ALLOW-UNTIL 2030-01-31 deploy — dev phase: agents may run deploy scripts and read logs
    ALLOW-UNTIL 2030-01-31 guard-write — dev phase: agents may repair guard false positives

With no line for an id, that gate stays shut. When the date passes, the gate
shuts again with no further action.

## The four acts no grant unlocks

1. **Force-push and any history rewrite** (`filter-branch`, `filter-repo`,
   `reset --hard origin`).
2. **Commit or push on a protected branch.** Cut a branch.
3. **Writing this file.** A grant that an agent can write is not a grant.
4. **Destroying or restoring infrastructure and data** (`terraform destroy`,
   `DROP`, dropping a remote branch, a publish).

Money, identity and third parties also stop an agent. An agent asks before it
charges a card, mails a real person, or writes a live customer's membership or
credit balance. A grant does not remove that duty.

## Report every use

An agent that acts under a grant says so in the same message. It names the act,
the target and the evidence. For example: "I restarted `api`, and `/version`
now serves `abc123`." A grant without a record is the failure this file exists
to prevent.

The test `node .claude/hooks/plan-guard.test.mjs` is the fence for all of this.
