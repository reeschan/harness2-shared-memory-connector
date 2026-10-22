# Copyright 2026 Ryuki Tobita
# SPDX-License-Identifier: Apache-2.0
"""The shape of a memory: the lesson's title, content, recall block and search query."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

TITLE_MAX = 200
QUERY_MAX = 2000
WHY_MAX = 1000

_FIELDS = ("cue", "lesson", "evidence")


def lesson_title(domain: str, task_id: str) -> str:
    """`<domain>: <task_id>`, cut to `TITLE_MAX` characters."""
    return f"{domain}: {task_id}"[:TITLE_MAX]


def lesson_content(experience: Mapping, *, why: str = "") -> str:
    """The cue, lesson and evidence as `- **<field>**: ...` lines, then an optional `## Why`."""
    lines = []
    for field in _FIELDS:
        value = " ".join(str(experience.get(field) or "").split())
        if value:
            lines.append(f"- **{field}**: {value}")
    body = why.strip()
    if body:
        if lines:
            lines.append("")
        lines += ["## Why", body[:WHY_MAX]]
    return "\n".join(lines)


def render_recall(memories: Sequence[Mapping]) -> str:
    """`get` results (`meta.title` and `body`) as `## <title>` blocks, one blank line apart."""
    blocks = []
    for memory in memories:
        meta = memory.get("meta") or {}
        title = str(meta.get("title") or "").strip()
        body = str(memory.get("body") or "").strip()
        parts = []
        if title:
            parts.append(f"## {title}")
        if body:
            parts.append(body)
        if parts:
            blocks.append("\n".join(parts))
    return "\n\n".join(blocks)


def query_text(task_prompt: str, domain: str) -> str:
    """The first `QUERY_MAX` characters of the task prompt; `domain` when it is empty."""
    if not task_prompt or not task_prompt.strip():
        return domain
    return task_prompt[:QUERY_MAX]
