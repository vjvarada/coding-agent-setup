#!/usr/bin/env python3
"""scaffold.py — lay down a complete, agent-ready workspace for a new project or agent.

Part of coding-agent-setup. The agent does the judgment (the intake interview, the
stack choice, prose that needs thought); this script does the mechanics, the same
way every time (DOE: directive → orchestration → execution). Read SCAFFOLD.md.

Commands
  list                                     archetypes and stack recipes
  intake-template [--archetype A] [--stack S]
                                           print a starter intake.json to fill in
  check-intake --intake FILE               validate an intake; write nothing
  new --intake FILE [--target DIR] [--dry-run]
                                           scaffold the workspace (never overwrites)
  install [--target DIR] [--dry-run]       run the kit installer with the project's capability toggles
  upgrade [--target DIR] [--dry-run]       re-apply kit-owned files the project has not edited

Stdlib only, Python >= 3.9. Exit codes: 0 ok · 1 invalid input or refused · 2 environment problem
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

KIT = Path(__file__).resolve().parents[1]
TEMPLATES = KIT / "templates"
CATALOG = KIT / "scaffold" / "catalog"
KIT_URL = "https://github.com/vjvarada/coding-agent-setup"
TODO = "TODO(" + "scaffold)"
TODAY = dt.date.today().isoformat()

HOSTS = {
    "claude-code": "Claude Code",
    "copilot": "GitHub Copilot",
    "cursor": "Cursor",
    "codex": "Codex",
    "other": "other AGENTS.md-aware hosts",
}
COMMAND_ROWS = [
    ("install", "Install dependencies"),
    ("dev", "Run (dev)"),
    ("test", "Test"),
    ("lint", "Lint"),
    ("typecheck", "Typecheck"),
    ("format", "Format"),
    ("build", "Build"),
]
CORE_SKILLS = ("self-annealing", "skill-authoring")  # copied verbatim, kit-owned
SESSION_HOOKS = ("session-handoff", "worktree-notice", "stop-children")
RUNTIMES = ("ide", "commandcenter")
# Integration Registry keys → environment variables (agent_repo_compatibility.md §13).
INTEGRATION_ENV = {
    "anthropic": ["ANTHROPIC_API_KEY"],
    "openai": ["OPENAI_API_KEY"],
    "litellm": ["LITELLM_BASE_URL", "LITELLM_MASTER_KEY"],
    "apollo": ["APOLLO_API_KEY"],
    "serpapi": ["SERPAPI_API_KEY"],
    "apify": ["APIFY_API_TOKEN"],
    "instantly": ["INSTANTLY_API_KEY"],
    "anymailfinder": ["ANYMAILFINDER_API_KEY"],
    "zoho-crm": ["ZOHO_CLIENT_ID", "ZOHO_CLIENT_SECRET", "ZOHO_REFRESH_TOKEN"],
    "google-sheets": ["GOOGLE_SHEETS_SA_JSON_PATH"],
    "clickup": ["CLICKUP_API_TOKEN", "CLICKUP_WORKSPACE_ID"],
}
GITIGNORE_BASE = [
    "# --- coding-agent-setup harness ---",
    "# Secrets (.env.example is the committed template)",
    ".env",
    ".env.*",
    "!.env.example",
    "# Local-only Claude Code settings: never commit permission overrides",
    ".claude/settings.local.json",
    "# Python caches (harness and skill scripts)",
    "__pycache__/",
    "*.py[cod]",
    "# Temp files. `?*.tmp`, NOT `*.tmp`: a bare `*.tmp` also matches a `.tmp/` directory",
    "# and silently untracks the shared utilities in `.tmp/scripts/` (DOE lesson).",
    "?*.tmp",
    "?*.temp",
    "# OS / editor",
    ".DS_Store",
    "Thumbs.db",
]
GITIGNORE_AGENT = [
    "# DOE agent workspace: .tmp/ is scratch; .tmp/scripts/ is tracked shared code",
    ".tmp/*",
    "!.tmp/scripts/",
    "!.tmp/scripts/**",
    "credentials.json",
    "token.json",
    "*.token_cache.json",
]
GITATTRIBUTES = [
    "# --- coding-agent-setup harness: scripts and hooks must stay LF ---",
    "*.sh   text eol=lf",
    "*.mjs  text eol=lf",
    "*.py   text eol=lf",
    "*.ps1  text eol=crlf",
]


class ScaffoldError(Exception):
    """Invalid input or a refused operation. The message is shown to the user."""


def say(text: str = "") -> None:
    try:
        sys.stdout.write(text + "\n")
    except UnicodeEncodeError:
        sys.stdout.write(text.encode("ascii", "replace").decode("ascii") + "\n")


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def catalogs() -> tuple[dict, dict]:
    return load_json(CATALOG / "archetypes.json"), load_json(CATALOG / "stacks.json")["stacks"]


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def kit_version() -> dict:
    version = (KIT / "VERSION").read_text(encoding="utf-8").strip() if (KIT / "VERSION").exists() else "0"
    commit = ""
    if shutil.which("git") and (KIT / ".git").exists():
        r = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=KIT, capture_output=True, text=True)
        commit = r.stdout.strip() if r.returncode == 0 else ""
    return {"source": KIT_URL, "version": version, "commit": commit}


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module  # dataclasses resolve annotations through sys.modules
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(name, None)
        raise
    return module


# ─────────────────────────────────────────────────────────────── rendering ──

TOKEN_RE = re.compile(r"(?<!\$)\{\{\s*([a-z_][a-z0-9_]*)\s*\}\}")


def render(text: str, ctx: dict, source: str) -> str:
    """Replace {{key}} tokens. `${{ ... }}` (GitHub Actions) is left alone. Unknown keys fail loudly."""
    missing: set[str] = set()

    def sub(m: re.Match) -> str:
        key = m.group(1)
        if key not in ctx:
            missing.add(key)
            return m.group(0)
        return str(ctx[key])

    out = TOKEN_RE.sub(sub, text)
    if missing:
        raise ScaffoldError(f"{source}: template uses unknown keys {sorted(missing)}")
    return out


# ────────────────────────────────────────────────────────────────── intake ──

def _str_list(value, field_name: str, errors: list[str]) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        errors.append(f"`{field_name}` must be a list of strings")
        return []
    return [v.strip() for v in value if v.strip()]


def _dedupe(items: list[str]) -> list[str]:
    seen, out = set(), []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def normalize(raw: dict) -> tuple[dict, list[str], list[str]]:
    """Validate an intake and fill defaults from the catalogs. Returns (intake, errors, warnings)."""
    archetypes_doc, stacks = catalogs()
    archetypes = archetypes_doc["archetypes"]
    base = archetypes_doc["base"]
    errors: list[str] = []
    warnings: list[str] = []
    raw = {k: v for k, v in raw.items() if not k.startswith("_")}

    name = str(raw.get("name", "")).strip()
    if not name:
        errors.append("`name` is required")
    slug = str(raw.get("slug") or slugify(name))
    if name and not slug:
        errors.append("the name has no ASCII letters or digits to build a slug from: give a `slug`, "
                      "e.g. \"sales-agent\"")
    elif slug and not re.match(r"^[a-z0-9][a-z0-9-]{0,48}[a-z0-9]$", slug):
        errors.append(f"`slug` `{slug}` must be lowercase letters, digits and hyphens (2-50 chars)")
    summary = " ".join(str(raw.get("summary", "")).split())
    if not summary:
        errors.append("`summary` is required: one paragraph on what this is and who it is for")

    archetype = raw.get("archetype", "")
    if archetype not in archetypes:
        errors.append(f"`archetype` must be one of: {', '.join(archetypes)}")
        arch = archetypes["other"]
    else:
        arch = archetypes[archetype]

    # stack: an id from the catalog, or an object (optionally with an id to extend)
    stack_raw = raw.get("stack", "")
    if isinstance(stack_raw, str):
        stack_raw = {"id": stack_raw} if stack_raw else {}
    if not isinstance(stack_raw, dict):
        errors.append("`stack` must be a stack id or an object")
        stack_raw = {}
    sid = stack_raw.get("id", "")
    if not sid and archetype == "agent":
        sid = "doe-agent"
    if sid and sid != "custom" and sid not in stacks:
        errors.append(f"unknown stack `{sid}`; use one of {', '.join(stacks)} or id `custom` with your own fields")
    stack = dict(stacks.get(sid, {}))
    stack.update({k: v for k, v in stack_raw.items() if v is not None})
    stack["id"] = sid or "custom"
    stack.setdefault("title", stack_raw.get("title") or "TBD")
    stack.setdefault("language", "TBD")
    module = slug.replace("-", "_")
    for key, _label in COMMAND_ROWS:
        value = stack.get(key, "") or ""
        stack[key] = value.replace("{slug}", slug).replace("{module}", module)
    init = stack.get("init", [])
    init = [init] if isinstance(init, str) else list(init or [])
    stack["init"] = [str(c).replace("{slug}", slug).replace("{module}", module) for c in init]
    if stack["title"] == "TBD":
        warnings.append("stack has no title: AGENTS.md will say TBD")

    hosts = _str_list(raw.get("hosts"), "hosts", errors) or ["claude-code", "copilot"]
    for h in hosts:
        if h not in HOSTS:
            errors.append(f"unknown host `{h}`; use: {', '.join(HOSTS)}")

    caps = dict(arch.get("capabilities", {}))
    caps_raw = raw.get("capabilities") or {}
    if not isinstance(caps_raw, dict):
        errors.append("`capabilities` must be an object of booleans")
        caps_raw = {}
    for key, value in caps_raw.items():
        if key not in ("graphify", "rtk", "loop", "delivery"):
            errors.append(f"unknown capability `{key}`")
        elif not isinstance(value, bool):
            errors.append(f"capability `{key}` must be true or false")
        else:
            caps[key] = value
    for key in ("graphify", "rtk", "loop", "delivery"):
        caps.setdefault(key, False)

    constraints = _dedupe(base["constraints"] + arch.get("constraints", [])
                          + _str_list(raw.get("constraints"), "constraints", errors))
    gates = _dedupe(base["gates"] + arch.get("gates", []) + _str_list(raw.get("gates"), "gates", errors))

    scopes_raw = raw.get("scopes")
    if scopes_raw is None:
        scopes_raw = arch.get("scopes", [])
        if archetype not in ("agent", "other") and scopes_raw:
            warnings.append("no `scopes` in the intake: using the archetype defaults — check they match "
                            "the generated layout")
    scopes = []
    for i, s in enumerate(scopes_raw or []):
        if not isinstance(s, dict) or not s.get("path") or not s.get("covers"):
            errors.append(f"scopes[{i}] needs `path` and `covers`")
            continue
        raw_path = str(s["path"]).strip().replace("\\", "/")
        path = raw_path.strip("/")
        parts = path.split("/")
        if (not path or raw_path.startswith("/") or re.match(r"^[A-Za-z]:", path)
                or any(p in ("", ".", "..") for p in parts)):
            errors.append(f"scopes[{i}].path `{raw_path}` must be a relative folder inside the project, "
                          "e.g. `src/app` (not empty, absolute, or using . / ..)")
            continue
        scopes.append({
            "path": path,
            "title": s.get("title") or path.split("/")[-1].replace("-", " ").title(),
            "covers": " ".join(str(s["covers"]).split()),
            "not_owns": s.get("not_owns", ""),
            "rules": _str_list(s.get("rules"), f"scopes[{i}].rules", errors),
        })

    brief_raw = raw.get("brief") or {}
    if not isinstance(brief_raw, dict):
        errors.append("`brief` must be an object")
        brief_raw = {}
    brief = {
        "problem": str(brief_raw.get("problem", "")).strip(),
        "users": str(brief_raw.get("users", "")).strip(),
        "goals": _str_list(brief_raw.get("goals"), "brief.goals", errors),
        "non_goals": _str_list(brief_raw.get("non_goals"), "brief.non_goals", errors),
        "success": _str_list(brief_raw.get("success"), "brief.success", errors),
        "risks": _str_list(brief_raw.get("risks"), "brief.risks", errors),
    }
    if not brief["problem"] or not brief["success"]:
        warnings.append("the brief has no problem and/or success criteria: docs/brief.md will carry "
                        "unfinished markers (ask the user)")

    skills = []
    reserved = set(CORE_SKILLS) | {"run-and-verify"}
    for i, s in enumerate(raw.get("skills") or []):
        if not isinstance(s, dict) or not s.get("name") or not s.get("description"):
            errors.append(f"skills[{i}] needs `name` and `description`")
            continue
        sname = s["name"]
        if not re.match(r"^[a-z0-9]+(?:-[a-z0-9]+)*$", sname) or len(sname) > 64:
            errors.append(f"skills[{i}].name `{sname}` must be kebab-case, <= 64 chars")
        if sname in reserved:
            errors.append(f"skills[{i}].name `{sname}` is a core skill the scaffolder already installs")
        authority = s.get("authority", "read")
        if authority not in ("read", "write", "external"):
            errors.append(f"skills[{i}].authority must be read, write or external")
        tier = s.get("cost_tier", 0)
        if not isinstance(tier, int) or not 0 <= tier <= 3:
            errors.append(f"skills[{i}].cost_tier must be an integer 0-3")
        script = s.get("script", "main")
        if not isinstance(script, str) or not re.match(r"^[a-z_][a-z0-9_]*$", script):
            errors.append(f"skills[{i}].script `{script}` must be a Python module name (snake_case), e.g. fetch_data")
        if len(" ".join(str(s["description"]).split())) > 1024:
            errors.append(f"skills[{i}].description is over 1024 characters")
        skills.append({"name": sname, "description": " ".join(str(s["description"]).split()),
                       "when": " ".join(str(s.get("when", "")).split()), "authority": authority,
                       "cost_tier": tier, "script": script})
    if len({s["name"] for s in skills}) != len(skills):
        errors.append("skill names must be unique")

    agent = None
    if archetype == "agent":
        a = raw.get("agent") or {}
        if not isinstance(a, dict):
            errors.append("`agent` must be an object")
            a = {}
        runtime = a.get("runtime", "ide")
        if runtime not in RUNTIMES:
            errors.append(f"agent.runtime must be one of {', '.join(RUNTIMES)}")
        tool_scope = a.get("tool_scope")
        if tool_scope is not None and not isinstance(tool_scope, list):
            errors.append("agent.tool_scope must be a list of tool names or null")
        agent = {
            "persona": " ".join(str(a.get("persona") or f"You are {name}. {summary}").split()),
            "runtime": runtime,
            "integrations": _str_list(a.get("integrations"), "agent.integrations", errors),
            "env": _str_list(a.get("env"), "agent.env", errors),
            "tags": _str_list(a.get("tags"), "agent.tags", errors) or [slug],
            "tool_scope": tool_scope,
            "icon": a.get("icon", "Bot"),
            "category": a.get("category", "external"),
        }
        if not skills:
            warnings.append("an agent with no `skills`: it will start with only the core skills — "
                            "name its first capabilities in the intake")
        if runtime == "commandcenter" and stack["id"] == "doe-agent" and "test" not in stack_raw:
            stack["test"] = "python -m pytest tests/ -q && python .harness/harness.py test"
            stack["install"] = "python -m pip install -r requirements.txt"
    elif raw.get("agent"):
        warnings.append("`agent` is ignored: the archetype is not `agent`")

    ci = raw.get("ci", "github")
    if ci not in ("github", "none"):
        errors.append("`ci` must be github or none")

    intake = {
        "name": name, "slug": slug, "module": module, "summary": summary,
        "owner": str(raw.get("owner", "")).strip(),
        "archetype": archetype if archetype in archetypes else "other",
        "stack": stack, "hosts": hosts, "capabilities": caps,
        "constraints": constraints, "gates": gates, "scopes": scopes, "brief": brief,
        "skills": skills, "agent": agent, "ci": ci,
    }
    return intake, errors, warnings


# ───────────────────────────────────────────────────────────────── context ──

def _cell(text: str) -> str:
    return text.replace("|", "\\|")


def commands_table(stack: dict) -> str:
    rows = ["| Task | Command |", "|---|---|"]
    for key, label in COMMAND_ROWS:
        value = stack.get(key, "")
        if value:
            rows.append(f"| {label} | `{_cell(value)}` |")
        elif key == "test":
            rows.append(f"| {label} | {TODO}: the one-line test command |")
    return "\n".join(rows)


def _bullets(items: list[str], empty: str) -> str:
    return "\n".join(f"- {i}" for i in items) if items else f"- {empty}"


CI_SETUP = {
    "uv": ["- uses: astral-sh/setup-uv@v5", "- run: uv sync"],
    "pnpm": ["- uses: pnpm/action-setup@v4", "  with:", "    version: 9", "- uses: actions/setup-node@v4",
             "  with:", "    node-version: \"20\"", "    cache: pnpm", "- run: pnpm install --frozen-lockfile"],
    "npm": ["- uses: actions/setup-node@v4", "  with:", "    node-version: \"20\"", "    cache: npm", "- run: npm ci"],
    "go": ["- uses: actions/setup-go@v5", "  with:", "    go-version-file: go.mod"],
    "rust": ["- uses: dtolnay/rust-toolchain@stable"],
    "dotnet": ["- uses: actions/setup-dotnet@v4", "  with:", "    dotnet-version: \"8.0.x\""],
    "flutter": ["- uses: subosito/flutter-action@v2", "  with:", "    channel: stable", "- run: flutter pub get"],
    "platformio": ["- uses: actions/setup-python@v5", "  with:", "    python-version: \"3.12\"",
                   "- run: pip install platformio"],
    "python": ["- uses: actions/setup-python@v5", "  with:", "    python-version: \"3.12\"",
               "- run: if [ -f requirements.txt ]; then pip install -r requirements.txt; fi"],
}


def ci_test_steps(stack: dict) -> str:
    lines = list(CI_SETUP.get(stack.get("ci", ""), []))
    test = stack.get("test", "")
    if test:
        # A block scalar carries any command text (colons, quotes, #) without YAML escaping.
        lines += ["- name: Test", "  run: |", f"    {test}"]
    else:
        lines += [f"# {TODO}: set up the toolchain above and run the project's test command.",
                  "- name: Test", "  run: echo \"no test command configured yet\" && exit 1"]
    return "\n".join("      " + ln for ln in lines)


def _py_str(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"')


def _docstring(text: str) -> str:
    """Text that can sit inside a triple-quoted docstring: C:\\Users or a stray \"\"\" would break it."""
    return text.replace("\\", "\\\\").replace('"""', "'''")


