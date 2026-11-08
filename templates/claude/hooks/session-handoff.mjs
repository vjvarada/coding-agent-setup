#!/usr/bin/env node
/**
 * SessionStart — inject the open entries of HANDOFF.md into the session context.
 *
 * Ported from Metorite (where it fixed: "work that spans sessions was carried in
 * the owner's head"). A session ended with three owner-gated items and two
 * scoped-out findings, and the next one started blind, so the items were
 * re-derived or, more often, lost.
 *
 * WHY A HOOK AND NOT A LINE IN CLAUDE.md / AGENTS.md. Those files are the stable
 * router; a pending-work queue changes every session. A mutable queue inside a
 * stable document makes the stable document untrustworthy, and a stale queue
 * entry there reads like doctrine. Separate file, separate lifetime.
 *
 * This hook deliberately does NOT run each entry's Check. Executing commands out
 * of a markdown file at session start is an arbitrary-execution seam pointed at
 * the one file every session loads, and a hanging Check would block startup. The
 * session runs the Checks itself, under the permission model, having read them.
 *
 * File location: $HANDOFF_PATH (relative to the repo root) if set, else the first
 * of HANDOFF.md, project-docs/HANDOFF.md, docs/HANDOFF.md that exists.
 * Formats: the kit's `## Queue` section, or the older `# OPEN` / `# DONE` split.
 *
 * Fails OPEN and silent: a missing or malformed HANDOFF.md never stops a session.
 */

import { readFileSync, existsSync } from "node:fs";
import { join } from "node:path";

/** Entries older than this are surfaced with a warning. */
const STALE_DAYS = 21;

const root = process.env.CLAUDE_PROJECT_DIR || process.cwd();

function emit(context) {
  process.stdout.write(
    JSON.stringify({
      hookSpecificOutput: {
        hookEventName: "SessionStart",
        additionalContext: context,
      },
    })
  );
  process.exit(0);
}

function locate() {
  const candidates = process.env.HANDOFF_PATH
    ? [process.env.HANDOFF_PATH]
    : ["HANDOFF.md", join("project-docs", "HANDOFF.md"), join("docs", "HANDOFF.md")];
  for (const rel of candidates) {
    if (existsSync(join(root, rel))) return rel;
  }
  return null;
}

const rel = locate();
if (!rel) process.exit(0); // No queue, nothing to say. Not an error.

let raw;
try {
  raw = readFileSync(join(root, rel), "utf-8");
} catch {
  process.exit(0);
}

/**
 * The open part of the file. Everything above it is the protocol, which the
 * session reads from the file when it needs to act. Repeating it in every prompt
 * would cost more than it buys.
 */
function openSection(text) {
  if (/^# OPEN\s*$/m.test(text)) {
    return text.split(/^# OPEN\s*$/m)[1]?.split(/^# DONE/m)[0] ?? "";
  }
  const parts = text.split(/^## Queue\s*$/m);
  if (parts.length < 2) return "";
  // Stop at the next level-2 heading, if any.
  return parts[1].split(/^## (?!#)/m)[0];
}

const blocks = openSection(raw)
  .replace(/<!--[\s\S]*?-->/g, "")
  .split(/^### /m)
  .slice(1) // text before the first ### is not an entry
  .map((b) => b.trim())
  .filter(Boolean);

if (blocks.length === 0) {
  emit(
    `**Handoff queue is empty** (\`${rel}\`). Nothing was left pending by a ` +
      "previous session. Add an entry before you end this one if you hand " +
      "anything over (`/handoff add`)."
  );
}

/** Days since an entry's `**Added:** YYYY-MM-DD`, or null if unparseable. */
function age(block) {
  const m = block.match(/\*\*Added:\*\*\s*(\d{4}-\d{2}-\d{2})/);
  if (!m) return null;
  const days = Math.floor((Date.now() - Date.parse(m[1])) / 86_400_000);
  return Number.isFinite(days) ? days : null;
}

const lines = blocks.map((block) => {
  const title = block.split("\n")[0].trim();
  const days = age(block);
  const warn = days !== null && days >= STALE_DAYS ? `  ⚠️ ${days}d old` : "";
  return `- ${title}${warn}`;
});

const owner = blocks.filter((b) => /\[OWNER\]/.test(b.split("\n")[0])).length;
const agent = blocks.length - owner;

emit(
  [
    `## Handoff queue — ${blocks.length} open (${agent} agent, ${owner} owner-gated)`,
    "",
    `Left unfinished by previous sessions. Each entry in \`${rel}\` has a`,
    "**Check** that re-derives whether it is still real.",
    "",
    ...lines,
    "",
    "**Before other work:** run each entry's Check, and **delete every entry",
    "whose Check shows it is done** (close its task on the board too) in your",
    "first commit. An entry that outlives its work is how this file starts lying.",
    "Then tell the user what is left, in one short list, and carry on with what",
    "they asked for.",
    "",
    "⚠️ `[OWNER]` entries are owner gates: verify and report them, never do them.",
    "⚠️ These are ACTIONS, not state. The task board or work plan holds the state,",
    "and an entry that disagrees with it is wrong.",
  ].join("\n")
);
