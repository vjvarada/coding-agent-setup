#!/usr/bin/env node
/**
 * Self-test for plan-guard.mjs.   Run: node .claude/hooks/plan-guard.test.mjs
 *
 * Add a case here for every gate you add to plan-guard.config.json. An untested
 * gate is a guess — regexes silently over- and under-match, and both failures
 * are expensive: over-matching blocks ordinary work, under-matching means the
 * boundary you think you have does not exist.
 *
 * Note: several patterns below are assembled by concatenation on purpose. The
 * guard also inspects file content being written, so a fixture containing a
 * literal gated string could block its own creation.
 */
import { spawnSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import { mkdtempSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import path from 'node:path'

const GUARD = path.join(path.dirname(fileURLToPath(import.meta.url)), 'plan-guard.mjs')
const bash = (command) => ({ tool_name: 'Bash', tool_input: { command } })
const write = (file_path, content) => ({ tool_name: 'Write', tool_input: { file_path, content } })

// [name, payload, expectBlocked]
const CASES = [
  // --- must block -----------------------------------------------------------
  ['force push', bash('git push --' + 'force origin main'), true],
  ['push -f', bash('git push -f origin feat'), true],
  ['filter-branch', bash('git filter-' + 'branch --tree-filter rm secret'), true],
  ['delete remote branch', bash('git push origin --delete release'), true],
  ['deploy script', bash('bash deploy/release.sh'), true],
  ['npm deploy', bash('npm run deploy'), true],
  ['vercel prod', bash('vercel --prod'), true],
  ['terraform apply', bash('terraform apply -auto-approve'), true],
  ['kubectl delete', bash('kubectl delete pod api-0'), true],
  ['ssh remote', bash('ssh deploy@prod.example.com uptime'), true],
  ['drop table', bash('psql -c "DROP TABLE users"'), true],
  ['npm publish', bash('npm publish --access public'), true],
  ['read dotenv', bash('cat .env.production'), true],
  ['write dotenv', write('services/.env.local', 'X=1'), true],
  ['write deploy dir', write('deploy/compose.yml', 'services: {}'), true],
  ['write CI workflow', write('.github/workflows/release.yml', 'on: push'), true],
  ['write pem', write('certs/server.pem', '---'), true],

  // --- must allow -----------------------------------------------------------
  ['run tests', bash('npm test'), false],
  ['run pytest', bash('pytest tests/unit/'), false],
  ['lint', bash('ruff check .'), false],
  ['git status', bash('git status --short'), false],
  ['git diff', bash('git diff main...HEAD'), false],
  ['cut a branch', bash('git switch -c ws-3-search main'), false],
  ['open a PR', bash('gh pr create --fill'), false],
  ['normal source edit', write('src/api/handler.ts', 'export const x = 1'), false],
  ['edit a spec', write('docs/specs/search.md', '## Status'), false],
  ['edit the work plan', write('docs/work-plan.md', '| WS-1 | ... |'), false],
]

let failed = 0
for (const [name, payload, expectBlocked] of CASES) {
  const res = spawnSync(process.execPath, [GUARD], {
    input: JSON.stringify(payload),
    encoding: 'utf8',
  })
  const blocked = res.status === 2
  const ok = blocked === expectBlocked
  if (!ok) failed++
  console.log(
    `${ok ? 'ok  ' : 'FAIL'}  ${name.padEnd(22)} expected=${expectBlocked ? 'block' : 'allow'} got=${blocked ? 'block' : 'allow'}`,
  )
  if (!ok && res.stderr) console.log(`        ${res.stderr.split('\n')[0]}`)
}

const probe = (payload) =>
  spawnSync(process.execPath, [GUARD], { input: JSON.stringify(payload), encoding: 'utf8' }).status === 2

// Branch discipline depends on the branch you happen to be on, so report rather
// than assert a fixed expectation.
const branch = spawnSync('git', ['rev-parse', '--abbrev-ref', 'HEAD'], { encoding: 'utf8' }).stdout.trim()
const onProtected = ['main', 'master'].includes(branch)
const commitBlocked = probe(bash('git ' + 'commit -m "wip"'))
const branchOk = commitBlocked === onProtected
if (!branchOk) failed++
console.log(
  `${branchOk ? 'ok  ' : 'FAIL'}  ${'commit on protected'.padEnd(22)} branch=${branch} blocked=${commitBlocked}`,
)

// Jurisdiction: branch discipline governs THIS repo only. A command operating on
// a different checkout answers to that project's rules. Claiming jurisdiction
// over it produces false blocks — which teach people to disable the guard, and
// that costs far more than the rule was worth.
const other = mkdtempSync(path.join(tmpdir(), 'plan-guard-'))
try {
  const g = (...a) => spawnSync('git', a, { cwd: other, encoding: 'utf8' })
  g('init', '-q')
  g('checkout', '-q', '-B', 'main')
  g('-c', 'user.email=t@t', '-c', 'user.name=t', 'commit', '-q', '--allow-empty', '-m', 'init')

  const foreignBlocked = probe(bash(`cd "${other}" && git ` + 'commit -m "wip"'))
  const ok = !foreignBlocked
  if (!ok) failed++
  console.log(
    `${ok ? 'ok  ' : 'FAIL'}  ${'foreign repo on main'.padEnd(22)} blocked=${foreignBlocked} (expect allow)`,
  )

  // ...but a dangerous command is dangerous in any repo, jurisdiction or not.
  const foreignForce = probe(bash(`cd "${other}" && git push --` + 'force'))
  if (!foreignForce) failed++
  console.log(
    `${foreignForce ? 'ok  ' : 'FAIL'}  ${'foreign repo force-push'.padEnd(22)} blocked=${foreignForce} (expect block)`,
  )
} finally {
  rmSync(other, { recursive: true, force: true })
}

// Fail-closed: a guard that cannot evaluate a call must block it, not wave it
// through. An uncaught throw exits 1, which the harness reads as "allow" — that
// is exactly how a boundary stops existing without anyone noticing.
const garbageBlocked =
  spawnSync(process.execPath, [GUARD], { input: 'not json at all', encoding: 'utf8' }).status === 2
if (!garbageBlocked) failed++
console.log(
  `${garbageBlocked ? 'ok  ' : 'FAIL'}  ${'unparseable payload'.padEnd(22)} blocked=${garbageBlocked} (expect block)`,
)

console.log(failed === 0 ? `\nall ${CASES.length + 4} cases passed` : `\n${failed} FAILED`)
process.exit(failed === 0 ? 0 : 1)