# Names agents.py already defines; a skill must never shadow them.
AGENTS_PY_NAMES = {"describe_skills", "build_agent", "build_agents", "SYSTEM_PROMPT"}


def tool_name(skill: str) -> str:
    """A safe Python identifier for a skill's tool: `3d-render` and `build-agent` get a prefix."""
    import keyword
    fn = skill.replace("-", "_")
    if not fn.isidentifier() or keyword.iskeyword(fn) or fn in AGENTS_PY_NAMES or fn.startswith("_"):
        fn = "skill_" + fn
    return fn


def tool_functions(skills: list[dict]) -> tuple[str, str]:
    funcs, names = [], []
    for s in skills:
        fn = tool_name(s["name"])
        doc = _docstring(s["description"][:400])
        funcs.append(
            f'async def {fn}(args: str = "") -> str:\n'
            f'    """{doc} args: command-line arguments for scripts/{s["script"]}.py (see --help)."""\n'
            f'    return await _run(_skill_script("{s["name"]}", "{s["script"]}.py", args))\n'
        )
        names.append(f"            {fn},")
    return "\n\n".join(funcs), "\n".join(names)


def env_lines(agent: dict | None) -> str:
    if not agent:
        return "# (none yet — add one line per secret a script reads)"
    keys: list[str] = []
    if agent["runtime"] == "commandcenter":
        keys += ["LITELLM_BASE_URL=http://127.0.0.1:8080", "LITELLM_MASTER_KEY=sk-local"]
    for integ in agent["integrations"]:
        keys += [f"{k}=" for k in INTEGRATION_ENV.get(integ, [f"{integ.upper().replace('-', '_')}_API_KEY"])]
    keys += [f"{k}=" if "=" not in k else k for k in agent["env"]]
    keys = _dedupe(keys)
    return "\n".join(keys) if keys else "# (none yet — add one line per secret a script reads)"


