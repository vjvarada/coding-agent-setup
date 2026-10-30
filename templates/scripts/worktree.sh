#!/usr/bin/env bash
# worktree.sh: start a session in its own worktree, and tear one down safely.
#
# WHY THIS EXISTS. Two sessions in one checkout fight over the same working
# tree. One switches branch under the other, `git status` mixes their edits,
# and a `reset --hard` by either destroys the other's uncommitted work. A
# worktree gives each session its own directory and its own branch, sharing
# one `.git`. That is the point: parallel sessions, one history.
#
# Usage:
#   bash scripts/worktree.sh new <slug> [base]   # base defaults to <remote>/<branch>
#   bash scripts/worktree.sh list
#   bash scripts/worktree.sh remove [--force] <slug>
#
# `remove` refuses a worktree with uncommitted or untracked files. Only
# `remove --force <slug>` deletes them.
#
# Config (environment variables, all optional):
#   WORKTREE_ROOT         prefix of every worktree path. A worktree lives at
#                         <WORKTREE_ROOT>-<slug>. Default: a sibling of the repo,
#                         <repo-parent>/wt-<repo-name>. Never inside the repo:
#                         inside, every tool that walks the tree (linters, test
#                         runners, `git status`) finds a second copy of the code.
#   WORKTREE_REMOTE       default: origin
#   WORKTREE_BASE_BRANCH  default: main
#
# `remove` IS THE DANGEROUS ONE. A worktree may carry a `node_modules` JUNCTION
# that points at the primary checkout's real directory. `git worktree remove`
# follows the junction and deletes THE REAL ONE. This has happened.
#
# The guard is `cmd //c rmdir`, which is precise where `rm -rf` is not:
#   * given a junction, it removes the LINK and never the target;
#   * given a real non-empty directory, it REFUSES.
# So the safe case succeeds and the dangerous case stops. No "is this a
# junction" test is needed, and none can get the answer wrong.
set -euo pipefail

# The MAIN checkout, even when this runs from inside a worktree: the common git
# dir is always <main>/.git, so its parent is the main checkout. --show-toplevel
# would return the worktree itself and build wt-wt-... paths.
COMMON="$(git rev-parse --git-common-dir)"
COMMON="$(cd "$COMMON" && pwd)"
REPO="$(dirname "$COMMON")"
REMOTE="${WORKTREE_REMOTE:-origin}"
BRANCH="${WORKTREE_BASE_BRANCH:-main}"
WT_ROOT="${WORKTREE_ROOT:-$(dirname "$REPO")/wt-$(basename "$REPO")}"
cmd="${1:-}"

usage() { sed -n '2,32p' "$0" | sed 's/^# \{0,1\}//'; exit 1; }

wt_path() { printf '%s-%s' "$WT_ROOT" "$1"; }

case "$cmd" in
new)
  slug="${2:-}"; base="${3:-$REMOTE/$BRANCH}"
  [ -n "$slug" ] || usage
  path="$(wt_path "$slug")"
  [ -e "$path" ] && { echo "!! $path already exists"; exit 1; }

  # Fetch first. A worktree cut from a stale base starts behind, and every PR
  # from it opens with an avoidable merge.
  git -C "$REPO" fetch --quiet "$REMOTE"
  git -C "$REPO" worktree add -b "$slug" "$path" "$base"

  echo
  echo "   worktree: $path"
  echo "   branch:   $slug   (from $base)"
  echo
  echo "   cd \"$path\""
  echo
  echo "   Install dependencies here. Do not link node_modules or .venv from"
  echo "   the primary checkout: tools resolve through the link to the wrong root."
  echo "   Run the stack with:  bash scripts/dev_up.sh"
  ;;

list)
  git -C "$REPO" worktree list
  # Mark worktrees that hold uncommitted work, so nobody prunes one blindly.
  git -C "$REPO" worktree list --porcelain | sed -n 's/^worktree //p' | while IFS= read -r wtp; do
    if [ "$wtp" != "$REPO" ] && [ -n "$(git -C "$wtp" status --porcelain 2>/dev/null)" ]; then
      echo "   DIRTY (uncommitted work, do not remove): $wtp"
    fi
  done
  echo
  echo "primary checkout: $REPO"
  n="$(git -C "$REPO" worktree list | wc -l)"
  if [ "$n" -gt 6 ]; then
    echo
    echo "!! $n worktrees. Stale ones hold branches nobody reads."
    echo "   Prune the merged, clean ones: bash scripts/worktree.sh remove <slug>"
    echo "   (remove refuses a dirty worktree; DIRTY ones are listed above)"
  fi
  ;;

