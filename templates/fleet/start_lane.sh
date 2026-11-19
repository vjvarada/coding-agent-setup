#!/usr/bin/env bash
# start_lane.sh <name> [model] — start one lane as a Claude Code background session.
#
# Reads the start note from $LANES_DIR/<name>.txt (the stream, then the common
# rules of templates/fleet/lane-rules.md). Runs in $REPO_DIR. FLEET.md §4.1.
# Host: Claude Code. Other hosts need their own background-session command.
set -euo pipefail
name="${1:?usage: start_lane.sh <name> [model]}"
model="${2:-sonnet}"
LANES_DIR="${LANES_DIR:-$HOME/lanes}"
REPO_DIR="${REPO_DIR:?set REPO_DIR to the repo checkout}"
note="$LANES_DIR/$name.txt"
[ -f "$note" ] || { echo "no start note at $note" >&2; exit 1; }
cd "$REPO_DIR"
nohup claude --bg --remote-control "$name" -n "$name" --model "$model" \
  --permission-mode auto "$(cat "$note")" > "$LANES_DIR/start-$name.out" 2>&1 < /dev/null &
echo "started $name (model $model). List it with: claude agents --json"
