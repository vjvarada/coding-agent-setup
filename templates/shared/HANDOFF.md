# HANDOFF — what the last session left unfinished

**This file is a QUEUE OF ACTIONS, not a status board.** A session hook, or the
first lines of `AGENTS.md`, point every new session here so that nobody has to
remember what was in flight.

## The one rule that keeps it honest

> Never restate state here. Point at it, and carry the command that re-derives it.

Your task board (or work plan) holds the current state. A handoff that also
described state would be a second board. One of the two stops being updated
first, and the stale one gets trusted because it is the one loaded into the
prompt.

So every entry carries a **Check**: a command whose output tells you whether
the entry is still real. You do not trust this file. You run the Check.

## The protocol

**At the start of a session**, before the work you were asked to do:

1. Run the **Check** of every entry.
2. **Delete every entry whose Check shows it is done.** Do it in your first
   commit. Close its task on the board too.
3. Tell the user what is left, in one short list. Then go on.

**During a session**, the moment you create an obligation, add its entry. Do it
then, while you remember why. Do not wait for the end, when context is short.

**Before you end a session**, add an entry for anything you hand over: work you
started, an owner gate you hit, a finding you scoped out, a decision you are
owed. If you are not sure it matters, add it. One line costs nothing.

## Entry shape

```
### H-<n> · <one line, imperative> · [AGENT|OWNER]
- **Task:** <task id or URL. The task holds the full text.>
- **Check:** `<command>` → <what its output means STILL PENDING>
- **Added:** <YYYY-MM-DD> by <session or person>
```

- `[AGENT]`: any session can do it. `[OWNER]`: only a human can (a gate, a
  decision, a secret).
- The Check must be runnable and cheap. "Ask Sam" is not a Check. If you cannot
  write one, the entry is state, and it belongs on the board.
- **Ids are never reused.** Take the next number from the highest `H-n` in this
  file and in `git log -p -- HANDOFF.md`. Check `origin/main` again right
  before you merge, because two branches can pick the same number.

## Queue

<!-- Add entries below, newest last. Delete an entry when its Check passes. -->

### H-1 · Example: delete this entry once you add a real one · [AGENT]
- **Task:** none
- **Check:** `grep -c "H-1 · Example" HANDOFF.md` → `1` means still pending
- **Added:** 2030-01-01 by the kit installer
