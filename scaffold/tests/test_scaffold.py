"""Kit tests for the scaffolder. Run from the kit root:

    python -m unittest discover -s scaffold/tests -v

Each test scaffolds into a throwaway directory and judges the result with the
project-side tool (`.harness/harness.py`) the way an agent would. The central
property, from the DOE framework's own lesson log: a scaffolder must emit
everything its validator requires — for EVERY archetype — or each new project
starts non-compliant and repeats the same manual repair.
"""
from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import io
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

KIT = Path(__file__).resolve().parents[2]
HAVE_GIT = shutil.which("git") is not None


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


scaffold = _load(KIT / "scaffold" / "scaffold.py", "kit_scaffold")
TODO = scaffold.TODO


def minimal_intake(archetype: str, **extra) -> dict:
    intake = {
        "name": f"Test {archetype}",
        "summary": f"A throwaway {archetype} used by the kit tests.",
        "owner": "kit-tests",
        "archetype": archetype,
        "brief": {"problem": "p", "users": "u", "goals": ["g"], "non_goals": ["n"], "success": ["s"]},
    }
    if archetype == "agent":
        intake["skills"] = [{"name": "do-thing", "description": "Do the thing. Use when asked to do it."}]
        intake["agent"] = {"runtime": "ide"}
    if archetype not in ("agent",):
        archetypes, _ = scaffold.catalogs()
        intake["scopes"] = archetypes["archetypes"][archetype]["scopes"]
    intake.update(extra)
    return intake


class Workspace:
    """A temp project directory (git-initialised when git exists) plus helpers."""

    def __init__(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name) / "project"
        self.root.mkdir()
        if HAVE_GIT:
            subprocess.run(["git", "init", "-q"], cwd=self.root, check=True)

    def close(self) -> None:
        self._tmp.cleanup()

    def scaffold(self, intake: dict, *extra: str) -> tuple[int, str]:
        path = self.root.parent / "intake.json"
        path.write_text(json.dumps(intake), encoding="utf-8")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = scaffold.main(["new", "--intake", str(path), "--target", str(self.root), *extra])
        return code, buf.getvalue()

    def harness(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(self.root / ".harness" / "harness.py"), *args],
                              cwd=self.root, capture_output=True, text=True, encoding="utf-8")

    def tree_hash(self) -> str:
        h = hashlib.sha256()
        for p in sorted(self.root.rglob("*")):
            if p.is_file() and ".git" not in p.parts and "__pycache__" not in p.parts:
                h.update(p.relative_to(self.root).as_posix().encode())
                h.update(p.read_bytes())
        return h.hexdigest()

    def resolve_markers(self) -> int:
        """Do what the scaffolding agent does in SCAFFOLD.md step 6, crudely."""
        n = 0
        for p in self.root.rglob("*"):
            if p.is_file() and ".git" not in p.parts and p.suffix in (".md", ".yml", ".json"):
                text = p.read_text(encoding="utf-8")
                if TODO in text:
                    n += text.count(TODO)
                    p.write_text(text.replace(TODO, "Filled"), encoding="utf-8")
        return n


