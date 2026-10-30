#!/usr/bin/env node
/**
 * Self-test for plan-guard.mjs.   Run: node .claude/hooks/plan-guard.test.mjs
 *
 * Add a case here for every gate you add to plan-guard.config.json. An untested
 * gate is a guess — regexes silently over- and under-match, and both failures
 * are expensive: over-matching blocks ordinary work, under-matching means the
 * boundary you think you have does not exist.
 *
 * The test builds a throwaway project in a temp folder (a git repo on a branch
 * called "work", the gate config copied from beside this file) and points the
 * guard at it with CLAUDE_PROJECT_DIR. So it runs the same from the kit
 * templates and from an installed .claude/hooks folder, and it never reads the
 * real grant file of the project.
 *
 * Note: several patterns below are assembled by concatenation on purpose. The
 * guard also inspects file content being written, so a fixture containing a
 * literal gated string could block its own creation.
 */
import { spawnSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import { mkdtempSync, mkdirSync, rmSync, copyFileSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import path from 'node:path'

const HERE = path.dirname(fileURLToPath(import.meta.url))
const GUARD = path.join(HERE, 'plan-guard.mjs')
const CONFIG = path.join(HERE, '..', 'plan-guard.config.json')
const GRANT_NAME = 'OWNER_' + 'GRANTS.md' // split: see the note above

const bash = (command) => ({ tool_name: 'Bash', tool_input: { command } })
const write = (file_path, content) => ({ tool_name: 'Write', tool_input: { file_path, content } })

// --- the sandbox project ----------------------------------------------------
const root = mkdtempSync(path.join(tmpdir(), 'plan-guard-proj-'))
mkdirSync(path.join(root, '.claude'))
copyFileSync(CONFIG, path.join(root, '.claude', 'plan-guard.config.json'))
const grantPath = path.join(root, '.claude', GRANT_NAME)
const git = (cwd, ...a) => spawnSync('git', a, { cwd, encoding: 'utf8' })
git(root, 'init', '-q')
git(root, 'checkout', '-q', '-B', 'work')
git(root, '-c', 'user.email=t@t', '-c', 'user.name=t', 'commit', '-q', '--allow-empty', '-m', 'init')

const pad = (n) => String(n).padStart(2, '0')
const dayOffset = (days) => {
  const d = new Date()
  d.setDate(d.getDate() + days)
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

/** Run the guard in the sandbox. `grants` is the full text of the grant file, or null for none. */
function blocked(payload, grants = null) {
  rmSync(grantPath, { force: true })
  if (grants !== null) writeFileSync(grantPath, grants)
  const res = spawnSync(process.execPath, [GUARD], {
    input: JSON.stringify({ cwd: root, ...payload }),
    encoding: 'utf8',
    env: { ...process.env, CLAUDE_PROJECT_DIR: root },
  })
  return { blocked: res.status === 2, stderr: res.stderr }
}

const FUTURE = dayOffset(30)
const PAST = dayOffset(-1)
const line = (kind, date, id) => `${kind} ${date} ${id} — test\n`

// [name, payload, expectBlocked, grantFileText]
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
  ['merge a PR', bash('gh pr merge 12 --squash'), true],
  ['write the guard', write('.claude/hooks/plan-guard.mjs', '//'), true],
  ['write settings', write('.claude/settings.json', '{}'), true],
  ['write grant file', write('.claude/' + GRANT_NAME, line('ALLOW-UNTIL', FUTURE, 'deploy')), true],
  ['shell-write grant file', bash(`echo x >> .claude/${GRANT_NAME}`), true],
  ['shell-edit grant file', bash(`sed -i s/a/b/ .claude/${GRANT_NAME}`), true],

  // --- must allow -----------------------------------------------------------
  ['run tests', bash('npm test'), false],
  ['run pytest', bash('pytest tests/unit/'), false],
  ['lint', bash('ruff check .'), false],
  ['git status', bash('git status --short'), false],
  ['git diff', bash('git diff main...HEAD'), false],
  ['cut a branch', bash('git switch -c ws-3-search main'), false],
  ['open a PR', bash('gh pr create --fill'), false],
  ['premerge script', bash('bash scripts/premerge.sh'), false],
  ['normal source edit', write('src/api/handler.ts', 'export const x = 1'), false],
  ['edit a spec', write('docs/specs/search.md', '## Status'), false],
  ['edit the work plan', write('docs/work-plan.md', '| WS-1 | ... |'), false],
  ['read grant file', bash(`cat .claude/${GRANT_NAME}`), false],
  ['grep grant file', bash(`grep ALLOW .claude/${GRANT_NAME} 2>/dev/null`), false],
  ['git add grant file', bash(`git add .claude/${GRANT_NAME}`), false],

  // --- grant window: a valid grant opens a grantable gate ---------------------
  ['deploy + valid grant', bash('bash deploy/release.sh'), false, line('ALLOW-UNTIL', FUTURE, 'deploy')],
  ['ssh + deploy grant', bash('ssh deploy@prod.example.com uptime'), false, line('ALLOW-UNTIL', FUTURE, 'deploy')],
  ['merge + valid grant', bash('gh pr merge 12 --squash'), false, line('ALLOW-UNTIL', FUTURE, 'merge')],
  ['dotenv write + grant', write('services/.env.local', 'X=1'), false, line('ALLOW-UNTIL', FUTURE, 'env-write')],
  ['dotenv read + grant', bash('cat .env.production'), false, line('ALLOW-UNTIL', FUTURE, 'secrets')],
  ['guard write + grant', write('.claude/hooks/plan-guard.mjs', '//'), false, line('ALLOW-UNTIL', FUTURE, 'guard-write')],
  ['one-day grant, today', bash('bash deploy/release.sh'), false, line('ALLOW', dayOffset(0), 'deploy')],

  // --- grant window: an expired or wrong grant does not -----------------------
  ['deploy + expired grant', bash('bash deploy/release.sh'), true, line('ALLOW-UNTIL', PAST, 'deploy')],
  ['one-day grant, past', bash('bash deploy/release.sh'), true, line('ALLOW', PAST, 'deploy')],
  ['one-day grant, future', bash('bash deploy/release.sh'), true, line('ALLOW', FUTURE, 'deploy')],
  ['wrong grant id', bash('bash deploy/release.sh'), true, line('ALLOW-UNTIL', FUTURE, 'secrets')],
  ['grant with no date', bash('bash deploy/release.sh'), true, 'ALLOW-UNTIL deploy — no date\n'],
  ['merge + expired grant', bash('gh pr merge 12 --squash'), true, line('ALLOW-UNTIL', PAST, 'merge')],

  // --- sealed acts stay blocked, whatever the grant file says -----------------
  ['force push + grant', bash('git push --' + 'force origin feat'), true, line('ALLOW-UNTIL', FUTURE, 'force-push') + line('ALLOW-UNTIL', FUTURE, 'deploy')],
  ['history rewrite + grant', bash('git filter-' + 'repo --path x'), true, line('ALLOW-UNTIL', FUTURE, 'history-rewrite')],
  ['reset to origin + grant', bash('git reset --hard origin/main'), true, line('ALLOW-UNTIL', FUTURE, 'history-rewrite')],
  ['terraform destroy + grant', bash('terraform destroy'), true, line('ALLOW-UNTIL', FUTURE, 'deploy')],
  ['drop table + grant', bash('psql -c "DROP TABLE users"'), true, line('ALLOW-UNTIL', FUTURE, 'deploy')],
  ['write grant file + grant', write('.claude/' + GRANT_NAME, 'x'), true, line('ALLOW-UNTIL', FUTURE, 'guard-write')],
  ['shell-write grant + grant', bash(`echo x >> .claude/${GRANT_NAME}`), true, line('ALLOW-UNTIL', FUTURE, 'deploy')],
]

let failed = 0
for (const [name, payload, expectBlocked, grants] of CASES) {
  const res = blocked(payload, grants ?? null)
  const ok = res.blocked === expectBlocked
  if (!ok) failed++
  console.log(
    `${ok ? 'ok  ' : 'FAIL'}  ${name.padEnd(26)} expected=${expectBlocked ? 'block' : 'allow'} got=${res.blocked ? 'block' : 'allow'}`,
  )
  if (!ok && res.stderr) console.log(`        ${res.stderr.split('\n')[0]}`)
}
let total = CASES.length

const check = (name, ok, note) => {
  total++
  if (!ok) failed++
  console.log(`${ok ? 'ok  ' : 'FAIL'}  ${name.padEnd(26)} ${note}`)
}

// Branch discipline. The sandbox sits on "work", so a commit is allowed. On a
// protected branch the commit is blocked, and a grant of any id cannot lift it.
const commit = bash('git ' + 'commit -m "wip"')
check('commit on work branch', !blocked(commit).blocked, '(expect allow)')
git(root, 'checkout', '-q', '-B', 'main')
check('commit on protected', blocked(commit).blocked, '(expect block)')
check(
  'commit on protected+grant',
  blocked(commit, ['deploy', 'merge', 'guard-write'].map((i) => line('ALLOW-UNTIL', FUTURE, i)).join('')).blocked,
  '(expect block)',
)

// Jurisdiction: branch discipline governs THIS repo only. A command operating on
// a different checkout answers to that project's rules. Claiming jurisdiction
// over it produces false blocks — which teach people to disable the guard, and
// that costs far more than the rule was worth.
const other = mkdtempSync(path.join(tmpdir(), 'plan-guard-other-'))
try {
  git(other, 'init', '-q')
  git(other, 'checkout', '-q', '-B', 'main')
  git(other, '-c', 'user.email=t@t', '-c', 'user.name=t', 'commit', '-q', '--allow-empty', '-m', 'init')
  check('foreign repo on main', !blocked(bash(`cd "${other}" && git ` + 'commit -m "wip"')).blocked, '(expect allow)')
  // ...but a dangerous command is dangerous in any repo, jurisdiction or not.
  check('foreign repo force-push', blocked(bash(`cd "${other}" && git push --` + 'force')).blocked, '(expect block)')
} finally {
  rmSync(other, { recursive: true, force: true })
}

// Fail-closed: a guard that cannot evaluate a call must block it, not wave it
// through. An uncaught throw exits 1, which the harness reads as "allow" — that
// is exactly how a boundary stops existing without anyone noticing.
const garbage = spawnSync(process.execPath, [GUARD], {
  input: 'not json at all',
  encoding: 'utf8',
  env: { ...process.env, CLAUDE_PROJECT_DIR: root },
})
check('unparseable payload', garbage.status === 2, '(expect block)')

rmSync(root, { recursive: true, force: true })
console.log(failed === 0 ? `\nall ${total} cases passed` : `\n${failed} of ${total} FAILED`)
process.exit(failed === 0 ? 0 : 1)
