# Copyright 2026 Ryuki Tobita
# SPDX-License-Identifier: Apache-2.0
"""Tests for the ledger that remembers the memory id written for each task."""

import json
import tempfile
import unittest
from pathlib import Path

from harness2_shared_memory_connector import ledger


class LedgerTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name) / ledger.LEDGER_NAME

    def read_json(self):
        return json.loads(self.path.read_text(encoding="utf-8"))

    def test_ledger_name(self):
        self.assertEqual(ledger.LEDGER_NAME, "shared-memory-ledger.json")

    def test_get_returns_none_when_the_file_is_missing(self):
        self.assertIsNone(ledger.Ledger(self.path).get("task-1"))

    def test_set_then_get(self):
        book = ledger.Ledger(self.path)
        book.set("task-1", "mem-1")
        self.assertEqual(book.get("task-1"), "mem-1")

    def test_set_writes_json_immediately(self):
        ledger.Ledger(self.path).set("task-1", "mem-1")
        self.assertEqual(self.read_json(), {"task-1": "mem-1"})

    def test_another_instance_reads_the_same_file(self):
        ledger.Ledger(self.path).set("task-1", "mem-1")
        self.assertEqual(ledger.Ledger(self.path).get("task-1"), "mem-1")

    def test_set_keeps_other_slugs(self):
        book = ledger.Ledger(self.path)
        book.set("a", "1")
        book.set("b", "2")
        self.assertEqual(book.get("a"), "1")
        self.assertEqual(book.get("b"), "2")

    def test_broken_json_is_treated_as_empty_and_overwritten(self):
        self.path.write_text("not json", encoding="utf-8")
        book = ledger.Ledger(self.path)
        self.assertIsNone(book.get("task-1"))
        book.set("task-1", "mem-1")
        self.assertEqual(self.read_json(), {"task-1": "mem-1"})

    def test_non_dict_json_is_treated_as_empty(self):
        self.path.write_text('["not", "a", "dict"]', encoding="utf-8")
        book = ledger.Ledger(self.path)
        self.assertIsNone(book.get("task-1"))
        book.set("task-1", "mem-1")
        self.assertEqual(book.get("task-1"), "mem-1")

    def test_creates_the_parent_directory(self):
        path = self.path.parent / "nested" / ledger.LEDGER_NAME
        ledger.Ledger(path).set("task-1", "mem-1")
        self.assertEqual(ledger.Ledger(path).get("task-1"), "mem-1")

    def test_leaves_no_temporary_file(self):
        ledger.Ledger(self.path).set("task-1", "mem-1")
        names = [entry.name for entry in self.path.parent.iterdir()]
        self.assertEqual(names, [ledger.LEDGER_NAME])


if __name__ == "__main__":
    unittest.main()
