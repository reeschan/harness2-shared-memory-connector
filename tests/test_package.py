# Copyright 2026 Ryuki Tobita
# SPDX-License-Identifier: Apache-2.0
"""Tests for the package skeleton: version, entry point, and the harness2 contract."""

import importlib
import inspect
import tomllib
import unittest
from pathlib import Path

import harness2_shared_memory_connector

PYPROJECT = Path(__file__).resolve().parent.parent / "pyproject.toml"


def read_pyproject():
    with PYPROJECT.open("rb") as fp:
        return tomllib.load(fp)


class PackageMetadataTest(unittest.TestCase):
    def test_version_matches_pyproject(self):
        project = read_pyproject()["project"]
        self.assertEqual(harness2_shared_memory_connector.__version__, project["version"])

    def test_entry_point_registers_shared_memory(self):
        group = read_pyproject()["project"]["entry-points"]["harness2.memory_connectors"]
        self.assertEqual(
            group["shared-memory"],
            "harness2_shared_memory_connector.connector:make_connector",
        )


class Harness2ContractTest(unittest.TestCase):
    def test_harness2_modules_are_importable(self):
        modules = (
            "harness2.core.memory",
            "harness2.plugins.mcp",
            "harness2.testing.memory_contract",
        )
        for module in modules:
            with self.subTest(module=module):
                importlib.import_module(module)

    def test_memory_exposes_check_options_and_close(self):
        memory = importlib.import_module("harness2.core.memory")
        for name in ("check_options", "close"):
            with self.subTest(name=name):
                self.assertTrue(callable(getattr(memory, name)))

    def test_recall_accepts_query_as_keyword(self):
        memory = importlib.import_module("harness2.core.memory")
        parameters = inspect.signature(memory.recall).parameters
        self.assertIn("query", parameters)
        self.assertIn(
            parameters["query"].kind,
            (inspect.Parameter.KEYWORD_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD),
        )


if __name__ == "__main__":
    unittest.main()
