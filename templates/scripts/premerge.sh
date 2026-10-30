#!/usr/bin/env bash
# ════════════════════════════════════════════════════════════════════════════
# premerge.sh: test the merge with TODAY's base branch, right before you merge.
#
#   bash scripts/premerge.sh      # in the PR's worktree. Commit everything first.
#
# WHY. CI tests a PR merged with the base branch AS IT WAS when the run started.
# Without a merge queue, or a rule that forces an up-to-date branch, a PR can
# merge green onto a base that moved after its run. Measured on one product:
#   * two PRs took the same migration number, 3 times in 2 weeks;
#   * two PRs took the same ID in a tracked list;
#   * two PRs went green alone and red together, twice in one day.
#
# WHAT. When the branch is behind the base, this script:
#   1. refuses a new migration numbered at or below the base's highest;
#   2. merges the base into the worktree WITHOUT a commit;
#   3. runs your collision fences on that result;
#   4. when both sides changed the same files, runs your affected-tests command;
#   5. aborts the merge, so the worktree is as it was.
# A squash merge lands the same tree that step 2 built. So a pass tests what
# lands, with no second CI run.
#
# EXIT 0: merge now. EXIT 1: merge the base into the branch, fix, push, and
# wait for CI.
#
# CONFIG. Environment variables, or a bash file named .premerge.conf at the
# repo root (sourced if present). All are optional.
#   PREMERGE_REMOTE          remote name                       (default: origin)
#   PREMERGE_BASE_BRANCH     base branch                       (default: main)
#   PREMERGE_MIGRATIONS_DIR  folder of numbered migration files. Empty turns the
#                            migration check off.              (default: empty)
#   PREMERGE_FENCES          fence tests, one per line. A line is a shell
#                            command, or a path to a test file (.py runs with
#                            pytest, .js/.mjs with node, .sh with bash).
#   .premerge-fences         the same list in a file, one per line, # comments.
#   PREMERGE_AFFECTED_CMD    run when both sides changed a file. It sees
#                            PREMERGE_BASE and PREMERGE_OVERLAP in its env.
#                            Print failures as `FAILED <id>` or `ERROR <id>`
#                            lines (pytest -rfE does) so a failure can be re-run.
#   PREMERGE_RERUN_CMD       re-runs the failed ids on the branch alone. The ids
#                            arrive as arguments. Only a test that fails merged
#                            and passes alone blocks. (default: pytest -q -rfE)
#   PREMERGE_SKIP_FETCH=1    do not fetch first (tests use this).
# ════════════════════════════════════════════════════════════════════════════
set -euo pipefail

say()  { printf 'premerge: %s\n' "$*"; }
fail() { printf 'premerge: FAIL. %s\n' "$*" >&2; exit 1; }

cd "$(git rev-parse --show-toplevel)"
# shellcheck disable=SC1091
[ -f .premerge.conf ] && . ./.premerge.conf

REMOTE="${PREMERGE_REMOTE:-origin}"
BRANCH="${PREMERGE_BASE_BRANCH:-main}"
BASE="$REMOTE/$BRANCH"
MIG_DIR="${PREMERGE_MIGRATIONS_DIR:-}"
MIG_DIR="${MIG_DIR%/}"

if ! git diff --quiet || ! git diff --cached --quiet; then
  fail "the worktree has uncommitted changes. Commit them first: the trial merge must not touch them."
fi
git rev-parse -q --verify MERGE_HEAD >/dev/null && fail "a merge is already in progress here."

[ "${PREMERGE_SKIP_FETCH:-0}" = 1 ] || git fetch -q "$REMOTE" "$BRANCH"

behind="$(git rev-list --count "HEAD..$BASE")"
if [ "$behind" = 0 ]; then
  say "the branch contains $BASE. CI tested what will land. Merge now."
  exit 0
fi
base="$(git merge-base HEAD "$BASE")"
say "the branch is $behind commit(s) behind $BASE"

# ── 1. Migration numbers ────────────────────────────────────────────────────
# The number is the digits at the start of the file name. Two PRs that take the
# same number apply in an order nobody chose.
num() { basename "$1" | { grep -oE '^[0-9]+' || true; } | sed 's/^0*//'; }
if [ -n "$MIG_DIR" ]; then
  main_max=0
  while IFS= read -r f; do
    n="$(num "$f")"
    if [ -n "$n" ] && [ "$n" -gt "$main_max" ]; then main_max="$n"; fi
  done < <(git ls-tree --name-only "$BASE" "$MIG_DIR/" | grep -E '/[0-9]+[^/]*$' || true)
  while IFS= read -r f; do
    [ -n "$f" ] || continue
    n="$(num "$f")"
    [ -n "$n" ] || continue
    if [ "$n" -le "$main_max" ]; then
      fail "migration $(basename "$f") is not above $BASE's highest number ($main_max). Take $((main_max + 1))."
    fi
  done < <(git diff --name-only --diff-filter=A "$base" HEAD -- "$MIG_DIR/" | grep -E '/[0-9]+[^/]*$' || true)
fi

