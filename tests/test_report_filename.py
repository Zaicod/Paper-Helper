"""Regression coverage for exporting reports with user-provided topics."""

import json
import re
import tempfile
import unittest
from datetime import datetime, timezone
from html import escape
from pathlib import Path

from paper_agent.core.models import FieldSynthesis, IdeaPortfolio, ResearchReport
from paper_agent.interfaces.report import save_report


class ReportFilenameTests(unittest.TestCase):
    def setUp(self):
        temporary_dir = tempfile.TemporaryDirectory(prefix="paper_agent_report_test_")
        self.addCleanup(temporary_dir.cleanup)
        self.output_dir = Path(temporary_dir.name)

    def make_report(self, topic):
        return ResearchReport(
            topic=topic,
            generated_at=datetime(2026, 10, 18, 8, 30, 45, tzinfo=timezone.utc),
            papers=[],
            analyses=[],
            synthesis=FieldSynthesis(
                topic=topic,
                overview="Offline export fixture",
                method_taxonomy=[],
                common_findings=[],
                disagreements=[],
                research_gaps=[],
                evidence_map=[],
            ),
            idea_portfolio=IdeaPortfolio(topic=topic, ideas=[], caution="Fixture only"),
        )

    def assert_exports_are_safe(self, topic):
        try:
            paths = save_report(self.make_report(topic), self.output_dir)
        except (OSError, ValueError) as exc:
            self.fail(f"Report export rejected a valid research topic: {exc}")
        self.assertEqual([path.suffix for path in paths], [".md", ".json", ".html"])
        for path in paths:
            self.assertEqual(path.parent.resolve(), self.output_dir.resolve())
            self.assertTrue(path.is_file())
            self.assertTrue(path.name.startswith("20261018_083045_"))
            self.assertIsNone(re.search(r'[<>:"/\\|?*\x00-\x1f]', path.name))
            slug = path.stem.removeprefix("20261018_083045_")
            self.assertTrue(slug)
            self.assertEqual(slug, slug.rstrip(". "))
            self.assertLessEqual(len(slug), 50)
        return paths

    def test_topic_with_colon_and_slash_exports_without_losing_original_topic(self):
        topic = "RAG: baseline/ablation"
        markdown, data, html = self.assert_exports_are_safe(topic)
        self.assertIn(topic, markdown.read_text(encoding="utf-8"))
        self.assertEqual(json.loads(data.read_text(encoding="utf-8"))["topic"], topic)
        self.assertIn(escape(topic), html.read_text(encoding="utf-8"))

    def test_windows_reserved_characters_and_path_separators_are_safe(self):
        for topic in ['RAG <model> "test" | why? *', r"..\nested\topic", "../../topic"]:
            with self.subTest(topic=topic):
                self.assert_exports_are_safe(topic)

    def test_control_characters_are_removed_from_filenames(self):
        self.assert_exports_are_safe("RAG\x00\x01\x1f evidence")

    def test_trailing_dots_and_spaces_are_trimmed_even_after_truncation(self):
        for topic in ["RAG...   ", "a" * 49 + "." + "b" * 10]:
            with self.subTest(topic=topic):
                self.assert_exports_are_safe(topic)

    def test_topic_with_no_usable_characters_uses_research_fallback(self):
        for topic in ['<>:"/\\|?*', "...", "   "]:
            with self.subTest(topic=topic):
                paths = self.assert_exports_are_safe(topic)
                self.assertEqual(paths[0].stem, "20261018_083045_research")

    def test_unicode_topic_remains_readable(self):
        paths = self.assert_exports_are_safe("论文检索 Agent")
        self.assertEqual(paths[0].stem, "20261018_083045_论文检索_agent")


if __name__ == "__main__":
    unittest.main()
