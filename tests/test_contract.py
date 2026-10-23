# Copyright 2026 Ryuki Tobita
# SPDX-License-Identifier: Apache-2.0
"""Contract tests: the connector meets harness2's MemoryConnector contract, both ways."""

import unittest
from pathlib import Path
from unittest import mock

from harness2 import config
from harness2.core import memory
from harness2.core.tree import SurfaceSpec
from harness2.testing.memory_contract import MemoryConnectorContractTests

from harness2_shared_memory_connector.connector import make_connector

SURFACE = SurfaceSpec(
    name="contract",
    always_on=("AGENTS.md",),
    always_on_max=10_000,
    always_on_cap_reason="contract checks",
    skill_dir="skills",
    skill_name_rule="test",
    trigger_hint="test",
    autotrigger_file="AGENTS.md",
    trigger_line="test",
    subagent_requires_mode=False,
    plugin_dir=None,
    hooks_file=None,
)


class FakeMcpClient:
    """A client whose search finds nothing and whose write always gives an id."""

    def __init__(self):
        self.calls = []

    def call_tool(self, name, arguments):
        self.calls.append((name, dict(arguments)))
        if name == "search":
            return {"memories": []}
        if name == "get":
            return {"meta": {}, "body": ""}
        if name == "write":
            return {"id": "mem-contract", "path": "memories/mem-contract.md"}
        raise AssertionError(f"unexpected tool: {name}")

    def close(self):
        pass


class FileOnlyContractTest(MemoryConnectorContractTests, unittest.TestCase):
    def make_connector(self, root: Path, domain: str):
        with mock.patch.object(config, "MEMORY_SCOPE", ""):
            return make_connector(root=root, domain=domain, surface=SURFACE)


class SharedMemoryContractTest(MemoryConnectorContractTests, unittest.TestCase):
    def make_connector(self, root: Path, domain: str):
        root = Path(root) / "library" / "lab" / "scope-team-a" / "seq"
        root.mkdir(parents=True, exist_ok=True)
        with mock.patch.object(config, "MEMORY_SCOPE", "team-a"):
            return make_connector(
                root=root,
                domain=domain,
                surface=SURFACE,
                write="1",
                client=FakeMcpClient(),
            )


class EntryPointTest(unittest.TestCase):
    def test_shared_memory_resolves_to_make_connector(self):
        self.assertIs(memory.resolve_factory("shared-memory"), make_connector)


if __name__ == "__main__":
    unittest.main()
