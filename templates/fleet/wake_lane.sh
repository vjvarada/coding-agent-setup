#!/usr/bin/env bash
# wake_lane.sh <session id> <message file> — type a message into a background lane.
#
# Attaches to the session in a throwaway tmux terminal, types the message,
# presses Enter TWICE (one Enter left the text unsubmitted), and detaches.
# It works by timing, so it can fail in silence. After each send, confirm that
# the text is in the lane's transcript, then that the lane read it and acted
# (FLEET.md §4.2). Write the message with no apostrophes or shell quotes.
# Host: Claude Code (`claude attach`) and tmux.
set -euo pipefail
id="${1:?usage: wake_lane.sh <session id> <message file>}"
msg="$(cat "${2:?message file}")"
s="wake$$"
tmux kill-session -t "$s" 2>/dev/null || true
tmux new-session -d -s "$s" -x 220 -y 50 "claude attach $id"
sleep 8
tmux send-keys -t "$s" -l "$msg"; sleep 2
tmux send-keys -t "$s" Enter; sleep 3
tmux send-keys -t "$s" Enter; sleep 3
tmux send-keys -t "$s" C-z; sleep 1
tmux kill-session -t "$s" 2>/dev/null || true
echo "sent to $id. Now confirm it in the transcript:"
echo "  grep -c \"<a phrase of the message>\" \$(ls -t ~/.claude/projects/*/$id*.jsonl | head -1)"
