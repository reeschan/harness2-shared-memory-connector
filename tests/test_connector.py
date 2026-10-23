# Copyright 2026 Ryuki Tobita
# SPDX-License-Identifier: Apache-2.0
"""Tests for the connector: the file library plus the lessons shared through shared-memory."""

import io
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest import mock

from harness2 import config
from harness2.core import memory
from harness2.core.memory import FileConnector
from harness2.core.tree import SurfaceSpec
from harness2.plugins.mcp import McpError, McpToolError

from harness2_shared_memory_connector import ledger
from harness2_shared_memory_connector.connector import (
    DEFAULT_LIMIT,
    DEFAULT_TIMEOUT,
    DEFAULT_URL,
    KIND,
    PROVENANCE,
    SOURCE_AGENT,
    SharedMemoryConnector,
    make_connector,
)

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

EXPERIENCE = {"cue": "alpha cue", "lesson": "alpha lesson", "evidence": "alpha evidence"}

SCOPE = "project:harness2.lab.seq.team-a"

_UNSET = object()


class FakeMcpClient:
    """Records `call_tool` calls; returns queued results, raising queued exceptions."""

    def __init__(self):
        self.calls = []
        self.queued = {}
        self.memories = {}
        self.default_search = []
        self.closed = False

    def queue(self, name, value):
        self.queued.setdefault(name, []).append(value)

    def calls_of(self, name):
        return [arguments for called, arguments in self.calls if called == name]

    def call_tool(self, name, arguments):
        self.calls.append((name, dict(arguments)))
        queued = self.queued.get(name)
        if queued:
            value = queued.pop(0)
            if isinstance(value, BaseException):
                raise value
            return value
        if name == "search":
            return self.default_search
        if name == "get":
            return self.memories.get(str(arguments.get("id")), {"meta": {}, "body": ""})
        if name == "write":
            return {"id": f"mem-{len(self.calls_of('write'))}", "path": "memories/m.md"}
        raise AssertionError(f"unexpected tool: {name}")

    def close(self):
        self.closed = True


class ConnectorTestCase(unittest.TestCase):
    def setUp(self):
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        self.tmp = Path(holder.name)
        self.root = self.tmp / "library" / "lab" / "scope-team-a" / "seq"
        self.root.mkdir(parents=True)
        self.client = FakeMcpClient()

    def build(
        self,
        *,
        sharing_name="team-a",
        root=None,
        client=_UNSET,
        write="1",
        limit="5",
        timeout="30",
        url=DEFAULT_URL,
    ):
        chosen = self.client if client is _UNSET else client
        with mock.patch.object(config, "MEMORY_SCOPE", sharing_name):
            return make_connector(
                root=self.root if root is None else root,
                domain="lab",
                surface=SURFACE,
                url=url,
                write=write,
                limit=limit,
                timeout=timeout,
                client=chosen,
            )

    def add(self, conn, task_id, experience=EXPERIENCE, why="because", label="best"):
        return conn.add(task_id, TREE, why=why, label=label, experience=experience)

    def memory(self, memory_id, title, slug=None, body="body"):
        tags = ["harness2"] if slug is None else ["harness2", f"task:{slug}"]
        self.client.memories[memory_id] = {
            "meta": {"title": title, "tags": tags},
            "body": body,
            "path": f"memories/{memory_id}.md",
            "freshness": "fresh",
        }
        return self.client.memories[memory_id]

    def stderr(self, fn, *args, **kwargs):
        err = io.StringIO()
        with redirect_stderr(err):
            value = fn(*args, **kwargs)
        return value, err.getvalue()

    def stored(self, slug):
        return ledger.Ledger(self.root / ledger.LEDGER_NAME).get(slug)


