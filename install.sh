#!/usr/bin/env bash
# coding-agent-setup installer (Unix / macOS / Git-Bash on Windows).
#
# Sets up a codebase for token-efficient agent development:
#   1. Graphify  — tree-sitter code knowledge graph (biggest token win on big repos)
#   2. RTK       — shell-output compressor (60-90% on tests/lint/git/docker)
#   3. Config    — RTK hook/nudge + project instructions
#   4. DOX       — seed a root AGENTS.md architecture contract (place-before-building)
#   5. Loop      — supervisor-worker planning + dispatch agents, commands, owner-gate hook
#
# Idempotent and non-destructive: merges into existing config, never overwrites,
# no-ops anything already installed. Run from the TARGET repo root, or pass it:
#   bash coding-agent-setup/install.sh [/path/to/repo]
#
# Env toggles: SKIP_GRAPHIFY=1  SKIP_RTK=1  SKIP_CONFIG=1  SKIP_DOX=1  SKIP_LOOP=1

set -uo pipefail

# --- locate self, target repo, templates ----------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEMPLATES="$SCRIPT_DIR/templates"
REPO="${1:-$(pwd)}"
REPO="$(cd "$REPO" && pwd)"

say()  { printf '\033[1;36m[setup]\033[0m %s\n' "$*"; }
ok()   { printf '\033[1;32m  ok  \033[0m %s\n' "$*"; }
skip() { printf '\033[1;33m skip \033[0m %s\n' "$*"; }
warn() { printf '\033[1;31m warn \033[0m %s\n' "$*"; }
have() { command -v "$1" >/dev/null 2>&1; }

# JSON deep-merge helper (python is near-universal; jq optional).
# merge_json <target-file> <json-to-merge>  — adds missing keys; appends missing
# list items (so a second hook lands next to an existing one). Never clobbers.
merge_json() {
  local target="$1" addition="$2"
  python - "$target" "$addition" <<'PY'
import json, sys, os
target, addition = sys.argv[1], sys.argv[2]
add = json.loads(addition)
cur = {}
if os.path.exists(target):
    try:
        cur = json.load(open(target, encoding="utf-8"))
    except Exception:
        print(f"__ERR__ existing {target} is not valid JSON; leaving untouched", file=sys.stderr)
        sys.exit(3)
def deep(dst, src):
    for k, v in src.items():
        if isinstance(v, dict) and isinstance(dst.get(k), dict):
            deep(dst[k], v)
        elif isinstance(v, list) and isinstance(dst.get(k), list):
            # append only entries that aren't already there — keeps re-runs a no-op
            for item in v:
                if item not in dst[k]:
                    dst[k].append(item)
        elif k not in dst:            # never clobber an existing key
            dst[k] = v
deep(cur, add)
os.makedirs(os.path.dirname(target) or ".", exist_ok=True)
json.dump(cur, open(target, "w", encoding="utf-8"), indent=2)
open(target, "a", encoding="utf-8").write("\n")
print(f"merged into {target}")
PY
}

say "target repo: $REPO"
cd "$REPO"

# ============================================================ 1. Graphify ===
if [ "${SKIP_GRAPHIFY:-0}" = "1" ]; then
  skip "Graphify (SKIP_GRAPHIFY=1)"