def harness_map(intake: dict) -> str:
    hosts, caps = intake["hosts"], intake["capabilities"]
    rows = [("`AGENTS.md` (+ nested `*/AGENTS.md`)", "The DOX contract every agent host reads")]
    if "claude-code" in hosts:
        rows += [("`CLAUDE.md`", "Claude Code entry point → AGENTS.md"),
                 ("`.claude/AGENTS.md`", "Claude Code harness: hooks, settings, subagents, commands"),
                 ("`.claude/skills/`", "Generated skill proxies (never hand-edit)")]
    if "copilot" in hosts:
        rows.append(("`.github/copilot-instructions.md`", "GitHub Copilot entry point → AGENTS.md"))
    rows += [("`.github/skills/<name>/`", "Canonical skills: SKILL.md + scripts/ + tests/"),
             ("`.harness/project.json`", "What this project is (archetype, stack, hosts, capabilities)"),
             ("`.harness/harness.py`", "`check` · `sync` · `test` · `session-start`"),
             ("`docs/AGENTS.md`", "Durable docs: brief, plan, specs, lessons"),
             ("`docs/lessons.md`", "Self-annealing backlog (`anneal.py`)"),
             ("`HANDOFF.md`", "Actions a session leaves the next, each with a Check")]
    if intake["agent"]:
        rows += [("`.github/prompts/system.md`", "Runtime system prompt (hosted runs)"),
                 (f"`.github/agents/{intake['slug']}.agent.md`", "VS Code Copilot Chat agent"),
                 ("`.tmp/scripts/`", "Shared execution utilities (`run_store.py`)"),
                 ("`outputs/<run>/`", "Run records: inputs, step files, status")]
        if intake["agent"]["runtime"] == "commandcenter":
            rows += [("`agents.py` · `config.json`", "CommandCenter contract: `build_agents()` and the registry entry"),
                     ("`tests/test_agents.py`", "CommandCenter CI gate")]
    if caps.get("loop"):
        rows += [("`.claude/agents/` · `.claude/commands/`", "Planning/dispatch loop: `/plan-feature`, `/next-ticket`"),
                 ("`.claude/plan-guard.config.json`", "Owner gates, enforced by a hook (keep in sync with § Owner Gates)"),
                 ("`docs/plan/work-plan.md`", "Dispatch board (written with the owner)")]
    if caps.get("delivery"):
        rows += [("`scripts/dev_up.sh` · `premerge.sh` · `worktree.sh`", "Local stack, merge test, one worktree per session")]
    if intake["ci"] == "github":
        rows.append(("`.github/workflows/harness.yml`", "CI: harness check, skill + hook tests, project tests, secret scan"))
    return "\n".join(f"| {a} | {b} |" for a, b in rows)


