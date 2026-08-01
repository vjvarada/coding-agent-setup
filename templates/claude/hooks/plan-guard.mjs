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

function block(reason) {
  process.stderr.write(
    `BLOCKED by plan-guard: ${reason}\n\n` +
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

let raw = ''
process.stdin.setEncoding('utf8')
for await (const chunk of process.stdin) raw += chunk

// A payload we cannot parse is a call we cannot evaluate — the uncaughtException
// handler turns that into a block, which is the point.
const payload = JSON.parse(raw)
const config = loadConfig()

const tool = payload.tool_name || ''
const input = payload.tool_input || {}

// ---------------------------------------------------------------- commands --
if (tool === 'Bash' || tool === 'PowerShell' || tool === 'Shell') {
  const cmd = String(input.command || '')

  for (const gate of config.commandGates) {
    if (gate.re.test(cmd)) block(`${gate.id} — ${gate.why}`)
  }

  // Work lands on a branch, never directly on a protected one. A PR is the
  // review surface the whole loop is built to produce; committing on main
  // skips it entirely.
  if (/\bgit\s+(commit|push|merge|rebase)\b/.test(cmd)) {
    const dir = effectiveCwd(cmd, payload.cwd)
    if (governsRepoAt(dir)) {
      const branch = git(dir, 'rev-parse', '--abbrev-ref', 'HEAD')
      if (branch && config.protectedBranches.includes(branch)) {
        block(
          `committing or pushing directly on protected branch "${branch}". ` +
            `Cut a ticket-named branch first: git switch -c <ticket>-<slug> ${branch}`,
        )
      }
    }
  }
}

// ------------------------------------------------------------------- writes --
if (['Edit', 'Write', 'MultiEdit', 'NotebookEdit'].includes(tool)) {
  const file = String(input.file_path || input.notebook_path || '')
  for (const gate of config.pathGates) {
    if (gate.re.test(file)) block(`writing to ${file} — ${gate.id}: ${gate.why}`)
  }

  // Some gates describe an *effect* (flipping a production flag) that can be
  // reached by editing a file just as easily as by running a command.
  const body = String(input.content || input.new_string || '')
  if (body) {
    for (const gate of config.commandGates) {
      if (gate.scanContent && gate.re.test(body)) {
        block(`${gate.id} in the content being written to ${file} — ${gate.why}`)
      }
    }
  }
}

process.exit(0)
