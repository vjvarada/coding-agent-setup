# FLEET — many agents, many machines, many people

Capability #7. [`ORCHESTRATION.md`](ORCHESTRATION.md) runs one supervisor and its
workers inside one session. [`DELIVERY.md`](DELIVERY.md) takes one slice from
"built" to "in production". This page runs **a fleet**: about ten long-lived
agent sessions on several machines, one merger and three releases a day. The
owner is sometimes on a plane. Next, a second person runs his own fleet.

**How to read the tags.** **[Repo]** means we ran it on the source product and
saw the result. **[Measured]** carries a number we read. **[Designed]** means
the design is written but has not run end to end yet. Do not treat a
[Designed] part as proven.

**Host.** The commands name Claude Code (`claude --bg`, `--remote-control`,
`claude attach`, `claude agents --json`). Other hosts need their own way to
start a background session, send it a message and list its state. The rules
do not change.

---

## 1. When you need this

You need it when one of these is true:

- More than three agent sessions work at once, and you lose track of who does what.
- Work must go on while you sleep or travel.
- A second person runs his own agents on the same repo.

You do not need it for one person with one or two sessions. Then
`DELIVERY.md` is enough.

---

## 2. The shape

| Part | What it is | Where it runs |
|---|---|---|
| **Orchestrator** | One session that plans, gives each lane its stream, relays messages, verifies releases and reports to the owner | Where the owner works, or on the always-on box when the owner is away (§7) |
| **Lane** | A background session on one stream of tasks, in its own worktree | The always-on box, or a PC |
| **Merge lane** | One lane that only merges: it reads a queue file, runs the merge check and merges | The always-on box. Exactly one per fleet |
| **Sub-agent** | A builder, a verifier or a reviewer that a lane starts for one slice | The machine of its lane |
| **Release timer** | Starts each release slot | Exactly ONE machine for the whole company |
| **The board** | The task board, over MCP. It is the only state | Every session signs in to it |
| **The queue file** | One line per hand-over and per result, on the merge lane's machine | The always-on box |

**Never run a lane, a test run or a CI runner on the production host.** A test
run can take the memory that customers need.

---

## 3. What limits throughput, in order

More machines raise only the last two limits. Check the first three first.

1. **Integration.** Reviews, previews and merges limit what lands. Keep three
   or four branches in flight for each person who integrates. Give each lane
   at most four open PRs. **[Repo]** One merge lane merged about 18 PRs in the
   9 hours between two releases. More lanes than that past the cap make a
   queue of unmerged work, not more delivery.
2. **Account usage limits.** **[Repo]** Twelve lanes used about 4% of one
   large subscription's weekly limit in one hour. Two machines on one account
   share one limit.
3. **CI concurrency.** Your forge plan caps the jobs that run at once for the
   whole organisation.
4. **Memory.** **[Repo]** On a 24 GB box, memory limited us before CPU. About
   ten sessions plus one full test run fit. A lane reads the free memory
   before a heavy job: a local stack, a full test run or a browser run. Below
   about 5 GB, it pushes and lets the forge CI run instead, or it waits.
5. **Disk.** Each worktree and each container image takes disk.

---

## 4. Lanes

### 4.1 Start a lane

A lane is a background session with a start note:

```bash
claude --bg --remote-control <name> -n <name> --model sonnet "<start note>"
```

The start note has two parts:

1. **The stream:** the tasks in order, the branches that already exist, the
   pull requests in flight, and the owner decisions that wait.
2. **The common rules**, the same for every lane:
   [`templates/fleet/lane-rules.md`](templates/fleet/lane-rules.md).

[`templates/fleet/start_lane.sh`](templates/fleet/start_lane.sh) starts a lane
from a note file.

### 4.2 Give a lane new orders

A message has three states, and each one needs its own check:

| State | How to check |
|---|---|
| **Landed** | The text is in the lane's transcript |
| **Read** | The lane's next reply refers to it |
| **Acted** | The board or the queue file shows the act |

**[Repo]** A lane stuck in one model request for 2.7 hours never read a
wind-down order. The transport reported success. The watch loop reported
"waiting", which it counted as healthy.

**[Repo]** The first wake script typed the message but left it unsubmitted.
A second Enter fixed it.
[`templates/fleet/wake_lane.sh`](templates/fleet/wake_lane.sh) attaches to the
session in a throwaway terminal, types, presses Enter twice and detaches. It
works by timing, so confirm each send in the transcript.

Write each order with no apostrophes or shell quotes. Name the tasks, the
branches and the next step. A lane cannot ask you what you meant at 3 a.m.

### 4.3 Watch the lanes

A watch loop runs in the background and exits with a reason. Act on the
reason, then start it again. Never sleep in the foreground.

Exit when one of these is true:

- A lane is idle, its transcript is older than 30 minutes, and it is not resting.
- A lane has said "waiting" for longer than its stated wait. **[Repo]** The
  hang above lasted hours because the loop trusted "waiting".
- A new BACK or HOLD line is in the queue file.
- The time window ends.

### 4.4 Keep lanes alive

