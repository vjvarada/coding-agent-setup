#!/usr/bin/env bash
# ════════════════════════════════════════════════════════════════════════════
# dev_up.sh: the whole app on THIS machine, in one command.
#
#   bash scripts/dev_up.sh                  start. The first run builds and seeds.
#   bash scripts/dev_up.sh --status         what runs, on which port
#   bash scripts/dev_up.sh --check          health, then your check hook
#   bash scripts/dev_up.sh --logs [api|web|migrate|seed]
#   bash scripts/dev_up.sh --env            the URLs and DSNs, as export lines
#   bash scripts/dev_up.sh --stop           stop the API and the web app
#   bash scripts/dev_up.sh --down           stop, then remove the containers and the data
#   bash scripts/dev_up.sh --reset          --down, then a fresh start
#   bash scripts/dev_up.sh --print-env      what each process would get (no start)
#   bash scripts/dev_up.sh --refresh-flags  run your refresh hook (flags come from you)
#
# EVERYTHING APP-SPECIFIC LIVES IN scripts/dev_up.config. This file holds none.
# Copy scripts/dev_up.config.example to scripts/dev_up.config and edit it.
#
# WHAT YOU GET, per worktree, on 127.0.0.1 only:
#   * a database container, with your migrations applied;
#   * an optional cache container (Redis) of its own, so two stacks never
#     share a cache;
#   * your API and your web app, started with your commands;
#   * your seed data, once.
# Two worktrees get two stacks on different ports, so they never collide.
#
# WHY THE MIGRATIONS RUN INSIDE THE CONTAINER. Measured on one product, on a
# Windows PC: a migration runner started from Git Bash took 515 s for 310 files,
# and 89 s with nothing to apply. Process start-up under Git Bash is the cost.
# The same runner inside the Linux container took 38 s and 6 s. So the script
# mounts your migration folder read-only and runs DEV_UP_MIGRATE_CMD there.
#
# NOTHING LEAVES THIS MACHINE:
#   * each process starts with a CLEAN environment (env -i), so a key in your
#     shell never reaches the stack;
#   * the script refuses a checkout that has a dotenv file (DEV_UP_DOTENV_FILES),
#     because most frameworks read those files themselves;
#   * production's switches come across with the outbound ones held OFF
#     (see DEV_UP_HELD in the config).
# ════════════════════════════════════════════════════════════════════════════
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="${DEV_UP_REPO:-$(cd "$SCRIPT_DIR/.." && pwd)}"
STATE_DIR="$REPO/.dev_up"
STATE="$STATE_DIR/state"
CONFIG="${DEV_UP_CONFIG:-$SCRIPT_DIR/dev_up.config}"

case "$(uname -s)" in MINGW*|MSYS*|CYGWIN*) WIN=1 ;; *) WIN=0 ;; esac

say()  { printf '%s\n' "$*"; }
fail() { printf 'dev_up: %s\n' "$*" >&2; exit 1; }
dk()   { MSYS_NO_PATHCONV=1 docker "$@"; }
val()  { { grep -E "^$1=" "$STATE" 2>/dev/null || true; } | tail -1 | cut -d= -f2-; }
has_fn() { declare -F "$1" >/dev/null; }

# ── The config ──────────────────────────────────────────────────────────────

case "${1:-up}" in
  -h|--help|help)
    # Print the whole usage block: every comment line up to the line that
    # starts "EVERYTHING APP-SPECIFIC".
    awk 'NR == 1 { next } /^# EVERYTHING/ { exit } /^#/ { sub(/^# ?/, ""); print }' "$0" | sed '/^[═]*$/d'
    exit 0 ;;
esac
[ -f "$CONFIG" ] || fail "no config at $CONFIG.
         Copy the example, then edit the values it marks CHANGE:
           cp $SCRIPT_DIR/dev_up.config.example $CONFIG"

