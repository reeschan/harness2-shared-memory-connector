# Copyright 2026 Ryuki Tobita
# SPDX-License-Identifier: Apache-2.0
"""Tests for the lesson title, content, recall block and search query."""

import unittest

from harness2_shared_memory_connector import lesson


class LessonTitleTest(unittest.TestCase):
    def test_joins_domain_and_task_id(self):
        self.assertEqual(lesson.lesson_title("lab", "task-1"), "lab: task-1")

    def test_cuts_to_title_max(self):
        self.assertEqual(lesson.TITLE_MAX, 200)
        self.assertEqual(lesson.lesson_title("d" * 300, "t"), "d" * 200)


class LessonContentTest(unittest.TestCase):
    EXPERIENCE = {"cue": "a cue", "lesson": "a lesson", "evidence": "a bit"}

    def test_lists_cue_lesson_and_evidence(self):
        content = lesson.lesson_content(self.EXPERIENCE)
        expected = "- **cue**: a cue\n- **lesson**: a lesson\n- **evidence**: a bit"
        self.assertEqual(content, expected)

    def test_skips_empty_fields(self):
        content = lesson.lesson_content({"lesson": "only"})
        self.assertEqual(content, "- **lesson**: only")

    def test_collapses_whitespace(self):
        content = lesson.lesson_content({"cue": "  two\n lines  "})
        self.assertEqual(content, "- **cue**: two lines")

    def test_appends_why(self):
        content = lesson.lesson_content({"cue": "c"}, why="because")
        expected = "- **cue**: c\n\n## Why\nbecause"
        self.assertEqual(content, expected)

    def test_cuts_why_to_why_max(self):
        self.assertEqual(lesson.WHY_MAX, 1000)
        content = lesson.lesson_content({}, why="w" * 2000)
        expected = "## Why\n" + "w" * 1000
        self.assertEqual(content, expected)

    def test_empty_experience_and_why_give_empty(self):
        self.assertEqual(lesson.lesson_content({}), "")


class RenderRecallTest(unittest.TestCase):
    def test_renders_each_memory_as_a_title_and_body(self):
        memories = [
            {"meta": {"title": "First"}, "body": "one\n"},
            {"meta": {"title": "Second"}, "body": "two"},
        ]
        expected = "## First\none\n\n## Second\ntwo"
        self.assertEqual(lesson.render_recall(memories), expected)

    def test_no_memories_give_empty(self):
        self.assertEqual(lesson.render_recall([]), "")


class QueryTextTest(unittest.TestCase):
    def test_returns_the_prompt(self):
        self.assertEqual(lesson.query_text("fix the bug", "lab"), "fix the bug")

    def test_cuts_to_query_max(self):
        self.assertEqual(lesson.QUERY_MAX, 2000)
        self.assertEqual(lesson.query_text("q" * 3000, "lab"), "q" * 2000)

    def test_falls_back_to_domain(self):
        self.assertEqual(lesson.query_text("", "lab"), "lab")
        self.assertEqual(lesson.query_text("   \n", "lab"), "lab")


if __name__ == "__main__":
    unittest.main()