def scopes_table(intake: dict) -> str:
    rows = ["| Docs | `docs/AGENTS.md` | Brief, plan, specs, decisions, lessons |"]
    for s in intake["scopes"]:
        rows.append(f"| {s['title']} | `{s['path']}/AGENTS.md` | {_cell(s['covers'])} |")
    return "\n".join(rows)


def build_context(intake: dict) -> dict:
    archetypes_doc, _ = catalogs()
    arch = archetypes_doc["archetypes"][intake["archetype"]]
    stack, brief, agent = intake["stack"], intake["brief"], intake["agent"]
    hosts_line = ", ".join(HOSTS[h] for h in intake["hosts"])
    smoke = arch.get("smoke_check") or f"{TODO}: the one observable check that proves it works."
    desc = intake["summary"]
    ctx = {
        "name": intake["name"], "slug": intake["slug"], "module": intake["module"],
        "summary": intake["summary"], "date": TODAY,
        "owner": intake["owner"] or f"{TODO}: owner",
        "archetype_title": arch["title"], "archetype_noun": arch.get("noun", "project"),
        "stack_title": stack["title"], "hosts_line": hosts_line,
        "commands_table": commands_table(stack),
        "test_cmd": f"`{stack['test']}`" if stack.get("test") else f"{TODO}: the test command",
        "dev_cmd": f"`{stack['dev']}`" if stack.get("dev") else "nothing long-running to start — use the smoke check",
        "smoke_check": smoke,
        "constraints_list": "\n".join(f"{i}. {c}" for i, c in enumerate(intake["constraints"], 1)),
        "gates_list": _bullets(intake["gates"], "none beyond the defaults"),
        "scopes_table": scopes_table(intake),
        "harness_map": harness_map(intake),
        "brief_problem": brief["problem"] or f"{TODO}: the problem, in two or three sentences.",
        "brief_users": brief["users"] or f"{TODO}: who uses it, and what they do today instead.",
        "brief_goals": _bullets(brief["goals"], f"{TODO}: the goals for the first milestone."),
        "brief_non_goals": _bullets(brief["non_goals"], f"{TODO}: what this deliberately does not do."),
        "brief_success": _bullets(brief["success"], f"{TODO}: checkable success criteria."),
        "brief_risks": _bullets(brief["risks"], "None recorded yet."),
        "ci_test_steps": ci_test_steps(stack),
        # agent keys (harmless defaults for other archetypes)
        "persona": agent["persona"] if agent else "",
        "integrations_line": ", ".join(agent["integrations"]) if agent and agent["integrations"] else "none yet",
        "env_lines": env_lines(agent),
        # Each value is escaped for the file it lands in (YAML, Python, JSON, TOML).
        "agent_md_name": "'" + intake["name"].replace("'", "''") + "'",
        "agent_md_description": "'" + desc[:300].replace("'", "''") + "'",
        "description_py": _py_str(desc),
        "name_doc": _docstring(intake["name"]),
        "summary_py": _docstring(desc),
        "description_json": json.dumps(desc),
        # TOML basic strings take JSON's escapes, but not \ud83d surrogate pairs: keep text raw.
        "description_toml": json.dumps(desc[:200], ensure_ascii=False),
        "integrations_json": json.dumps(agent["integrations"] if agent else []),
        "tags_json": json.dumps(agent["tags"] if agent else []),
        "tool_scope_json": json.dumps(agent["tool_scope"] if agent else None),
        "icon_json": json.dumps(agent["icon"] if agent else "Bot"),
        "category_json": json.dumps(agent["category"] if agent else "external"),
    }
    if agent and agent["runtime"] == "commandcenter":
        ctx["runtime_line"] = ("CommandCenter (MAF). `agents.py` `build_agents()` loads `.github/prompts/system.md` "
                               "plus every runtime skill; one `async def` tool per skill script; `config.json` is the "
                               "registry contract (agent_repo_compatibility.md v6.0, DOE Framework repo). Locally, "
                               "Claude Code or Copilot in this workspace runs the same skills.")
        ctx["runtime_rules"] = ("7. Platform tools (`web_search`, `fetch_page`, `write_artifact`, `ask_user`, "
                                "`manage_todo_list`, ...) are injected by CommandCenter — use them; never "
                                "re-implement them.\n")
    else:
        ctx["runtime_line"] = ("IDE-hosted. The agent is Claude Code or GitHub Copilot running in this workspace: "
                               "interactive (`claude`), or headless (`claude -p \"<task>\"`). No runtime code to "
                               "maintain; embed it elsewhere later with the Claude Agent SDK if needed.")
        ctx["runtime_rules"] = ""
    funcs, names = tool_functions(intake["skills"])
    ctx["tool_functions"], ctx["tools_list"] = funcs, names
    if agent:
        ctx["archetype_section"] = render((TEMPLATES / "agent" / "_AGENTS.agent.md.tmpl").read_text(encoding="utf-8"),
                                          ctx, "agent/_AGENTS.agent.md.tmpl")
    else:
        ctx["archetype_section"] = arch.get("section", "")
    ctx["readme_agents_section"] = render(
        (TEMPLATES / "project" / "_README.section.md.tmpl").read_text(encoding="utf-8"), ctx, "_README.section.md.tmpl")
    return ctx


# ──────────────────────────────────────────────────────────────────── plan ──

@dataclass
class Op:
    path: str            # posix, relative to the target
    content: str
    owner: str           # "kit": copied verbatim, upgradable · "project": rendered, the project's own
    kind: str = "create"  # create | compose (AGENTS/CLAUDE/copilot entry) | readme


@dataclass
class Plan:
    ops: list = field(default_factory=list)
    dirs: list = field(default_factory=list)
    gitignore: list = field(default_factory=list)
    gitattributes: list = field(default_factory=list)
    settings: list = field(default_factory=list)
    skills: list = field(default_factory=list)
    required: list = field(default_factory=list)


def dox_framework() -> str:
    """The DOX framework sections of templates/shared/AGENTS.md (single source), minus its guidance quote."""
    text = (TEMPLATES / "shared" / "AGENTS.md").read_text(encoding="utf-8")
    head = text.split("\n---\n", 1)[0]
    lines, out, seen_h2 = head.splitlines(), [], False
    for ln in lines:
        if ln.startswith("## "):
            seen_h2 = True
        if not seen_h2 and ln.startswith(">"):
            continue
        out.append(ln)
    body = re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip()
    return "<!-- harness:dox -->\n" + body + "\n"


