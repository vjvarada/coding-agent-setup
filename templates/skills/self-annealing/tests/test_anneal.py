"""Tests for anneal.py. Run: python .harness/harness.py test"""
from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import anneal  # noqa: E402


class AnnealTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / ".harness").mkdir()
        (self.root / ".harness" / "project.json").write_text(
            json.dumps({"lessons_path": "docs/lessons.md"}), encoding="utf-8")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def run_cli(self, *argv: str) -> tuple[int, str]:
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = anneal.main(["--root", str(self.root), *argv])
        return code, buf.getvalue()

    def lessons(self) -> str:
        return (self.root / "docs" / "lessons.md").read_text(encoding="utf-8")

    def test_log_numbers_entries_and_creates_the_file(self) -> None:
        self.run_cli("log", "--title", "first", "--lesson", "a", "--target", "x")
        self.run_cli("log", "--title", "second", "--lesson", "b", "--target", "y")
        text = self.lessons()
        self.assertIn("### L001 · first", text)
        self.assertIn("### L002 · second", text)
        self.assertEqual(text.count("**Status:** OPEN"), 2)

    def test_apply_closes_only_the_named_lesson(self) -> None:
        for t in ("one", "two", "three"):
            self.run_cli("log", "--title", t, "--lesson", "l", "--target", "x")
        code, _ = self.run_cli("apply", "L002", "--note", "landed in SKILL.md")
        self.assertEqual(code, 0)
        es = {e["id"]: e for e in anneal.entries(self.lessons())}
        self.assertEqual(es["L001"]["status"], "OPEN")
        self.assertEqual(es["L002"]["status"], "APPLIED")
        self.assertIn("landed in SKILL.md", es["L002"]["body"])
        self.assertEqual(es["L003"]["status"], "OPEN")
        # the blank line between entries survives the edit
        self.assertIn("\n\n### L003", self.lessons())

    def test_list_shows_open_only_by_default(self) -> None:
        self.run_cli("log", "--title", "a", "--lesson", "l", "--target", "x")
        self.run_cli("log", "--title", "b", "--lesson", "l", "--target", "x")
        self.run_cli("defer", "L001", "--note", "needs the owner")
        _, out = self.run_cli("list")
        self.assertIn("1 OPEN", out)
        self.assertNotIn("L001", out)
        _, out = self.run_cli("list", "--all")
        self.assertIn("L001 [DEFERRED]", out)

    def test_unknown_id_is_an_error(self) -> None:
        code, out = self.run_cli("apply", "L099", "--note", "x")
        self.assertEqual(code, 1)
        self.assertIn("no lesson", out)

    def test_gate_flags_open_lessons(self) -> None:
        self.run_cli("log", "--title", "pending", "--lesson", "l", "--target", "x")
        code, out = self.run_cli("gate")
        self.assertEqual(code, 1)
        self.assertIn("ACTION NEEDED", out)
        self.assertIn("1 OPEN lesson", out)

    def test_gate_is_clear_with_nothing_to_do(self) -> None:
        code, out = self.run_cli("gate")
        self.assertEqual(code, 0, out)
        self.assertIn("CLEAR", out)

    def test_suggested_commit_names_applied_lessons(self) -> None:
        msg = anneal.suggest_commit([".github/skills/x/SKILL.md"], [{"id": "L004", "title": "retry on 429"}])
        self.assertTrue(msg.startswith("Anneal: 1 lesson(s) integrated"))
        self.assertIn("L004 retry on 429", msg)


if __name__ == "__main__":
    unittest.main()