# Defaults first. The config overrides them.
DEV_UP_PROJECT="$(basename "$REPO" | tr 'A-Z' 'a-z' | tr -c 'a-z0-9-\n' '-' | cut -c1-20)"
DEV_UP_DOTENV_FILES=(".env")
DEV_UP_REQUIRED_TOOLS=(docker curl)
DEV_UP_DB_BASE=6400;     DEV_UP_CACHE_BASE="";   DEV_UP_API_BASE=8400;   DEV_UP_WEB_BASE=3400
DEV_UP_DB_IMAGE="";      DEV_UP_DB_USER=app_owner; DEV_UP_DB_PASSWORD=app_owner; DEV_UP_DB_NAME=app_dev
DEV_UP_DB_MOUNTS=()
DEV_UP_MIGRATE_CMD=""
DEV_UP_CACHE_IMAGE=""
DEV_UP_API_DIR=".";      DEV_UP_API_CMD="";      DEV_UP_API_HEALTH="/health"; DEV_UP_API_WAIT=240
DEV_UP_WEB_DIR=".";      DEV_UP_WEB_CMD="";      DEV_UP_WEB_HEALTH="/";       DEV_UP_WEB_WAIT=240
DEV_UP_WEB_INSTALL_PROBE=""; DEV_UP_WEB_INSTALL_CMD=""
DEV_UP_SEED_CMD="";      DEV_UP_SEED_PROBE_SQL=""
DEV_UP_CHECK_CMD=""
DEV_UP_FLAGS_FILE="$SCRIPT_DIR/dev_up.flags"
DEV_UP_FLAGS_API_SCOPE="api"; DEV_UP_FLAGS_WEB_SCOPE="web"
DEV_UP_SWITCH='^(NEXT_PUBLIC_[A-Z0-9_]+|[A-Z0-9_]+_ENABLED)$'
DEV_UP_HELD='(EMAIL|SMS|PUSH|WEBHOOK|SEND|OUTBOUND|NOTIFY|SYNC|SCHEDULER|DIGEST|INVITE|SIGNUP)'
DEV_UP_LOCAL_OFF='^$'
DEV_UP_FORCED_OFF=()
DEV_UP_READY_NOTE="This stack has no keys. Anything that needs a real third party does not work here."
# shellcheck disable=SC1090
. "$CONFIG"

# ── The environment each process gets ──────────────────────────────────────

BASE_NAMES_WIN="PATH SYSTEMROOT WINDIR COMSPEC PATHEXT TEMP TMP USERPROFILE HOME APPDATA LOCALAPPDATA PROGRAMDATA USERNAME NUMBER_OF_PROCESSORS PROCESSOR_ARCHITECTURE"
BASE_NAMES_LINUX="PATH HOME USER LANG TMPDIR"

# The minimum a process needs to run. Nothing else leaks in from your shell.
base_env() {
  local v names
  if [ "$WIN" = 1 ]; then names="$BASE_NAMES_WIN"; else names="$BASE_NAMES_LINUX"; fi
  for v in $names; do
    [ -n "${!v:-}" ] && printf '%s=%s\n' "$v" "${!v}"
  done
  printf 'PYTHONUTF8=1\nPYTHONIOENCODING=utf-8\n'
}

# flag_env <scope>: production's switches for one scope, held ones off.
# The file format is  <scope>:<NAME>=<value>, one per line.
flag_env() {
  local scope="$1" line name value all=""
  if [ -f "$DEV_UP_FLAGS_FILE" ]; then
    while IFS= read -r line || [ -n "$line" ]; do
      # A Windows checkout can give the file CRLF endings. With the CR left on,
      # the strict test below dropped every line, and no switch reached the stack.
      line="${line%$'\r'}"
      case "$line" in "$scope":*) ;; *) continue ;; esac
      line="${line#"$scope":}"
      [[ "$line" =~ ^[A-Z0-9_]+=[A-Za-z0-9_.:-]{0,64}$ ]] || continue
      name="${line%%=*}"
      value="${line#*=}"
      [[ "$name" =~ $DEV_UP_SWITCH ]] || continue
      # Secrets never come across, whatever the file says.
      [[ "$name" =~ (KEY|SECRET|TOKEN|PASSWORD|PASSWD|DSN|URL|PASS) ]] && continue
      if [[ "$name" =~ $DEV_UP_HELD ]] || [[ "$name" =~ $DEV_UP_LOCAL_OFF ]]; then
        case "$value" in 0|1) value=0 ;; *) value=false ;; esac
      fi
      all="$all$name=$value"$'\n'
    done < "$DEV_UP_FLAGS_FILE"
  fi
  if [ "$scope" = "$DEV_UP_FLAGS_API_SCOPE" ]; then
    for line in "${DEV_UP_FORCED_OFF[@]+"${DEV_UP_FORCED_OFF[@]}"}"; do all="$all$line"$'\n'; done
  fi
  # The last value of a name wins. awk reads ALL its input (no early exit).
  printf '%s' "$all" | awk -F= 'NF { if (!($1 in v)) { n++; k[n] = $1 } v[$1] = $0 } END { for (i = 1; i <= n; i++) print v[k[i]] }' | sort
}

