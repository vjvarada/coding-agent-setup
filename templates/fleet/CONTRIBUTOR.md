# The contributor playbook: build `<project>` with your own agent fleet

Template (`FLEET.md` §9.3). Copy it to `docs/contributor_playbook.md` in your
repo and fill in every `<...>`. Route each fact to the file that owns it, and
add only what changes for a second person. A rule marked **(owner to
confirm)** is a default. It binds until the owner answers on `<task>`.

---

## 0. The short version

- You run your own fleet on your own machine, with your own AI accounts.
- The owner runs his fleet on `<his machines>`.
- The two fleets share three things only: the task board, `main`, and the
  release slots.
- **The board claim is the lock.** Claim a task before the first edit. Never
  work on a task that another live session holds.
- You own the area in §2. The owner's fleet does not claim tasks in it. You do
  not claim the owner's tasks.
- The forge CI is the gate. Then `premerge.sh` tests the merge with today's
  `main`. Then you merge (§6).
- **You never touch production.** The owner's fleet verifies each release.

## 1. Read these first

| Topic | The owner file |
|---|---|
| The rules of every session | `<instructions file>` (read §8 first) |
| Which specs you may build from | `<spec index>` |
| The cycle of one slice | `<loop command or doc>` |
| The common lane rules | `<lane rules>` |

## 2. What you own (owner to confirm)

**Your area is `<app or project>`.** No lane of the owner's fleet builds there.

| Order | Work | Tasks | State |
|---|---|---|---|
| 1 | Warm-up: a small, low-risk fix that teaches the loop | `<task>` | `<state>` |
| 2 | `<first real slice>` | `<task>` | `<state>` |

**When your area has no free task:** ask the owner on `<task>`. Do not take a
task in another area because it is free.

## 3. The access you need

| Access | Who gives it |
|---|---|
| A board member with a grant on your area | The owner |
| Write access to the repo | The owner (owner to confirm) |
| AI accounts | You. Never an account that the owner's machines use |
| Production, secrets, deploy | Nobody |
| The owner's always-on box | Nobody |

## 4. Set up your machine

1. `<setup steps, or a pointer to the setup doc>`
2. Sign in to the board MCP as yourself. Check the account with `whoami`.
3. Put the block of §10 in the user-level instructions file of your machine.

**Install none of these:** the release timer, the merge lane, a CI runner with
a shared label. Each one acts for the whole company.

## 5. Run your fleet

One orchestrator, a few lanes (`FLEET.md` §4), one slice at a time, the
verifier never the builder. You are one integrator: three or four branches in
flight, at most four open PRs per lane.

## 6. The merge path (owner to confirm)

1. The verifier passed, and the review of the tier passed, on the pushed head.
2. The forge CI passed.
3. Run `premerge.sh` in the PR's worktree. On a refusal, merge `main` into the
   branch, push, and wait for CI again.
4. Squash-merge. Never bypass branch protection.
5. Close the task with the merge SHA.

Merge nothing in the freeze window before each release slot: `<windows>`.
A high-risk slice waits for the owner's Approve on its task (owner to confirm).

## 7. Do not collide with the owner's fleet

| Collision | What stops it | Fence |
|---|---|---|
| Two sessions build one task | The board refuses a second claim | The board |
| Two fleets build one area | §2 | Advisory |
| You take a task from a lane that went quiet | Never take another member's hold. Ask on the task | Advisory |
| Two PRs take one migration number | `premerge.sh` refuses a number at or below `main`'s highest | `premerge.sh` |
| Two PRs pass alone and fail together | `premerge.sh` runs the tests both sides can affect | `premerge.sh` |
| A rewritten branch | Never rebase or force-push a pushed branch | The guard hook |
| A release that runs twice | Never install the release timer | Advisory |
| One usage limit for two fleets | Separate accounts | Advisory |

**See who works on what:** open a task. It shows the holder and its open
agent runs. `<fleet view, if you have one>`

## 8. How to read the repo's instructions as a contributor

- **"The owner"** is `<name>`. Ask him on the task.
- **The owner-grants file** opens gates for the owner's agents only. Your
  fleet refuses every production act (owner to confirm).
- **The owner's box and its scripts** are not yours.

## 9. What you must refuse

Production, secrets, money, identity, messages to real people, paid evals over
`<budget>`, force-push, commits on `main`, and writes to the owner-grants file.

## 10. The block for your user-level instructions file

```markdown
# <project> contributor fleet

You work for a contributor to <project>, not for the owner.
Read docs/contributor_playbook.md before your first tool call.

- "The owner" in the repo instructions is <name>. Ask him on the task.
- The owner-grants file opens gates for the owner's agents only.
  Refuse every production act.
- Take tasks only from the area in section 2 of the playbook.
  Never claim a task that another member holds, even a quiet one.
- Merge only by section 6 of the playbook, never in a freeze window.
- Never install the release timer, the merge lane or a shared CI runner.
```

## 11. Open decisions for the owner

| # | Decision | The default |
|---|---|---|
| 1 | The area | `<area>` |
| 2 | Repo write access | The owner gives it |
| 3 | AI accounts | Separate from the owner's |
| 4 | The owner-grants window | Does not cover the contributor |
| 5 | The merge path | §6. High-risk slices wait for the owner |
| 6 | Shared core code | Ask the owner first (advisory until a code-owners file) |
| 7 | Previews and flag flips | The owner approves both |
| 8 | His machine | No shared runner, no release timer |
