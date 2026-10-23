# Copyright 2026 Ryuki Tobita
# SPDX-License-Identifier: Apache-2.0
"""Tests that the connector decodes the raw MCP results through harness2's real converter."""

import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest import mock

from harness2 import config
from harness2.core.tree import SurfaceSpec
from harness2.plugins import mcp

from harness2_shared_memory_connector.connector import make_connector

SURFACE = SurfaceSpec(
    name="lab",
    always_on=("AGENTS.md",),
    always_on_max=10_000,
    always_on_cap_reason="tests",
    skill_dir="skills",
    skill_name_rule="test",
    trigger_hint="test",
    autotrigger_file="AGENTS.md",
    trigger_line="test",
    subagent_requires_mode=False,
    plugin_dir=None,
    hooks_file=None,
)

TREE = {
    "AGENTS.md": "# Agent\nbe brief\n",
    "skills/x/SKILL.md": "---\nname: x\n---\n",
}

LOCAL_EXPERIENCE = {
    "cue": "local cue",
    "lesson": "local lesson",
    "evidence": "local evidence",
}

SHARED_TITLE = "shared lesson"
SHARED_BODY = "the shared body"


def text_result(value):
    """A tools/call result as shared-memory sends it: the JSON document in one text content."""
    return {"content": [{"type": "text", "text": json.dumps(value)}]}


class RawResultClient:
    """The raw tools/call results per tool, decoded like `HttpMcpClient` decodes them."""

    def __init__(self, results):
        self.results = dict(results)
        self.calls = []

    def call_tool(self, name, arguments):
        self.calls.append((name, dict(arguments)))
        raw = self.results[name]
        if name == "get":
            raw = raw[str(arguments["id"])]
        return mcp.tool_result(raw)

    def close(self):
        pass


class ToolResultTest(unittest.TestCase):
    def test_a_top_level_array_becomes_a_list(self):
        raw = text_result([{"id": "m1"}, {"id": "m2"}])
        self.assertEqual(mcp.tool_result(raw), [{"id": "m1"}, {"id": "m2"}])


class RecallThroughToolResultTest(unittest.TestCase):
    def setUp(self):
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        self.root = Path(holder.name) / "library" / "lab" / "scope-team-a" / "seq"
        self.root.mkdir(parents=True)
        self.client = RawResultClient(
            {
                "search": text_result([{"id": "m1"}, {"id": "m2"}]),
                "get": {
                    "m1": text_result(
                        {
                            "meta": {
                                "title": "current task",
                                "tags": ["harness2", "task:task-9"],
                            },
                            "path": "memories/m1.md",
                            "body": "the current task's own body",
                            "freshness": {},
                        }
                    ),
                    "m2": text_result(
                        {
                            "meta": {
                                "title": SHARED_TITLE,
                                "tags": ["harness2", "domain:lab", "task:task-2"],
                            },
                            "path": "memories/m2.md",
                            "body": SHARED_BODY,
                            "freshness": {},
                        }
                    ),
                },
            }
        )

    def build(self):
        with mock.patch.object(config, "MEMORY_SCOPE", "team-a"):
            return make_connector(
                root=self.root,
                domain="lab",
                surface=SURFACE,
                write="0",
                client=self.client,
            )

    def test_recall_returns_the_shared_lesson_without_the_file_recall(self):
        conn = self.build()
        self.assertIsNotNone(conn.add("task-1", TREE, why="because", experience=LOCAL_EXPERIENCE))
        err = io.StringIO()
        with redirect_stderr(err):
            text = conn.recall("task-9", 10_000, query="a prompt")
        self.assertIn(SHARED_TITLE, text)
        self.assertIn(SHARED_BODY, text)
        self.assertNotIn(LOCAL_EXPERIENCE["lesson"], text)
        self.assertEqual(err.getvalue(), "")
        self.assertEqual([name for name, _ in self.client.calls], ["search", "get", "get"])


if __name__ == "__main__":
    unittest.main()
