# Copyright 2026 Ryuki Tobita
# SPDX-License-Identifier: Apache-2.0
"""The memory connector: files keep the library, shared-memory shares the lessons.

`SharedMemoryConnector` wraps harness2's file connector. The library and the whole harness
are still kept in files; only the lessons are written to shared-memory, and only when a
sharing name is set and `write` is on. Recall asks shared-memory for the lessons that fit the
task prompt and falls back to the file recall when the server cannot be reached.
"""

from __future__ import annotations

import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from harness2 import config
from harness2.core import library, memory
from harness2.core.memory import FileConnector
from harness2.core.tree import SurfaceSpec, Tree
from harness2.plugins import mcp

from . import ledger, lesson, naming

DEFAULT_URL = "http://127.0.0.1:7820/mcp"
DEFAULT_LIMIT = 5
DEFAULT_TIMEOUT = 30.0
SOURCE_AGENT = "harness2"
KIND = "semantic"
PROVENANCE = "agent_inferred"

_TRUE = frozenset({"1", "true", "yes"})
_FALSE = frozenset({"0", "false", "no", ""})
_SEARCH_MAX = 50


class SharedMemoryConnector:
    """The file connector, plus the lessons shared through shared-memory.

    Without a placement or a client it behaves exactly like the file connector.
    """

    def __init__(
        self,
        inner: FileConnector,
        *,
        client: mcp.McpClient | None,
        placement: naming.Placement | None,
        write: bool,
        limit: int,
    ) -> None:
        self._inner = inner
        self._client = client
        self._placement = placement
        self._write = bool(write)
        self._limit = int(limit)
        self._hidden: set[str] = set()
        self._ledger = ledger.Ledger(Path(inner.root) / ledger.LEDGER_NAME)

    @property
    def domain(self) -> str:
        return self._inner.domain

    def entries(self) -> list[str]:
        return self._inner.entries()

    def context_dir(self) -> Path | None:
        return self._inner.context_dir()

    def retain(self, task_ids: Sequence[str]) -> None:
        before = set(self._inner.entries())
        self._inner.retain(task_ids)
        kept = {library.slug(task_id) for task_id in task_ids}
        self._hidden = (self._hidden | (before - set(self._inner.entries()))) - kept

    def add(
        self,
        task_id: str,
        harness: Tree,
        *,
        why: str = "",
        label: str = "",
        run_id: str = "",
        experience: dict | None = None,
    ) -> Path | None:
        entry = self._inner.add(
            task_id, harness, why=why, label=label, run_id=run_id, experience=experience
        )
        if entry is None:
            return None
        self._hidden.discard(entry.name)
        if self._placement is not None and self._client is not None and self._write:
            self._share(task_id, entry, experience or {}, why)
        return entry

    def recall(self, task_id: str, limit_chars: int, *, query: str = "") -> str:
        if self._placement is None or self._client is None:
            return memory.recall(self._inner, task_id, limit_chars)
        if limit_chars <= 0:
            return ""
        try:
            memories = self._search(task_id, query)
        except mcp.McpError as exc:
            _warn(f"recall failed ({type(exc).__name__})")
            return memory.recall(self._inner, task_id, limit_chars)
        if not memories:
            return ""
        return lesson.render_recall(memories)[:limit_chars]

    def close(self) -> None:
        if self._client is not None:
            self._client.close()

    def _share(self, task_id: str, entry: Path, experience: Mapping, why: str) -> None:
        """Write one lesson, then record its id, superseding the task's earlier memory."""
        slug = entry.name
        arguments: dict[str, Any] = {
            "title": lesson.lesson_title(self.domain, task_id),
            "content": lesson.lesson_content(experience, why=why),
            "scope": self._placement.memory_scope,
            "kind": KIND,
            "provenance": PROVENANCE,
            "source_agent": SOURCE_AGENT,
            "tags": naming.tags_for(self.domain, slug),
            "source_path": str(Path(entry).resolve()),
        }
        try:
            previous = self._ledger.get(slug)
        except OSError as exc:
            _warn(f"ledger read failed ({type(exc).__name__})")
            previous = None
        if previous:
            arguments["supersedes"] = previous
        written = self._write_memory(arguments)
        if not isinstance(written, Mapping):
            return
        memory_id = written.get("id")
        if not memory_id:
            return
        try:
            self._ledger.set(slug, str(memory_id))
        except OSError as exc:
            _warn(f"ledger write failed ({type(exc).__name__})")

    def _write_memory(self, arguments: dict[str, Any]) -> Any:
        try:
            return self._client.call_tool("write", arguments)
        except mcp.McpToolError as exc:
            if "supersedes" not in arguments:
                _warn(f"write failed ({type(exc).__name__})")
                return None
            arguments.pop("supersedes")
            try:
                return self._client.call_tool("write", arguments)
            except mcp.McpError as retry_exc:
                _warn(f"write failed ({type(retry_exc).__name__})")
                return None
        except mcp.McpError as exc:
            _warn(f"write failed ({type(exc).__name__})")
            return None

    def _search(self, task_id: str, query: str) -> list[Mapping]:
        """The top lessons for the prompt, without this task's and the hidden tasks' own."""
        found = self._client.call_tool(
            "search",
            {
                "query": lesson.query_text(query, self.domain),
                "scope": self._placement.memory_scope,
                "kind": KIND,
                "tags": [f"{naming.DOMAIN_TAG_PREFIX}{self.domain}"],
                "limit": min(_SEARCH_MAX, self._limit * 4),
            },
        )
        current = library.slug(task_id)
        memories: list[Mapping] = []
        for item in _search_items(found):
            if len(memories) >= self._limit:
                break
            if not isinstance(item, Mapping):
                continue
            memory_id = item.get("id")
            if not memory_id:
                continue
            got = self._client.call_tool("get", {"id": str(memory_id)})
            if not isinstance(got, Mapping):
                continue
            tasks = _task_tags(got)
            if current in tasks or tasks & self._hidden:
                continue
            memories.append(got)
        return memories


