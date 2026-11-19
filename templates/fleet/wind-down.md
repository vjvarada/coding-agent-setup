# Wind-down note for a lane

Send this to each lane on a machine that must close (`FLEET.md` §7.2).
Replace `<queue file>` and `<machine>`.

---

The owner needs this machine. Wind down NOW. Start nothing new. Within 10 minutes:

1. Stop your sub-agents and your background jobs. Do not start a new test run or build.
2. In each worktree you used: show the diff stat, then commit all your work
   as a WIP commit on its own branch (never on `main`), and push it. Lose
   nothing. Keep scratch files out of commits.
3. Stop each local stack, preview server, tunnel and container that you started.
4. Append ONE line to `<queue file>` on `<machine>`: `NOTE`, tab, your lane
   name, tab, "wound down <UTC time>: <each branch and its head>, <the state
   of each open PR>, <the next step>".
5. Send the orchestrator the same line. Then end your turn. Do not wait for an answer.

---

**For the orchestrator:** stop each session only after its NOTE line is in
the queue file. A lane that does not answer may be stuck in one request.
Check its worktrees yourself: every commit pushed, nothing uncommitted. Then
write its NOTE line for it, and stop it.