api_env() {
  base_env
  flag_env "$DEV_UP_FLAGS_API_SCOPE"
  if has_fn dev_up_api_env; then dev_up_api_env; fi
}
web_env() {
  base_env
  flag_env "$DEV_UP_FLAGS_WEB_SCOPE"
  if has_fn dev_up_web_env; then dev_up_web_env; fi
}
seed_env() {
  base_env
  if has_fn dev_up_seed_env; then dev_up_seed_env; fi
}

# ── Ports and state ─────────────────────────────────────────────────────────
# A slot from 0 to 49 comes from the worktree path. Each slot owns one port per
# service, counted up from the base ports in the config. Pick bases that clear
# the ports your repo already uses.

ports_for() {
  DB_PORT=$((DEV_UP_DB_BASE + $1))
  CACHE_PORT=0; [ -z "$DEV_UP_CACHE_BASE" ] || CACHE_PORT=$((DEV_UP_CACHE_BASE + $1))
  API_PORT=$((DEV_UP_API_BASE + $1))
  WEB_PORT=$((DEV_UP_WEB_BASE + $1))
}

# listener_pid <port>: the PID that listens on it, or nothing. awk reads ALL
# its input: an early `exit` breaks the pipe, and under pipefail the broken
# pipe ends the whole script.
listener_pid() {
  if [ "$WIN" = 1 ]; then
    { netstat -ano 2>/dev/null || true; } | tr -d '\r' \
      | awk -v p=":$1" '$4 == "LISTENING" && !hit && substr($2, length($2) - length(p) + 1) == p { hit = $5 } END { if (hit) print hit }'
  elif command -v ss >/dev/null 2>&1; then
    { ss -ltnpH "sport = :$1" 2>/dev/null || true; } \
      | awk 'match($0, /pid=[0-9]+/) && !hit { hit = substr($0, RSTART + 4, RLENGTH - 4) } END { if (hit) print hit }'
  elif command -v lsof >/dev/null 2>&1; then
    # macOS: no ss. lsof -t prints bare PIDs. awk reads ALL input (no early exit).
    { lsof -nP -iTCP:"$1" -sTCP:LISTEN -t 2>/dev/null || true; } \
      | awk '!hit { hit = $1 } END { if (hit) print hit }'
  fi
  # With neither ss nor lsof there is no PID to give. port_busy still works.
}
port_busy() {
  [ "$1" != 0 ] || return 1
  if [ "$WIN" = 1 ]; then [ -n "$(listener_pid "$1")" ]
  elif command -v ss >/dev/null 2>&1; then
    { ss -ltnH "sport = :$1" 2>/dev/null || true; } | grep -q .
  elif command -v lsof >/dev/null 2>&1; then
    [ -n "$(listener_pid "$1")" ]
  else
    # Last resort: netstat -an. Linux prints 0.0.0.0:PORT, BSD prints *.PORT.
    { netstat -an 2>/dev/null || true; } | grep -E "[.:]$1[[:space:]].*LISTEN" >/dev/null
  fi
}

load_state() {
  if [ -f "$STATE" ]; then
    SLOT="$(val SLOT)"; TOKEN="$(val TOKEN)"; NAME="$(val NAME)"
    ports_for "$SLOT"
    return 0
  fi
  return 1
}