else
  if ! have graphify; then
    # package is 'graphifyy' (two y's); the command is 'graphify'
    if have uv; then
      say "installing Graphify CLI (uv tool install graphifyy)"
      uv tool install graphifyy >/dev/null 2>&1
    elif have pipx; then
      say "installing Graphify CLI (pipx install graphifyy)"
      pipx install graphifyy >/dev/null 2>&1
    elif have pip; then
      say "installing Graphify CLI (pip install graphifyy)"
      pip install graphifyy >/dev/null 2>&1
    else
      warn "no uv/pipx/pip — install Python ≥3.10 + uv, then: uv tool install graphifyy"
    fi
    have graphify \
      && ok "Graphify installed ($(graphify --version 2>/dev/null))" \
      || warn "graphify not on PATH — run 'uv tool update-shell' (or 'pipx ensurepath'), open a new shell, re-run"
  else
    ok "Graphify already present ($(graphify --version 2>/dev/null))"
  fi

  if have graphify; then
    # index scoping (gitignore-syntax excludes) — only if repo has none
    if [ ! -f .graphifyignore ] && [ -f "$TEMPLATES/shared/.graphifyignore" ]; then
      cp "$TEMPLATES/shared/.graphifyignore" .graphifyignore
      ok "wrote .graphifyignore (edit the exclude list for this repo)"
    else
      skip ".graphifyignore exists"
    fi
    # register the /graphify skill + query-first hook (repo-scoped)
    graphify install --project >/dev/null 2>&1 \
      && ok "Claude Code: /graphify skill + query-first hook (graphify install --project)" \
      || warn "graphify install --project failed"
    graphify install --project --platform copilot >/dev/null 2>&1 \
      && ok "Copilot CLI: /graphify skill (graphify install --project --platform copilot)" || true
    # build the code graph (deterministic AST pass, fully offline, no API key)
    if [ ! -d graphify-out ]; then
      say "building code graph (graphify extract . --code-only) — may take a minute"
      graphify extract . --code-only >/dev/null 2>&1 \
        && ok "graph built (graphify-out/)" \
        || warn "extract failed — run '/graphify .' in your assistant instead"
    else
      skip "graphify-out exists (run '/graphify . --update' to refresh)"
    fi
  fi
fi

# ============================================================ 2. RTK =========
if [ "${SKIP_RTK:-0}" = "1" ]; then
  skip "RTK (SKIP_RTK=1)"
elif have rtk; then
  ok "RTK already present ($(rtk --version 2>/dev/null))"
else
  say "installing RTK"
  if have winget;  then winget install rtk-ai.rtk --exact --accept-package-agreements --accept-source-agreements --disable-interactivity >/dev/null 2>&1
  elif have brew;  then brew install rtk-ai/tap/rtk >/dev/null 2>&1
  elif have cargo; then cargo install --git https://github.com/rtk-ai/rtk >/dev/null 2>&1
  else warn "no winget/brew/cargo — install rtk manually from https://www.rtk-ai.app"; fi
  have rtk && ok "RTK installed ($(rtk --version 2>/dev/null))" || warn "RTK not on PATH (open a new shell?)"
fi

# ============================================================ 3. Config ======
if [ "${SKIP_CONFIG:-0}" = "1" ]; then
  skip "config (SKIP_CONFIG=1)"
else
  # Graphify host registration is handled in step 1 (graphify install --project).
  # Its optional MCP server needs graphifyy[mcp] importable from `python`, so it
  # is left as a manual step — see SETUP.md §2 and templates/*/mcp.json.

  # -- Claude Code: RTK hook + settings (settings also registers plan-guard) --
  if [ -f "$TEMPLATES/claude/hooks/rtk-bash.sh" ]; then
    mkdir -p .claude/hooks
    cp "$TEMPLATES/claude/hooks/rtk-bash.sh" .claude/hooks/rtk-bash.sh
    chmod +x .claude/hooks/rtk-bash.sh
    merge_json ".claude/settings.json" "$(cat "$TEMPLATES/claude/settings.json")" >/dev/null 2>&1
    ok ".claude/ RTK hook + settings"
  fi

  # -- Copilot instructions: append RTK block if absent --
  CPI=".github/copilot-instructions.md"
  if [ -f "$TEMPLATES/copilot/copilot-instructions-rtk-block.md" ]; then
    mkdir -p .github
    if [ -f "$CPI" ] && grep -q "prefix noisy commands with .rtk." "$CPI" 2>/dev/null; then
      skip "copilot-instructions.md already has RTK block"
    else
      printf '\n' >> "$CPI"
      cat "$TEMPLATES/copilot/copilot-instructions-rtk-block.md" >> "$CPI"
      ok "appended RTK block to $CPI"
    fi
  fi
fi

