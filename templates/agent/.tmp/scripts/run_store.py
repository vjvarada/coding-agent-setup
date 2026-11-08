#!/usr/bin/env python3
"""run_store.py — one folder per agent run: inputs, one file per step, a final status.

The DOE agent's working memory that survives sessions. Every run is a directory
under outputs/<slug>/ holding run.json (inputs, steps, status, summary) and one
step_<n>_<name>.json per pipeline step — the contract between steps. Past runs are
searchable, so the agent checks what it already did before repeating work.

CLI:
  run_store.py new <slug> [--input key=value ...]
  run_store.py step <slug> <name> (--json '{...}' | --file path.json)
  run_store.py finish <slug> --status success|failed|partial --summary "..."
  run_store.py list [--status S]
  run_store.py search <words...>

Library (from any skill script; .tmp/scripts is on the path when run via agents.py,
otherwise add it):
  from run_store import new_run, save_step, finish_run

Stdlib only. Slugs are kebab-case; nested slugs (<project>/<run>) are allowed.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUTPUTS = ROOT / "outputs"
SLUG_RE = re.compile(r"^[a-z0-9]+(?:[-_][a-z0-9]+)*(?:/[a-z0-9]+(?:[-_][a-z0-9]+)*)*$")


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def _run_dir(slug: str, base: Path = OUTPUTS) -> Path:
    if not SLUG_RE.match(slug):
        raise ValueError(f"slug `{slug}` must be kebab-case, optionally nested with /")
    return base / slug


def _load(run_dir: Path) -> dict:
    path = run_dir / "run.json"
    if not path.exists():
        raise FileNotFoundError(f"no run at {run_dir} — start it with `new`")
    return json.loads(path.read_text(encoding="utf-8"))


def _save(run_dir: Path, run: dict) -> None:
    (run_dir / "run.json").write_text(json.dumps(run, indent=2, default=str) + "\n", encoding="utf-8")


def new_run(slug: str, inputs: dict | None = None, base: Path = OUTPUTS) -> Path:
    run_dir = _run_dir(slug, base)
    if (run_dir / "run.json").exists():
        raise FileExistsError(f"run `{slug}` exists — pick a new slug or continue it with `step`")
    run_dir.mkdir(parents=True, exist_ok=True)
    _save(run_dir, {"slug": slug, "created": _now(), "status": "running", "inputs": inputs or {},
                    "steps": [], "summary": ""})
    return run_dir


def save_step(slug: str, name: str, data, base: Path = OUTPUTS) -> Path:
    run_dir = _run_dir(slug, base)
    run = _load(run_dir)
    n = len(run["steps"]) + 1
    safe = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_") or "step"
    path = run_dir / f"step_{n}_{safe}.json"
    path.write_text(json.dumps(data, indent=2, default=str) + "\n", encoding="utf-8")
    run["steps"].append({"n": n, "name": name, "file": path.name, "at": _now()})
    _save(run_dir, run)
    return path


def finish_run(slug: str, status: str, summary: str, base: Path = OUTPUTS) -> dict:
    if status not in ("success", "failed", "partial"):
        raise ValueError("status must be success, failed or partial")
    run_dir = _run_dir(slug, base)
    run = _load(run_dir)
    run.update(status=status, summary=summary, finished=_now())
    _save(run_dir, run)
    return run


def list_runs(base: Path = OUTPUTS) -> list[dict]:
    runs = []
    for path in sorted(base.rglob("run.json")) if base.exists() else []:
        try:
            runs.append(json.loads(path.read_text(encoding="utf-8")))
        except ValueError:
            continue
    return runs


def search(words: list[str], base: Path = OUTPUTS) -> list[dict]:
    terms = [w.lower() for w in words if w.strip()]
    hits = []
    for run in list_runs(base):
        hay = json.dumps({k: run.get(k) for k in ("slug", "inputs", "summary", "steps")},
                         ensure_ascii=False).lower()  # escaped JSON would never match "münchen"
        if all(t in hay for t in terms):
            hits.append(run)
    return hits


def _kv(pairs: list[str]) -> dict:
    out = {}
    for pair in pairs:
        key, sep, value = pair.partition("=")
        if not sep:
            raise ValueError(f"--input expects key=value, got `{pair}`")
        out[key.strip()] = value.strip()
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", default=str(OUTPUTS), help=argparse.SUPPRESS)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("new", help="start a run")
    p.add_argument("slug")
    p.add_argument("--input", action="append", default=[], metavar="KEY=VALUE")
    p = sub.add_parser("step", help="record one step's output")
    p.add_argument("slug")
    p.add_argument("name")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--json", help="inline JSON")
    g.add_argument("--file", help="path to a JSON file")
    p = sub.add_parser("finish", help="close a run")
    p.add_argument("slug")
    p.add_argument("--status", required=True, choices=["success", "failed", "partial"])
    p.add_argument("--summary", required=True)
    p = sub.add_parser("list", help="list runs")
    p.add_argument("--status")
    p = sub.add_parser("search", help="find past runs by words in slug, inputs, steps or summary")
    p.add_argument("words", nargs="+")
    args = ap.parse_args(argv)
    base = Path(args.base)

    try:
        if args.cmd == "new":
            d = new_run(args.slug, _kv(args.input), base)
            print(json.dumps({"run": args.slug, "dir": str(d)}))
        elif args.cmd == "step":
            data = json.loads(args.json) if args.json else json.loads(Path(args.file).read_text(encoding="utf-8"))
            path = save_step(args.slug, args.name, data, base)
            print(json.dumps({"run": args.slug, "step": path.name}))
        elif args.cmd == "finish":
            run = finish_run(args.slug, args.status, args.summary, base)
            print(json.dumps({"run": args.slug, "status": run["status"], "steps": len(run["steps"])}))
        elif args.cmd == "list":
            runs = [r for r in list_runs(base) if not args.status or r.get("status") == args.status]
            print(json.dumps([{k: r.get(k) for k in ("slug", "status", "created", "summary")} for r in runs],
                             indent=2))
        elif args.cmd == "search":
            hits = search(args.words, base)
            print(json.dumps([{k: r.get(k) for k in ("slug", "status", "created", "summary")} for r in hits],
                             indent=2))
    except (ValueError, FileExistsError, FileNotFoundError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