class NoSharingNameTest(ConnectorTestCase):
    def test_add_and_recall_match_the_file_connector(self):
        plain_root = self.tmp / "plain"
        plain = FileConnector(plain_root, "lab", SURFACE)
        plain_entry = plain.add("task-1", TREE, why="because", label="best", experience=EXPERIENCE)
        conn = self.build(sharing_name="", client=None)
        entry = self.add(conn, "task-1")
        self.assertIsNotNone(entry)
        self.assertEqual(entry.relative_to(self.root), plain_entry.relative_to(plain_root))
        self.assertEqual(conn.entries(), plain.entries())
        self.assertEqual(conn.recall("task-9", 10_000), plain.recall("task-9", 10_000))

    def test_never_calls_mcp(self):
        conn = self.build(sharing_name="", write="1")
        self.add(conn, "task-1")
        conn.recall("task-2", 1000, query="a prompt")
        self.assertEqual(self.client.calls, [])

    def test_no_client_is_created_without_a_sharing_name(self):
        with mock.patch("harness2_shared_memory_connector.connector.mcp.client_from") as factory:
            conn = self.build(sharing_name="", client=None)
            self.add(conn, "task-1")
        factory.assert_not_called()
        self.assertIsInstance(conn, SharedMemoryConnector)


class WriteTest(ConnectorTestCase):
    def test_write_carries_the_lesson_and_the_memory_identity(self):
        conn = self.build(write="1")
        entry = self.add(conn, "task-1")
        writes = self.client.calls_of("write")
        self.assertEqual(len(writes), 1)
        arguments = writes[0]
        self.assertEqual(arguments["title"], "lab: task-1")
        self.assertEqual(arguments["scope"], SCOPE)
        self.assertEqual(arguments["kind"], KIND)
        self.assertEqual(arguments["provenance"], PROVENANCE)
        self.assertEqual(arguments["source_agent"], SOURCE_AGENT)
        self.assertEqual(arguments["tags"], ["harness2", "domain:lab", "task:task-1"])
        self.assertEqual(Path(arguments["source_path"]), entry.resolve())
        self.assertIn("alpha cue", arguments["content"])
        self.assertIn("alpha lesson", arguments["content"])
        self.assertIn("alpha evidence", arguments["content"])
        self.assertIn("because", arguments["content"])
        self.assertNotIn("supersedes", arguments)

    def test_records_the_written_id_in_the_ledger(self):
        conn = self.build(write="1")
        self.add(conn, "task-1")
        self.assertEqual(self.stored("task-1"), "mem-1")

    def test_second_write_supersedes_the_first_id(self):
        conn = self.build(write="1")
        self.add(conn, "task-1")
        self.add(conn, "task-1", experience={**EXPERIENCE, "lesson": "beta lesson"})
        writes = self.client.calls_of("write")
        self.assertEqual(len(writes), 2)
        self.assertEqual(writes[1]["supersedes"], "mem-1")
        self.assertEqual(self.stored("task-1"), "mem-2")

    def test_rejected_supersedes_is_rewritten_without_it(self):
        conn = self.build(write="1")
        self.add(conn, "task-1")
        self.client.queue("write", McpToolError("no such memory"))
        self.client.queue("write", {"id": "mem-new", "path": "memories/mem-new.md"})
        self.add(conn, "task-1", experience={**EXPERIENCE, "lesson": "beta lesson"})
        writes = self.client.calls_of("write")
        self.assertEqual(len(writes), 3)
        self.assertEqual(writes[1]["supersedes"], "mem-1")
        self.assertNotIn("supersedes", writes[2])
        self.assertEqual(self.stored("task-1"), "mem-new")

    def test_write_is_off_without_the_flag(self):
        conn = self.build(write="0")
        entry = self.add(conn, "task-1")
        self.assertTrue(entry.is_dir())
        self.assertEqual(self.client.calls, [])
        self.assertIsNone(self.stored("task-1"))

    def test_write_failure_keeps_the_entry_and_warns(self):
        conn = self.build(write="1")
        self.client.queue("write", McpError("server down"))
        entry, err = self.stderr(self.add, conn, "task-1")
        self.assertTrue(entry.is_dir())
        self.assertEqual(conn.entries(), ["task-1"])
        self.assertEqual(len(self.client.calls_of("write")), 1)
        self.assertIn("warning", err)
        self.assertIn("McpError", err)
        self.assertNotIn("alpha cue", err)
        self.assertIsNone(self.stored("task-1"))

    def test_ledger_write_failure_keeps_the_entry_and_warns(self):
        conn = self.build(write="1")
        with mock.patch.object(ledger.Ledger, "set", side_effect=OSError("read-only")):
            entry, err = self.stderr(self.add, conn, "task-1")
        self.assertTrue(entry.is_dir())
        self.assertEqual(conn.entries(), ["task-1"])
        self.assertEqual(len(self.client.calls_of("write")), 1)
        self.assertIn("ledger write failed (OSError)", err)
        self.assertNotIn(self.tmp.name, err)

    def test_ledger_read_failure_writes_without_supersedes_and_warns(self):
        conn = self.build(write="1")
        with mock.patch.object(ledger.Ledger, "get", side_effect=OSError("denied")):
            entry, err = self.stderr(self.add, conn, "task-1")
        self.assertTrue(entry.is_dir())
        writes = self.client.calls_of("write")
        self.assertEqual(len(writes), 1)
        self.assertNotIn("supersedes", writes[0])
        self.assertIn("ledger read failed (OSError)", err)
        self.assertNotIn(self.tmp.name, err)

    def test_tool_error_without_supersedes_warns_without_a_retry(self):
        conn = self.build(write="1")
        self.client.queue("write", McpToolError("rejected"))
        entry, err = self.stderr(self.add, conn, "task-1")
        self.assertTrue(entry.is_dir())
        self.assertEqual(len(self.client.calls_of("write")), 1)
        self.assertIn("McpToolError", err)


