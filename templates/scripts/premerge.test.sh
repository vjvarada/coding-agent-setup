#!/usr/bin/env bash
# Self-test for premerge.sh. Plain bash, no test framework.
#
#   bash scripts/premerge.test.sh
#
# It builds throwaway git repos with a bare origin, so it needs git and bash
# and no network. It exits non-zero when any case fails.
#
# PREMERGE_SCRIPT points the test at another copy of the script. Use it to
# prove the test bites: break the copy, run this, and watch a case fail.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT="${PREMERGE_SCRIPT:-$HERE/premerge.sh}"
[ -f "$SCRIPT" ] || { echo "premerge.test: no script at $SCRIPT" >&2; exit 2; }

export GIT_AUTHOR_NAME=t GIT_AUTHOR_EMAIL=t@example.com
export GIT_COMMITTER_NAME=t GIT_COMMITTER_EMAIL=t@example.com
export PREMERGE_MIGRATIONS_DIR=db/migrations
export GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=core.autocrlf GIT_CONFIG_VALUE_0=false

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

PASS=0; FAILED=0; FAILURES=()
RC=0; OUT=""; ERR=""

check() {  # check <name> <condition-exit-code> [detail]
  if [ "$2" = 0 ]; then PASS=$((PASS + 1)); printf '  ok    %s\n' "$1"
  else FAILED=$((FAILED + 1)); FAILURES+=("$1"); printf '  FAIL  %s %s\n' "$1" "${3:-}"; fi
}

commit_file() {  # commit_file <repo> <path> [text]
  mkdir -p "$(dirname "$1/$2")"
  printf '%s\n' "${3:-x}" > "$1/$2"
  git -C "$1" add "$2"
  git -C "$1" commit -q -m "add $2"
}

new_repo() {  # new_repo <name>: a clone of a bare origin. main holds migration 315. Branch feat is cut.
  local d="$TMP/$1"
  mkdir -p "$d"
  git init -q --bare -b main "$d/origin.git"
  git init -q -b main "$d/work"
  git -C "$d/work" remote add origin "$d/origin.git"
  commit_file "$d/work" db/migrations/315_base.sql
  git -C "$d/work" push -q origin main
  git -C "$d/work" checkout -q -b feat
  REPO="$d/work"
}

advance_main() {  # advance_main <repo> <path>: another PR merges while feat waits
  git -C "$1" checkout -q main
  commit_file "$1" "$2"
  git -C "$1" push -q origin main
  git -C "$1" checkout -q feat
}

run_pm() {  # run_pm <repo>: sets RC, OUT, ERR
  ( cd "$1" && bash "$SCRIPT" ) > "$TMP/out" 2> "$TMP/err"
  RC=$?
  OUT="$(cat "$TMP/out")"; ERR="$(cat "$TMP/err")"
}

has() { case "$1" in *"$2"*) return 0 ;; *) return 1 ;; esac; }
head_of() { git -C "$1" rev-parse HEAD; }
undone() {  # undone <repo> <head>: HEAD same, status clean, no MERGE_HEAD
  [ "$(head_of "$1")" = "$2" ] && [ -z "$(git -C "$1" status --porcelain)" ] \
    && [ ! -e "$1/.git/MERGE_HEAD" ]
}

echo "premerge.test: script under test: $SCRIPT"

# 1. A branch that contains main passes.
new_repo contains
commit_file "$REPO" db/migrations/316_feat.sql
run_pm "$REPO"
check "a branch that contains main passes" "$([ $RC = 0 ] && has "$OUT" 'Merge now'; echo $?)" "rc=$RC $ERR"

# 2. The collision: both took 316 and the other merged first.
new_repo collision
commit_file "$REPO" db/migrations/316_feat.sql
advance_main "$REPO" db/migrations/316_other.sql
run_pm "$REPO"
check "a migration number main took meanwhile fails, naming Take 317" \
  "$([ $RC = 1 ] && has "$ERR" '316_feat.sql' && has "$ERR" 'Take 317'; echo $?)" "rc=$RC $ERR"

# 3. A number below main's highest fails.
new_repo below
commit_file "$REPO" db/migrations/316_feat.sql
advance_main "$REPO" db/migrations/317_other.sql
run_pm "$REPO"
check "a migration below main's highest fails, naming Take 318" \
  "$([ $RC = 1 ] && has "$ERR" 'Take 318'; echo $?)" "rc=$RC $ERR"

# 4. A conflict fails and leaves the worktree as it was.
new_repo conflict
commit_file "$REPO" notes.md feat
advance_main "$REPO" notes.md
H="$(head_of "$REPO")"
run_pm "$REPO"
check "a conflict fails and names the file" \
  "$([ $RC = 1 ] && has "$ERR" 'conflicts in: notes.md'; echo $?)" "rc=$RC $ERR"
check "a conflict leaves HEAD, status and MERGE_HEAD as they were" "$(undone "$REPO" "$H"; echo $?)"