def handoff_text(intake: dict) -> str:
    base = (TEMPLATES / "shared" / "HANDOFF.md").read_text(encoding="utf-8")
    head = base.split("### H-1 · Example", 1)[0].rstrip() + "\n\n"
    caps, n = intake["capabilities"], 0
    entries = []

    def entry(title: str, who: str, check: str) -> None:
        nonlocal n
        n += 1
        entries.append(f"### H-{n} · {title} · [{who}]\n- **Task:** none\n- **Check:** {check}\n"
                       f"- **Added:** {TODAY} by the scaffolder\n")

    entry("Finish the scaffold: resolve every unfinished scaffold marker", "AGENT",
          "`python .harness/harness.py check --strict` → exit 1 (FAIL) means still pending")
    if caps.get("loop"):
        entry("Draft the first work-plan rows and one spec from docs/brief.md; agree acceptance criteria "
              "(as commands) with the owner", "AGENT",
              "`ls docs/plan/work-plan.md` → \"No such file\" means still pending")
        entry("Replace the placeholder gate in .claude/plan-guard.config.json with this project's owner gates "
              "(AGENTS.md § Owner Gates), one test case each — in the scaffolding session; once the guard is "
              "live, guard files are owner-only", "AGENT",
              "`grep -c prod-flag-flip .claude/plan-guard.config.json` → a number above 0, or \"No such "
              "file\" (the loop is not installed yet: run `scaffold.py install`), means still pending")
    if caps.get("delivery"):
        entry("Configure the one-command local stack (scripts/dev_up.config)", "AGENT",
              "`ls scripts/dev_up.config` → \"No such file\" means still pending")
    if intake["skills"]:
        names = ", ".join(s["name"] for s in intake["skills"])
        entry(f"Implement the intake skills test-first: {names}", "AGENT",
              "`grep -l \"TODO: implement\" .github/skills/*/scripts/*.py` → any path printed means still pending")
    agent = intake["agent"]
    if agent and (agent["integrations"] or agent["env"]):
        entry("Create .env from .env.example with real credentials (an agent never writes secrets)", "OWNER",
              "`ls .env` → \"No such file\" means still pending")
    if agent and agent["runtime"] == "commandcenter":
        entry("Register the agent in CommandCenter (Control Plane → Agents → Add Agent → repo URL)", "OWNER",
              f"cannot be run by an agent — ask the owner whether `{intake['slug']}` appears in the agent picker")
    return head + "\n".join(entries)


def _walk_layer(layer: Path):
    for path in sorted(layer.rglob("*")):
        if path.is_file() and "__pycache__" not in path.parts and not path.name.startswith("_"):
            yield path


def _layer_ops(layer: Path, ctx: dict, skip) -> list[Op]:
    ops = []
    for src in _walk_layer(layer):
        rel = src.relative_to(layer).as_posix()
        if skip(rel):
            continue
        text = src.read_text(encoding="utf-8")
        if rel.endswith(".tmpl"):
            dest = render(rel[: -len(".tmpl")], ctx, f"path {rel}")
            ops.append(Op(dest, render(text, ctx, f"{layer.name}/{rel}"), "project"))
        else:
            ops.append(Op(render(rel, ctx, f"path {rel}"), text, "kit"))
    return ops


def build_plan(intake: dict, ctx: dict) -> Plan:
    plan = Plan()
    hosts, caps = intake["hosts"], intake["capabilities"]
    claude, copilot, github_ci = "claude-code" in hosts, "copilot" in hosts, intake["ci"] == "github"

    def skip_project(rel: str) -> bool:
        if rel in ("CLAUDE.md.tmpl", ".claude/AGENTS.md") and not claude:
            return True
        if rel == ".github/copilot-instructions.md.tmpl" and not copilot:
            return True
        if (rel.startswith(".github/workflows/") or rel == ".github/pull_request_template.md") and not github_ci:
            return True
        return rel == "README.md.tmpl"  # handled as kind=readme below

    for op in _layer_ops(TEMPLATES / "project", ctx, skip_project):
        if op.path in ("CLAUDE.md", ".github/copilot-instructions.md"):
            op.kind = "compose"
        plan.ops.append(op)

    project_md = render((TEMPLATES / "project" / "_AGENTS.project.md.tmpl").read_text(encoding="utf-8"),
                        ctx, "_AGENTS.project.md.tmpl")
    plan.ops.append(Op("AGENTS.md", dox_framework() + project_md, "project", "compose"))
    plan.ops.append(Op("README.md", render((TEMPLATES / "project" / "README.md.tmpl").read_text(encoding="utf-8"),
                                           ctx, "README.md.tmpl"), "project", "readme"))
    plan.ops.append(Op("HANDOFF.md", handoff_text(intake), "project"))
    anneal = load_module(TEMPLATES / "skills" / "self-annealing" / "scripts" / "anneal.py", "_kit_anneal")
    plan.ops.append(Op("docs/lessons.md", anneal.HEADER, "project"))

    scope_tmpl = (TEMPLATES / "project" / "_scope.AGENTS.md.tmpl").read_text(encoding="utf-8")
    for s in intake["scopes"]:
        rules = s["rules"] or [f"{TODO}: local conventions — naming, where each kind of file goes, "
                               "and the test command for this scope."]
        sctx = dict(ctx, scope_path=s["path"], scope_title=s["title"], scope_covers=s["covers"],
                    scope_covers_short=s["covers"].split(". ")[0].rstrip("."),
                    scope_not_owns=s["not_owns"] or "anything another scope in the root Child DOX Index owns",
                    scope_rules="\n".join(f"- {r}" for r in rules))
        plan.ops.append(Op(f"{s['path']}/AGENTS.md", render(scope_tmpl, sctx, "_scope.AGENTS.md.tmpl"), "project"))
        plan.dirs.append(s["path"])
        plan.required.append(f"{s['path']}/AGENTS.md")

    for name in CORE_SKILLS:
        layer = TEMPLATES / "skills" / name
        for op in _layer_ops(layer, ctx, lambda rel: False):
            op.path = f".github/skills/{name}/{op.path}"
            plan.ops.append(op)
    plan.ops.append(Op(".github/skills/run-and-verify/SKILL.md",
                       render((TEMPLATES / "skills" / "run-and-verify" / "SKILL.md.tmpl").read_text(encoding="utf-8"),
                              ctx, "run-and-verify/SKILL.md.tmpl"), "project"))

    if claude:
        for hook in SESSION_HOOKS:
            for suffix in (".mjs", ".test.mjs"):
                src = TEMPLATES / "claude" / "hooks" / f"{hook}{suffix}"
                plan.ops.append(Op(f".claude/hooks/{hook}{suffix}", src.read_text(encoding="utf-8"), "kit"))
        plan.ops.append(Op(".claude/commands/handoff.md",
                           (TEMPLATES / "claude" / "commands" / "handoff.md").read_text(encoding="utf-8"), "kit"))
        shared = load_json(TEMPLATES / "claude" / "settings.json")
        plan.settings.append({"hooks": {k: v for k, v in shared["hooks"].items() if k in ("SessionStart", "Stop")}})
        plan.settings.append({k: v for k, v in load_json(TEMPLATES / "project" / "_settings.json").items()})

    if caps.get("graphify"):
        base = (TEMPLATES / "shared" / ".graphifyignore").read_text(encoding="utf-8").rstrip() + "\n"
        extra = intake["stack"].get("graphifyignore", [])
        if extra:
            base += "\n# stack: " + intake["stack"]["title"] + "\n" + "\n".join(extra) + "\n"
        plan.ops.append(Op(".graphifyignore", base, "project"))

    agent = intake["agent"]
    if agent:
        plan.ops += _layer_ops(TEMPLATES / "agent", ctx, lambda rel: False)
        plan.dirs += ["inputs", "outputs", "agent-data", ".tmp/scripts"]
        if agent["runtime"] == "commandcenter":
            plan.ops += _layer_ops(TEMPLATES / "agent-commandcenter", ctx, lambda rel: False)

    plan.skills = list(intake["skills"])
    plan.gitignore = GITIGNORE_BASE + (GITIGNORE_AGENT if agent else [])
    stack_ignores = intake["stack"].get("gitignore", [])
    if stack_ignores:
        plan.gitignore += [f"# stack: {intake['stack']['title']}"] + stack_ignores
    plan.gitattributes = list(GITATTRIBUTES)

    required = ["AGENTS.md", "HANDOFF.md", "docs/AGENTS.md", "docs/brief.md", "docs/lessons.md",
                ".harness/harness.py", ".harness/project.json",
                *(f".github/skills/{n}/SKILL.md" for n in (*CORE_SKILLS, "run-and-verify"))]
    if claude:
        required += ["CLAUDE.md", ".claude/settings.json", ".claude/AGENTS.md"]
    if copilot:
        required.append(".github/copilot-instructions.md")
    if github_ci:
        required.append(".github/workflows/harness.yml")
    if agent:
        required += [".github/prompts/system.md", f".github/agents/{intake['slug']}.agent.md",
                     "agent-data/INDEX.md", "inputs/README.md", "outputs/README.md", ".tmp/scripts/run_store.py"]
        if agent["runtime"] == "commandcenter":
            required += ["agents.py", "config.json", "instructions.md", "pyproject.toml", "requirements.txt",
                         "tests/test_agents.py", ".env.example"]
    plan.required = _dedupe(required + plan.required)
    return plan