class RecallTest(ConnectorTestCase):
    def test_search_asks_for_the_prompt_the_scope_and_the_tags(self):
        conn = self.build(limit="3")
        conn.recall("task-9", 1000, query="fix the bug")
        searches = self.client.calls_of("search")
        self.assertEqual(len(searches), 1)
        self.assertEqual(
            searches[0],
            {
                "query": "fix the bug",
                "scope": SCOPE,
                "kind": "semantic",
                "tags": ["domain:lab"],
                "limit": 12,
            },
        )

    def test_search_falls_back_to_the_domain_for_an_empty_prompt(self):
        conn = self.build()
        conn.recall("task-9", 1000)
        self.assertEqual(self.client.calls_of("search")[0]["query"], "lab")

    def test_search_result_as_a_list(self):
        self.memory("m1", "First", slug="t1", body="one")
        self.client.default_search = [{"id": "m1"}]
        conn = self.build()
        self.assertEqual(conn.recall("task-9", 10_000), "## First\none")

    def test_search_result_as_a_dict_of_lists(self):
        self.memory("m1", "First", slug="t1", body="one")
        self.client.default_search = {"total": 1, "memories": [{"id": "m1"}]}
        conn = self.build()
        self.assertEqual(conn.recall("task-9", 10_000), "## First\none")

    def test_skips_the_current_task(self):
        self.memory("m1", "Self", slug="t2", body="self body")
        self.memory("m2", "Other", slug="t1", body="other body")
        self.client.default_search = [{"id": "m1"}, {"id": "m2"}]
        conn = self.build()
        self.assertEqual(conn.recall("t2", 10_000), "## Other\nother body")
        self.assertEqual(self.client.calls_of("get"), [{"id": "m1"}, {"id": "m2"}])

    def test_skips_tasks_hidden_by_retain(self):
        conn = self.build(write="0")
        self.add(conn, "task-1")
        self.add(conn, "task-2")
        conn.retain(["task-1"])
        self.memory("m1", "Later", slug="task-2", body="later body")
        self.memory("m2", "Earlier", slug="task-1", body="earlier body")
        self.client.default_search = {"results": [{"id": "m1"}, {"id": "m2"}]}
        text = conn.recall("task-3", 10_000)
        self.assertNotIn("Later", text)
        self.assertEqual(text, "## Earlier\nearlier body")

    def test_stops_at_the_limit(self):
        self.client.default_search = {"memories": [{"id": f"m{i}"} for i in range(5)]}
        for i in range(5):
            self.memory(f"m{i}", f"T{i}", slug=f"t{i}", body=f"body {i}")
        conn = self.build(limit="2")
        text = conn.recall("task-9", 10_000)
        self.assertEqual(len(self.client.calls_of("get")), 2)
        self.assertEqual(self.client.calls_of("search")[0]["limit"], 8)
        self.assertIn("## T0", text)
        self.assertIn("## T1", text)
        self.assertNotIn("## T2", text)

    def test_cuts_the_rendered_text_to_limit_chars(self):
        self.memory("m1", "First", slug="t1", body="one")
        self.memory("m2", "Second", slug="t2", body="two")
        self.client.default_search = [{"id": "m1"}, {"id": "m2"}]
        conn = self.build(limit="5")
        full = conn.recall("task-9", 10_000)
        short = conn.recall("task-9", 5)
        self.assertGreater(len(full), 5)
        self.assertEqual(short, full[:5])

    def test_no_memories_gives_empty_without_the_file_recall(self):
        conn = self.build(write="0")
        self.add(conn, "task-1")
        plain = FileConnector(self.root, "lab", SURFACE)
        self.assertNotEqual(plain.recall("task-9", 10_000), "")
        self.client.default_search = []
        self.assertEqual(conn.recall("task-9", 10_000), "")

    def test_search_failure_falls_back_to_the_file_recall_and_warns(self):
        conn = self.build(write="0")
        self.add(conn, "task-1")
        expected = FileConnector(self.root, "lab", SURFACE).recall("task-9", 10_000)
        self.client.queue("search", McpError("server down"))
        text, err = self.stderr(conn.recall, "task-9", 10_000, query="a prompt")
        self.assertEqual(text, expected)
        self.assertIn("warning", err)
        self.assertIn("McpError", err)
        self.assertNotIn("alpha lesson", err)

    def test_get_failure_falls_back_to_the_file_recall_and_warns(self):
        conn = self.build(write="0")
        self.add(conn, "task-1")
        expected = FileConnector(self.root, "lab", SURFACE).recall("task-9", 10_000)
        self.client.default_search = [{"id": "m1"}]
        self.client.queue("get", McpError("server down"))
        text, err = self.stderr(conn.recall, "task-9", 10_000)
        self.assertEqual(text, expected)
        self.assertIn("warning", err)
        self.assertIn("McpError", err)