# 5. An untracked file in the way is named and kept.
new_repo untracked
commit_file "$REPO" feat.md
advance_main "$REPO" zone.md
printf 'mine\n' > "$REPO/zone.md"
run_pm "$REPO"
check "an untracked file in the way is named in the failure" \
  "$([ $RC = 1 ] && has "$ERR" 'zone.md' && has "$ERR" 'untracked'; echo $?)" "rc=$RC $ERR"
check "the untracked file is kept" "$([ "$(cat "$REPO/zone.md")" = mine ]; echo $?)"

# 6. A clean branch that is behind passes, and the trial merge is undone.
new_repo clean
commit_file "$REPO" db/migrations/317_feat.sql
advance_main "$REPO" db/migrations/316_other.sql
H="$(head_of "$REPO")"
run_pm "$REPO"
check "a clean behind branch passes" "$([ $RC = 0 ] && has "$OUT" PASS; echo $?)" "rc=$RC $ERR"
check "the trial merge is undone after a pass" "$(undone "$REPO" "$H"; echo $?)"

# 7. Uncommitted work is refused.
new_repo dirty
printf 'wip\n' > "$REPO/wip.md"
git -C "$REPO" add wip.md
run_pm "$REPO"
check "uncommitted work is refused" "$([ $RC = 1 ] && has "$ERR" uncommitted; echo $?)" "rc=$RC $ERR"

# 8. A failing fence fails the run, and the merge is still undone.
new_repo fence
commit_file "$REPO" feat.md
advance_main "$REPO" other.md
H="$(head_of "$REPO")"
PREMERGE_FENCES='false' run_pm "$REPO"
check "a failing fence fails the run" "$([ $RC = 1 ] && has "$ERR" "fence 'false'"; echo $?)" "rc=$RC $ERR"
check "the merge is undone after a failing fence" "$(undone "$REPO" "$H"; echo $?)"
printf '# a comment\ntrue\n' > "$REPO/.premerge-fences"
run_pm "$REPO"
check "a passing fence in .premerge-fences passes" "$([ $RC = 0 ] && has "$OUT" PASS; echo $?)" "rc=$RC $ERR"

# 9. An empty migration dir turns the migration check off.
new_repo nomig
commit_file "$REPO" db/migrations/316_feat.sql
advance_main "$REPO" db/migrations/316_other.sql
PREMERGE_MIGRATIONS_DIR='' run_pm "$REPO"
check "an empty PREMERGE_MIGRATIONS_DIR skips the migration check" \
  "$([ $RC = 0 ] && has "$OUT" PASS; echo $?)" "rc=$RC $ERR"

# 10. Both sides change one file (a clean merge with overlap). A test that fails
#     only on the merge result blocks. One that fails alone too does not.
overlap_repo() {
  new_repo "$1"
  git -C "$REPO" checkout -q main
  commit_file "$REPO" shared.md "$(printf 'a\nb\nc\nd\ne')"
  git -C "$REPO" push -q origin main
  git -C "$REPO" checkout -q feat
  git -C "$REPO" merge -q --ff-only main
  commit_file "$REPO" shared.md "$(printf 'A\nb\nc\nd\ne')"
  git -C "$REPO" checkout -q main
  commit_file "$REPO" shared.md "$(printf 'a\nb\nc\nd\nE')"
  git -C "$REPO" push -q origin main
  git -C "$REPO" checkout -q feat
}
FAILS='echo "FAILED tests/t.py::test_a[x y] - boom"; exit 1'
overlap_repo merged_only
PREMERGE_AFFECTED_CMD="$FAILS" PREMERGE_RERUN_CMD=true run_pm "$REPO"
check "a test that fails only when merged blocks, by name" \
  "$([ $RC = 1 ] && has "$ERR" 'tests/t.py::test_a' && has "$ERR" 'pass on the branch alone'; echo $?)" "rc=$RC $ERR"
check "the branch is checked out again after a block" \
  "$([ "$(git -C "$REPO" symbolic-ref --short HEAD)" = feat ]; echo $?)"
overlap_repo fails_alone
H="$(head_of "$REPO")"
PREMERGE_AFFECTED_CMD="$FAILS" PREMERGE_RERUN_CMD="$FAILS" run_pm "$REPO"
check "a test that fails alone too does not block" \
  "$([ $RC = 0 ] && has "$OUT" 'did not cause them' && has "$OUT" PASS; echo $?)" "rc=$RC $ERR"
check "the worktree is as it was, on the branch" \
  "$(undone "$REPO" "$H" && [ "$(git -C "$REPO" symbolic-ref --short HEAD)" = feat ]; echo $?)"
overlap_repo unnamed
PREMERGE_AFFECTED_CMD='echo boom; exit 2' PREMERGE_RERUN_CMD=true run_pm "$REPO"
check "a run that names no test blocks" "$([ $RC = 1 ] && has "$ERR" 'no test is named'; echo $?)" "rc=$RC $ERR"

echo
echo "premerge.test: $PASS passed, $FAILED failed"
if [ "$FAILED" -gt 0 ]; then
  printf '  failed: %s\n' "${FAILURES[@]}"
  exit 1
fi
exit 0