- **A keeper** restarts a lane whose session died. A keeper restarts a
  session. It does not give the session work.
- **A usage-limit waker** wakes each idle lane after its "limit resets at
  `<time>`" time passes.
  [`templates/fleet/limit_waker.py`](templates/fleet/limit_waker.py).
  **[Designed]** It ran for a day with no limit event, so no real wake has
  tested it.
- **After an account switch, wake every lane.** A switch ends the turn of
  every busy lane.

### 4.5 Rest a lane

A lane that is at its PR cap, or whose stream is done, rests. Put its name in
a resting list so the watch does not alarm. Do not start new lanes to "use the
capacity". The integration cap of §3 is the limit.

---

## 5. The merge lane and its queue

One merge lane merges for the whole fleet. The building lanes keep building.

### 5.1 The queue file

One line per event, tab-separated, appended only:

| Line | Who writes it | Meaning |
|---|---|---|
| `READY <pr> <task> <lane> <note>` | A building lane | The verifier passed, the review of the tier passed, and the preview was approved if it needed one |
| `REQUEUE <pr> ...` | A building lane | Fixed after a BACK. Take it again |
| `HOLD <pr> <reason>` | Anyone | Do not merge it yet |
| `BACK <pr> <reason>` | The merge lane | A conflict, a red check or a failed merge check. The owning lane fixes it |
| `DONE <pr> <sha>` | The merge lane | Merged. The merge lane also closes the task |
| `NOTE <who> <text>` | Anyone | A status line that people read later |

### 5.2 Rules the merge lane follows

- **Build the order from the queue file**, then apply the owner's priority.
  **[Repo]** A rung 0 fix (a broken live upload) was left out of a merge
  order typed from memory. It missed one release by 3 minutes.
- **A review binds to a pushed head.** A verdict on an older head does not
  cover a new commit.
- **Merge `main` into a pushed branch.** Never rebase it.
- **Run the merge check** (`premerge.sh`, see `DELIVERY.md` §7) on today's
  `main`, right before each merge.
- **Close the task on the merge**, with the merge SHA as evidence.
  **[Repo]** When building lanes closed their own tasks, about 170 merged
  tasks still read "in progress".
- **Freeze before each release.** Merge nothing in the 70 minutes before a
  release slot, until its release run starts. Then the release picks a `main`
  that has had its full test run.
- **Gate only with memory free** (§3).

---

## 6. Releases

### 6.1 The clock

**[Repo]** The source product releases three times a day. Each slot ships
the newest commit of `main` that passed the full test suite. A red tip holds
no release. A slot ships once. One machine runs the timer, and the forge's own
cron is the backup. `DELIVERY.md` §8 has the reasons.

### 6.2 Verify each release by evidence

Never report a release from a green job. Read these five facts:

1. **The run that published.** **[Repo]** A dispatched run skipped its deploy
   because the scheduled run had already published that slot. Find the run
   whose log says "this release ships `<sha>`" and whose deploy job ran.
2. **A backup before any migration.** If the release applies migrations, the
   deploy log shows the backup line before the migration line. If it applies
   none, it says so.
3. **The served SHA** on the host equals the released SHA.
4. **The services are active**, and the smoke jobs passed.
5. **The fix you shipped works**, when you can test it. A grep that finds no
   error proves nothing until you know the log holds the lines you grep for.
   **[Repo]** After one release, the log held one line since the deploy. "No
   upload errors" meant "no uploads yet".

Post the evidence on the task of each priority change in that release.

---

## 7. When the owner is away

### 7.1 Move the orchestrator to the always-on box

Before the owner leaves, start a box orchestrator with a written start note:
[`templates/fleet/orchestrator-note.md`](templates/fleet/orchestrator-note.md).
The note holds its duties, every lane with its stream, the owner's priorities
in order, the decisions that wait, and the rules. The owner reads its status
lines when he is back.

### 7.2 Wind down the PC lanes

When the PC must close, send each PC lane the wind-down note
[`templates/fleet/wind-down.md`](templates/fleet/wind-down.md):

1. Stop sub-agents and background jobs.
2. Commit all work as a WIP commit on its own branch, and push. Lose nothing.
3. Stop local stacks and containers.
4. Append one NOTE line with each branch, its head, each open PR and the next step.
5. End the turn.

Stop each session only after its NOTE line is in the queue file. **[Repo]**
One lane hung and never read the order. The orchestrator checked its
worktrees itself, found every commit pushed, and wrote the NOTE line for it.

### 7.3 Cancel a hand-over fast

**[Repo]** A hand-over went to the box orchestrator. Ten minutes later the
owner gave the same work to another person. By then the box orchestrator had
already given three streams to box lanes. It recalled each one, and each lane
confirmed that it had claimed nothing. Name every task in a cancel, and ask
each lane to confirm.

---

## 8. Accounts and sign-ins

- **Use several subscriptions.** One machine signs in to one account at a
  time. Two machines on one account share its limit.