# ─────────────────────────────────────────────────────────────────── apply ──

def _hook_scripts(item) -> frozenset:
    """The hook scripts a settings hook-group runs, e.g. {'session-handoff.mjs'}."""
    if not isinstance(item, dict) or not isinstance(item.get("hooks"), list):
        return frozenset()
    found = set()
    for h in item["hooks"]:
        if isinstance(h, dict):
            found.update(re.findall(r"[\w.-]+\.(?:mjs|js|sh|py)\b", str(h.get("command", ""))))
    return frozenset(found)


def deep_merge(dst: dict, src: dict) -> bool:
    """Add what is missing; append list items not already present; never clobber. Returns changed.

    A hook group whose scripts are already registered is not added again, even if its
    command or timeout differs: the project's entry wins, and nothing is duplicated.
    """
    changed = False
    for k, v in src.items():
        if isinstance(v, dict) and isinstance(dst.get(k), dict):
            changed |= deep_merge(dst[k], v)
        elif isinstance(v, list) and isinstance(dst.get(k), list):
            registered = {s for item in dst[k] for s in _hook_scripts(item)}
            for item in v:
                scripts = _hook_scripts(item)
                if item in dst[k] or (scripts and scripts <= registered):
                    continue
                dst[k].append(item)
                registered |= scripts
                changed = True
        elif k not in dst:
            dst[k] = v
            changed = True
    return changed


def merge_lines(path: Path, lines: list[str], dry_run: bool) -> int:
    """Append the rules of `lines` that the file lacks, keeping each block's order.

    Ignore files are order-sensitive: `!.env.example` only re-includes a file if it
    comes AFTER the rule that ignores it. So when any rule of the batch is new, every
    negation that follows it in the batch is written again too.
    """
    current = path.read_text(encoding="utf-8-sig").splitlines() if path.exists() else []
    have = {ln.strip() for ln in current}
    missing, new_rule_seen = [], False
    for ln in lines:
        key = ln.strip()
        if not key:
            continue
        negation_after_new = key.startswith("!") and new_rule_seen
        if key not in have or negation_after_new:
            missing.append(ln)
            if not key.startswith("#"):
                have.add(key)  # a rule listed twice in one batch is written once
                new_rule_seen = True
    # Keep comments only when at least one rule under them is new.
    rules = [ln for ln in missing if not ln.startswith("#")]
    if not rules:
        return 0
    if not dry_run:
        text = "\n".join(current).rstrip("\n")
        block = "\n".join(missing)
        write(path, (text + "\n\n" if text else "") + block + "\n")
    return len(rules)


@dataclass
class Result:
    created: list = field(default_factory=list)
    kept: list = field(default_factory=list)
    composed: list = field(default_factory=list)
    merged: list = field(default_factory=list)
    manifest: dict = field(default_factory=dict)


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:  # Path.write_text(newline=) is 3.10+
        fh.write(text)


def compose_with_carry_over(new: str, old: str, name: str) -> str:
    return (new.rstrip("\n") + f"\n\n## Notes carried over from the previous {name}\n\n"
            f"{TODO}: merge these notes into the sections above, then delete this section.\n\n"
            + old.strip() + "\n")


def apply_plan(plan: Plan, target: Path, dry_run: bool) -> Result:
    res = Result()
    for d in plan.dirs:
        if not dry_run:
            (target / d).mkdir(parents=True, exist_ok=True)
    for op in plan.ops:
        dest = target / op.path
        if op.kind == "readme" and dest.exists():
            old = dest.read_text(encoding="utf-8")
            if "<!-- harness:readme -->" in old:
                res.kept.append(op.path)
            else:
                section = op.content.split("<!-- harness:readme -->", 1)
                addition = "<!-- harness:readme -->" + section[1] if len(section) == 2 else op.content
                if not dry_run:
                    write(dest, old.rstrip("\n") + "\n\n" + addition.lstrip("\n"))
                res.merged.append(op.path)
            continue
        if op.kind == "compose" and dest.exists():
            old = dest.read_text(encoding="utf-8")
            marker = "<!-- harness:dox -->" if op.path == "AGENTS.md" else "<!-- harness:entry -->"
            if marker in old:
                res.kept.append(op.path)
            else:
                if not dry_run:
                    write(dest, compose_with_carry_over(op.content, old, op.path))
                res.composed.append(op.path)
            continue
        if dest.exists():
            res.kept.append(op.path)
            if dest.read_text(encoding="utf-8", errors="replace") == op.content:
                res.manifest[op.path] = {"sha256": sha256(op.content), "owner": op.owner}
            continue
        if not dry_run:
            write(dest, op.content)
        res.created.append(op.path)
        res.manifest[op.path] = {"sha256": sha256(op.content), "owner": op.owner}

    n = merge_lines(target / ".gitignore", plan.gitignore, dry_run)
    if n:
        res.merged.append(f".gitignore (+{n})")
    n = merge_lines(target / ".gitattributes", plan.gitattributes, dry_run)
    if n:
        res.merged.append(f".gitattributes (+{n})")

    if plan.settings:
        spath = target / ".claude" / "settings.json"
        current = {}
        if spath.exists():
            try:
                current = json.loads(spath.read_text(encoding="utf-8"))
            except ValueError as exc:
                raise ScaffoldError(f"{spath} is not valid JSON ({exc}); fix it, then re-run") from exc
        changed = False
        for frag in plan.settings:
            changed |= deep_merge(current, json.loads(json.dumps(frag)))
        if changed:
            if not dry_run:
                write(spath, json.dumps(current, indent=2) + "\n")
            res.merged.append(".claude/settings.json")
    return res


