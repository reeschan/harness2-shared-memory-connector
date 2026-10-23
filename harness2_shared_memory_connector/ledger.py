# Copyright 2026 Ryuki Tobita
# SPDX-License-Identifier: Apache-2.0
"""The local ledger of memory ids this connector wrote, one per task slug."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

LEDGER_NAME = "shared-memory-ledger.json"


class Ledger:
    """`{slug: memory id}` kept in one JSON file, written through a temporary file."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def get(self, slug: str) -> str | None:
        """The memory id recorded for `slug`, or None when there is none or the file is bad."""
        return self._load().get(slug)

    def set(self, slug: str, memory_id: str) -> None:
        """Record `memory_id` for `slug` and write the file at once."""
        entries = self._load()
        entries[slug] = memory_id
        self._write(entries)

    def _load(self) -> dict[str, str]:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        if not isinstance(raw, dict):
            return {}
        return {str(key): value for key, value in raw.items() if isinstance(value, str)}

    def _write(self, entries: dict[str, str]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(prefix="ledger.", suffix=".tmp", dir=self.path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as tmp:
                json.dump(entries, tmp, ensure_ascii=False, indent=2)
                tmp.write("\n")
            os.replace(tmp_name, self.path)
        except BaseException:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise
