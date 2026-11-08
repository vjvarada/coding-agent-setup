#!/usr/bin/env node
/**
 * stop-children — before a session ends its turn, list the child processes it
 * still has that are older than 30 minutes (CIV-16, task 1828).
 *
 * WHY. On 2026-11-06 four wait loops (`until ... ; do sleep 5; done`) ran for
 * 10 to 12 hours on the box, and a test run hung for 10 h. The sessions that
 * started them had ended. The agent never saw what it left behind.
 *
 * It REPORTS and never kills. The first Stop with old children exits 2, so the
 * list reaches the agent, which then stops the jobs it does not need or names
 * the ones that stay. `stop_hook_active` is true on the second Stop, and the
 * hook then exits 0, so it can never loop.
 *
 * THE ROOT. Claude Code can start the hook through a shell (`sh -c`), so the
 * parent pid is not always the session. The hook walks up from its own pid to
 * the nearest `claude` process. When it finds none, it exits 0.
 *
 * MCP SERVERS STAY. The session starts its stdio MCP servers as children
 * (`codegraph serve --mcp`, for example). They live as long as the session,
 * so the hook never lists them or their workers. Only a direct child of the
 * root whose argv0 is not a shell or a wrapper can match.
 *
 * THE LABEL. A job of the Bash tool runs inside a long `bash -c` preamble.
 * The report shows the text inside its `eval`, with obvious secrets masked.
 *
 * ⚠️ FAILS OPEN AND SILENT. No `ps` (Windows), no `claude` ancestor, a parse
 * error or a crash all end in exit 0.
 * Fence: `node .claude/hooks/stop-children.test.mjs`, run by pr-check.yml.
 * The env var STOP_CHILDREN_MIN_AGE (seconds) changes the age limit. Only
 * the live proof of the test uses it.
 */

import { execFileSync } from 'node:child_process'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { pathToFileURL } from 'node:url'

export const MIN_AGE_SECONDS = 30 * 60

/** `[[dd-]hh:]mm:ss` (BSD/macOS `etime`) → seconds, or null. */
export function etimeToSeconds(etime) {
  const m = String(etime).trim().match(/^(?:(\d+)-)?(?:(\d+):)?(\d+):(\d+)$/)
  if (!m) return null
  const [, d = 0, h = 0, mi, s] = m
  return ((+d * 24 + +h) * 60 + +mi) * 60 + +s
}

/**
 * Process rows in the `etimes` (seconds) shape. procps (Linux) has `etimes`; BSD
 * and macOS `ps` only have `etime`, so fall back to it and convert.
 */
function listProcesses() {
  try {
    return execFileSync('ps', ['-eo', 'pid=,ppid=,etimes=,args='], { encoding: 'utf8', timeout: 5000 })
  } catch {
    const text = execFileSync('ps', ['-axo', 'pid=,ppid=,etime=,args='], { encoding: 'utf8', timeout: 5000 })
    return text
      .split('\n')
      .map((line) => {
        const m = line.match(/^\s*(\d+)\s+(\d+)\s+(\S+)\s+(.*)$/)
        const secs = m && etimeToSeconds(m[3])
        return m && secs != null ? `${m[1]} ${m[2]} ${secs} ${m[4]}` : ''
      })
      .join('\n')
  }
}

/** Parse `ps -eo pid=,ppid=,etimes=,args=` into rows. */
export function parsePs(text) {
  const rows = []
  for (const line of text.split('\n')) {
    const m = line.match(/^\s*(\d+)\s+(\d+)\s+(\d+)\s+(.*)$/)
    if (m) rows.push({ pid: +m[1], ppid: +m[2], age: +m[3], cmd: m[4] })
  }
  return rows
}

/**
 * True when `cmd` is the Claude Code CLI. The native build runs as
 * `claude ...` or as `~/.local/share/claude/versions/<v>`. The npm build runs
 * as `node .../@anthropic-ai/claude-code/cli.js`.
 */
export function isClaude(cmd) {
  const argv0 = cmd.trim().split(/\s+/)[0] || ''
  if (/(^|[\\/])claude(\.exe)?$/i.test(argv0)) return true
  if (/[\\/]claude[\\/]versions[\\/][^\\/]+$/i.test(argv0)) return true
  return /@anthropic-ai[\\/]claude-code[\\/]/i.test(cmd)
}