def make_connector(
    *,
    root: Path | str,
    domain: str,
    surface: SurfaceSpec,
    url: str = DEFAULT_URL,
    write: str = "0",
    limit: str = str(DEFAULT_LIMIT),
    timeout: str = str(DEFAULT_TIMEOUT),
    client: mcp.McpClient | None = None,
) -> SharedMemoryConnector:
    """The entry point factory: convert the string options and build the connector."""
    root = Path(root)
    writing = _as_write(write)
    count = _as_limit(limit)
    seconds = _as_timeout(timeout)
    sharing_name = config.MEMORY_SCOPE
    placement = naming.placement_for(root, sharing_name)
    if sharing_name and placement is None:
        _warn("the library root does not match the sharing name; shared-memory is off")
    if placement is not None and client is None:
        client = mcp.client_from(url=url, timeout=seconds)
    inner = memory.FileConnector(root, domain, surface)
    return SharedMemoryConnector(
        inner, client=client, placement=placement, write=writing, limit=count
    )


def _as_write(value: str) -> bool:
    text = str(value).strip().lower()
    if text in _TRUE:
        return True
    if text in _FALSE:
        return False
    raise ValueError(f"write must be 1/true/yes or 0/false/no, got {value!r}")


def _as_limit(value: str) -> int:
    try:
        count = int(str(value).strip())
    except (TypeError, ValueError):
        raise ValueError(f"limit must be an integer of 1 or more, got {value!r}") from None
    if count < 1:
        raise ValueError(f"limit must be an integer of 1 or more, got {value!r}")
    return count


def _as_timeout(value: str) -> float:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        raise ValueError(f"timeout must be a number of seconds, got {value!r}") from None


def _search_items(result: Any) -> list[Any]:
    """The memories of a search result: a list, or the first list value of a dict."""
    if isinstance(result, list):
        return result
    if isinstance(result, Mapping):
        for value in result.values():
            if isinstance(value, list):
                return value
    return []


def _task_tags(got: Mapping) -> set[str]:
    """The slugs named by the `task:` tags of a `get` result."""
    meta = got.get("meta")
    if not isinstance(meta, Mapping):
        return set()
    tags = meta.get("tags")
    if not isinstance(tags, list):
        return set()
    prefix = naming.TASK_TAG_PREFIX
    return {tag[len(prefix) :] for tag in tags if isinstance(tag, str) and tag.startswith(prefix)}


def _warn(reason: str) -> None:
    """One line to stderr: the reason and the exception type, never a value or a body."""
    print(f"harness2-shared-memory-connector: warning: {reason}", file=sys.stderr)
