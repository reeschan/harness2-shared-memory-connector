# Copyright 2026 Ryuki Tobita
# SPDX-License-Identifier: Apache-2.0
"""Names shared with shared-memory: the library placement, the memory scope and tags."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

DOMAIN_TAG_PREFIX = "domain:"
TASK_TAG_PREFIX = "task:"
BASE_TAG = "harness2"

_SCOPE_PREFIX = "project:harness2."
_UNSAFE = re.compile(r"[^A-Za-z0-9._-]")


@dataclass(frozen=True)
class Placement:
    """Where a run's library sits: its benchmark, mode and sharing name."""

    benchmark: str
    mode: str
    sharing_name: str
    memory_scope: str


def placement_for(root: Path, sharing_name: str) -> Placement | None:
    """Read the placement from a `<benchmark>/scope-<sharing name>/<mode>` root.

    None when there is no sharing name, or when the root is not under the
    `scope-<sharing name>` directory; the caller warns in the latter case.
    """
    if not sharing_name:
        return None
    root = Path(root)
    if root.parent.name != f"scope-{sharing_name}":
        return None
    benchmark = root.parent.parent.name
    mode = root.name
    return Placement(
        benchmark=benchmark,
        mode=mode,
        sharing_name=sharing_name,
        memory_scope=memory_scope(benchmark, mode, sharing_name),
    )


def memory_scope(benchmark: str, mode: str, sharing_name: str) -> str:
    """`project:harness2.<benchmark>.<mode>.<sharing name>`, unsafe characters as `-`."""
    parts = (_safe(part) for part in (benchmark, mode, sharing_name))
    return _SCOPE_PREFIX + ".".join(parts)


def tags_for(domain: str, slug: str) -> list[str]:
    """The tags every memory this connector writes carries."""
    return [BASE_TAG, f"{DOMAIN_TAG_PREFIX}{domain}", f"{TASK_TAG_PREFIX}{slug}"]


def _safe(part: str) -> str:
    cleaned = _UNSAFE.sub("-", part)
    return cleaned or "-"