class ScaffoldTests(unittest.TestCase):
    def setUp(self) -> None:
        self.ws = Workspace()

    def tearDown(self) -> None:
        self.ws.close()

    # ── the core property ────────────────────────────────────────────────────
    def test_every_archetype_scaffolds_and_passes_its_own_check(self) -> None:
        archetypes, _ = scaffold.catalogs()
        for name in archetypes["archetypes"]:
            with self.subTest(archetype=name):
                ws = Workspace()
                try:
                    code, out = ws.scaffold(minimal_intake(name))
                    self.assertEqual(code, 0, out)
                    r = ws.harness("check")
                    self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
                    project = json.loads((ws.root / ".harness/project.json").read_text(encoding="utf-8"))
                    for req in project["required_paths"]:
                        self.assertTrue((ws.root / req).exists(), f"{name}: required {req} not emitted")
                finally:
                    ws.close()

    def test_strict_check_fails_until_the_agent_resolves_every_marker(self) -> None:
        self.ws.scaffold(minimal_intake("agent"))
        strict = self.ws.harness("check", "--strict")
        self.assertEqual(strict.returncode, 1, strict.stdout)
        self.assertIn(TODO, strict.stdout)
        self.assertGreater(self.ws.resolve_markers(), 0)
        strict = self.ws.harness("check", "--strict")
        self.assertEqual(strict.returncode, 0, strict.stdout)

    def test_skill_tests_pass_out_of_the_box(self) -> None:
        self.ws.scaffold(minimal_intake("agent"))
        r = self.ws.harness("test")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("do-thing: OK (skipped=1)", r.stdout)  # the behaviour test waits, visibly

    # ── non-destructive and idempotent ───────────────────────────────────────
    def test_a_second_run_is_a_no_op(self) -> None:
        self.ws.scaffold(minimal_intake("web-app"))
        before = self.ws.tree_hash()
        code, out = self.ws.scaffold(minimal_intake("web-app"))
        self.assertEqual(code, 0, out)
        self.assertIn("NO-OP", out)
        self.assertEqual(before, self.ws.tree_hash())

    def test_existing_files_are_composed_or_kept_never_lost(self) -> None:
        (self.ws.root / "AGENTS.md").write_text("# Generator notes\n\nKEEP-ME-AGENTS\n", encoding="utf-8")
        (self.ws.root / "README.md").write_text("# App\n\nKEEP-ME-README\n", encoding="utf-8")
        (self.ws.root / ".gitignore").write_text("node_modules/\n", encoding="utf-8")
        (self.ws.root / "docs").mkdir()
        (self.ws.root / "docs" / "brief.md").write_text("MY OWN BRIEF\n", encoding="utf-8")
        code, out = self.ws.scaffold(minimal_intake("cli"))
        self.assertEqual(code, 0, out)
        agents = (self.ws.root / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("<!-- harness:dox -->", agents)
        self.assertIn("KEEP-ME-AGENTS", agents)
        self.assertIn(TODO, agents.split("Notes carried over")[1])  # the agent must merge them
        readme = (self.ws.root / "README.md").read_text(encoding="utf-8")
        self.assertTrue(readme.startswith("# App\n\nKEEP-ME-README"))
        self.assertIn("<!-- harness:readme -->", readme)
        self.assertEqual((self.ws.root / "docs/brief.md").read_text(encoding="utf-8"), "MY OWN BRIEF\n")
        gi = (self.ws.root / ".gitignore").read_text(encoding="utf-8")
        self.assertTrue(gi.startswith("node_modules/"))
        self.assertEqual(gi.count("__pycache__/"), 1)

    def test_dry_run_writes_nothing(self) -> None:
        code, out = self.ws.scaffold(minimal_intake("library"), "--dry-run")
        self.assertEqual(code, 0, out)
        self.assertIn("DRY RUN", out)
        self.assertEqual([p.name for p in self.ws.root.iterdir() if p.name != ".git"], [])

    # ── intake validation ────────────────────────────────────────────────────
    def test_invalid_intakes_are_refused_with_reasons(self) -> None:
        bad = minimal_intake("agent")
        bad["archetype"] = "spaceship"
        code, out = self.ws.scaffold(bad)
        self.assertEqual(code, 1)
        self.assertIn("archetype", out)
        bad = minimal_intake("agent")
        bad["skills"] = [{"name": "Bad_Name", "description": "x"}, {"name": "self-annealing", "description": "y"}]
        code, out = self.ws.scaffold(bad)
        self.assertEqual(code, 1)
        self.assertIn("kebab-case", out)
        self.assertIn("core skill", out)
        code, out = self.ws.scaffold({"name": "x", "archetype": "cli"})
        self.assertIn("summary", out)
        self.assertFalse((self.ws.root / "AGENTS.md").exists())

    # ── the harness check catches what it claims to ──────────────────────────
    @unittest.skipUnless(HAVE_GIT, "git not installed")
    def test_ignore_traps_are_caught(self) -> None:
        self.ws.scaffold(minimal_intake("agent"))
        gi = self.ws.root / ".gitignore"
        gi.write_text(gi.read_text(encoding="utf-8") + "\n*.tmp\n.claude/\n", encoding="utf-8")
        r = self.ws.harness("check")
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn(".tmp/scripts/run_store.py", r.stdout)
        self.assertIn(".claude/settings.json", r.stdout)

    @unittest.skipUnless(HAVE_GIT, "git not installed")
    def test_env_example_is_not_a_false_alarm(self) -> None:
        self.ws.scaffold(minimal_intake("agent"))
        r = self.ws.harness("check")
        self.assertNotIn(".env.example", r.stdout)

    def test_proxy_drift_fails_check_and_sync_repairs_it(self) -> None:
        self.ws.scaffold(minimal_intake("agent"))
        skill = self.ws.root / ".github/skills/do-thing/SKILL.md"
        skill.write_text(skill.read_text(encoding="utf-8").replace("Do the thing.", "Do a different thing."),
                         encoding="utf-8")
        r = self.ws.harness("check")
        self.assertEqual(r.returncode, 1)
        self.assertIn(".claude/skills/do-thing/SKILL.md out of date", r.stdout)
        self.assertEqual(self.ws.harness("sync").returncode, 0)
        self.assertEqual(self.ws.harness("check").returncode, 0)
        self.assertIn("Do a different thing", (self.ws.root / "AGENTS.md").read_text(encoding="utf-8"))

    def test_a_missing_child_contract_is_an_error(self) -> None:
        self.ws.scaffold(minimal_intake("api-service"))
        (self.ws.root / "src" / "AGENTS.md").unlink()
        r = self.ws.harness("check")
        self.assertEqual(r.returncode, 1)
        self.assertIn("src/AGENTS.md", r.stdout)

    # ── upgrade ──────────────────────────────────────────────────────────────
    def test_upgrade_refreshes_untouched_kit_files_and_spares_edited_ones(self) -> None:
        self.ws.scaffold(minimal_intake("agent"))
        harness = self.ws.root / ".harness/harness.py"
        anneal = self.ws.root / ".github/skills/self-annealing/scripts/anneal.py"
        manifest = json.loads((self.ws.root / ".harness/manifest.json").read_text(encoding="utf-8"))
        # Simulate an older kit version of harness.py that the project never touched.
        old = harness.read_text(encoding="utf-8") + "\n# older kit version\n"
        harness.write_text(old, encoding="utf-8")
        manifest["files"][".harness/harness.py"]["sha256"] = hashlib.sha256(old.encode()).hexdigest()
        (self.ws.root / ".harness/manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        anneal.write_text(anneal.read_text(encoding="utf-8") + "\n# local edit\n", encoding="utf-8")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = scaffold.main(["upgrade", "--target", str(self.ws.root)])
        out = buf.getvalue()
        self.assertEqual(code, 0, out)
        self.assertNotIn("older kit version", harness.read_text(encoding="utf-8"))
        self.assertIn("local edit", anneal.read_text(encoding="utf-8"))
        self.assertIn("anneal.py was edited", out)

    # ── runtimes ─────────────────────────────────────────────────────────────
    def test_commandcenter_runtime_emits_a_loadable_contract(self) -> None:
        intake = minimal_intake("agent")
        intake["agent"] = {"runtime": "commandcenter", "integrations": ["anthropic"]}
        code, out = self.ws.scaffold(intake)
        self.assertEqual(code, 0, out)
        cfg = json.loads((self.ws.root / "config.json").read_text(encoding="utf-8"))
        self.assertEqual(cfg["max_mutation_attempts"], 1)
        self.assertEqual(cfg["name"], "test-agent")
        r = subprocess.run([sys.executable, "-c", "import agents; print(len(agents.SYSTEM_PROMPT)); "
                            "print('Tool: do-thing' in agents.SYSTEM_PROMPT, 'Tool: self-annealing' in agents.SYSTEM_PROMPT)"],
                           cwd=self.ws.root, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("True False", r.stdout)  # runtime skills in, developer skills out
        self.assertIn("ANTHROPIC_API_KEY=", (self.ws.root / ".env.example").read_text(encoding="utf-8"))
        self.assertEqual(self.ws.harness("check").returncode, 0)

    def test_run_store_records_and_finds_runs(self) -> None:
        self.ws.scaffold(minimal_intake("agent"))
        rs = _load(self.ws.root / ".tmp/scripts/run_store.py", "ws_run_store")
        base = self.ws.root / "outputs"
        rs.new_run("acme/rfq-1", {"customer": "acme"}, base)
        rs.save_step("acme/rfq-1", "Extract requirements", {"rows": 3}, base)
        rs.finish_run("acme/rfq-1", "success", "3 requirements", base)
        self.assertTrue((base / "acme/rfq-1/step_1_extract_requirements.json").exists())
        self.assertEqual([r["slug"] for r in rs.search(["acme", "requirements"], base)], ["acme/rfq-1"])
        with self.assertRaises(FileExistsError):
            rs.new_run("acme/rfq-1", {}, base)


class ReviewRegressionTests(unittest.TestCase):
    """Defects an independent review found; each test failed before its fix."""

    def setUp(self) -> None:
        self.ws = Workspace()

    def tearDown(self) -> None:
        self.ws.close()

    def test_hostile_intake_text_still_yields_parseable_files(self) -> None:
        intake = minimal_intake("agent")
        intake["name"] = "Acme: Lead \"Finder\" 'X'"
        intake["slug"] = "acme-finder"
        intake["summary"] = r"Reads C:\Users\data, says \"hi\" — handles ü, 日本, 🚀 and a stray triple quote '''."
        intake["skills"] = [
            {"name": "3d-render", "description": r"Render C:\models\x.step: fast. Use when asked → render.",
             "when": r"a path like C:\cad\part 'quoted' appears"},
            {"name": "build-agent", "description": "Shadows a name in agents.py. Use never."},
        ]
        intake["agent"] = {"runtime": "commandcenter"}
        intake["stack"] = {"id": "doe-agent", "test": 'make test ARGS="-v: all"'}
        code, out = self.ws.scaffold(intake)
        self.assertEqual(code, 0, out)
        root = self.ws.root
        # Python: agents.py and every generated script compile.
        compile((root / "agents.py").read_text(encoding="utf-8"), "agents.py", "exec")
        for script in root.glob(".github/skills/*/scripts/*.py"):
            compile(script.read_text(encoding="utf-8"), str(script), "exec")
        self.assertIn("async def skill_3d_render", (root / "agents.py").read_text(encoding="utf-8"))
        self.assertIn("async def skill_build_agent", (root / "agents.py").read_text(encoding="utf-8"))
        # JSON and TOML parse.
        json.loads((root / "config.json").read_text(encoding="utf-8"))
        try:
            import tomllib
            tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
        except ImportError:  # Python < 3.11
            pass
        # Front matter: the agent file's name is a quoted scalar; when_to_use is single-quoted.
        agent_md = (root / ".github/agents/acme-finder.agent.md").read_text(encoding="utf-8")
        self.assertIn("name: 'Acme: Lead \"Finder\" ''X'''", agent_md)
        skill = (root / ".github/skills/3d-render/SKILL.md").read_text(encoding="utf-8")
        self.assertIn(r"when_to_use: 'a path like C:\cad\part ''quoted'' appears'", skill)
        # CI command sits in a block scalar.
        self.assertIn('run: |\n          make test ARGS="-v: all"',
                      (root / ".github/workflows/harness.yml").read_text(encoding="utf-8"))
        # And the workspace still passes its own check and skill tests.
        self.assertEqual(self.ws.harness("check").returncode, 0, self.ws.harness("check").stdout)
        r = self.ws.harness("test")
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_validation_refuses_what_new_would_mishandle(self) -> None:
        cases = [
            ({"skills": [{"name": "fetch", "description": "x. Use when y.", "script": "fetch-data"}]}, "snake_case"),
            ({"name": "営業エージェント"}, "slug"),
            ({"scopes": [{"path": "/", "covers": "everything"}]}, "relative folder"),
            ({"scopes": [{"path": "C:/x", "covers": "x"}]}, "relative folder"),
            ({"scopes": [{"path": "a/../../b", "covers": "x"}]}, "relative folder"),
        ]
        for extra, expect in cases:
            with self.subTest(expect=expect):
                raw = minimal_intake("agent")
                raw.update(extra)
                _, errors, _ = scaffold.normalize(raw)
                self.assertTrue(any(expect in e for e in errors), errors)

    def test_rerun_with_a_changed_intake_updates_the_record(self) -> None:
        first = minimal_intake("agent", hosts=["copilot"])
        self.ws.scaffold(first)
        self.assertFalse((self.ws.root / ".claude/skills").exists())
        second = minimal_intake("agent", hosts=["claude-code", "copilot"])
        second["skills"].append({"name": "second-skill", "description": "Another. Use when asked."})
        code, out = self.ws.scaffold(second)
        self.assertEqual(code, 0, out)
        project = json.loads((self.ws.root / ".harness/project.json").read_text(encoding="utf-8"))
        self.assertEqual(project["skill_proxy_dirs"], [".claude/skills"])
        self.assertIn("second-skill", [s["name"] for s in project["skills"]])
        self.assertTrue((self.ws.root / ".claude/skills/second-skill/SKILL.md").exists())
        self.assertEqual(self.ws.harness("check").returncode, 0)

    @unittest.skipUnless(HAVE_GIT, "git not installed")
    def test_gitignore_merge_keeps_env_example_tracked(self) -> None:
        (self.ws.root / ".gitignore").write_text(".env*\n!.env.example\n", encoding="utf-8")
        intake = minimal_intake("agent")
        intake["agent"] = {"runtime": "ide", "integrations": ["anthropic"]}
        self.ws.scaffold(intake)
        r = subprocess.run(["git", "check-ignore", "--no-index", "-q", ".env.example"], cwd=self.ws.root)
        self.assertEqual(r.returncode, 1, "`.env.example` is ignored after the merge")
        self.assertEqual(self.ws.harness("check").returncode, 0)

    def test_check_ignores_os_junk_urls_and_boms(self) -> None:
        self.ws.scaffold(minimal_intake("agent"))
        root = self.ws.root
        (root / ".github/skills/do-thing/.DS_Store").write_bytes(b"\0junk")
        (root / ".gitignore").write_text((root / ".gitignore").read_text(encoding="utf-8") + "\n.DS_Store\n",
                                         encoding="utf-8")
        agents = root / "AGENTS.md"
        agents.write_text(agents.read_text(encoding="utf-8")
                          + "\nSee https://github.com/o/r/blob/main/AGENTS.md for the original.\n",
                          encoding="utf-8")
        skill = root / ".github/skills/do-thing/SKILL.md"
        skill.write_text("\ufeff" + skill.read_text(encoding="utf-8"), encoding="utf-8")
        r = self.ws.harness("check")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertTrue((root / ".claude/skills/do-thing/SKILL.md").exists(), "proxy deleted as an orphan")

    def test_upgrade_leaves_deleted_kit_files_deleted(self) -> None:
        self.ws.scaffold(minimal_intake("agent"))
        (self.ws.root / ".github/workflows/review-reminder.yml").unlink()
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            scaffold.main(["upgrade", "--target", str(self.ws.root)])
        self.assertFalse((self.ws.root / ".github/workflows/review-reminder.yml").exists(), buf.getvalue())
        self.assertIn("1 deleted here", buf.getvalue())

    def test_settings_merge_never_registers_a_hook_twice(self) -> None:
        settings = {"hooks": {"Stop": [{"hooks": [{"type": "command", "timeout": 99,
                                                   "command": "node \"x/.claude/hooks/stop-children.mjs\""}]}]}}
        fragment = {"hooks": {"Stop": [{"hooks": [{"type": "command", "timeout": 10,
                                                   "command": "node \"${CLAUDE_PROJECT_DIR}/.claude/hooks/stop-children.mjs\""}]}]}}
        self.assertFalse(scaffold.deep_merge(settings, fragment))
        self.assertEqual(len(settings["hooks"]["Stop"]), 1)
        self.assertEqual(settings["hooks"]["Stop"][0]["hooks"][0]["timeout"], 99)  # the project's entry wins


class KitTests(unittest.TestCase):
    @unittest.skipUnless(HAVE_GIT and (KIT / ".git").exists(), "not a git checkout of the kit")
    def test_no_template_is_gitignored_in_the_kit(self) -> None:
        # An unanchored `.claude/` in the kit's .gitignore once dropped
        # templates/project/.claude/ from the published kit. Never again.
        files = [p.relative_to(KIT).as_posix() for p in (KIT / "templates").rglob("*")
                 if p.is_file() and "__pycache__" not in p.parts]
        r = subprocess.run(["git", "check-ignore", "--no-index", "-z", "--stdin"], cwd=KIT,
                           input="\0".join(files).encode() + b"\0", capture_output=True)
        ignored = [p for p in r.stdout.decode().split("\0") if p]
        self.assertEqual(ignored, [])

    def test_dox_framework_is_single_sourced_from_the_shared_template(self) -> None:
        text = scaffold.dox_framework()
        for section in ("## Core Contract", "## Read Before Editing", "## Place Before Building",
                        "## Update After Editing", "## Communication (BLUF)"):
            self.assertIn(section, text)
        self.assertNotIn("Fill in the `<...>` placeholders", text)

    def test_render_leaves_github_expressions_and_rejects_unknown_keys(self) -> None:
        self.assertEqual(scaffold.render("a ${{ github.ref }} {{name}}", {"name": "x"}, "t"), "a ${{ github.ref }} x")
        with self.assertRaises(scaffold.ScaffoldError):
            scaffold.render("{{nope}}", {}, "t")

    def test_every_template_renders_for_every_archetype(self) -> None:
        archetypes, _ = scaffold.catalogs()
        for name in archetypes["archetypes"]:
            for runtime in (("ide", "commandcenter") if name == "agent" else ("ide",)):
                with self.subTest(archetype=name, runtime=runtime):
                    raw = minimal_intake(name)
                    if name == "agent":
                        raw["agent"] = {"runtime": runtime}
                    intake, errors, _ = scaffold.normalize(raw)
                    self.assertEqual(errors, [])
                    plan = scaffold.build_plan(intake, scaffold.build_context(intake))
                    leftovers = [op.path for op in plan.ops
                                 if op.owner == "project" and scaffold.TOKEN_RE.search(op.content)]
                    self.assertEqual(leftovers, [], "unrendered {{tokens}} survived")

    def test_every_stack_recipe_has_the_fields_the_templates_use(self) -> None:
        _, stacks = scaffold.catalogs()
        for sid, s in stacks.items():
            with self.subTest(stack=sid):
                for key in ("title", "language", "test", "ci", "gitignore", "init"):
                    self.assertIn(key, s)
                self.assertIn(s["ci"], scaffold.CI_SETUP)


if __name__ == "__main__":
    unittest.main()