class RetainTest(ConnectorTestCase):
    def setUp(self):
        super().setUp()
        self.conn = self.build(write="0")
        for task_id in ("t1", "t2", "t3"):
            self.add(self.conn, task_id)
        self.memory("m1", "First", slug="t1", body="first body")
        self.memory("m2", "Second", slug="t2", body="second body")
        self.memory("m3", "Third", slug="t3", body="third body")
        self.client.default_search = [{"id": "m1"}, {"id": "m2"}, {"id": "m3"}]

    def test_a_kept_task_is_in_view_again(self):
        self.conn.retain([])
        self.add(self.conn, "t1")
        self.conn.retain(["t1"])
        text = self.conn.recall("t2", 10_000)
        self.assertIn("first body", text)
        self.assertNotIn("second body", text)
        self.assertNotIn("third body", text)

    def test_a_saved_task_is_no_longer_hidden(self):
        self.conn.retain([])
        self.add(self.conn, "t1")
        text = self.conn.recall("t2", 10_000)
        self.assertIn("first body", text)
        self.assertNotIn("third body", text)

    def test_every_preceding_task_stays_in_view(self):
        self.conn.retain([])
        self.add(self.conn, "t1")
        self.conn.retain(["t1"])
        self.add(self.conn, "t2")
        self.conn.retain(["t1", "t2"])
        text = self.conn.recall("t3", 10_000)
        self.assertIn("first body", text)
        self.assertIn("second body", text)
        self.assertNotIn("third body", text)


