// Fence for stop-children.mjs (CIV-16, task 1828). pr-check.yml runs it.
// Run: node .claude/hooks/stop-children.test.mjs
import test from 'node:test'
import assert from 'node:assert/strict'
import { spawnSync } from 'node:child_process'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import {
  etimeToSeconds,
  parsePs,
  oldChildren,
  report,
  findSessionRoot,
  isClaude,
  isMcpServer,
  mcpNeedles,
  commandLabel,
  main,
} from './stop-children.mjs'

const HOOK = fileURLToPath(new URL('./stop-children.mjs', import.meta.url))
const HOUR = 3600

// macOS/BSD `ps` has no `etimes`; the hook falls back to `etime` and converts it.
test('etime ([[dd-]hh:]mm:ss) converts to seconds', () => {
  assert.equal(etimeToSeconds('05:07'), 307)
  assert.equal(etimeToSeconds('01:00:00'), 3600)
  assert.equal(etimeToSeconds('2-03:04:05'), ((2 * 24 + 3) * 60 + 4) * 60 + 5)
  assert.equal(etimeToSeconds('garbage'), null)
})

// A session tree as `ps -eo pid=,ppid=,etimes=,args=` prints it. The hook
// (pid 30) runs under an `sh -c` wrapper (pid 20), under claude (pid 10).
const PS = `
   1     0 99999 /sbin/init
   9     1 99999 claude daemon run --json-path /x
  10     9  9000 /home/dev/.local/share/claude/versions/2.1.319 --print --session-id abc
  20    10     1 /bin/sh -c node "/repo/.claude/hooks/stop-children.mjs"
  30    20     1 node /repo/.claude/hooks/stop-children.mjs
  40    10 36000 /bin/bash -c until [ -f /tmp/x ]; do sleep 5; done
  41    40     3 sleep 5
  50    10  7200 /repo/.venv/bin/python -m pytest tests/unit
  60    10  8000 node /home/dev/.local/bin/codegraph serve --mcp
  61    60  8000 /usr/lib/node --liftoff-only /x/codegraph-linux-x64/worker.js
  70    10  8000 node /home/dev/srv/mcp-server.js
  80    10  8000 node /opt/tools/acme-tracker/dist/index.js stdio
  90    10    60 timeout 600 pytest tests/unit/test_x.py
  99     1 99999 unrelated-old-daemon
`
const ROWS = parsePs(PS)

test('parsePs reads every row', () => {
  assert.equal(ROWS.length, 14)
})

test('isClaude knows the native, versioned and npm builds', () => {
  assert.ok(isClaude('claude remote-control --name x'))
  assert.ok(isClaude('/home/dev/.local/bin/claude daemon run'))
  assert.ok(isClaude('/home/dev/.local/share/claude/versions/2.1.318 --print'))
  assert.ok(isClaude('node /usr/lib/node_modules/@anthropic-ai/claude-code/cli.js'))
  assert.ok(!isClaude('/bin/sh -c node /repo/.claude/hooks/stop-children.mjs'))
  assert.ok(!isClaude('node /repo/.claude/hooks/stop-children.mjs'))
})

test('(a) the walk finds claude through an sh -c wrapper', () => {
  assert.equal(findSessionRoot(ROWS, 30), 10)
  // With no wrapper, the parent is the root.
  const direct = parsePs('10 1 9000 claude --print\n30 10 1 node hook.mjs\n')
  assert.equal(findSessionRoot(direct, 30), 10)
})

test('(b) MCP servers stay off the list. A 10 h wait loop and a hung pytest are on it', () => {
  const needles = mcpNeedles([{ mcpServers: { acme: { command: 'node', args: ['/opt/tools/acme-tracker/dist/index.js'] } } }])
  const old = oldChildren(ROWS, 10, 30 * 60, 30, needles).map((r) => r.pid)
  assert.deepEqual(old, [40, 50], 'oldest first')
  for (const pid of [60, 61, 70, 80]) assert.ok(!old.includes(pid), `MCP pid ${pid} is not listed`)
  assert.ok(!old.includes(99), 'a process outside the tree is never listed')
  assert.ok(!old.includes(90) && !old.includes(41), 'a young child is not listed')
  assert.ok(isMcpServer('npx -y @modelcontextprotocol/server-github'))
  assert.ok(!isMcpServer('/bin/bash -c until [ -f /tmp/x ]; do sleep 5; done'))
})

