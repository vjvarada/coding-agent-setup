#!/usr/bin/env bash
# RTK (Rust Token Killer) PreToolUse hook for Claude Code Bash calls.
#
# Shrinks noisy shell OUTPUT (pytest/ruff/git/docker/...) before it reaches the
# agent context — typically 60-90% fewer tokens, with full output tee'd to disk
# on failure so nothing is lost.
#
# WHY A WRAPPER INSTEAD OF `rtk init`'s DEFAULT HOOK:
# The stock rtk hook rewrites EVERYTHING, including two cases that are wrong:
#   1. `uv run pytest ...` -> `uv run rtk pytest ...`  (BROKEN: rtk is a
#      standalone binary, not a uv-managed tool)
#   2. `cat FILE` / head / tail -> `rtk read FILE`     (UNWANTED: Graphify and
#      the built-in Read tool give better, symbol-aware file context)
# So this wrapper is a STRICT ALLOWLIST: it rewrites only safe command classes
# and passes everything else through untouched.
#
# SECURITY NOTE: to make the rewrite take effect, the hook returns
# permissionDecision:"allow", which auto-approves the REWRITTEN command. The
# allowlist below IS the security boundary — only benign read/test/lint/git
# commands ever reach that path. Surface this tradeoff to the user.
#
# Disable: remove the hook from .claude/settings.json, or set RTK_DISABLE=1.

set -euo pipefail

[ "${RTK_DISABLE:-0}" = "1" ] && exit 0
command -v rtk >/dev/null 2>&1 || exit 0   # no rtk -> no-op, don't break Bash

payload="$(cat)"

# Extract tool_name + command. jq if present, else python (Git-Bash lacks jq).
if command -v jq >/dev/null 2>&1; then
  tool_name="$(printf '%s' "$payload" | jq -r '.tool_name // empty' 2>/dev/null)"
  command="$(printf '%s' "$payload" | jq -r '.tool_input.command // empty' 2>/dev/null)"
else
  fields="$(printf '%s' "$payload" | python -c '
import sys, json
try: d = json.load(sys.stdin)
except Exception: sys.exit(0)
print(d.get("tool_name", ""))
print(d.get("tool_input", {}).get("command", ""))
' 2>/dev/null)"
  tool_name="$(printf '%s\n' "$fields" | sed -n '1p')"
  command="$(printf '%s\n' "$fields" | sed -n '2p')"
fi

[ "$tool_name" = "Bash" ] && [ -n "$command" ] || exit 0

# --- strict allowlist / denylist ------------------------------------------
first_word="$(printf '%s' "$command" | sed -E 's/^[[:space:]]+//' | awk '{print $1}')"

case "$command" in
  uv\ *|*\ uv\ *) exit 0 ;;   # uv is the runner; rtk inserts itself wrong
esac
case "$first_word" in
  cat|less|more|head|tail|bat) exit 0 ;;   # keep file reads native
  git|pytest|ruff|mypy|docker|psql|pip|npm|pnpm|npx|tsc|eslint|prettier|go|cargo|jest|vitest|playwright|kubectl|find|grep|rg|ls|tree|diff|wc|curl|gh) ;;
  *) exit 0 ;;
esac

rewritten="$(rtk hook check "$command" 2>/dev/null || true)"
case "$rewritten" in ''|No\ rewrite\ for:*) exit 0 ;; esac
[ "$rewritten" = "$command" ] && exit 0
# defense in depth: never reintroduce the broken forms
case "$rewritten" in *uv\ run\ rtk\ *|rtk\ read\ *) exit 0 ;; esac

# The rewrite is only honored WITH permissionDecision alongside updatedInput.
if command -v jq >/dev/null 2>&1; then
  jq -cn --arg cmd "$rewritten" \
    '{hookSpecificOutput:{hookEventName:"PreToolUse",permissionDecision:"allow",permissionDecisionReason:"rtk output compression",updatedInput:{command:$cmd}}}'
else
  python - "$rewritten" <<'PY'
import json, sys
print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse",
      "permissionDecision": "allow", "permissionDecisionReason": "rtk output compression",
      "updatedInput": {"command": sys.argv[1]}}}))
PY
fi
exit 0