new_state() {
  local slot tries=0
  slot=$(( $(printf '%s' "$REPO" | cksum | cut -d' ' -f1) % 50 ))
  while :; do
    ports_for "$slot"
    if ! port_busy "$DB_PORT" && ! port_busy "$CACHE_PORT" \
       && ! port_busy "$API_PORT" && ! port_busy "$WEB_PORT"; then break; fi
    tries=$((tries + 1)); [ "$tries" -lt 50 ] || fail "no free port slot (bases $DEV_UP_DB_BASE, $DEV_UP_API_BASE, $DEV_UP_WEB_BASE, each plus 0 to 49)"
    slot=$(( (slot + 1) % 50 ))
  done
  SLOT="$slot"
  NAME="$DEV_UP_PROJECT-dev-$(basename "$REPO" | tr 'A-Z' 'a-z' | tr -c 'a-z0-9-\n' '-' | cut -c1-40)"
  TOKEN="dev-$(head -c 16 /dev/urandom | od -An -tx1 | tr -d ' \n')"
  mkdir -p "$STATE_DIR"
  printf 'SLOT=%s\nNAME=%s\nTOKEN=%s\n' "$SLOT" "$NAME" "$TOKEN" > "$STATE"
}

# ── Guards ──────────────────────────────────────────────────────────────────

refuse_dotenv() {
  local f
  for f in "${DEV_UP_DOTENV_FILES[@]+"${DEV_UP_DOTENV_FILES[@]}"}"; do
    if [ -f "$REPO/$f" ]; then
      fail "$REPO/$f exists. Your framework reads it itself, so its keys
         would reach this stack. Run dev_up in a worktree instead:
           bash scripts/worktree.sh new <slug>"
    fi
  done
}

need_tools() {
  local t
  for t in "${DEV_UP_REQUIRED_TOOLS[@]+"${DEV_UP_REQUIRED_TOOLS[@]}"}"; do
    command -v "$t" >/dev/null || fail "$t is not on PATH"
  done
  docker info >/dev/null 2>&1 || fail "the Docker daemon is not running. Start Docker Desktop, then run this again."
}

# ── Processes ───────────────────────────────────────────────────────────────

# launch <name> <dir> <env-lines-fn> <port> <command>: start a process in the
# background with ONLY the environment that <env-lines-fn> prints. {PORT} in the
# command becomes the port.
launch() {
  local name="$1" dir="$2" envfn="$3" port="$4" cmd="$5" line
  cmd="${cmd//\{PORT\}/$port}"
  local -a envs=()
  while IFS= read -r line; do [ -n "$line" ] && envs+=("$line"); done < <("$envfn")
  if [ "$WIN" = 1 ]; then
    ( cd "$dir" && exec env -i "${envs[@]}" bash -c "$cmd" ) > "$STATE_DIR/$name.log" 2>&1 &
  elif command -v setsid >/dev/null 2>&1; then
    ( cd "$dir" && exec setsid env -i "${envs[@]}" bash -c "$cmd" ) > "$STATE_DIR/$name.log" 2>&1 &
    echo group > "$STATE_DIR/$name.mode"
  elif command -v perl >/dev/null 2>&1; then
    # macOS has no setsid. perl makes the same new session, then execs.
    ( cd "$dir" && exec perl -MPOSIX -e 'POSIX::setsid(); exec @ARGV' -- env -i "${envs[@]}" bash -c "$cmd" ) > "$STATE_DIR/$name.log" 2>&1 &
    echo group > "$STATE_DIR/$name.mode"
  else
    # No way to open a new session. --stop then kills the PID and its children.
    ( cd "$dir" && exec nohup env -i "${envs[@]}" bash -c "$cmd" ) > "$STATE_DIR/$name.log" 2>&1 &
    echo tree > "$STATE_DIR/$name.mode"
  fi
  local pid=$! winpid=""
  [ "$WIN" = 1 ] && winpid="$(cat "/proc/$pid/winpid" 2>/dev/null || true)"
  printf '%s %s\n' "$pid" "$winpid" > "$STATE_DIR/$name.pid"
}