class MalformedRootTest(ConnectorTestCase):
    def test_warns_and_leaves_shared_memory_off(self):
        bad = self.tmp / "library" / "lab" / "k1-oc" / "seq"
        bad.mkdir(parents=True)
        with mock.patch("harness2_shared_memory_connector.connector.mcp.client_from") as factory:
            conn, err = self.stderr(self.build, root=bad, client=None)
        self.assertIn("warning", err)
        factory.assert_not_called()
        self.assertIsInstance(conn, SharedMemoryConnector)
        self.add(conn, "task-1")
        conn.recall("task-2", 1000, query="a prompt")
        self.assertEqual(self.client.calls, [])


class OptionsTest(ConnectorTestCase):
    def test_constants(self):
        self.assertEqual(DEFAULT_URL, "http://127.0.0.1:7820/mcp")
        self.assertEqual(DEFAULT_LIMIT, 5)
        self.assertEqual(DEFAULT_TIMEOUT, 30.0)
        self.assertEqual(SOURCE_AGENT, "harness2")
        self.assertEqual(KIND, "semantic")
        self.assertEqual(PROVENANCE, "agent_inferred")

    def test_truthy_write_spellings_write(self):
        for text in ("1", "true", "TRUE", "Yes"):
            with self.subTest(value=text):
                client = FakeMcpClient()
                conn = self.build(write=text, client=client)
                entry = self.add(conn, "task-1")
                self.assertTrue(entry.is_dir())
                self.assertEqual(len(client.calls_of("write")), 1)

    def test_falsy_write_spellings_do_not_write(self):
        for text in ("0", "false", "False", "no", ""):
            with self.subTest(value=text):
                client = FakeMcpClient()
                conn = self.build(write=text, client=client)
                self.add(conn, "task-1")
                self.assertEqual(client.calls, [])

    def test_unknown_write_value_is_an_error(self):
        with self.assertRaises(ValueError):
            self.build(write="maybe")

    def test_limit_is_converted(self):
        conn = self.build(limit="3")
        conn.recall("task-9", 1000, query="a prompt")
        self.assertEqual(self.client.calls_of("search")[0]["limit"], 12)

    def test_invalid_limits_are_errors(self):
        for text in ("0", "-1", "abc", "1.5", ""):
            with self.subTest(value=text), self.assertRaises(ValueError):
                self.build(limit=text)

    def test_url_and_timeout_are_passed_to_the_client(self):
        with mock.patch("harness2_shared_memory_connector.connector.mcp.client_from") as factory:
            self.build(write="0", client=None, timeout="5.5", url="http://127.0.0.1:9/mcp")
        factory.assert_called_once_with(url="http://127.0.0.1:9/mcp", timeout=5.5)

    def test_default_url_and_timeout_are_passed_to_the_client(self):
        with mock.patch("harness2_shared_memory_connector.connector.mcp.client_from") as factory:
            self.build(write="0", client=None)
        factory.assert_called_once_with(url=DEFAULT_URL, timeout=DEFAULT_TIMEOUT)

    def test_invalid_timeouts_are_errors(self):
        for text in ("x", ""):
            with self.subTest(value=text), self.assertRaises(ValueError):
                self.build(timeout=text)


class CloseTest(ConnectorTestCase):
    def test_close_closes_the_client(self):
        conn = self.build()
        conn.close()
        self.assertTrue(self.client.closed)

    def test_close_without_a_client_is_harmless(self):
        conn = self.build(sharing_name="", client=None)
        conn.close()


class CheckOptionsTest(unittest.TestCase):
    def test_accepts_the_connector_options(self):
        memory.check_options(
            "shared-memory", {"url": "x", "write": "1", "limit": "3", "timeout": "5"}
        )

    def test_rejects_an_unknown_option(self):
        with self.assertRaises(ValueError):
            memory.check_options("shared-memory", {"nope": "1"})


if __name__ == "__main__":
    unittest.main()
