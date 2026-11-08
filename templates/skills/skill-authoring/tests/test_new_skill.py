"""Tests for new_skill.py. Run: python .harness/harness.py test"""
from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import new_skill  # noqa: E402


class NewSkillTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_creates_the_doe_package(self) -> None:
        files = new_skill.create_skill(self.root, "enrich-leads",
                                       "Enrich leads with emails. Use when a lead list lacks contacts.",
                                       when="a lead list needs emails", authority="external", cost_tier=2)
        rels = sorted(p.relative_to(self.root).as_posix() for p in files)
        self.assertEqual(rels, [
            ".github/skills/enrich-leads/SKILL.md",
            ".github/skills/enrich-leads/scripts/main.py",
            ".github/skills/enrich-leads/tests/test_main.py",
        ])
        md = (self.root / rels[0]).read_text(encoding="utf-8")
        for section in ("## Goal", "## Inputs", "## Process", "## Outputs", "## Definition of Done",
                        "## Edge Cases", "## Learnings"):
            self.assertIn(section, md)
        self.assertIn("name: enrich-leads", md)
        self.assertIn("authority: external", md)
        self.assertIn("--dry-run", md)  # external skills tell the agent to dry-run first

    def test_generated_script_honours_the_cli_contract(self) -> None:
        new_skill.create_skill(self.root, "demo", "Demo skill. Use for tests.")
        script = self.root / ".github/skills/demo/scripts/main.py"
        r = subprocess.run([sys.executable, str(script), "--help"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        r = subprocess.run([sys.executable, str(script)], capture_output=True, text=True)
        self.assertEqual(r.returncode, 3)  # unimplemented is a loud, distinct failure
        self.assertIn("TODO: implement demo", r.stderr)

    def test_generated_test_passes_with_a_visible_skip(self) -> None:
        new_skill.create_skill(self.root, "demo", "Demo skill. Use for tests.")
        tests = self.root / ".github/skills/demo/tests"
        r = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", str(tests), "-t", str(tests)],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("skipped=1", r.stderr)

    def test_front_matter_survives_awkward_descriptions(self) -> None:
        desc = "Parse: 'quoted' and \"double\" text # not a comment. Use when: always."
        new_skill.create_skill(self.root, "awkward", desc)
        md = (self.root / ".github/skills/awkward/SKILL.md").read_text(encoding="utf-8")
        # A folded block scalar carries any characters; every continuation line is indented.
        self.assertIn("description: >-", md)
        header = md.split("---")[1]
        block = header.split("description: >-\n")[1].split("\n")
        folded = []
        for line in block:
            if not line.startswith("  "):
                break
            folded.append(line.strip())
        self.assertEqual(" ".join(folded), desc)

    def test_refusals(self) -> None:
        with self.assertRaises(ValueError):
            new_skill.create_skill(self.root, "Bad_Name", "x. Use when y.")
        with self.assertRaises(ValueError):
            new_skill.create_skill(self.root, "ok", "")
        with self.assertRaises(ValueError):
            new_skill.create_skill(self.root, "ok", "x", authority="root")
        new_skill.create_skill(self.root, "dupe", "x. Use when y.")
        with self.assertRaises(FileExistsError):
            new_skill.create_skill(self.root, "dupe", "x. Use when y.")


if __name__ == "__main__":
    unittest.main()