# kill_tree <pid>: TERM the children (pkill -P, else ps), then the process.
kill_tree() {
  local c
  if command -v pgrep >/dev/null 2>&1; then
    for c in $(pgrep -P "$1" 2>/dev/null || true); do kill_tree "$c"; done
  else
    for c in $({ ps -A -o pid= -o ppid= 2>/dev/null || true; } | awk -v p="$1" '$2 == p { print $1 }'); do kill_tree "$c"; done
  fi
  kill -TERM "$1" 2>/dev/null || true
}

# stop_one <name> <port>: end the process tree, then whatever still listens on
# the port. A dev server with a reloader runs a parent and a worker, and a kill
# of the wrapper does not always reach both, so the port is the final test.
stop_one() {
  local name="$1" port="$2" pid="" winpid="" lp i
  if [ -f "$STATE_DIR/$name.pid" ]; then
    read -r pid winpid < "$STATE_DIR/$name.pid" || true
    if [ "$WIN" = 1 ]; then
      [ -n "$winpid" ] && taskkill //F //T //PID "$winpid" >/dev/null 2>&1 || true
    else
      if [ -n "$pid" ]; then
        if [ "$(cat "$STATE_DIR/$name.mode" 2>/dev/null || echo group)" = tree ]; then
          kill_tree "$pid"
        else
          kill -TERM -- "-$pid" 2>/dev/null || kill_tree "$pid"
        fi
      fi
    fi
  fi
  for i in 1 2 3 4 5 6 7 8 9 10; do
    lp="$(listener_pid "$port")"
    [ -z "$lp" ] && break
    if [ "$WIN" = 1 ]; then taskkill //F //T //PID "$lp" >/dev/null 2>&1 || true
    else kill -TERM "$lp" 2>/dev/null || true
    fi
    sleep 1
  done
  rm -f "${STATE_DIR:?}/${name:?}.pid" "${STATE_DIR:?}/${name:?}.mode"
  [ -z "$(listener_pid "$port")" ] || fail "port $port still has a listener after the $name stop"
}

# wait_http <url> <seconds>: one try at once, then every 2 s until <seconds>.
# With 0 seconds it still tries once. --status uses that.
wait_http() {
  local url="$1" secs="$2" waited=0
  while :; do
    [ "$(curl -s -o /dev/null -w '%{http_code}' "$url" 2>/dev/null || true)" = 200 ] && return 0
    [ "$waited" -ge "$secs" ] && return 1
    sleep 2
    waited=$((waited + 2))
  done
}

# ── The database ────────────────────────────────────────────────────────────
# These helpers are also for your hooks in dev_up.config.

# pg_sql [psql args]: psql in the DB container as the owner. Reads SQL on stdin.
pg_sql()    { dk exec -i "$NAME-pg" psql -X -q -v ON_ERROR_STOP=1 -U "$DEV_UP_DB_USER" -d "$DEV_UP_DB_NAME" "$@"; }
# pg_scalar <sql>: one value, with spaces and CRs stripped.
pg_scalar() { dk exec "$NAME-pg" psql -X -U "$DEV_UP_DB_USER" -d "$DEV_UP_DB_NAME" -tAc "$1" 2>/dev/null | tr -d '[:space:]'; }

# ensure_container <suffix> <image> [docker run args]: start or create one container.
ensure_container() {
  local suffix="$1" image="$2"; shift 2
  if [ "$(dk inspect -f '{{.State.Running}}' "$NAME-$suffix" 2>/dev/null || true)" != true ]; then
    if dk inspect "$NAME-$suffix" >/dev/null 2>&1; then
      dk start "$NAME-$suffix" >/dev/null
    else
      dk run -d --name "$NAME-$suffix" --label "dev_up=$REPO" "$@" "$image" >/dev/null
    fi
  fi
}

