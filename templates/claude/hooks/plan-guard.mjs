#!/usr/bin/env node
/**
 * plan-guard — deterministic owner-gate enforcement for the dispatch loop.
 *
 * The premise of an autonomous loop is that an agent can run unattended. The
 * premise only holds if there is a boundary the agent cannot argue its way past.
 * Instructions degrade over a long run — a hook does not. This is that boundary.
 *
 * Gates are declared in .claude/plan-guard.config.json, so they are reviewable
 * as data and stay in sync with the work plan's owner-gate section.
 *
 * Owner grants: the owner may open some gates for a dated window by writing
 * `ALLOW-UNTIL YYYY-MM-DD <grant-id> — reason` in .claude/OWNER_GRANTS.md. The
 * line starts at column 0 and sits outside any fenced code block. A gate
 * is grantable only when its config entry names a `grant` id. The sealed acts
 * (force-push, history rewrite, a commit on a protected branch or a push to
 * one, writing the grant file, destroying infrastructure or data) carry no
 * `grant`, so no line in any file opens them. A grant past its date is ignored.
 *
 * Contract: Claude Code PreToolUse hook. Tool call arrives as JSON on stdin.
 *   exit 0  -> allow
 *   exit 2  -> block; stderr is fed back to the agent as the reason
 *
 * FAILS CLOSED. If this script crashes or cannot read its config, it blocks
 * rather than allowing. A guard that silently stops guarding is worse than no
 * guard, because it is still believed — and in an unattended run there is nobody
 * to notice the warning it would otherwise print. Every block says how to fix it,
 * and the escape hatch is removing the hook from settings.json deliberately.
 * Self-test: node .claude/hooks/plan-guard.test.mjs
 */