# ── 2. The trial merge ──────────────────────────────────────────────────────
overlap="$(comm -12 <(git diff --name-only "$base" HEAD | sort) <(git diff --name-only "$base" "$BASE" | sort))"
logs="$(mktemp -d)"
# The trial merge is a real commit on a DETACHED head, so tests see a clean,
# committed checkout. An uncommitted merge broke a test that compares a build
# SHA with `git rev-parse HEAD`. The trap aborts any merge and goes back to the
# branch on every exit. The trial commit is left unreferenced. No ref moves.
branch="$(git symbolic-ref -q --short HEAD)" || fail "HEAD is detached. Check out the PR branch first."
back() {
  git rev-parse -q --verify MERGE_HEAD >/dev/null && git merge --abort
  [ "$(git symbolic-ref -q --short HEAD || true)" = "$branch" ] || git checkout -q "$branch"
}
trap 'back; rm -rf "$logs"; true' EXIT
git checkout -q --detach
if ! git merge --no-ff --no-edit -q "$BASE" > "$logs/merge.log" 2>&1; then
  conflicts="$(git diff --name-only --diff-filter=U | tr '\n' ' ')"
  if [ -z "$conflicts" ]; then
    # No conflicted path: git refused before it merged, most often because an
    # untracked file here has the name of a file that the base adds. Show git's words.
    sed 's/^/  /' "$logs/merge.log" >&2
    fail "git refused the trial merge (above). Move the untracked files it names, then run this again."
  fi
  fail "merging $BASE conflicts in: $conflicts. Merge it, resolve, push, and wait for CI."
fi

# ── 3. The collision fences, on the merge result ───────────────────────────
fences=()
if [ -f .premerge-fences ]; then
  while IFS= read -r line || [ -n "$line" ]; do
    line="${line%$'\r'}"
    case "$line" in ''|'#'*) continue ;; esac
    fences+=("$line")
  done < .premerge-fences
fi
if [ -n "${PREMERGE_FENCES:-}" ]; then
  while IFS= read -r line; do
    line="${line%$'\r'}"
    [ -n "$line" ] && fences+=("$line")
  done <<< "$PREMERGE_FENCES"
fi

# run_fence <line>: a path to an existing test file runs by its extension. Any
# other line runs as a shell command. A one-word path that is missing is skipped:
# the base may not have the file yet.
run_fence() {
  local f="$1" py=python
  case "$f" in
    *' '*) bash -c "$f"; return ;;
  esac
  [ -f "$f" ] || { case "$f" in *.*) return 0 ;; *) bash -c "$f"; return ;; esac; }
  case "$f" in
    *.py) command -v python >/dev/null 2>&1 || py=python3; "$py" -m pytest -q -p no:cacheprovider "$f" ;;
    *.js|*.mjs|*.cjs) node "$f" ;;
    *) bash "$f" ;;
  esac
}

say "collision fences on the merge result: ${#fences[@]} entries"
i=0
for f in "${fences[@]+"${fences[@]}"}"; do
  i=$((i + 1))
  if ! run_fence "$f" > "$logs/fence.$i.log" 2>&1; then
    tail -15 "$logs/fence.$i.log" >&2
    fail "the fence '$f' fails once $BASE is merged in. Fix it on the branch, push, and wait for CI."
  fi
done

# ── 4. Both sides changed the same files ───────────────────────────────────
# A test that fails on the merge result is a merge failure only when it PASSES
# on the branch alone (green alone, red together). A test that fails both ways
# is this machine or an older red. On one Windows PC six tests failed locally
# and passed in CI, so without this re-run the step always failed.
RERUN_CMD="${PREMERGE_RERUN_CMD:-python -m pytest -q -p no:cacheprovider --continue-on-collection-errors -rfE}"
# Ids at the function level: a parameter such as [a b] holds a space, and a cut
# id selects nothing on the re-run.
failed_ids() { { grep -E '^(FAILED|ERROR) ' "$1" || true; } | awk '{print $2}' | sed 's/\[.*//' | sort -u; }

if [ -n "$overlap" ]; then
  say "both sides changed: $(printf '%s' "$overlap" | tr '\n' ' ')"
  if [ -n "${PREMERGE_AFFECTED_CMD:-}" ]; then
    say "running the affected tests on the merge result"
    if ! PREMERGE_BASE="$BASE" PREMERGE_OVERLAP="$overlap" bash -c "$PREMERGE_AFFECTED_CMD" > "$logs/affected.log" 2>&1; then
      merged_fail="$(failed_ids "$logs/affected.log")"
      if [ -z "$merged_fail" ]; then
        tail -20 "$logs/affected.log" >&2
        fail "the affected tests did not run cleanly on the merge result, and no test is named (log above)."
      fi
      back
      # shellcheck disable=SC2086
      bash -c "$RERUN_CMD \"\$@\"" _ $merged_fail > "$logs/rerun.log" 2>&1 || true
      alone_fail="$(failed_ids "$logs/rerun.log")"
      caused="$(comm -23 <(printf '%s\n' "$merged_fail") <(printf '%s\n' "$alone_fail"))"
      if [ -n "$caused" ]; then
        printf '  %s\n' $caused >&2
        fail "these tests pass on the branch alone and fail once $BASE is merged in. Merge $BASE into the branch, fix, push, and wait for CI."
      fi
      say "these tests fail on the branch alone too, so the merge did not cause them (this machine, or already red):"
      printf '  %s\n' $merged_fail
    fi
  else
    say "set PREMERGE_AFFECTED_CMD to run the affected tests here too."
  fi
fi

say "PASS. The merge with $BASE is clean and the fences hold. Merge now."