remove)
  force=0
  if [ "${2:-}" = "--force" ]; then force=1; shift; fi
  slug="${2:-}"
  [ -n "$slug" ] || usage
  path="$(wt_path "$slug")"
  [ -d "$path" ] || { echo "!! no worktree at $path"; exit 1; }

  # REFUSE to delete work that exists nowhere else. Uncommitted and untracked
  # files are lost for good with the folder. Only --force passes this.
  dirty="$(git -C "$path" status --porcelain 2>/dev/null || true)"
  if [ -n "$dirty" ] && [ "$force" != 1 ]; then
    echo "!! $path has uncommitted or untracked work:"
    printf '%s
' "$dirty" | sed 's/^/     /'
    echo "   Commit or move it. To delete it anyway:"
    echo "      bash scripts/worktree.sh remove --force $slug"
    exit 1
  fi
  # Commits that exist only on this branch are lost with it if never pushed.
  unpushed=""
  if git -C "$path" rev-parse --abbrev-ref '@{upstream}' >/dev/null 2>&1; then
    unpushed="$(git -C "$path" rev-list --count '@{upstream}..HEAD' 2>/dev/null || true)"
  else
    unpushed="$(git -C "$path" rev-list --count HEAD --not --remotes 2>/dev/null || true)"
  fi
  if [ -n "$unpushed" ] && [ "$unpushed" != 0 ]; then
    echo "   !! branch $slug has $unpushed commit(s) not on any remote. The branch survives, the commits stay reachable only through it."
  fi

  # A dev stack first. Its containers and servers run from this folder, and the
  # files will not delete while they run. Its state folder says one exists.
  if [ -f "$path/.dev_up/state" ] && [ -f "$path/scripts/dev_up.sh" ]; then
    echo "   stopping the dev stack of this worktree"
    bash "$path/scripts/dev_up.sh" --down || echo "   !! dev_up --down failed. Check: docker ps"
  fi

  # A RUNNING PROCESS next. Measured once: a removed worktree still had a
  # server running out of its virtualenv. Nothing was lost, but the server then
  # ran from a folder git no longer tracked. A file mtime does not catch this,
  # because the folder can sit unwritten for a day while a process uses it.
  # This is a warning, not a refusal: you may want the worktree gone.
  if command -v powershell >/dev/null 2>&1; then
    win_prefix="$(printf '%s' "$path" | sed 's|^/\([a-zA-Z]\)/|\1:\\|; s|/|\\|g')"
    procs="$(powershell -NoProfile -Command \
      "(Get-Process | Where-Object { \$_.Path -like '${win_prefix}*' } | \
        ForEach-Object { \$_.ProcessName + '(' + \$_.Id + ')' }) -join ' '" 2>/dev/null | tr -d '\r')"
    if [ -n "$procs" ]; then
      echo "   !! PROCESSES ARE STILL RUNNING FROM THIS WORKTREE:"
      echo "      $procs"
      echo "      Stop them first, or the files will not delete."
      echo "      Continuing in 5s. Press Ctrl-C to stop."
      sleep 5
    fi
  fi

  # THE JUNCTION FIRST, ALWAYS. See the header. `cmd rmdir` unlinks a junction
  # and refuses a real non-empty directory, so this line is safe to run blind.
  if command -v cmd >/dev/null 2>&1; then
    win="$(cd "$path" && pwd -W 2>/dev/null || true)"
    if [ -n "$win" ] && [ -d "$path/node_modules" ]; then
      cmd //c rmdir "$(printf '%s' "$win" | tr '/' '\')\node_modules" >/dev/null 2>&1 \
        && echo "   unlinked the node_modules junction" \
        || echo "   node_modules is a real directory (left alone)"
    fi
  fi

  if [ "$force" = 1 ]; then
    git -C "$REPO" worktree remove "$path" --force
  else
    git -C "$REPO" worktree remove "$path"
  fi
  echo "   removed $path"
  echo "   The BRANCH still exists. Delete it when it is merged:"
  echo "      git -C \"$REPO\" branch -d $slug"
  ;;

*)
  usage
  ;;
esac
