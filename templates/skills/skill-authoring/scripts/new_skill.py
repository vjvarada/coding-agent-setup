#!/usr/bin/env python3
"""new_skill.py — create a skill package in the DOE shape, then sync every host.

A skill is a directive (SKILL.md: goal, inputs, process, outputs, edge cases,
definition of done) plus its execution layer (scripts/) plus its tests (tests/).
It lives once, in .github/skills/<name>/; `harness.py sync` writes the proxies
other hosts need and refreshes every skills table.

Usage:
  new_skill.py <name> --description "What it does and WHEN to use it"
               [--when "trigger conditions"] [--authority read|write|external]
               [--cost-tier 0-3] [--script main] [--no-sync] [--root DIR]

Exit codes: 0 created · 1 refused (bad name, exists, bad args)
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
import textwrap
from pathlib import Path

DEFAULT_ROOT = Path(__file__).resolve().parents[4]
NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
AUTHORITIES = ("read", "write", "external")


def _title(name: str) -> str:
    return " ".join(w.capitalize() for w in name.split("-"))


def _folded(text: str, indent: str = "  ") -> str:
    lines = textwrap.wrap(" ".join(text.split()), width=84) or [""]
    return "\n".join(indent + ln for ln in lines)


def _summary(description: str) -> str:
    return " ".join(description.split()).split(". ")[0].rstrip(".")


def _docstring_safe(text: str) -> str:
    """Text that can sit inside a triple-quoted Python docstring (C:\\Users would not)."""
    return text.replace("\\", "\\\\").replace('"""', "'''")


def _yaml_single(text: str) -> str:
    """A single-quoted YAML scalar: no escapes except '' for a quote."""
    return "'" + " ".join(text.split()).replace("'", "''") + "'"


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:  # Path.write_text(newline=) is 3.10+
        fh.write(text)


def skill_md(name: str, description: str, when: str, authority: str, cost_tier: int, script: str) -> str:
    when_line = f"when_to_use: {_yaml_single(when)}\n" if when else ""
    summary = _summary(description)
    confirm = ("\n> **Authority: external.** This skill acts outside the workspace (sends, publishes,\n"
               "> spends or deletes). Run it with `--dry-run` first and get the user's go-ahead\n"
               "> before the real run.\n") if authority == "external" else ""
    return f"""---
name: {name}
description: >-
{_folded(description)}
{when_line}authority: {authority}
cost_tier: {cost_tier}
version: 0.1.0
---

# {_title(name)}

{summary}.
{confirm}
## Goal

TODO: the outcome this skill produces, in one sentence a reviewer could check.

## Inputs

| Input | Required | Description |
|---|---|---|
| TODO | yes | |

## Scripts

| Script | Purpose |
|---|---|
| `scripts/{script}.py` | Primary entry point — `python .github/skills/{name}/scripts/{script}.py --help` |

## Process

1. TODO: read the inputs; ask for anything missing before running.
2. TODO: test on a small input first (e.g. `--limit 5`) and check the output.
3. TODO: the full run.
4. TODO: verify the Definition of Done below before reporting.

## Outputs

TODO: where results land (e.g. `outputs/<run-slug>/step_N_<name>.json`) and their shape.

## Definition of Done

- TODO: a statement a command can check, e.g. "the output file exists and every row has a non-empty `email`".

## Edge Cases

- TODO: rate limits, empty results, partial failure — and what to do for each.

## Environment

- None. (List each environment variable the scripts read, and where to get it.)

## Learnings

<!-- Self-annealing: dated, one line each, newest last. What broke, what fixed it. -->
"""


