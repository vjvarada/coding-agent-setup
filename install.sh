#!/usr/bin/env bash
# coding-agent-setup installer (Unix / macOS / Git-Bash on Windows).
#
# Sets up a codebase for token-efficient agent development:
#   1. CodeGraph  — symbol/call-graph MCP server (biggest token win on big repos)
#   2. RTK        — shell-output compressor (60-90% on tests/lint/git/docker)
#   3. Config     — MCP registration + RTK hook/nudge + project instructions
#
# Idempotent and non-destructive: merges into existing config, never overwrites,
# no-ops anything already installed. Run from the TARGET repo root, or pass it:
#   bash coding-agent-setup/install.sh [/path/to/repo]
#
# Env toggles: SKIP_CODEGRAPH=1  SKIP_RTK=1  SKIP_CONFIG=1

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
# merge_json <target-file> <json-to-merge>  — merges keys, target wins on leaf conflicts? no: source adds only missing.
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

# ============================================================ 1. CodeGraph ===
if [ "${SKIP_CODEGRAPH:-0}" = "1" ]; then
  skip "CodeGraph (SKIP_CODEGRAPH=1)"
else
  if ! have codegraph; then
    if have npm; then
      say "installing CodeGraph CLI (npm -g @colbymchenry/codegraph)"
      npm install -g @colbymchenry/codegraph >/dev/null 2>&1 \
        && ok "CodeGraph installed ($(codegraph --version 2>/dev/null))" \
        || warn "npm install failed — install Node/npm then re-run"
    else
      warn "npm not found — install Node.js ≥18, then: npm i -g @colbymchenry/codegraph"
    fi
  else
    ok "CodeGraph already present ($(codegraph --version 2>/dev/null))"
  fi

  if have codegraph; then
    # index config (scoped exclude list) — only if repo has none
    if [ ! -f codegraph.json ] && [ -f "$TEMPLATES/shared/codegraph.json" ]; then
      cp "$TEMPLATES/shared/codegraph.json" codegraph.json
      ok "wrote codegraph.json (edit the exclude list for this repo)"
    else
      skip "codegraph.json exists"
    fi
    if [ ! -d .codegraph ]; then
      say "building initial index (codegraph init) — may take a minute"
      codegraph init . >/dev/null 2>&1 && ok "index built" || warn "codegraph init failed"
    else
      skip ".codegraph index exists (run 'codegraph sync .' to refresh)"
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
  CG='{"type":"stdio","command":"codegraph","args":["serve","--mcp"]}'

  # -- Claude Code: .mcp.json (key mcpServers) --
  merge_json ".mcp.json" "{\"mcpServers\":{\"codegraph\":$CG}}" && ok ".mcp.json (Claude Code MCP)" \
    || warn ".mcp.json merge skipped (see message above)"

  # -- Claude Code: RTK hook + settings --
  if [ -f "$TEMPLATES/claude/hooks/rtk-bash.sh" ]; then
    mkdir -p .claude/hooks
    cp "$TEMPLATES/claude/hooks/rtk-bash.sh" .claude/hooks/rtk-bash.sh
    chmod +x .claude/hooks/rtk-bash.sh
    merge_json ".claude/settings.json" "$(cat "$TEMPLATES/claude/settings.json")" >/dev/null 2>&1
    ok ".claude/ RTK hook + settings"
  fi

  # -- VS Code Copilot: .vscode/mcp.json (key servers) --
  merge_json ".vscode/mcp.json" "{\"servers\":{\"codegraph\":$CG}}" >/dev/null 2>&1 \
    && ok ".vscode/mcp.json (Copilot MCP)"

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

# ============================================================ Verify =========
say "verify:"
have codegraph && codegraph status . 2>/dev/null | head -3 || true
have rtk && rtk --version || true
say "done. Read coding-agent-setup/SETUP.md §6 and report the numbers."