test('the hook never lists itself', () => {
  const rows = parsePs('10 1 9000 claude\n30 10 9000 node hook.mjs\n')
  assert.deepEqual(oldChildren(rows, 10, 1800, 30), [])
})

test('(c) the report names MCP servers as processes to keep', () => {
  // No config needles here, so the unnamed server at pid 80 is listed.
  const text = report(oldChildren(ROWS, 10, 1800, 30))
  assert.match(text, /3 child process/)
  assert.match(text, /KEEP the MCP servers/)
  assert.match(text, /Do not kill them/)
  assert.match(text, /name the ones that stay/)
})

test('(e) no claude ancestor gives exit 0', () => {
  assert.equal(findSessionRoot(parsePs('1 0 9 init\n20 1 9 sh -c x\n30 20 9 node hook\n'), 30), null)
  assert.equal(findSessionRoot([], 30), null)
  assert.deepEqual(main('{}', '1 0 9 init\n'), { code: 0 })
})

test('(f) stop_hook_active true gives exit 0', () => {
  assert.deepEqual(main('{"stop_hook_active": true}', PS), { code: 0 })
})

// The real form of a job that the Bash tool starts (copied from a live row).
const SNAP = '/bin/bash -c source /home/dev/.claude/shell-snapshots/snapshot-bash-1794002587456-1ebbn6.sh 2>/dev/null || true && shopt -u extglob 2>/dev/null || true && { \\builtin unalias -- \'which\'; \\builtin unset -f -- \'which\'; } >/dev/null 2>&1 || true && { \\builtin unalias -- \'unsetenv\'; \\builtin unset -f -- \'unsetenv\'; } >/dev/null 2>&1 || true && eval '
const wrap = (inner) => `${SNAP}'${inner}' < /dev/null && pwd -P >| /tmp/claude-9ef4-cwd`