/** The pid of the nearest `claude` ancestor of `self`, or null. */
export function findSessionRoot(rows, self = process.pid) {
  const byPid = new Map(rows.map((r) => [r.pid, r]))
  const seen = new Set()
  let cur = byPid.get(self)
  while (cur && !seen.has(cur.pid)) {
    seen.add(cur.pid)
    const parent = byPid.get(cur.ppid)
    if (!parent || parent.pid <= 1) return null
    if (isClaude(parent.cmd)) return parent.pid
    cur = parent
  }
  return null
}

const MCP_PATTERNS = [
  /(^|\s)--mcp(\s|=|$)/i,
  /mcp[-_]server/i,
  /@modelcontextprotocol[\\/]/i,
  /(^|[\\/\s])codegraph(\s|$)/i,
]
const RUNNERS = new Set(['node', 'npx', 'npm', 'uvx', 'python', 'python3', 'bash', 'docker', 'deno', 'pnpm', 'yarn'])

/**
 * Words that name the stdio MCP servers in `.mcp.json` and `~/.claude.json`.
 * Best effort: a token is a needle when it is not a flag, not a runner and
 * at least 6 characters long. A config that does not parse gives no needles.
 */
export function mcpNeedles(configs) {
  const out = new Set()
  for (const cfg of configs) {
    for (const s of Object.values((cfg && cfg.mcpServers) || {})) {
      if (!s || typeof s.command !== 'string') continue
      for (const tok of [s.command, ...(Array.isArray(s.args) ? s.args : [])]) {
        if (typeof tok !== 'string' || tok.startsWith('-')) continue
        const base = path.basename(tok)
        if (base.length >= 6 && !RUNNERS.has(base)) out.add(base)
      }
    }
  }
  return [...out]
}

/**
 * A process whose argv0 is one of these words is never an MCP server. A shell
 * or a wrapper holds the command of an agent, and that text can name `mcp` or
 * `codegraph` by chance (a test file, a wait loop on `.codegraph/`).
 */
const WRAPPERS = new Set(['bash', 'sh', 'dash', 'zsh', 'timeout', 'env', 'uv', 'nohup', 'nice', 'pytest', 'xargs', 'watch'])

/**
 * True when `cmd` is a stdio MCP server that the session keeps. The test reads
 * only argv0 and its arguments. It never reads the `-c` text of a shell.
 */
export function isMcpServer(cmd, needles = []) {
  const argv = cmd.trim().split(/\s+/)
  const argv0 = path.basename(argv[0] || '').replace(/\.exe$/i, '')
  if (!argv0 || WRAPPERS.has(argv0)) return false
  // `python -m pytest tests/unit/test_mcp_x.py` is a test run, not a server.
  if (argv.includes('pytest') && argv[argv.indexOf('pytest') - 1] === '-m') return false
  const text = [argv0, ...argv.slice(1)].join(' ')
  if (MCP_PATTERNS.some((re) => re.test(text))) return true
  return needles.some((n) => text.includes(n))
}

