# Copyright 2026 Ryuki Tobita
# SPDX-License-Identifier: Apache-2.0
"""Tests for the placement, the memory scope and the tags."""

import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path

from harness2_shared_memory_connector import naming


class PlacementForTest(unittest.TestCase):
    def test_reads_benchmark_mode_and_sharing_name(self):
        root = Path("library/lab/scope-team-a/seq")
        placement = naming.placement_for(root, "team-a")
        self.assertIsNotNone(placement)
        self.assertEqual(placement.benchmark, "lab")
        self.assertEqual(placement.mode, "seq")
        self.assertEqual(placement.sharing_name, "team-a")
        self.assertEqual(placement.memory_scope, "project:harness2.lab.seq.team-a")

    def test_empty_sharing_name_gives_none(self):
        root = Path("library/lab/scope-team-a/seq")
        self.assertIsNone(naming.placement_for(root, ""))

    def test_root_outside_the_scope_directory_gives_none(self):
        root = Path("library/lab/k1-oc/seq")
        self.assertIsNone(naming.placement_for(root, "team-a"))

    def test_scope_directory_must_match_the_sharing_name(self):
        root = Path("library/lab/scope-team-b/seq")
        self.assertIsNone(naming.placement_for(root, "team-a"))

    def test_placement_is_frozen(self):
        placement = naming.Placement("lab", "seq", "team-a", "scope")
        with self.assertRaises(FrozenInstanceError):
            placement.mode = "parallel"


class MemoryScopeTest(unittest.TestCase):
    def test_scope(self):
        scope = naming.memory_scope("lab", "seq", "team-a")
        self.assertEqual(scope, "project:harness2.lab.seq.team-a")

    def test_replaces_characters_outside_the_allowed_set(self):
        scope = naming.memory_scope("lab x", "se/q", "team a:b")
        self.assertEqual(scope, "project:harness2.lab-x.se-q.team-a-b")

    def test_keeps_dots_dashes_and_underscores(self):
        scope = naming.memory_scope("a.b", "c-d", "e_f")
        self.assertEqual(scope, "project:harness2.a.b.c-d.e_f")

    def test_empty_parts_become_a_dash(self):
        scope = naming.memory_scope("", "", "")
        self.assertEqual(scope, "project:harness2.-.-.-")


class TagsForTest(unittest.TestCase):
    def test_tags(self):
        tags = naming.tags_for("lab", "t-1")
        self.assertEqual(tags, ["harness2", "domain:lab", "task:t-1"])

    def test_tag_constants(self):
        self.assertEqual(naming.BASE_TAG, "harness2")
        self.assertEqual(naming.DOMAIN_TAG_PREFIX, "domain:")
        self.assertEqual(naming.TASK_TAG_PREFIX, "task:")


if __name__ == "__main__":
    unittest.main()
