#!/usr/bin/env python3
"""anneal.py — capture, integrate and gate lessons (the self-annealing loop).

Usage:
  anneal.py log --title T --lesson L --target X [--source S]
  anneal.py list [--all]
  anneal.py apply L003 --note "where it landed"
  anneal.py defer L003 --note "why it waits"
  anneal.py gate [--run-tests]

Lessons live in the file named by `lessons_path` in .harness/project.json
(default docs/lessons.md). Stdlib only. The gate never commits: it prints a
suggested commit message for the user to approve.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

DEFAULT_ROOT = Path(__file__).resolve().parents[4]
ENTRY_RE = re.compile(r"^### (L\d{3,}) · (.*)$", re.M)
HEADER = """# Lessons — the self-annealing backlog

Every fix, gotcha, validated setting or wrong instruction found while working here
is logged as a lesson, then integrated into its architectural home (a SKILL.md, a
script plus a test, an AGENTS.md contract). See `.github/skills/self-annealing/SKILL.md`.

Status: **OPEN** (not yet integrated) · **APPLIED** (landed; note says where) ·
**DEFERRED** (parked; note says why). Manage entries with
`python .github/skills/self-annealing/scripts/anneal.py`, not by hand.

<!-- New lessons are appended below. -->
"""


def _out(text: str = "") -> None:
    try:
        sys.stdout.write(text + "\n")
    except UnicodeEncodeError:
        sys.stdout.write(text.encode("ascii", "replace").decode("ascii") + "\n")


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:  # Path.write_text(newline=) is 3.10+
        fh.write(text)


def lessons_file(root: Path) -> Path:
    cfg = root / ".harness" / "project.json"
    rel = "docs/lessons.md"
    if cfg.exists():
        try:
            rel = json.loads(cfg.read_text(encoding="utf-8")).get("lessons_path", rel)
        except ValueError:
            pass
    return root / rel


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else HEADER


def entries(text: str) -> list[dict]:
    out = []
    matches = list(ENTRY_RE.finditer(text))
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[m.start():end]
        status = re.search(r"\*\*Status:\*\*\s*(\w+)", body)
        out.append({"id": m.group(1), "title": m.group(2).strip(), "status":
                    status.group(1) if status else "?", "start": m.start(), "end": end, "body": body})
    return out


def next_id(text: str) -> str:
    nums = [int(e["id"][1:]) for e in entries(text)]
    return f"L{(max(nums) + 1) if nums else 1:03d}"


def cmd_log(root: Path, args: argparse.Namespace) -> int:
    path = lessons_file(root)
    text = read(path)
    lid = next_id(text)
    today = dt.date.today().isoformat()
    block = (
        f"\n### {lid} · {args.title.strip()}\n"
        f"- **Status:** OPEN\n"
        f"- **Date:** {today}\n"
        f"- **Target:** {args.target.strip()}\n"
        + (f"- **Source:** {args.source.strip()}\n" if args.source else "")
        + f"- **Lesson:** {' '.join(args.lesson.split())}\n"
    )
    write(path, text.rstrip("\n") + "\n" + block)
    _out(f"logged {lid} · {args.title.strip()} → {path.relative_to(root).as_posix()}")
    return 0


def cmd_list(root: Path, args: argparse.Namespace) -> int:
    es = entries(read(lessons_file(root)))
    shown = es if args.all else [e for e in es if e["status"] == "OPEN"]
    _out(f"{len(shown)} {'lesson(s)' if args.all else 'OPEN lesson(s)'}")
    for e in shown:
        _out(f"  {e['id']} [{e['status']}] {e['title']}")
    return 0


def _close(root: Path, lid: str, status: str, note: str) -> int:
    path = lessons_file(root)
    text = read(path)
    match = next((e for e in entries(text) if e["id"] == lid.upper()), None)
    if match is None:
        _out(f"error: no lesson {lid} in {path.name}")
        return 1
    body = re.sub(r"(\*\*Status:\*\*\s*)\w+", rf"\g<1>{status}", match["body"], count=1)
    label = "Applied" if status == "APPLIED" else "Deferred"
    body = body.rstrip("\n") + f"\n- **{label}:** {dt.date.today().isoformat()} — {' '.join(note.split())}\n"
    if match["end"] != len(text):
        body += "\n"  # keep the blank line before the next entry
    text = text[:match["start"]] + body + text[match["end"]:]
    write(path, text)
    _out(f"{lid.upper()} → {status}")
    return 0


def _git(root: Path, *args: str) -> subprocess.CompletedProcess | None:
    if not shutil.which("git") or not (root / ".git").exists():
        return None
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, encoding="utf-8")


def suggest_commit(changed: list[str], applied: list[dict]) -> str:
    areas: dict[str, int] = {}
    for path in changed:
        parts = path.split("/")
        key = "/".join(parts[:3]) if parts[0] == ".github" and len(parts) > 2 else parts[0]
        areas[key] = areas.get(key, 0) + 1
    top = ", ".join(sorted(areas, key=lambda k: -areas[k])[:4])
    subject = f"Anneal: {len(applied)} lesson(s) integrated" if applied else f"Update {top}"
    lines = [subject, ""]
    for e in applied[:10]:
        lines.append(f"- {e['id']} {e['title']}")
    if not applied:
        lines.append(f"Touches: {top}.")
    return "\n".join(lines)


def cmd_gate(root: Path, args: argparse.Namespace) -> int:
    problems: list[str] = []
    details: list[str] = []
    es = entries(read(lessons_file(root)))
    open_ = [e for e in es if e["status"] == "OPEN"]
    if open_:
        problems.append(f"{len(open_)} OPEN lesson(s)")
        details += [f"  integrate or defer: {e['id']} {e['title']}" for e in open_]

    harness = root / ".harness" / "harness.py"
    if harness.exists():
        r = subprocess.run([sys.executable, str(harness), "check"], cwd=root, capture_output=True, text=True)
        if r.returncode != 0:
            problems.append("harness check failing")
            details += ["  " + ln for ln in r.stdout.strip().splitlines()[:12]]
        if args.run_tests:
            r = subprocess.run([sys.executable, str(harness), "test"], cwd=root, capture_output=True, text=True)
            if r.returncode != 0:
                problems.append("skill tests failing")
                details += ["  " + ln for ln in r.stdout.strip().splitlines()[:12]]

    commit = ""
    st = _git(root, "status", "--porcelain")
    if st is not None and st.stdout.strip():
        changed = [ln[3:].strip().strip('"') for ln in st.stdout.splitlines() if ln.strip()]
        problems.append(f"{len(changed)} uncommitted change(s)")
        today = dt.date.today().isoformat()
        applied_today = [e for e in es if e["status"] == "APPLIED" and today in e["body"]]
        commit = suggest_commit(changed, applied_today)

    if not problems:
        _out("anneal gate: CLEAR — no open lessons, harness passes, nothing uncommitted")
        return 0
    _out("anneal gate: ACTION NEEDED — " + "; ".join(problems))
    for d in details:
        _out(d)
    if commit:
        _out("\nSuggested commit (ASK THE USER before committing):\n")
        for ln in commit.splitlines():
            _out("    " + ln)
    return 1


def main(argv: list[str] | None = None) -> int:
    try:  # agents read this through pipes; Windows defaults pipes to cp1252
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=str(DEFAULT_ROOT), help="workspace root")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("log", help="capture a lesson")
    p.add_argument("--title", required=True)
    p.add_argument("--lesson", required=True)
    p.add_argument("--target", required=True, help="skill, module or doc that should absorb it")
    p.add_argument("--source", help="session, PR, run or project it came from")
    p = sub.add_parser("list", help="show OPEN lessons")
    p.add_argument("--all", action="store_true", help="show every lesson")
    for name in ("apply", "defer"):
        p = sub.add_parser(name, help=f"{name} a lesson")
        p.add_argument("id")
        p.add_argument("--note", required=True)
    p = sub.add_parser("gate", help="session-end gate")
    p.add_argument("--run-tests", action="store_true", help="also run `harness.py test`")
    args = ap.parse_args(argv)
    root = Path(args.root).resolve()

    if args.cmd == "log":
        return cmd_log(root, args)
    if args.cmd == "list":
        return cmd_list(root, args)
    if args.cmd == "apply":
        return _close(root, args.id, "APPLIED", args.note)
    if args.cmd == "defer":
        return _close(root, args.id, "DEFERRED", args.note)
    if args.cmd == "gate":
        return cmd_gate(root, args)
    return 1


if __name__ == "__main__":
    sys.exit(main())