def create_intake_skills(plan: Plan, target: Path, dry_run: bool, res: Result) -> None:
    new_skill = load_module(TEMPLATES / "skills" / "skill-authoring" / "scripts" / "new_skill.py", "_kit_new_skill")
    for s in plan.skills:
        base = target / ".github" / "skills" / s["name"]
        if base.exists():
            res.kept.append(f".github/skills/{s['name']}/")
            continue
        if dry_run:
            res.created.append(f".github/skills/{s['name']}/ (SKILL.md, scripts/{s['script']}.py, tests/)")
            continue
        files = new_skill.create_skill(target, s["name"], s["description"], s["when"], s["authority"],
                                       s["cost_tier"], s["script"])
        res.created += [p.relative_to(target).as_posix() for p in files]


def project_record(intake: dict, plan: Plan, previous: dict | None = None) -> dict:
    record = {
        "schema": 1,
        "kit": kit_version(),
        "created": (previous or {}).get("created", TODAY),
        "updated": TODAY,
        **intake,
        "lessons_path": "docs/lessons.md",
        "skill_proxy_dirs": [".claude/skills"] if "claude-code" in intake["hosts"] else [],
        "required_paths": plan.required,
    }
    return record


def run_sync(target: Path) -> list[str]:
    harness = load_module(target / ".harness" / "harness.py", "_project_harness")
    return harness.sync(target)


# ──────────────────────────────────────────────────────────────── commands ──

def read_intake(path: str) -> dict:
    p = Path(path)
    if not p.exists():
        raise ScaffoldError(f"intake file not found: {p}")
    try:
        data = p.read_bytes()
        if data[:2] in (b"\xff\xfe", b"\xfe\xff"):  # Windows PowerShell 5.1 `>` writes UTF-16
            text = data.decode("utf-16")
        else:
            text = data.decode("utf-8-sig")
        raw = json.loads(text)
    except (ValueError, UnicodeDecodeError) as exc:
        raise ScaffoldError(f"{p} is not valid JSON: {exc}") from exc
    if not isinstance(raw, dict):
        raise ScaffoldError("the intake must be a JSON object")
    return raw


def cmd_list() -> int:
    archetypes_doc, stacks = catalogs()
    say("Archetypes (--archetype):")
    for key, a in archetypes_doc["archetypes"].items():
        say(f"  {key:<14} {a['title']} — {a['description']}")
    say("\nStacks (stack id; or `custom` with your own commands):")
    for key, s in stacks.items():
        say(f"  {key:<14} {s['title']}")
    return 0


def cmd_intake_template(archetype: str, stack: str, out: str = "") -> int:
    archetypes_doc, stacks = catalogs()
    if archetype not in archetypes_doc["archetypes"]:
        raise ScaffoldError(f"unknown archetype `{archetype}`")
    arch = archetypes_doc["archetypes"][archetype]
    stack = stack or (arch["suggested_stacks"][0] if arch["suggested_stacks"] else "custom")
    template = {
        "_guide": "Fill every field from the intake interview (SCAFFOLD.md step 2). Keys starting with _ are ignored. "
                  "Remove what you do not need; defaults come from scaffold/catalog/.",
        "name": "Human-readable project name",
        "summary": "One paragraph: what it is, who it is for, what it does.",
        "owner": "Who decides scope and owns the gates",
        "archetype": archetype,
        "stack": stack if stack != "custom" else {"id": "custom", "title": "", "language": "", "install": "",
                                                  "dev": "", "test": "", "lint": "", "build": "", "ci": ""},
        "hosts": ["claude-code", "copilot"],
        "capabilities": arch["capabilities"],
        "scopes": arch["scopes"],
        "constraints": [],
        "gates": [],
        "brief": {"problem": "", "users": "", "goals": [], "non_goals": [], "success": [], "risks": []},
        "skills": [{"name": "example-skill", "description": "What it does. Use when <trigger words>.",
                    "authority": "read", "cost_tier": 0}] if archetype == "agent" else [],
        "ci": "github",
    }
    if archetype == "agent":
        template["agent"] = {"persona": "You are ... (one sentence: role, expertise, who you serve).",
                             "runtime": "ide", "integrations": [], "env": [], "tags": [], "tool_scope": None}
    text = json.dumps(template, indent=2) + "\n"
    if out:
        write(Path(out), text)
        say(f"intake template written to {out} — fill it in, then run check-intake")
    else:
        say(text.rstrip("\n"))
    return 0


def cmd_check_intake(path: str) -> int:
    intake, errors, warnings = normalize(read_intake(path))
    for w in warnings:
        say(f"  [!] {w}")
    if errors:
        say(f"intake: INVALID — {len(errors)} error(s)")
        for e in errors:
            say(f"  [x] {e}")
        return 1
    say(f"intake: OK — {intake['name']} ({intake['archetype']}, {intake['stack']['title']})")
    return 0


def cmd_new(intake_path: str, target: Path, dry_run: bool) -> int:
    intake, errors, warnings = normalize(read_intake(intake_path))
    if errors:
        say(f"scaffold: REFUSED — the intake has {len(errors)} error(s)")
        for e in errors:
            say(f"  [x] {e}")
        return 1
    target.mkdir(parents=True, exist_ok=True) if not dry_run else None
    existing = target / ".harness" / "project.json"
    previous = load_json(existing) if existing.exists() else None
    if previous and previous.get("slug") != intake["slug"]:
        raise ScaffoldError(f"{target} is already scaffolded as `{previous.get('slug')}`; use `upgrade`")

    ctx = build_context(intake)
    plan = build_plan(intake, ctx)
    res = apply_plan(plan, target, dry_run)
    create_intake_skills(plan, target, dry_run, res)

    record = project_record(intake, plan, previous)
    volatile = ("updated", "kit")
    changed_record = previous is not None and (
        {k: v for k, v in record.items() if k not in volatile}
        != {k: v for k, v in previous.items() if k not in volatile})
    if not dry_run:
        # The record always matches the latest intake: a re-run that adds a host or a
        # skill must also add its proxy dirs and required paths, or `check` lies.
        if previous is None:
            write(existing, json.dumps(record, indent=2) + "\n")
            res.created.append(".harness/project.json")
        elif changed_record:
            write(existing, json.dumps(record, indent=2) + "\n")
            res.merged.append(".harness/project.json (updated from the new intake)")
        manifest_path = target / ".harness" / "manifest.json"
        manifest = load_json(manifest_path) if manifest_path.exists() else {"files": {}}
        for path, entry in res.manifest.items():
            manifest["files"].setdefault(path, entry)
        manifest["kit"] = record["kit"]
        write(manifest_path, json.dumps(manifest, indent=2, sort_keys=True) + "\n")
        synced = run_sync(target)
    else:
        synced = []

    if dry_run:
        verdict = "DRY RUN"
    elif res.created:
        verdict = "DONE"
    elif res.merged or res.composed or synced:
        verdict = "UPDATED"
    else:
        verdict = "NO-OP (already scaffolded)"
    say(f"scaffold: {verdict} — {intake['name']} ({intake['archetype']}, {intake['stack']['title']}) → {target}")
    say(f"  created {len(res.created)} · kept {len(res.kept)} (already there) · composed {len(res.composed)} "
        f"· merged {len(res.merged)} · synced {len(synced)}")
    for w in warnings:
        say(f"  [!] {w}")
    for c in res.composed:
        say(f"  [!] {c} existed without the harness marker: composed, old text kept under 'Notes carried over'")
    if dry_run:
        for p in res.created:
            say(f"    + {p}")
        return 0
    caps = intake["capabilities"]
    tools = ", ".join(k for k in ("graphify", "rtk", "loop", "delivery") if caps.get(k)) or "none"
    say("\nNext (SCAFFOLD.md):")
    say(f"  1. Install the tools ({tools}):  python \"{Path(__file__).resolve()}\" install --target \"{target}\"")
    say("  2. Resolve the unfinished markers:  python .harness/harness.py check --strict")
    say("  3. Verify, then ask the user before the first commit.")
    return 0


