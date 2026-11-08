#!/usr/bin/env node
/**
 * Tests for worktree-notice.mjs. Run: node .claude/hooks/worktree-notice.test.mjs
 *
 * The fence for the stale-rules notice (ported from Metorite). A session loads
 * AGENTS.md, CLAUDE.md and `.claude/` from its own checkout. When that checkout
 * falls behind `origin/main`, the session follows old rules and nothing says so.
 * On the source platform the primary checkout was once 258 commits behind. These
 * tests fail when the hook stops naming that gap, or when it starts to crash a
 * session.
 */
import assert from 'node:assert/strict'
import { spawnSync, execFileSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import { mkdtempSync, mkdirSync, writeFileSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import path from 'node:path'

const HOOK = path.join(path.dirname(fileURLToPath(import.meta.url)), 'worktree-notice.mjs')

// Importing the hook must not run it: a top-level process.exit would end this
// test here, before any check below, and print nothing.
const { staleRulesNotice, RULE_PATHS } = await import(new URL('./worktree-notice.mjs', import.meta.url))

let passed = 0
function test(name, fn) {
  try {
    fn()
    passed += 1
  } catch (err) {
    console.error(`FAIL ${name}\n${err.stack}`)
    process.exit(1)
  }
}

function gitIn(root, ...args) {
  return execFileSync('git', args, { cwd: root, encoding: 'utf-8', stdio: ['ignore', 'pipe', 'pipe'] }).trim()
}

function runHook(root) {
  return spawnSync(process.execPath, [HOOK], {
    env: { ...process.env, CLAUDE_PROJECT_DIR: root },
    encoding: 'utf-8',
  })
}

test('current rules give no notice', () => {
  assert.equal(staleRulesNotice(0, ['CLAUDE.md'], 0), '')
  assert.equal(staleRulesNotice(12, [], 0), '')
})

test('stale rules name the gap, the files and the rule of record', () => {
  const text = staleRulesNotice(258, ['CLAUDE.md', '.claude/commands/next-ticket.md'], 0)
  assert.match(text, /258 commits behind origin\/main/)
  assert.match(text, /`CLAUDE.md`/)
  assert.match(text, /next-ticket\.md/)
  assert.match(text, /git show origin\/main:CLAUDE\.md/)
})

test('a branch with no commits of its own is told to fast-forward', () => {
  assert.match(staleRulesNotice(3, ['CLAUDE.md'], 0), /git merge --ff-only origin\/main/)
})

test('a branch with its own commits is told to merge main, never to reset', () => {
  const text = staleRulesNotice(3, ['CLAUDE.md'], 2)
  assert.match(text, /merge `origin\/main` into it/)
  assert.doesNotMatch(text, /--ff-only|reset/)
})

test('a long file list is cut, and says how many it left out', () => {
  const files = Array.from({ length: 9 }, (_, i) => `.claude/hooks/h${i}.mjs`)
  assert.match(staleRulesNotice(5, files, 0), /and 3 more/)
})

test('the rule paths hold the entry points, the loop commands and the skills', () => {
  for (const p of ['CLAUDE.md', 'AGENTS.md', '.claude/commands', '.github/skills']) {
    assert.ok(RULE_PATHS.includes(p), p)
  }
})

test('the hook reports a checkout that is behind on its rules', () => {
  const root = mkdtempSync(path.join(tmpdir(), 'wt-notice-'))
  try {
    gitIn(root, 'init', '-q', '-b', 'main')
    gitIn(root, 'config', 'user.email', 'test@example.com')
    gitIn(root, 'config', 'user.name', 'test')
    writeFileSync(path.join(root, 'CLAUDE.md'), 'old rules\n', 'utf-8')
    gitIn(root, 'add', 'CLAUDE.md')
    gitIn(root, 'commit', '-q', '-m', 'old')
    const old = gitIn(root, 'rev-parse', 'HEAD')
    writeFileSync(path.join(root, 'CLAUDE.md'), 'new rules\n', 'utf-8')
    gitIn(root, 'commit', '-q', '-am', 'new')
    gitIn(root, 'update-ref', 'refs/remotes/origin/main', 'HEAD')
    gitIn(root, 'checkout', '-q', '--detach', old)
    // The worktree convention is adopted only when scripts/worktree.sh exists.
    mkdirSync(path.join(root, 'scripts'))
    writeFileSync(path.join(root, 'scripts', 'worktree.sh'), '#!/bin/sh\n', 'utf-8')

    const r = runHook(root)
    assert.equal(r.status, 0)
    assert.match(r.stdout, /1 commits behind origin\/main/)
    assert.match(r.stdout, /`CLAUDE.md`/)
    assert.match(r.stdout, /PRIMARY checkout/)
  } finally {
    rmSync(root, { recursive: true, force: true })
  }
})

test('a checkout level with main gets no stale notice', () => {
  const root = mkdtempSync(path.join(tmpdir(), 'wt-notice-'))
  try {
    gitIn(root, 'init', '-q', '-b', 'main')
    gitIn(root, 'config', 'user.email', 'test@example.com')
    gitIn(root, 'config', 'user.name', 'test')
    writeFileSync(path.join(root, 'CLAUDE.md'), 'rules\n', 'utf-8')
    gitIn(root, 'add', 'CLAUDE.md')
    gitIn(root, 'commit', '-q', '-m', 'one')
    gitIn(root, 'update-ref', 'refs/remotes/origin/main', 'HEAD')

    const r = runHook(root)
    assert.equal(r.status, 0)
    assert.doesNotMatch(r.stdout, /commits behind/)
  } finally {
    rmSync(root, { recursive: true, force: true })
  }
})

test('without scripts/worktree.sh the primary checkout gets no worktree warning', () => {
  const root = mkdtempSync(path.join(tmpdir(), 'wt-notice-'))
  try {
    gitIn(root, 'init', '-q', '-b', 'main')
    gitIn(root, 'config', 'user.email', 'test@example.com')
    gitIn(root, 'config', 'user.name', 'test')
    writeFileSync(path.join(root, 'AGENTS.md'), 'rules\n', 'utf-8')
    gitIn(root, 'add', 'AGENTS.md')
    gitIn(root, 'commit', '-q', '-m', 'one')

    const r = runHook(root)
    assert.equal(r.status, 0)
    assert.doesNotMatch(r.stdout, /PRIMARY checkout/)
  } finally {
    rmSync(root, { recursive: true, force: true })
  }
})

test('outside a git repo the hook exits 0 and says nothing', () => {
  const root = mkdtempSync(path.join(tmpdir(), 'wt-notice-'))
  try {
    const r = runHook(root)
    assert.equal(r.status, 0)
    assert.equal(r.stdout.trim(), '')
  } finally {
    rmSync(root, { recursive: true, force: true })
  }
})

console.log(`worktree-notice: ${passed} passed`)