# ============================================================ 4. DOX =========
# Seed a root AGENTS.md "DOX" architecture contract (place-before-building) if
# the repo has none. Non-destructive: never touches an existing AGENTS.md.
if [ "${SKIP_DOX:-0}" = "1" ]; then
  skip "DOX architecture contract (SKIP_DOX=1)"
elif [ -f AGENTS.md ]; then
  skip "AGENTS.md exists (DOX contract already present — leaving it untouched)"
elif [ -f "$TEMPLATES/shared/AGENTS.md" ]; then
  cp "$TEMPLATES/shared/AGENTS.md" AGENTS.md
  ok "wrote AGENTS.md (DOX root — fill in the <...> placeholders for this repo)"
else
  warn "DOX template missing from kit ($TEMPLATES/shared/AGENTS.md)"
fi

# ============================================================ 5. LOOP =======
# Planning + dispatch loop: subagent roles, slash commands, and the owner-gate
# hook. Copies files only if absent — never overwrites a customised agent.
# Deliberately does NOT seed a work plan: a board of placeholder rows is worse
# than no board. See SETUP.md §6 and ORCHESTRATION.md.
if [ "${SKIP_LOOP:-0}" = "1" ]; then
  skip "planning + dispatch loop (SKIP_LOOP=1)"
elif [ ! -d "$TEMPLATES/claude/agents" ]; then
  warn "loop templates missing from kit ($TEMPLATES/claude/agents)"
else
  mkdir -p .claude/agents .claude/commands .claude/hooks
  copied=0; kept=0
  for f in "$TEMPLATES"/claude/agents/*.md; do
    dest=".claude/agents/$(basename "$f")"
    if [ -f "$dest" ]; then kept=$((kept+1)); else cp "$f" "$dest"; copied=$((copied+1)); fi
  done
  for f in "$TEMPLATES"/claude/commands/*.md; do
    dest=".claude/commands/$(basename "$f")"
    if [ -f "$dest" ]; then kept=$((kept+1)); else cp "$f" "$dest"; copied=$((copied+1)); fi
  done
  ok "dispatch-loop agents + commands ($copied added, $kept left as-is)"

  for f in plan-guard.mjs plan-guard.test.mjs; do
    if [ -f ".claude/hooks/$f" ]; then skip ".claude/hooks/$f exists"
    else cp "$TEMPLATES/claude/hooks/$f" ".claude/hooks/$f"; ok ".claude/hooks/$f"; fi
  done

  if [ -f .claude/plan-guard.config.json ]; then
    skip "plan-guard.config.json exists (your gates left untouched)"
  else
    cp "$TEMPLATES/claude/plan-guard.config.json" .claude/plan-guard.config.json
    ok "plan-guard.config.json — EDIT IT: add this project's production flags and gates"
  fi

  if have node; then
    node .claude/hooks/plan-guard.test.mjs >/dev/null 2>&1 \
      && ok "plan-guard self-test passed" \
      || warn "plan-guard self-test FAILED — run: node .claude/hooks/plan-guard.test.mjs"
  else
    warn "node not found — plan-guard cannot run; the loop would be UNGUARDED"
  fi

  # Copilot / no-subagent hosts: sequential-role instructions
  CPI=".github/copilot-instructions.md"
  if [ -f "$TEMPLATES/copilot/orchestration-instructions.md" ]; then
    mkdir -p .github
    if [ -f "$CPI" ] && grep -q "Planning and dispatch loop" "$CPI" 2>/dev/null; then
      skip "copilot-instructions.md already has the dispatch-loop block"
    else
      printf '\n' >> "$CPI"
      cat "$TEMPLATES/copilot/orchestration-instructions.md" >> "$CPI"
      ok "appended dispatch-loop block to $CPI"
    fi
  fi

  say "next: copy templates/shared/work-plan.md + spec.md into your docs and fill them in by hand (SETUP.md §6.3)"
fi

# ============================================================ Verify =========
say "verify:"
have graphify && { graphify --version 2>/dev/null; [ -f graphify-out/graph.json ] && ok "graphify-out/graph.json present"; } || true
have rtk && rtk --version || true
say "done. Read coding-agent-setup/SETUP.md §7 and report the numbers."