test('the label shows the eval text of a Bash tool job', () => {
  const a = wrap('until [ -s .codegraph/codegraph.db ]; do sleep 5; done')
  const b = wrap('timeout 900 uv run pytest tests/unit/test_x.py -q')
  const c = wrap("cd /w && grep -n '\\''foo bar'\\'' x.py")
  const rows = parsePs(`10 1 90000 claude\n40 10 36000 ${a}\n41 10 36000 ${b}\n42 10 36000 ${c}\n`)
  const old = oldChildren(rows, 10, 1800, 30)
  assert.deepEqual(old.map((r) => r.pid).sort(), [40, 41, 42], 'all three are listed')
  const labels = old.map((r) => commandLabel(r.cmd))
  assert.equal(new Set(labels).size, 3, 'three jobs give three labels')
  assert.equal(commandLabel(a), 'until [ -s .codegraph/codegraph.db ]; do sleep 5; done')
  assert.equal(commandLabel(c), "cd /w && grep -n 'foo bar' x.py")
  // The live form of 2026-11-06 also escapes a single quote as '"'"'.
  assert.equal(commandLabel(wrap(`bash -c '"'"'sleep 5'"'"' & wait`)), "bash -c 'sleep 5' & wait")
  for (const l of labels) assert.ok(l.length <= 100)
  assert.ok(commandLabel(wrap('x'.repeat(500))).length <= 100)
  assert.ok(commandLabel('x '.repeat(500)).length <= 100, 'a plain command is cut too')
  assert.equal(commandLabel('sleep   99'), 'sleep 99', 'a plain command keeps the old form')
  assert.match(report(old), /until \[ -s \.codegraph/)
})

test('the label masks obvious secrets', () => {
  assert.equal(commandLabel('TOKEN=abc123 cmd'), 'TOKEN=*** cmd')
  const l = commandLabel(wrap('GH_API_KEY=xyz9 DB_PASSWORD="p w" curl -H "Authorization: Bearer abc.def" postgresql://u:pw@h/db sk-abcdef123456'))
  for (const s of ['abc123', 'xyz9', 'p w', 'abc.def', ':pw@', 'abcdef123456']) assert.ok(!l.includes(s), `${s} is masked in: ${l}`)
  assert.match(l, /GH_API_KEY=\*\*\*/)
})

test('the MCP test reads only a direct non-shell child of the root', () => {
  const rows = parsePs(
    '10 1 90000 claude\n' +
      `40 10 36000 ${wrap('until [ -s .codegraph/codegraph.db ]; do sleep 5; done')}\n` +
      "41 10 36000 bash -c until [ -s .codegraph/codegraph.db ]; do sleep 5; done\n" +
      '42 10 36000 timeout 900 uv run pytest tests/unit/test_mcp_servers_org_scope.py\n' +
      '43 42 36000 uv run pytest tests/unit/test_mcp_servers_org_scope.py\n' +
      '44 10 36000 /repo/.venv/bin/python -m pytest tests/unit/test_mcp_servers_org_scope.py\n' +
      '50 10 36000 node /home/dev/.local/bin/codegraph serve --mcp\n' +
      '51 10 36000 node /x/mcp-server.js\n' +
      '52 10 36000 node /opt/tools/acme-tracker/dist/index.js stdio\n' +
      '53 52 36000 /usr/bin/helper-worker\n' +
      '60 40 36000 node /x/mcp-server.js\n',
  )
  const needles = ['acme-tracker']
  const old = oldChildren(rows, 10, 1800, 30, needles).map((r) => r.pid)
  for (const pid of [40, 41, 42, 43, 44]) assert.ok(old.includes(pid), `job ${pid} is listed`)
  for (const pid of [50, 51, 52, 53]) assert.ok(!old.includes(pid), `MCP pid ${pid} is not listed`)
  assert.ok(old.includes(60), 'a grandchild is never taken as an MCP server')
  assert.ok(!isMcpServer('bash -c codegraph serve --mcp'), 'the -c text of a shell is never read')
  assert.ok(!isMcpServer('timeout 900 uv run pytest tests/unit/test_mcp_servers_org_scope.py'))
  assert.ok(isMcpServer('codegraph serve --mcp'))
  assert.ok(isMcpServer('/opt/x/acme-tracker serve', ['acme-tracker']))
})

// The CLI tests put a fake `ps` first on PATH. It prints a tree in which the
// hook (its parent, $PPID) runs under `sh -c`, under a claude process.
function fakeBin(dir, withPs = true) {
  const bin = path.join(dir, 'bin')
  fs.mkdirSync(bin, { recursive: true })
  if (withPs) {
    fs.writeFileSync(
      path.join(bin, 'ps'),
      '#!/bin/sh\n' +
        'echo "$PPID 900001 1 node hook"\n' +
        'echo "900001 900000 1 /bin/sh -c node hook"\n' +
        'echo "900000 1 9000 claude --print"\n' +
        'echo "900002 900000 36000 /bin/bash -c until false; do sleep 5; done"\n' +
        'echo "900003 900000 9000 node /x/codegraph serve --mcp"\n',
      { mode: 0o755 },
    )
  }
  return bin
}

function runCli(hookPath, bin, stdin) {
  const tmpHome = path.dirname(bin)
  return spawnSync(process.execPath, [hookPath], {
    input: stdin,
    encoding: 'utf8',
    timeout: 20000,
    env: { PATH: bin, HOME: tmpHome, CLAUDE_PROJECT_DIR: tmpHome },
  })
}

const posix = process.platform !== 'win32'

test('(d) the main guard runs on a path with a space', { skip: !posix }, () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'stop children '))
  try {
    const copy = path.join(dir, 'hook dir', 'stop-children.mjs')
    fs.mkdirSync(path.dirname(copy))
    fs.copyFileSync(HOOK, copy)
    const r = runCli(copy, fakeBin(dir), '{}')
    assert.equal(r.status, 2, r.stderr)
    assert.match(r.stderr, /900002/, 'the wait loop is listed')
    assert.doesNotMatch(r.stderr, /900003/, 'the MCP server is not listed')
    assert.match(r.stderr, /KEEP the MCP servers/)
  } finally {
    fs.rmSync(dir, { recursive: true, force: true })
  }
})

test('(e) no ps on PATH gives exit 0 and no output', { skip: !posix }, () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'stop-children-'))
  try {
    const r = runCli(HOOK, fakeBin(dir, false), '{}')
    assert.equal(r.status, 0)
    assert.equal(r.stderr, '')
  } finally {
    fs.rmSync(dir, { recursive: true, force: true })
  }
})

test('(f) stop_hook_active true exits 0 from the CLI', { skip: !posix }, () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'stop-children-'))
  try {
    const r = runCli(HOOK, fakeBin(dir), '{"stop_hook_active": true}')
    assert.equal(r.status, 0)
    assert.equal(r.stderr, '')
  } finally {
    fs.rmSync(dir, { recursive: true, force: true })
  }
})
