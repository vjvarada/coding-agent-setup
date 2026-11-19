"""Wake each lane whose usage limit has reset (FLEET.md §4.4).

STATUS: [Designed]. It ran for a day on the source product with no limit
event, so no real wake has tested it. Check its log after the first limit.

Every 10 minutes, for each lane in $LANES_DIR/waker_lanes.txt
("<session id> <name>" per line): if `claude agents` shows the lane idle, and
its last reply says "... limit ... resets <time> (UTC)", and that time plus
3 minutes has passed, send $LANES_DIR/limit_reset_note.txt with wake_lane.sh.
Each limit message is woken once. Log: $LANES_DIR/limit_waker.log.

Run:  nohup python3 limit_waker.py > /dev/null 2>&1 &
Stop: kill the process by its PID. Do not `pkill -f` from a shell whose own
command line holds the same text: it kills that shell too.

Host: Claude Code. The transcript path and the limit text are Claude Code's.
"""
import datetime as dt
import glob
import json
import os
import re
import subprocess
import time

HOME = os.path.expanduser("~")
LANES_DIR = os.environ.get("LANES_DIR", f"{HOME}/lanes")
LANES = f"{LANES_DIR}/waker_lanes.txt"
NOTE = f"{LANES_DIR}/limit_reset_note.txt"
LOG = f"{LANES_DIR}/limit_waker.log"
WAKE = os.environ.get("WAKE_SCRIPT", f"{LANES_DIR}/wake_lane.sh")
RESET = re.compile(r"resets (\d{1,2})(?::(\d{2}))?\s*(am|pm) \(UTC\)", re.I)
done = set()


def log(msg):
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(f"{dt.datetime.utcnow():%Y-%m-%d %H:%M} {msg}\n")


def last_reply(sid):
    """The text and timestamp of the lane's last assistant message."""
    files = glob.glob(f"{HOME}/.claude/projects/*/{sid}*.jsonl")
    if not files:
        return None, None
    text, ts = None, None
    with open(max(files, key=os.path.getmtime), encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if '"assistant"' not in line:
                continue
            try:
                o = json.loads(line)
            except ValueError:
                continue
            if o.get("type") != "assistant":
                continue
            blocks = (o.get("message") or {}).get("content") or []
            t = " ".join(b.get("text", "") for b in blocks
                         if isinstance(b, dict) and b.get("type") == "text").strip()
            if t:
                text, ts = t, o.get("timestamp")
    return text, ts


def reset_time(text, ts):
    m = RESET.search(text or "")
    if not m or not ts:
        return None
    hour = int(m.group(1)) % 12 + (12 if m.group(3).lower() == "pm" else 0)
    said = dt.datetime.fromisoformat(ts.replace("Z", "+00:00")).replace(tzinfo=None)
    r = said.replace(hour=hour, minute=int(m.group(2) or 0), second=0, microsecond=0)
    return r if r > said else r + dt.timedelta(days=1)


def statuses():
    try:
        out = subprocess.run(["claude", "agents", "--json", "--all"],
                             capture_output=True, text=True, timeout=90).stdout
        return {x.get("id"): x.get("status") for x in json.loads(out[out.index("["):])}
    except (OSError, ValueError, subprocess.SubprocessError) as e:
        log(f"agents read failed: {e}")
        return {}


log("start")
while True:
    try:
        lanes = [l.split()[:2] for l in open(LANES, encoding="utf-8")
                 if l.strip() and not l.startswith("#")]
        st = statuses()
        now = dt.datetime.utcnow()
        for sid, name in lanes:
            if st.get(sid) != "idle":
                continue
            text, ts = last_reply(sid)
            r = reset_time(text, ts)
            if not r or (sid, ts) in done or now < r + dt.timedelta(minutes=3):
                continue
            subprocess.run(["bash", WAKE, sid, NOTE], capture_output=True, timeout=120)
            done.add((sid, ts))
            log(f"woke {name} {sid} (limit said at {ts}, reset {r:%H:%M})")
    except Exception as e:  # keep the loop alive; the log shows the cause
        log(f"loop error: {e}")
    time.sleep(600)