- **Never copy a credential file between machines.** **[Repo]** Sessions that
  share one rotating refresh token race. One spent refresh made the server
  revoke the connection for nine sessions at once. Use a separate sign-in, or
  a per-machine token, on each machine.
- **Sign a headless machine in through a tunnel.** On the box, run the
  sign-in in a terminal multiplexer. Copy the link. Open an SSH tunnel from
  the PC to the box's callback port. Open the link in the PC browser.
- **Check who you are before any write.** **[Repo]** The PC browser was
  signed in to a member of another organisation. The box connected as that
  member. One lane called `whoami`, saw a strange organisation, and wrote
  nothing. Then:
  1. Sign the box out.
  2. Tell every lane to write nothing to the board.
  3. Scan every transcript for board writes since the sign-in. There were none.
  4. Sign in again. Use the owner's normal browser profile, and check the
     organisation on the approval page.
  5. One lane calls only `whoami`.
  6. Then lift the write freeze.

  **[Repo]** Two tries in a private window timed out. After the sign-in step,
  the page did not return to the approval step.
- **Revoke what a wrong sign-in left.** The other account still lists the
  connection until its owner removes it.

---

## 9. Many people, each with a fleet

**[Designed]** The rules below are written down and given to the second
person. They have not yet run with two fleets at once.

### 9.1 What each person owns

- **Partition by area, not by task.** Give each person a whole app or project
  where no lane of another fleet builds. Shared files collide even when tasks
  do not.
- **Give back work that overlaps.** **[Repo]** We first released a set of
  chat tasks to the second person. They touched files that the box lanes were
  changing that day, so they went back. He got a project that no box lane
  touched: the fleet view in §9.4.
- **The board claim is the lock.** A held task cannot be claimed twice.
- **Never take a task that another member holds, even a quiet one.** A board
  may hand a quiet hold to the next claim after a while. Lanes go quiet while
  they still work. Ask on the task first. Bind this rule in the lane rules of
  both fleets.

### 9.2 What exists once

| Thing | Rule |
|---|---|
| The release timer | One machine for the company. A second timer releases twice |
| CI runners with a shared label | A runner on the second person's machine takes jobs of the first fleet. Ask before you register one |
| The merge fences | In the forge and in `premerge.sh`, which both fleets run. A list on one box protects only that box |
| A ledger of booked migration numbers | Readable by both fleets. Until then, `premerge.sh` refuses a number at or below `main`'s highest, and the later PR takes a new number |
| The freeze windows | Written in the repo, where both fleets read them |

### 9.3 Give the second person a playbook

[`templates/fleet/CONTRIBUTOR.md`](templates/fleet/CONTRIBUTOR.md) is the
template. It holds:

- What he owns.
- The access he needs, and what he gets none of (production, the other fleet's box).
- The machine setup, and what he must not install.
- The merge path.
- A table of collisions, each with its fence, or the word "advisory".
- How to read the repo's instructions as a contributor.
- What he refuses.
- A block for the user-level instructions file on his machine. Each of his
  sessions then knows it works for him, before it reads the repo's rules.

Write each open question as a default marked "owner to confirm". The default
binds until the owner answers. The playbook can then ship before every
decision is made.

### 9.4 The missing piece: one view of every agent

The board shows the holder and the open runs of each task. It does not show
every agent of both fleets on one screen. Each person sees his own runs.
Build a fleet view: each person, each session by name, its machine, its
model, its task, and who dispatched whom. **[Designed]** It is the second
person's first project.

---

## 10. Failure modes seen in practice

| What happened | What we do now |
|---|---|
| A lane hung for 2.7 hours, and the watch counted "waiting" as healthy | Alarm on a wait that runs past its stated end |
| A wind-down order landed but was never read | Check landed, read and acted separately (§4.2) |
| A wake left the text unsubmitted | Press Enter twice, and confirm in the transcript |
| A rung 0 fix missed a release | Build the merge order from the queue file |
| A dispatched run skipped its deploy, and the scheduled run published | Verify the run that published (§6.2) |
| "No errors in the log" after a release meant "no traffic yet" | Prove the grep can match before you report "none" |
| A hand-over was cancelled after lanes got the work | Name every task in the cancel, and get a confirmation from each lane |
| The box connected to the board as a member of another organisation | Run `whoami` before any write, and freeze writes on a mismatch |
| One spent refresh token revoked the connection of nine sessions | A sign-in or a token for each machine, never a copied file |
| The box clock stepped back 2.5 s every 30 s, and timestamp tests failed | Run one time-sync service, not two that fight |
| Memory ran out when lanes started gates together | Read free memory before each heavy job (§3) |
| About 170 merged tasks still read "in progress" | The merge lane closes the task on the merge |

---

## 11. Adoption path

1. Run two or three lanes with the common rules and a merge lane. Measure
   merges per hour.
2. Add the watch loop and the queue file. Add the keeper when a lane first
   dies in the night.
3. Move the orchestrator to the always-on box for one night. Read its status
   lines in the morning.
4. Add release checks by evidence before the second release that ships with
   no person watching.
5. Add a second person only after the board shows each holder clearly. Give
   him a whole area and the contributor playbook.