const SECRET_PATTERNS = [
  [/\b(\w*(?:KEY|TOKEN|SECRET|PASSWORD|PASSWD|PWD)\w*)=("[^"]*"|'[^']*'|\S+)/gi, '$1=***'],
  [/\bBearer\s+\S+/gi, 'Bearer ***'],
  [/\bsk-[A-Za-z0-9_-]{6,}/g, 'sk-***'],
  [/(:\/\/[^\s:/@]+):[^\s@/]+@/g, '$1:***@'],
]

/**
 * A short label for a command, at most 100 characters. A job that the Bash
 * tool started runs as `bash -c source <snapshot> ... && eval '<command>' ...`.
 * The label is the text inside the eval. The label masks obvious secrets.
 */
export function commandLabel(cmd) {
  let text = String(cmd)
  const m = text.match(/\beval (['"])/)
  if (m) {
    const q = m[1]
    let body = text.slice(m.index + m[0].length)
    const cut = [`${q} < /dev/null`, `${q} && pwd -P`]
      .map((s) => body.indexOf(s))
      .filter((i) => i >= 0)
    if (cut.length) body = body.slice(0, Math.min(...cut))
    else if (body.endsWith(q)) body = body.slice(0, -1)
    // The Bash tool escapes a single quote as '\'' or as '"'"'.
    text = q === "'" ? body.replaceAll(`'\\''`, `'`).replaceAll(`'"'"'`, `'`) : body
  }
  text = text.replace(/\s+/g, ' ').trim()
  for (const [re, to] of SECRET_PATTERNS) text = text.replace(re, to)
  return text.slice(0, 100)
}

/**
 * The descendants of `root` that are older than `minAge`, oldest first.
 * The hook never lists an MCP server or a worker under it. Only a direct
 * child of `root` can be an MCP server, because the session starts them.
 */
export function oldChildren(rows, root, minAge = MIN_AGE_SECONDS, self = process.pid, needles = []) {
  const kids = new Map()
  for (const r of rows) {
    if (!kids.has(r.ppid)) kids.set(r.ppid, [])
    kids.get(r.ppid).push(r)
  }
  const out = []
  const seen = new Set([root])
  const stack = [root]
  while (stack.length) {
    for (const c of kids.get(stack.pop()) || []) {
      if (seen.has(c.pid)) continue
      seen.add(c.pid)
      if (c.ppid === root && isMcpServer(c.cmd, needles)) continue
      stack.push(c.pid)
      if (c.pid !== self && c.age >= minAge) out.push(c)
    }
  }
  return out.sort((a, b) => b.age - a.age)
}

export function report(list, minAge = MIN_AGE_SECONDS) {
  const lines = list.slice(0, 12).map((p) => {
    const hours = (p.age / 3600).toFixed(1)
    return `  pid ${p.pid}  ${hours} h  ${commandLabel(p.cmd)}`
  })
  return (
    `You still have ${list.length} child process(es) older than ` +
    (minAge >= 60 ? `${Math.round(minAge / 60)} minutes:\n` : `${minAge} seconds:\n`) +
    lines.join('\n') +
    '\nStop each one that the next step does not need (TaskStop, or kill the pid you started).' +
    ' KEEP the MCP servers of the session (codegraph serve --mcp and the like). Do not kill them.' +
    ' This list leaves them out on purpose.' +
    ' In your final message, name the ones that stay, and say why.'
  )
}

function readJson(file) {
  try {
    if (fs.statSync(file).size > 5_000_000) return null
    return JSON.parse(fs.readFileSync(file, 'utf8'))
  } catch {
    return null
  }
}

function mcpConfigs() {
  const dir = process.env.CLAUDE_PROJECT_DIR || process.cwd()
  const user = readJson(path.join(os.homedir(), '.claude.json'))
  const project = user && user.projects ? user.projects[dir] : null
  return [readJson(path.join(dir, '.mcp.json')), user, project]
}

function minAge() {
  const raw = process.env.STOP_CHILDREN_MIN_AGE
  const v = Number(raw)
  return raw && Number.isFinite(v) && v >= 0 ? v : MIN_AGE_SECONDS
}

/** One hook run. Returns `{ code, message? }`. `psText` is for the tests. */
export function main(stdin = '', psText = null) {
  let input = {}
  try {
    input = JSON.parse(stdin || '{}')
  } catch {}
  if (input.stop_hook_active) return { code: 0 }
  const text = psText ?? listProcesses()
  const rows = parsePs(text)
  const root = findSessionRoot(rows)
  if (root == null) return { code: 0 }
  const age = minAge()
  const list = oldChildren(rows, root, age, process.pid, mcpNeedles(mcpConfigs()))
  if (!list.length) return { code: 0 }
  return { code: 2, message: report(list, age) }
}

function isEntry() {
  const arg = process.argv[1]
  if (!arg) return false
  if (import.meta.url === pathToFileURL(arg).href) return true
  try {
    return import.meta.url === pathToFileURL(fs.realpathSync(arg)).href
  } catch {
    return false
  }
}

if (isEntry()) {
  let code = 0
  try {
    let stdin = ''
    try {
      stdin = fs.readFileSync(0, 'utf8')
    } catch {}
    const r = main(stdin)
    if (r.message) process.stderr.write(r.message + '\n')
    code = r.code
  } catch {
    code = 0
  }
  process.exit(code)
}
