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
import { mkdtempSync, mkdirSync, rmSync, copyFileSync, writeFileSync, existsSync, readFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import path from 'node:path'

const HERE = path.dirname(fileURLToPath(import.meta.url))
const GUARD = path.join(HERE, 'plan-guard.mjs')
const CONFIG = path.join(HERE, '..', 'plan-guard.config.json')
const GRANT_NAME = 'OWNER_' + 'GRANTS.md' // split: see the note above

const bash = (command) => ({ tool_name: 'Bash', tool_input: { command } })
const pwsh = (command) => ({ tool_name: 'PowerShell', tool_input: { command } })
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
// Pin push.default, so a global git config cannot change the push cases.
git(root, 'config', 'push.default', 'simple')

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

  // --- grant file in a shell: ONE plain read or git carry, nothing more ------
  // The start of a command is not enough. A second command or a redirect can
  // ride along, and `git show <old>:<file> > <file>` revives a dead grant.
  ['grant: status && append', bash(`git status && echo "ALLOW-UNTIL 2099-12-31 guard-write — x" >> .claude/${GRANT_NAME}`), true],
  ['grant: show > revive', bash(`git show HEAD~3:.claude/${GRANT_NAME} > .claude/${GRANT_NAME}`), true],
  ['grant: show --output', bash(`git show --output=.claude/${GRANT_NAME} HEAD~3:.claude/${GRANT_NAME}`), true],
  ['grant: log quoted --output', bash(`git log -1 --format='ALLOW-UNTIL 2099-12-31 deploy' '--output=.claude/${GRANT_NAME}'`), true],
  ['grant: add; append', bash(`git add x; echo y >> .claude/${GRANT_NAME}`), true],
  ['grant: commit "$(cat)"', bash(`git commit -m "$(cat .claude/${GRANT_NAME})"`), true],
  ['grant: " hides a quote', bash(`git commit -m "it's" ; echo x >> .claude/${GRANT_NAME} ; echo "'"`), true],
  ['grant: backslash quote', bash(`git commit -m \\'; echo x >> .claude/${GRANT_NAME}; echo \\'`), true],
  ['grant: curly quotes', pwsh(`git commit -m ’a' ; echo x >> .claude/${GRANT_NAME} ; '’`), true],
  ['grant: read + newline', bash(`cat .claude/${GRANT_NAME}\nsed -i s/a/b/ .claude/${GRANT_NAME}`), true],
  ['grant: rg --pre runs', bash(`rg --pre ./x.sh ALLOW .claude/${GRANT_NAME}`), true],
  ['grant: cd && add', bash(`cd . && git add .claude/${GRANT_NAME}`), true],
  ['grant: git commit', bash(`git commit -m 'grant: deploy' -- .claude/${GRANT_NAME}`), false],
  ['grant: git commit -F', bash(`git commit -F msg.txt -- .claude/${GRANT_NAME}`), false],
  ['grant: git diff', bash(`git diff .claude/${GRANT_NAME}`), false],
  ['grant: git log', bash(`git log -- .claude/${GRANT_NAME}`), false],
  ['grant: git log --pretty', bash(`git log --oneline --pretty=format:%h -- .claude/${GRANT_NAME}`), false],
  ['grant: git -C add', bash(`git -C "${root}" add .claude/${GRANT_NAME}`), false],
  ['grant: git show read', bash(`git show HEAD:.claude/${GRANT_NAME}`), false],
  ['grant: quoted | in grep', bash(`grep 'ALLOW|DENY' .claude/${GRANT_NAME}`), false],

  // --- grant parser: a grant is a column-0 line outside any code fence --------
  ['indented grant', bash('bash deploy/release.sh'), true, '    ' + line('ALLOW-UNTIL', FUTURE, 'deploy')],
  ['tab-indented grant', bash('bash deploy/release.sh'), true, '\t' + line('ALLOW-UNTIL', FUTURE, 'deploy')],
  ['grant in ``` fence', bash('bash deploy/release.sh'), true, '```\n' + line('ALLOW-UNTIL', FUTURE, 'deploy') + '```\n'],
  ['grant in ~~~ fence', bash('bash deploy/release.sh'), true, '~~~text\n' + line('ALLOW-UNTIL', FUTURE, 'deploy') + '~~~\n'],
  ['grant in open fence', bash('bash deploy/release.sh'), true, '```\n' + line('ALLOW-UNTIL', FUTURE, 'deploy')],
  ['```js does not close', bash('bash deploy/release.sh'), true, '```\n```js\n' + line('ALLOW-UNTIL', FUTURE, 'deploy') + '```\n'],
  ['``` does not close ~~~', bash('bash deploy/release.sh'), true, '~~~\n```\n' + line('ALLOW-UNTIL', FUTURE, 'deploy') + '~~~\n'],
  ['grant after a fence', bash('bash deploy/release.sh'), false, '```\nexample\n```\n' + line('ALLOW-UNTIL', FUTURE, 'deploy')],
  ['grant after a BOM', bash('bash deploy/release.sh'), false, '﻿' + line('ALLOW-UNTIL', FUTURE, 'deploy')],

  // --- push: checked by where it writes, not only by the local branch ---------
  // The sandbox sits on "work", so the local-branch rule alone allows all of these.
  ['push HEAD:main', bash('git push origin HEAD:main'), true],
  ['push main by name', bash('git push origin main'), true],
  ['push +x:refs/heads/main', bash('git push origin +feature:refs/heads/main'), true],
  ['push feature:main', bash('git push origin feature:main'), true],
  ['push HEAD:master', bash('git push origin HEAD:master'), true],
  ['push HEAD:heads/main', bash('git push origin HEAD:heads/main'), true],
  ['push HEAD:MAIN', bash('git push origin HEAD:MAIN'), true],
  ['push quoted HEAD:main', bash("git push origin 'HEAD:main'"), true],
  ['push escaped ma\\in', bash('git push origin HEAD:ma\\in'), true],
  ['push --all', bash('git push --all origin'), true],
  ['push --mirror', bash('git push --mirror origin'), true],
  ['push --branches', bash('git push --branches origin'), true],
  ['push --al (prefix)', bash('git push --al origin'), true],
  ['push glob refspec', bash("git push origin 'refs/heads/*:refs/heads/*'"), true],
  ['push $VAR refspec', bash('git push origin HEAD:$BRANCH'), true],
  ['push $( ) refspec', bash('git push origin HEAD:$(echo main)'), true],
  ['push remote HEAD', bash('git push origin feature:HEAD'), true],
  ['push git -C .', bash('git -C . push origin HEAD:main'), true],
  ['push after &&', bash('npm test && git push origin HEAD:main'), true],
  ['push in bash -c', bash("bash -c 'git push origin HEAD:main'"), true],
  ['push in "$( )"', bash('echo "$(git push origin HEAD:main)"'), true],
  ['push in piped heredoc', bash('cat <<EOF | bash\ngit push origin HEAD:main\nEOF'), true],
  ['push under xargs', bash('echo HEAD:main | xargs git push origin'), true],
  ['push PS (expr)', pwsh('git push origin (Get-Branch)'), true],
  ['push PS backtick', pwsh('git push origin HEAD:ma`in'), true],
  ['push "+" forces', bash('git push origin +feature-x'), true],
  ['push -fu forces', bash('git push -fu origin feature-x'), true],
  ['push -d deletes', bash('git push origin -d release'), true],
  ['push +:x deletes', bash('git push origin +:release'), true],
  ['push -u feature', bash('git push -u origin feature-x'), false],
  ['push origin HEAD', bash('git push origin HEAD'), false],
  ['push feature:feature', bash('git push origin feature-x:feature-x'), false],
  ['push -o value', bash('git push -o ci.skip origin feature-x'), false],
  ['push --dry-run', bash('git push --dry-run origin feature-x'), false],
  ['push --tags', bash('git push --tags'), false],
  ['commit msg names push', bash("git commit -m 'never git push origin main'"), false],
  ['heredoc names push', bash("git commit -F- <<'EOF'\nnever git push origin HEAD:main\nEOF"), false],
  ['"$(cat <<EOF)" names push', bash(`git commit -m "$(cat <<'EOF'\nnever git push origin HEAD:main\nEOF\n)"`), false],
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

// A push with no refspec. git takes the target from the config, so the guard
// reads the config too. The sandbox gets a bare remote with a "main" branch,
// and "work" tracks origin/main.
const remote = mkdtempSync(path.join(tmpdir(), 'plan-guard-remote-'))
try {
  git(remote, 'init', '-q', '--bare')
  git(root, 'remote', 'add', 'origin', remote)
  git(root, 'push', '-q', 'origin', 'work:main')
  git(root, 'fetch', '-q', 'origin')
  git(root, 'branch', '-q', '--set-upstream-to=origin/main', 'work')
  const barePush = bash('git ' + 'push')
  check('bare push, simple', !blocked(barePush).blocked, '(expect allow)')
  check('push origin work', !blocked(bash('git push origin work')).blocked, '(expect allow)')
  git(root, 'config', 'push.default', 'upstream')
  check('bare push, upstream main', blocked(barePush).blocked, '(expect block)')
  check('push origin, upstream main', blocked(bash('git push origin')).blocked, '(expect block)')
  check('push origin work, upstream', !blocked(bash('git push origin work')).blocked, '(expect allow)')
  git(root, 'config', 'push.default', 'simple')
  check('push -c push.default', blocked(bash('git -c push.default=upstream push')).blocked, '(expect block)')
  git(root, 'config', 'push.default', 'matching')
  check('bare push, matching', blocked(barePush).blocked, '(expect block)')
  git(root, 'config', 'push.default', 'simple')
  git(root, 'config', 'remote.origin.push', 'HEAD:refs/heads/main')
  check('push origin, config refspec', blocked(bash('git push origin')).blocked, '(expect block)')
  git(root, 'config', '--unset', 'remote.origin.push')
  git(root, 'config', 'remote.origin.mirror', 'true')
  check('bare push, remote mirror', blocked(barePush).blocked, '(expect block)')
} finally {
  git(root, 'config', 'push.default', 'simple')
  git(root, 'remote', 'remove', 'origin')
  rmSync(remote, { recursive: true, force: true })
}

// The kit's grant-file template must open nothing when someone copies it into
// place. Its examples sit in a fence and carry a past date. The second pass
// moves every date into the future, to prove the fence alone keeps them shut.
// The third pass adds one real line, to prove the fence closes.
const TEMPLATE = path.join(HERE, '..', '..', 'shared', GRANT_NAME)
if (existsSync(TEMPLATE)) {
  const text = readFileSync(TEMPLATE, 'utf8')
  const future = text.replace(/\d{4}-\d{2}-\d{2}/g, FUTURE)
  const probes = [
    ['deploy', bash('bash deploy/release.sh')],
    ['merge', bash('gh pr merge 12 --squash')],
    ['guard-write', write('.claude/hooks/plan-guard.mjs', '//')],
    ['secrets', bash('cat .env.production')],
    ['env-write', write('services/.env.local', 'X=1')],
    ['deploy-write', write('deploy/compose.yml', 'services: {}')],
  ]
  for (const [id, probe] of probes) {
    check(`template: no ${id}`, blocked(probe, text).blocked, '(expect block)')
    check(`template+future: no ${id}`, blocked(probe, future).blocked, '(expect block)')
  }
  const added = text + line('ALLOW-UNTIL', FUTURE, 'deploy')
  check('template + real line', !blocked(bash('bash deploy/release.sh'), added).blocked, '(expect allow)')
} else {
  console.log(`skip  template grants             (no ${TEMPLATE})`)
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
  check('foreign repo push main', !blocked(bash(`cd "${other}" && git push origin HEAD:main`)).blocked, '(expect allow)')
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