start_containers() {
  local mount_root="$REPO" m host cont i
  [ "$WIN" = 1 ] && mount_root="$(cd "$REPO" && pwd -W)"
  if [ -n "$DEV_UP_DB_IMAGE" ]; then
    local -a mounts=()
    for m in "${DEV_UP_DB_MOUNTS[@]+"${DEV_UP_DB_MOUNTS[@]}"}"; do
      host="${m%%:*}"; cont="${m#*:}"
      mounts+=(-v "$mount_root/$host:$cont:ro")
    done
    ensure_container pg "$DEV_UP_DB_IMAGE" \
      -e POSTGRES_USER="$DEV_UP_DB_USER" -e POSTGRES_PASSWORD="$DEV_UP_DB_PASSWORD" -e POSTGRES_DB="$DEV_UP_DB_NAME" \
      "${mounts[@]+"${mounts[@]}"}" -p "127.0.0.1:$DB_PORT:5432"
  fi
  if [ -n "$DEV_UP_CACHE_IMAGE" ]; then
    ensure_container cache "$DEV_UP_CACHE_IMAGE" -p "127.0.0.1:$CACHE_PORT:6379"
  fi
  [ -n "$DEV_UP_DB_IMAGE" ] || return 0
  for i in $(seq 1 60); do
    dk exec "$NAME-pg" pg_isready -U "$DEV_UP_DB_USER" -d "$DEV_UP_DB_NAME" >/dev/null 2>&1 && return 0
    sleep 1
  done
  fail "the database in $NAME-pg did not become ready"
}

# Order: before-hook, migrations (inside the container), after-hook. The
# before-hook is for a role that some migrations grant to only if it exists.
build_database() {
  [ -n "$DEV_UP_DB_IMAGE" ] || return 0
  local started
  started=$(date +%s)
  : > "$STATE_DIR/migrate.log"
  if has_fn dev_up_before_migrate; then dev_up_before_migrate; fi
  if [ -n "$DEV_UP_MIGRATE_CMD" ]; then
    if ! dk exec "$NAME-pg" bash -c "$DEV_UP_MIGRATE_CMD" >> "$STATE_DIR/migrate.log" 2>&1; then
      tail -20 "$STATE_DIR/migrate.log" >&2
      fail "a migration failed. The whole log: $STATE_DIR/migrate.log"
    fi
    say "  migrations: $(tail -1 "$STATE_DIR/migrate.log")"
  fi
  if has_fn dev_up_after_migrate; then dev_up_after_migrate; fi
  say "  database ready in $(( $(date +%s) - started )) s"
}

# Seeded? Your hook dev_up_seeded wins. Else DEV_UP_SEED_PROBE_SQL must return a
# count above 0. Else a marker in the state file records one finished seed.
# Make the seed write its probe row LAST, so a seed that failed half-way reads
# as not seeded.
seeded() {
  local n
  if has_fn dev_up_seeded; then dev_up_seeded; return; fi
  if [ -n "$DEV_UP_SEED_PROBE_SQL" ]; then
    n="$(pg_scalar "$DEV_UP_SEED_PROBE_SQL")"
    [ -n "$n" ] && [ "$n" != 0 ]
    return
  fi
  [ "$(val SEEDED)" = 1 ]
}

run_seed() {
  if has_fn dev_up_seed; then dev_up_seed; return; fi
  [ -n "$DEV_UP_SEED_CMD" ] || return 0
  local line; local -a envs=()
  while IFS= read -r line; do [ -n "$line" ] && envs+=("$line"); done < <(seed_env)
  ( cd "$REPO" && env -i "${envs[@]}" bash -c "$DEV_UP_SEED_CMD" ) > "$STATE_DIR/seed.log" 2>&1 \
    || { tail -20 "$STATE_DIR/seed.log" >&2; fail "the seed failed. Run --reset for a clean start. Log: $STATE_DIR/seed.log"; }
  grep -q '^SEEDED=' "$STATE" || printf 'SEEDED=1\n' >> "$STATE"
}

# ── Commands ────────────────────────────────────────────────────────────────