def cmd_install(target: Path, dry_run: bool) -> int:
    project_path = target / ".harness" / "project.json"
    if not project_path.exists():
        raise ScaffoldError(f"{target} is not scaffolded (.harness/project.json missing): run `new` first")
    project = load_json(project_path)
    caps, hosts = project["capabilities"], project["hosts"]
    skip = {
        "Graphify": not caps.get("graphify"),
        "Rtk": not caps.get("rtk"),
        "Config": not ({"claude-code", "copilot"} & set(hosts)),
        "Dox": True,  # the scaffolder wrote AGENTS.md
        "Loop": not caps.get("loop"),
        "Delivery": not caps.get("delivery"),
    }
    env = os.environ.copy()
    if os.name == "nt":
        shell = shutil.which("pwsh") or shutil.which("powershell")
        if not shell:
            raise ScaffoldError("PowerShell not found: run install.ps1 by hand (SETUP.md §1)")
        cmd = [shell, "-NoProfile", "-File", str(KIT / "install.ps1"), "-Repo", str(target)]
        cmd += [f"-Skip{k}" for k, v in skip.items() if v]
    else:
        if not shutil.which("bash"):
            raise ScaffoldError("bash not found: run install.sh by hand (SETUP.md §1)")
        cmd = ["bash", str(KIT / "install.sh"), str(target)]
        env.update({f"SKIP_{k.upper()}": "1" if v else "0" for k, v in skip.items()})
    say("install: " + " ".join(f'"{c}"' if " " in c else c for c in cmd))
    if dry_run:
        return 0
    r = subprocess.run(cmd, cwd=target, env=env)
    if r.returncode != 0:
        say(f"install: the installer exited {r.returncode} — read its output above")
        return 2
    synced = run_sync(target)
    say(f"install: done · skill proxies synced ({len(synced)} change(s)). "
        "Next: python .harness/harness.py check --strict")
    return 0


def cmd_upgrade(target: Path, dry_run: bool) -> int:
    project_path = target / ".harness" / "project.json"
    manifest_path = target / ".harness" / "manifest.json"
    if not project_path.exists():
        raise ScaffoldError(f"{target} is not scaffolded: nothing to upgrade")
    project = load_json(project_path)
    manifest = load_json(manifest_path) if manifest_path.exists() else {"files": {}}
    raw = {k: v for k, v in project.items() if k in (
        "name", "slug", "summary", "owner", "archetype", "stack", "hosts", "capabilities",
        "constraints", "gates", "scopes", "brief", "skills", "agent", "ci")}
    intake, errors, _ = normalize(raw)
    if errors:
        raise ScaffoldError("the recorded project no longer validates: " + "; ".join(errors))
    plan = build_plan(intake, build_context(intake))
    updated, added, diverged, deleted, same = [], [], [], [], 0
    for op in plan.ops:
        if op.owner != "kit":
            continue
        dest = target / op.path
        entry = manifest["files"].get(op.path)
        if not dest.exists() and entry is not None:
            deleted.append(op.path)  # the project removed a file it once had: respect that
            continue
        if not dest.exists():
            added.append(op.path)
            if not dry_run:
                write(dest, op.content)
            manifest["files"][op.path] = {"sha256": sha256(op.content), "owner": "kit"}
            continue
        current = dest.read_text(encoding="utf-8", errors="replace")
        if current == op.content:
            same += 1
            manifest["files"][op.path] = {"sha256": sha256(op.content), "owner": "kit"}
        elif entry and sha256(current) == entry["sha256"]:
            updated.append(op.path)
            if not dry_run:
                write(dest, op.content)
            manifest["files"][op.path] = {"sha256": sha256(op.content), "owner": "kit"}
        else:
            diverged.append(op.path)
    merged = []
    if not dry_run:
        n = merge_lines(target / ".gitignore", plan.gitignore, False)
        if n:
            merged.append(f".gitignore (+{n})")
        if plan.settings:
            spath = target / ".claude" / "settings.json"
            current = json.loads(spath.read_text(encoding="utf-8")) if spath.exists() else {}
            if any(deep_merge(current, json.loads(json.dumps(f))) for f in plan.settings):
                write(spath, json.dumps(current, indent=2) + "\n")
                merged.append(".claude/settings.json")
        project["kit"] = kit_version()
        project["updated"] = TODAY
        project["required_paths"] = plan.required
        write(project_path, json.dumps(project, indent=2) + "\n")
        manifest["kit"] = project["kit"]
        write(manifest_path, json.dumps(manifest, indent=2, sort_keys=True) + "\n")
        run_sync(target)
    say(f"upgrade: {'DRY RUN' if dry_run else 'DONE'} — {len(updated)} updated · {len(added)} added · "
        f"{same} unchanged · {len(diverged)} diverged (left alone) · {len(deleted)} deleted here (left deleted) "
        f"· merged {len(merged)}")
    for p in updated:
        say(f"  ~ {p}")
    for p in added:
        say(f"  + {p}")
    for p in diverged:
        say(f"  [!] {p} was edited in this project: merge the kit's version by hand "
            f"(templates/ in {KIT_URL})")
    return 0


def main(argv: list[str] | None = None) -> int:
    try:  # agents read this through pipes; Windows defaults pipes to cp1252
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list", help="archetypes and stacks")
    p = sub.add_parser("intake-template", help="print a starter intake.json")
    p.add_argument("--archetype", default="other")
    p.add_argument("--stack", default="")
    p.add_argument("--out", default="", help="write to this file (UTF-8) instead of stdout")
    p = sub.add_parser("check-intake", help="validate an intake")
    p.add_argument("--intake", required=True)
    p = sub.add_parser("new", help="scaffold a workspace")
    p.add_argument("--intake", required=True)
    p.add_argument("--target", default=".")
    p.add_argument("--dry-run", action="store_true")
    for name in ("install", "upgrade"):
        p = sub.add_parser(name)
        p.add_argument("--target", default=".")
        p.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    try:
        if args.cmd == "list":
            return cmd_list()
        if args.cmd == "intake-template":
            return cmd_intake_template(args.archetype, args.stack, args.out)
        if args.cmd == "check-intake":
            return cmd_check_intake(args.intake)
        target = Path(args.target).resolve()
        if args.cmd == "new":
            return cmd_new(args.intake, target, args.dry_run)
        if args.cmd == "install":
            return cmd_install(target, args.dry_run)
        if args.cmd == "upgrade":
            return cmd_upgrade(target, args.dry_run)
    except (ValueError, FileExistsError) as exc:
        # Validation should catch these first; if one slips through, refuse with the
        # reason instead of a traceback, and say how to recover.
        say(f"scaffold: REFUSED — {exc}. Fix the intake and re-run `new` (it is idempotent).")
        return 1
    except ScaffoldError as exc:
        say(f"scaffold: REFUSED — {exc}")
        return 1
    return 1


if __name__ == "__main__":
    sys.exit(main())