import { execFileSync } from 'node:child_process'
import { readFileSync, existsSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

process.on('uncaughtException', (err) => {
  process.stderr.write(
    `BLOCKED by plan-guard: the guard itself crashed (${err.message}).\n\n` +
      'Failing closed on purpose — an unevaluated call is not a safe call. Fix the\n' +
      'guard before continuing: node .claude/hooks/plan-guard.test.mjs\n',
  )
  process.exit(2)
})

const HERE = path.dirname(fileURLToPath(import.meta.url))
const PROJECT_DIR = process.env.CLAUDE_PROJECT_DIR || path.resolve(HERE, '..', '..')
const CONFIG_PATH = path.join(PROJECT_DIR, '.claude', 'plan-guard.config.json')
const GRANT_FILE_RE = /(^|[\\/])\.claude[\\/]OWNER_GRANTS\.md$/i

/**
 * Grant ids the owner has opened today. Two line forms, both written by hand:
 *   ALLOW YYYY-MM-DD <id> — reason         (that local day only)
 *   ALLOW-UNTIL YYYY-MM-DD <id> — reason   (every day through that date)
 * A grant line starts at column 0. An indented line grants nothing. A line
 * inside a fenced code block (``` or ~~~) grants nothing. So an example in a
 * doc stays an example, even when someone copies the doc into place.
 * `ALLOW-UNTIL` with no date does not parse, so it grants nothing. ISO dates
 * compare as strings, so no timezone moves the boundary.
 */
function ownerGrants() {
  let text
  try {
    text = readFileSync(path.join(PROJECT_DIR, '.claude', 'OWNER_GRANTS.md'), 'utf8')
  } catch {
    return new Set()
  }
  const t = new Date()
  const today = `${t.getFullYear()}-${String(t.getMonth() + 1).padStart(2, '0')}-${String(t.getDate()).padStart(2, '0')}`
  const ids = new Set()
  // The open fence, such as "```" or "~~~~", or null outside a fence. The rules
  // follow CommonMark: an opener has at most 3 spaces before it. A closer uses
  // the same character, is at least as long, and has nothing after it. A fence
  // that never closes runs to the end of the file.
  let fence = null
  for (const line of text.replace(/^\uFEFF/, '').split(/\r?\n/)) {
    if (fence) {
      const close = line.match(/^ {0,3}(`{3,}|~{3,})[ \t]*$/)
      if (close && close[1][0] === fence[0] && close[1].length >= fence.length) fence = null
      continue
    }
    const open = line.match(/^ {0,3}(`{3,}(?=[^`]*$)|~{3,})/)
    if (open) {
      fence = open[1]
      continue
    }
    const m = line.match(/^ALLOW(-UNTIL)?\s+(\d{4}-\d{2}-\d{2})\s+([\w-]+)/)
    if (!m) continue
    const [, ranged, date, id] = m
    if (ranged ? date >= today : date === today) ids.add(id)
  }
  return ids
}

function loadConfig() {
  if (!existsSync(CONFIG_PATH)) {
    throw new Error(`no gate config at ${CONFIG_PATH} — copy it from the kit templates`)
  }
  const cfg = JSON.parse(readFileSync(CONFIG_PATH, 'utf8'))
  const compile = (list = []) => list.map((g) => ({ ...g, re: new RegExp(g.pattern, 'i') }))
  return {
    protectedBranches: cfg.protectedBranches || [],
    commandGates: compile(cfg.commandGates),
    pathGates: compile(cfg.pathGates),
  }
}

function block(reason, grant) {
  const how = grant
    ? 'The OWNER can open this gate for a dated window. Hand-write\n' +
      `"ALLOW-UNTIL <YYYY-MM-DD> ${grant} — reason" into .claude/OWNER_GRANTS.md,\n` +
      'at column 0 and outside any code block. In-chat permission is not a grant.\n\n'
    : 'No grant opens this act. It is sealed.\n\n'
  process.stderr.write(
    `BLOCKED by plan-guard: ${reason}\n\n${how}` +
      'This is an OWNER-GATE action — reserved for a human by the project work plan.\n' +
      'Do not look for another route to the same effect, and do not ask a subagent to\n' +
      'do it for you. Stop, write down the exact action the owner needs to take, and\n' +
      'report it as a blocker on the current ticket.\n',
  )
  process.exit(2)
}

function git(dir, ...args) {
  try {
    return execFileSync('git', args, {
      encoding: 'utf8',
      cwd: dir,
      stdio: ['ignore', 'pipe', 'ignore'],
    }).trim()
  } catch {
    return null
  }
}

/**
 * Where the command will actually run. A session can touch more than one repo,
 * and agents habitually write `cd <path> && git ...`, so the payload's cwd alone
 * is not enough.
 */
function effectiveCwd(cmd, payloadCwd) {
  const m = cmd.match(/^\s*cd\s+(?:"([^"]+)"|'([^']+)'|([^\s;&|]+))\s*(?:&&|;)/)
  const target = m ? m[1] || m[2] || m[3] : null
  if (!target) return payloadCwd || PROJECT_DIR
  return path.isAbsolute(target) ? target : path.resolve(payloadCwd || PROJECT_DIR, target)
}

const samePath = (a, b) =>
  a && b && path.resolve(a).toLowerCase() === path.resolve(b).toLowerCase()

/**
 * Branch discipline is scoped to the repo this guard governs. A command
 * operating on a *different* checkout answers to that project's rules, not
 * ours — claiming jurisdiction over it produces false blocks that teach people
 * to disable the guard, which costs far more than the rule was worth.
 * The command gates above stay universal: they are dangerous anywhere.
 */
function governsRepoAt(dir) {
  const here = git(dir, 'rev-parse', '--show-toplevel')
  const ours = git(PROJECT_DIR, 'rev-parse', '--show-toplevel')
  if (!here || !ours) return true // can't tell — fail closed
  return samePath(here, ours)
}

// ------------------------------------------------- the grant file in a shell --

// A command that names the grant file must be ONE of these, and nothing else.
// A read prints the file. A carry stages or commits what the owner wrote.
const DIR_OPT = String.raw`(-C\s+("[^"]*"|'[^']*'|\S+)\s+)?`
const GRANT_FILE_READ = new RegExp(
  String.raw`^\s*(cat|head|tail|grep|rg|type|Get-Content|ls|wc|git\s+${DIR_OPT}show)(?=\s|$)`,
  'i',
)
const GRANT_FILE_CARRY = new RegExp(String.raw`^\s*git\s+${DIR_OPT}(add|commit|diff|log|status)(?=\s|$)`, 'i')

/**
 * True when the shell runs `cmd` as one program and redirects nothing. Text in
 * single quotes is literal, so the scan skips it. Double quotes do not
 * protect: `$(`, a backtick and `;` still count inside them. The scan refuses
 * text that sh and PowerShell read in different ways: a backslash before a
 * quote, and the curly quotes that PowerShell takes as real quotes.
 */
function isOnePlainCommand(cmd) {
  if (/[\u2018-\u201F]/.test(cmd)) return false
  let inDouble = false
  for (let i = 0; i < cmd.length; i++) {
    const c = cmd[i]
    if (c === '\\' && (cmd[i + 1] === "'" || cmd[i + 1] === '"')) return false
    if (c === '"') inDouble = !inDouble
    else if (c === "'" && !inDouble) {
      i = cmd.indexOf("'", i + 1)
      if (i === -1) return false
    } else if (';&|<>`$()\r\n'.includes(c)) return false
  }
  return !inDouble
}

/**
 * May this shell command name the grant file? Only a read, or a git command
 * that carries what the owner wrote, and only as ONE plain command. Without
 * that rule `git status && echo ... >> <grant file>` passes. So does
 * `git show <old>:<grant file> > <grant file>`, which revives a dead grant.
 */
function grantFileCommandOk(cmd) {
  const bare = cmd.replace(/\s2>\s*(\/dev\/null|\$null|&1)(?=\s|$)/gi, '')
  // The words the program gets once the shell drops the quotes. --output makes
  // git log, diff and show write a file. --pre makes rg run a program.
  const unquoted = bare.replace(/['"\\`]/g, '')
  if (/--(ou|pre(?=[=\s]|$))/i.test(unquoted)) return false
  return isOnePlainCommand(bare) && (GRANT_FILE_READ.test(bare) || GRANT_FILE_CARRY.test(bare))
}

// ------------------------------------------------------ reading a git push --

const baseName = (w) => w.split(/[\\/]/).pop()
const isShellWord = (w) => /^(bash|sh|zsh|dash|ksh|fish|pwsh|powershell|cmd|eval|wsl)(\.exe)?$/i.test(baseName(w))

/**
 * Skip heredoc bodies that start at `start`. Returns the index after the last
 * delimiter line. A body with no delimiter line runs to the end.
 */
function skipHeredocs(cmd, start, docs) {
  let j = start
  for (const { delim, strip } of docs) {
    while (j < cmd.length) {
      const nl = cmd.indexOf('\n', j)
      const end = nl === -1 ? cmd.length : nl
      let text = cmd.slice(j, end).replace(/\r$/, '')
      if (strip) text = text.replace(/^\t+/, '')
      j = end + 1
      if (text === delim) break
    }
  }
  return j
}

/**
 * Split a command line into simple commands, each a list of words. It reads
 * quotes and escapes the way the shell does, and it drops redirections and
 * heredoc bodies. It is not a full shell parser. It only has to find each
 * `git push` and its words. When `(`, `$(` or a backtick cuts a word short, the
 * word keeps that mark, so the push check sees that the shell changes it.
 * PowerShell escapes with a backtick. sh escapes with a backslash.
 */
function simpleCommands(cmd, powershell) {
  const esc = powershell ? '`' : '\\'
  const out = []
  let words = []
  let word = null // the word being read, or null between words
  let redirect = false // the next word is a redirect target, not an argument
  let tick = false // inside a sh backtick span
  let heredocs = [] // heredoc bodies that start on the next line
  const add = (s) => {
    word = (word ?? '') + s
  }
  const endWord = () => {
    if (word === null) return
    if (redirect) redirect = false
    else words.push(word)
    word = null
  }
  const endCommand = () => {
    endWord()
    redirect = false
    if (words.length) out.push(words)
    words = []
  }
  for (let i = 0; i < cmd.length; i++) {
    const c = cmd[i]
    if (c === esc) {
      if (cmd[i + 1] === '\n') i++ // a line continuation
      else if (i + 1 < cmd.length) add(cmd[++i])
    } else if (c === "'") {
      const end = cmd.indexOf("'", i + 1)
      const stop = end === -1 ? cmd.length : end
      add(cmd.slice(i + 1, stop))
      i = stop
    } else if (c === '"') {
      let s = ''
      for (i++; i < cmd.length && cmd[i] !== '"'; i++) {
        if (cmd[i] === esc && i + 1 < cmd.length && (powershell || '$`"\\\n'.includes(cmd[i + 1]))) i++
        s += cmd[i]
      }
      add(s)
    } else if (c === ' ' || c === '\t') {
      endWord()
    } else if ('\r\n;&|'.includes(c)) {
      endCommand()
      if (c === '\n' && heredocs.length) {
        // A heredoc body is data, unless a shell in the same pipeline reads it.
        const shellReads = out.slice(heredocs[0].from).some((ws) => ws.some(isShellWord))
        if (!shellReads) i = skipHeredocs(cmd, i + 1, heredocs) - 1
        heredocs = []
      }
    } else if (c === '(' || c === ')' || (c === '`' && !powershell)) {
      // These start or end other commands. Mark a word they cut short. In
      // PowerShell, `git push origin (Get-X)` runs Get-X for the refspec.
      if (c === '`') tick = !tick
      if (c === '(' ? word !== null || words.length > 0 : c === '`' && tick && word !== null) add(c)
      endCommand()
    } else if (c === '<' && cmd[i + 1] === '<' && cmd[i + 2] !== '<' && !powershell) {
      i += 2
      const strip = cmd[i] === '-'
      if (strip) i++
      while (cmd[i] === ' ' || cmd[i] === '\t') i++
      let delim = ''
      for (; i < cmd.length && !/[\s;&|<>()]/.test(cmd[i]); i++) {
        if (!`'"\\`.includes(cmd[i])) delim += cmd[i]
      }
      i--
      if (delim) heredocs.push({ delim, strip, from: out.length })
    } else if (c === '>' || c === '<') {
      if (word !== null && /^\d+$/.test(word)) word = null // "2>" names a stream
      endWord()
      while ('<>&|'.includes(cmd[i + 1] ?? 'x')) i++ // also eats a <<< here-string
      redirect = true
    } else {
      add(c)
    }
  }
  endCommand()
  return out
}

/**
 * Read the words after `git push`. Returns the flags that matter here and the
 * positional words. The first positional is the remote. The guard checks it
 * like a refspec too, because a remote named "main" is rarer than a trick.
 * git accepts a long option by any unique prefix, so `--mir` is `--mirror`.
 */
function readPush(args) {
  const push = { force: false, del: false, all: null, words: [] }
  let options = true
  for (const w of args) {
    if (options && w === '--') {
      options = false
      continue
    }
    if (options && w.startsWith('--')) {
      const name = w.slice(2).split('=')[0].toLowerCase()
      const is = (...full) => name !== '' && full.some((f) => f.startsWith(name))
      if (is('force', 'force-with-lease', 'force-if-includes')) push.force = true
      if (is('delete', 'prune')) push.del = true
      if (is('all', 'branches', 'mirror')) push.all = w
      continue
    }
    if (options && /^-./.test(w)) {
      const flags = w.slice(1).split('o')[0] // -o takes the rest as its value
      if (flags.includes('f')) push.force = true
      if (flags.includes('d')) push.del = true
      continue
    }
    if (w.startsWith('+')) push.force = true
    if (/^\+?:/.test(w)) push.del = true
    push.words.push(w)
  }
  return push
}

/**
 * Every `git push` in the command, with its -C dirs, its -c config and its
 * words. A shell runs its argument, and `$(` or a backtick inside a
 * double-quoted word runs too. So the guard reads that text as commands.
 */
function gitPushes(cmd, powershell, depth = 0) {
  const found = []
  for (const words of simpleCommands(cmd, powershell)) {
    let shell = false
    for (const w of words) {
      if (depth < 3 && (shell || /\$\(|`/.test(w)) && /\bpush\b/i.test(w)) {
        found.push(...gitPushes(w, powershell, depth + 1))
      }
      if (isShellWord(w)) shell = true
    }
    let i = words.findIndex((w) => /^git(\.exe)?$/i.test(baseName(w)))
    if (i === -1) continue
    // xargs adds words from its input, so the guard cannot see them.
    const xargs = words.slice(0, i).some((w) => /^xargs(\.exe)?$/i.test(baseName(w)))
    const push = { chdir: [], config: [], xargs }
    for (i++; i < words.length && words[i].startsWith('-'); i++) {
      const w = words[i]
      if ((w === '-C' || w === '-c') && i + 1 < words.length) {
        i++
        if (w === '-C') push.chdir.push(words[i])
        else push.config.push('-c', words[i])
      } else if (/^--(git-dir|work-tree|namespace|config-env)$/.test(w)) i++
    }
    if (words[i] !== 'push') continue
    found.push({ ...push, ...readPush(words.slice(i + 1)) })
  }
  return found
}

// ---------------------------------------------------------------- run it --

let raw = ''
process.stdin.setEncoding('utf8')
for await (const chunk of process.stdin) raw += chunk

// A payload we cannot parse is a call we cannot evaluate — the uncaughtException
// handler turns that into a block, which is the point.
const payload = JSON.parse(raw)
const config = loadConfig()
const grants = ownerGrants()
const granted = (gate) => Boolean(gate.grant) && grants.has(gate.grant)
const isProtected = (name) =>
  Boolean(name) && config.protectedBranches.some((b) => b.toLowerCase() === name.toLowerCase())

const tool = payload.tool_name || ''
const input = payload.tool_input || {}

const PUSH_FIX = 'Push your own branch and open a PR: git push -u origin <your-branch>'

/**
 * Refuse a push word that writes a protected branch on the remote. A word is
 * `<src>:<dst>`, or `<name>` alone, which pushes to the same name. `branch`
 * is the local branch, which is what a bare HEAD pushes.
 */
function checkPushWords(words, branch) {
  for (const word of words) {
    const w = word.replace(/^\+/, '')
    const colon = w.lastIndexOf(':')
    let dst = colon === -1 ? w : w.slice(colon + 1)
    // `@x` is a PowerShell splat. The other marks are globs and expansions.
    if (/[$*?[\]{}()`]|^@\w/.test(w) || (colon !== -1 && (dst === '' || /^(head|@)$/i.test(dst)))) {
      block(
        `cannot tell which remote branch "${word}" writes. A glob, a shell expansion or a ` +
          `remote HEAD can reach a protected branch. Name the branch in plain text. ${PUSH_FIX}`,
      )
    }
    if (colon === -1 && /^(head|@)$/i.test(dst)) dst = branch || ''
    dst = dst.replace(/\/{2,}/g, '/').replace(/^\/?(refs\/)?heads\//i, '')
    if (isProtected(dst)) block(`pushing to protected branch "${dst}" ("${word}"). ${PUSH_FIX}`)
  }
}

/**
 * With no refspec on the command line, git takes the target from the config:
 * remote.<name>.push, remote.<name>.mirror, push.default and the upstream.
 * Read those the same way, with the -c values of the push itself.
 */
function checkConfiguredPush(push, dir, branch) {
  const cfg = git(dir, ...push.config, 'config', '--get-regexp', '^(remote\\..+\\.(push|mirror)|push\\.default)$')
  const fromConfig = []
  for (const row of (cfg || '').split(/\r?\n/)) {
    const m = row.match(/^(\S+)\s+(.*)$/)
    if (!m) continue
    const [, key, value] = m
    if (/\.mirror$/i.test(key) && /^(true|yes|on|1)$/i.test(value)) {
      block(`${key} is true, so "git push" mirrors every branch, protected ones too. ${PUSH_FIX}`)
    }
    if (/^push\.default$/i.test(key) && /^matching$/i.test(value)) {
      block(`push.default is "matching", so "git push" pushes every branch, protected ones too. ${PUSH_FIX}`)
    }
    if (/\.push$/i.test(key)) fromConfig.push(value)
  }
  checkPushWords(fromConfig, branch)
  if (!branch || branch === 'HEAD') return
  const row = git(dir, ...push.config, 'for-each-ref', '--format=%(push:remotename)|%(push)', `refs/heads/${branch}`)
  const [remote, ref] = (row || '').split('|')
  const dst = remote && ref ? ref.replace(`refs/remotes/${remote}/`, '') : ''
  if (isProtected(dst)) {
    block(`"git push" sends "${branch}" to ${remote}/${dst}, a protected branch. The upstream and push.default decide that. ${PUSH_FIX}`)
  }
}

// ---------------------------------------------------------------- commands --
if (tool === 'Bash' || tool === 'PowerShell' || tool === 'Shell') {
  const cmd = String(input.command || '')

  // The grant file is never shell-writable, and no grant lifts that. A read, or
  // a git command that carries what the owner wrote, may name it. Each must be
  // ONE plain command, so no second command and no redirect can ride along.
  if (/OWNER_GRANTS/i.test(cmd) && !grantFileCommandOk(cmd)) {
    block(
      'shell command touching .claude/OWNER_GRANTS.md — only the owner writes grants.\n' +
        'You may read the file, or commit what the owner wrote, with ONE plain command.\n' +
        'Put no ;, &&, |, redirect, $( ), backtick or newline in it. For example:\n' +
        '  git add .claude/OWNER_GRANTS.md\n' +
        "  git commit -m 'grant: <id>' -- .claude/OWNER_GRANTS.md\n" +
        'Write the commit message in single quotes, or pass it with -F <file>.\n' +
        'Use git -C <dir> in place of cd <dir> &&.',
    )
  }

  for (const gate of config.commandGates) {
    if (gate.re.test(cmd) && !granted(gate)) block(`${gate.id} — ${gate.why}`, gate.grant)
  }

  const dir = effectiveCwd(cmd, payload.cwd)
  const pushes = gitPushes(cmd, tool === 'PowerShell')

  // Like the command gates, these two are dangerous in any repo. The config
  // patterns miss a "+" refspec, a flag group such as -fu, -d and ":<branch>".
  for (const push of pushes) {
    if (push.xargs) {
      block('cannot read "xargs git push": xargs adds words from its input. Run git push with every word in plain text.')
    }
    if (push.force) {
      block('force-push — a "+" refspec or an -f flag forces the push. Force-push discards history that may not exist anywhere else.')
    }
    if (push.del) {
      block('branch-delete-remote — git push -d, --delete, --prune or ":<branch>" deletes a remote branch the agent cannot restore.')
    }
  }

  // Work lands on a branch, never directly on a protected one. A PR is the
  // review surface the whole loop is built to produce; committing on main
  // skips it entirely. A push is checked by where it WRITES, not only by the
  // local branch, so `git push origin HEAD:main` from a feature branch fails.
  if (pushes.length || /\bgit\s+(commit|push|merge|rebase)\b/.test(cmd)) {
    if (governsRepoAt(dir)) {
      const branch = git(dir, 'rev-parse', '--abbrev-ref', 'HEAD')
      if (branch && isProtected(branch)) {
        block(
          `committing or pushing directly on protected branch "${branch}". ` +
            `Cut a ticket-named branch first: git switch -c <ticket>-<slug> ${branch}`,
        )
      }
    }
    for (const push of pushes) {
      const pushDir = push.chdir.reduce((d, c) => path.resolve(d, c), dir)
      if (!governsRepoAt(pushDir)) continue
      if (push.all) block(`"git push ${push.all}" pushes every branch, protected ones too. ${PUSH_FIX}`)
      const branch = git(pushDir, 'rev-parse', '--abbrev-ref', 'HEAD')
      checkPushWords(push.words, branch)
      // One word is the remote alone. Then git reads the target from config.
      if (push.words.length <= 1) checkConfiguredPush(push, pushDir, branch)
    }
  }
}

// ------------------------------------------------------------------- writes --
if (['Edit', 'Write', 'MultiEdit', 'NotebookEdit'].includes(tool)) {
  const file = String(input.file_path || input.notebook_path || '')
  // A grant an agent can write is not a grant. Sealed: no grant lifts this.
  if (GRANT_FILE_RE.test(file)) {
    block(`writing to ${file} — only the owner writes grants.`)
  }
  for (const gate of config.pathGates) {
    if (gate.re.test(file) && !granted(gate)) {
      block(`writing to ${file} — ${gate.id}: ${gate.why}`, gate.grant)
    }
  }

  // Some gates describe an *effect* (flipping a production flag) that can be
  // reached by editing a file just as easily as by running a command.
  const body = String(input.content || input.new_string || '')
  if (body) {
    for (const gate of config.commandGates) {
      if (gate.scanContent && gate.re.test(body) && !granted(gate)) {
        block(`${gate.id} in the content being written to ${file} — ${gate.why}`, gate.grant)
      }
    }
  }
}

process.exit(0)