cmd_up() {
  refuse_dotenv
  need_tools
  load_state || new_state
  say "dev stack, slot $SLOT ($NAME)"
  start_containers
  build_database

  if [ -n "$DEV_UP_API_CMD" ]; then
    if wait_http "http://127.0.0.1:$API_PORT$DEV_UP_API_HEALTH" 0 2>/dev/null; then
      say "  API already running"
    else
      port_busy "$API_PORT" && fail "port $API_PORT is in use by another process"
      say "  starting the API"
      launch api "$REPO/$DEV_UP_API_DIR" api_env "$API_PORT" "$DEV_UP_API_CMD"
      wait_http "http://127.0.0.1:$API_PORT$DEV_UP_API_HEALTH" "$DEV_UP_API_WAIT" \
        || { tail -30 "$STATE_DIR/api.log" >&2; fail "the API did not answer $DEV_UP_API_HEALTH. Log: $STATE_DIR/api.log"; }
    fi
  fi

  if { [ -n "$DEV_UP_SEED_CMD" ] || has_fn dev_up_seed; } && ! seeded; then
    say "  seeding"
    run_seed
    if [ -f "$STATE_DIR/seed.log" ]; then { grep -iE "isolation|seeded|done" "$STATE_DIR/seed.log" || true; } | sed 's/^ */  /'; fi
  fi

  if [ -n "$DEV_UP_WEB_CMD" ]; then
    local web_dir="$REPO/$DEV_UP_WEB_DIR"
    if wait_http "http://127.0.0.1:$WEB_PORT$DEV_UP_WEB_HEALTH" 0 2>/dev/null; then
      say "  web app already running"
    else
      port_busy "$WEB_PORT" && fail "port $WEB_PORT is in use by another process"
      if [ -n "$DEV_UP_WEB_INSTALL_CMD" ] && [ ! -e "$web_dir/$DEV_UP_WEB_INSTALL_PROBE" ]; then
        say "  installing the web app's packages"
        ( cd "$web_dir" && bash -c "$DEV_UP_WEB_INSTALL_CMD" ) > "$STATE_DIR/install.log" 2>&1 \
          || { tail -20 "$STATE_DIR/install.log" >&2; fail "the install failed. Log: $STATE_DIR/install.log"; }
      fi
      say "  starting the web app"
      launch web "$web_dir" web_env "$WEB_PORT" "$DEV_UP_WEB_CMD"
      wait_http "http://127.0.0.1:$WEB_PORT$DEV_UP_WEB_HEALTH" "$DEV_UP_WEB_WAIT" \
        || { tail -30 "$STATE_DIR/web.log" >&2; fail "the web app did not answer. Log: $STATE_DIR/web.log"; }
    fi
  fi

  say ""
  say "Ready."
  [ -z "$DEV_UP_WEB_CMD" ] || say "  Web       http://127.0.0.1:$WEB_PORT"
  [ -z "$DEV_UP_API_CMD" ] || say "  API       http://127.0.0.1:$API_PORT"
  [ -z "$DEV_UP_DB_IMAGE" ] || say "  Database  postgresql://$DEV_UP_DB_USER:$DEV_UP_DB_PASSWORD@127.0.0.1:$DB_PORT/$DEV_UP_DB_NAME"
  say "  Logs      bash scripts/dev_up.sh --logs api|web"
  say "  Stop      bash scripts/dev_up.sh --stop    (--down also removes the data)"
  say ""
  say "$DEV_UP_READY_NOTE"
}

cmd_stop() {
  load_state || { say "no dev stack in this worktree"; return 0; }
  [ -z "$DEV_UP_WEB_CMD" ] || stop_one web "$WEB_PORT"
  [ -z "$DEV_UP_API_CMD" ] || stop_one api "$API_PORT"
  say "stopped the API and the web app (slot $SLOT). The containers keep running."
}

cmd_down() {
  load_state || { say "no dev stack in this worktree"; return 0; }
  [ -z "$DEV_UP_WEB_CMD" ] || stop_one web "$WEB_PORT"
  [ -z "$DEV_UP_API_CMD" ] || stop_one api "$API_PORT"
  dk rm -fv "$NAME-pg" "$NAME-cache" >/dev/null 2>&1 || true
  rm -rf "${STATE_DIR:?}"
  say "removed the dev stack of this worktree (slot $SLOT), data included"
}