def script_py(name: str, description: str, script: str) -> str:
    summary = _docstring_safe(_summary(description))
    return f'''#!/usr/bin/env python3
"""{name}: {summary}.

Usage:
  python .github/skills/{name}/scripts/{script}.py --help

Execution-layer contract (DOE): one job; the same inputs give the same outputs;
a JSON summary on stdout; a non-zero exit and a message on stderr on failure;
never swallow an exception; secrets only from environment variables; anything
outward-facing supports --dry-run.
"""
from __future__ import annotations

import argparse
import json
import sys


def run(args: argparse.Namespace) -> dict:
    """Do the one job. Return a JSON-serialisable summary of what happened."""
    raise NotImplementedError("TODO: implement {name} (write the behaviour test first)")


def main(argv: list[str] | None = None) -> int:
    try:  # pipes default to the locale encoding on Windows; agents read this through pipes
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="show what would happen; change nothing")
    args = ap.parse_args(argv)
    try:
        result = run(args)
    except NotImplementedError as exc:
        print(f"error: {{exc}}", file=sys.stderr)
        return 3
    json.dump(result, sys.stdout, indent=2, default=str)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
'''


def test_py(name: str, script: str) -> str:
    return f'''"""Tests for the {name} skill. Run: python .harness/harness.py test"""
from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "{script}.py"


class CliContract(unittest.TestCase):
    def test_help_works(self) -> None:
        r = subprocess.run([sys.executable, str(SCRIPT), "--help"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)

    @unittest.skip("TODO: write the behaviour test BEFORE implementing run() — it is the skill's acceptance")
    def test_behaviour(self) -> None:
        self.fail("replace with a test that runs the script on a small fixture and checks the output")


if __name__ == "__main__":
    unittest.main()
'''


def create_skill(root: Path, name: str, description: str, when: str = "", authority: str = "read",
                 cost_tier: int = 0, script: str = "main") -> list[Path]:
    """Create .github/skills/<name>/ with SKILL.md, scripts/<script>.py and a test. Returns the files."""
    if not NAME_RE.match(name) or len(name) > 64:
        raise ValueError(f"skill name `{name}` must be kebab-case (a-z, 0-9, hyphens), <= 64 chars")
    if not description.strip():
        raise ValueError("a description is required: hosts route on it")
    if len(" ".join(description.split())) > 1024:
        raise ValueError("description is over 1024 characters")
    if authority not in AUTHORITIES:
        raise ValueError(f"authority must be one of {', '.join(AUTHORITIES)}")
    if not 0 <= int(cost_tier) <= 3:
        raise ValueError("cost tier must be 0-3")
    if not re.match(r"^[a-z_][a-z0-9_]*$", script):
        raise ValueError("script name must be a python module name (snake_case)")
    base = root / ".github" / "skills" / name
    if base.exists():
        raise FileExistsError(f"{base.relative_to(root).as_posix()} already exists — edit it instead")
    files = {
        base / "SKILL.md": skill_md(name, description, when, authority, int(cost_tier), script),
        base / "scripts" / f"{script}.py": script_py(name, description, script),
        base / "tests" / f"test_{script}.py": test_py(name, script),
    }
    for path, text in files.items():
        write(path, text)
    return list(files)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("name", help="kebab-case skill name, e.g. enrich-leads")
    ap.add_argument("--description", required=True, help="what it does AND when to use it (routing signal)")
    ap.add_argument("--when", default="", help="plain-English trigger conditions")
    ap.add_argument("--authority", default="read", choices=AUTHORITIES,
                    help="read: looks only · write: changes the workspace · external: acts outside it")
    ap.add_argument("--cost-tier", type=int, default=0, help="0 free · 1 cheap · 2 paid API · 3 expensive/long")
    ap.add_argument("--script", default="main", help="entry script module name (default: main)")
    ap.add_argument("--no-sync", action="store_true", help="skip `harness.py sync` afterwards")
    ap.add_argument("--root", default=str(DEFAULT_ROOT), help="workspace root")
    args = ap.parse_args(argv)
    root = Path(args.root).resolve()
    try:
        created = create_skill(root, args.name, args.description, args.when, args.authority,
                               args.cost_tier, args.script)
    except (ValueError, FileExistsError) as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 1
    print(f"created skill `{args.name}`:")
    for p in created:
        print(f"  {p.relative_to(root).as_posix()}")
    harness = root / ".harness" / "harness.py"
    if not args.no_sync and harness.exists():
        subprocess.run([sys.executable, str(harness), "sync"], cwd=root, check=False)
    print("next: fill the TODOs in SKILL.md, write the behaviour test, then implement run().")
    return 0


if __name__ == "__main__":
    sys.exit(main())