cmd_status() {
  load_state || { say "no dev stack in this worktree. Start one: bash scripts/dev_up.sh"; return 0; }
  local s
  say "slot $SLOT ($NAME)"
  for s in pg cache; do
    say "  $s: $(dk inspect -f '{{.State.Status}}' "$NAME-$s" 2>/dev/null || echo absent)"
  done
  wait_http "http://127.0.0.1:$API_PORT$DEV_UP_API_HEALTH" 0 && s=up || s=down
  say "  api:     $s   http://127.0.0.1:$API_PORT"
  wait_http "http://127.0.0.1:$WEB_PORT$DEV_UP_WEB_HEALTH" 0 && s=up || s=down
  say "  web:     $s   http://127.0.0.1:$WEB_PORT"
}

cmd_check() {
  load_state || fail "no dev stack in this worktree"
  [ -z "$DEV_UP_API_CMD" ] || wait_http "http://127.0.0.1:$API_PORT$DEV_UP_API_HEALTH" 0 || fail "the API is down"
  [ -z "$DEV_UP_WEB_CMD" ] || wait_http "http://127.0.0.1:$WEB_PORT$DEV_UP_WEB_HEALTH" 0 || fail "the web app is down"
  say "  the API and the web app answer"
  if has_fn dev_up_check; then dev_up_check; return; fi
  if [ -n "$DEV_UP_CHECK_CMD" ]; then
    local line; local -a envs=()
    while IFS= read -r line; do [ -n "$line" ] && envs+=("$line"); done < <(seed_env)
    ( cd "$REPO" && env -i "${envs[@]}" bash -c "$DEV_UP_CHECK_CMD" )
  fi
}

cmd_env() {
  load_state || fail "no dev stack in this worktree"
  # Not DATABASE_URL: many test suites read that name, and a suite that resets
  # its database must never reach this one.
  printf 'export DEV_UP_APP_URL=http://127.0.0.1:%s\n' "$WEB_PORT"
  printf 'export DEV_UP_API_URL=http://127.0.0.1:%s\n' "$API_PORT"
  printf 'export DEV_UP_TOKEN=%s\n' "$TOKEN"
  printf 'export DEV_UP_DB_URL=postgresql://%s:%s@127.0.0.1:%s/%s\n' "$DEV_UP_DB_USER" "$DEV_UP_DB_PASSWORD" "$DB_PORT" "$DEV_UP_DB_NAME"
  if has_fn dev_up_extra_exports; then dev_up_extra_exports; fi
}

cmd_logs() {
  load_state || fail "no dev stack in this worktree"
  local which="${1:-api}"
  [ -f "$STATE_DIR/$which.log" ] || fail "no $which log in $STATE_DIR"
  tail -n 50 -f "$STATE_DIR/$which.log"
}

# For tests and for a look before a start: what each process would get.
cmd_print_env() {
  load_state 2>/dev/null || { SLOT=0; ports_for 0; TOKEN=dev-preview; NAME="$DEV_UP_PROJECT-dev-preview"; }
  local hide='^(PATH|SYSTEMROOT|WINDIR|COMSPEC|PATHEXT|TEMP|TMP|USERPROFILE|HOME|APPDATA|LOCALAPPDATA|PROGRAMDATA|USERNAME|NUMBER_OF_PROCESSORS|PROCESSOR_ARCHITECTURE|USER|LANG|TMPDIR)='
  say "[api]"; api_env | grep -vE "$hide" || true
  say "[web]"; web_env | grep -vE "$hide" || true
}

cmd_refresh_flags() {
  has_fn dev_up_refresh_flags \
    || fail "define dev_up_refresh_flags in $CONFIG. It must write $DEV_UP_FLAGS_FILE, one <scope>:<NAME>=<value> per line."
  dev_up_refresh_flags
}

case "${1:-up}" in
  up|--up|start)    cmd_up ;;
  --stop|stop)      cmd_stop ;;
  --down|down)      cmd_down ;;
  --reset|reset)    cmd_down; cmd_up ;;
  --status|status)  cmd_status ;;
  --check|check)    cmd_check ;;
  --env|env)        cmd_env ;;
  --logs|logs)      cmd_logs "${2:-api}" ;;
  --print-env)      cmd_print_env ;;
  --refresh-flags)  cmd_refresh_flags ;;
  *) fail "unknown option '$1'. Try --help." ;;
esac
