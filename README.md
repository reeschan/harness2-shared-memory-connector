# harness2-shared-memory-connector

English | [日本語](README.ja.md)

## Overview

A memory connector for [Harness²](https://github.com/reeschan/harness2). The harness library stays in files, as before. Only the lessons (cue, lesson and evidence) are shared through a [shared-memory](https://github.com/reeschan/shared-memory) server. Recall asks shared-memory for the lessons that fit the task prompt.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/architecture/architecture-dark.svg">
  <img src="assets/architecture/architecture-light.svg" alt="harness2-shared-memory-connector architecture: harness2 loads SharedMemoryConnector through the shared-memory entry point; it delegates entries, retain and the harness files to the wrapped FileConnector under the library root, searches and gets lessons from shared-memory with the task prompt as the query, writes a lesson only with write=1 (superseding the task's earlier memory from the ledger), and points each memory back to its harness files with source_path; other agents' memories live in other scopes and are never recalled.">
</picture>

The diagram source is `assets/architecture/architecture.d2`; redraw it with the arch-diagram skill's `render.py`.

## Requirements

- POSIX. On Windows, use WSL.
- Python 3.12 to 3.13.
- harness2. It is installed as a dependency and pinned to a commit that passes the tests.
- A shared-memory server. It is an MCP server at `http://127.0.0.1:7820/mcp` by default. It must run on the PC that runs harness2. For the server itself, see the shared-memory repository.

## Install

```bash
pip install "harness2-shared-memory-connector @ git+https://github.com/reeschan/harness2-shared-memory-connector.git"
```

## Usage

`HARNESS2_MEMORY_CONNECTOR=shared-memory` selects this connector. `HARNESS2_MEMORY_SCOPE` gives a sharing name. The sharing name decides where the library and the memories live.

```bash
export HARNESS2_MEMORY_CONNECTOR=shared-memory
export HARNESS2_MEMORY_SCOPE=team-alpha
export HARNESS2_MEMORY_RECALL=1
harness2 --bench jb --substrate oc --k 1 --split all \
  --memory-opt url=http://127.0.0.1:7820/mcp \
  --memory-opt write=1
```

- `HARNESS2_MEMORY_RECALL=1` makes harness2 inject recall into each task. Recall is off in harness2 by default.
- Without a sharing name, the connector behaves exactly like the file connector. It never contacts shared-memory.
- The sharing name must match the library root, `<runs_root>/library/<benchmark>/scope-<sharing name>/<mode>`. If it does not match, the connector prints one warning and leaves shared-memory off.

## Options

Every value is passed as a string with `--memory-opt`.

| Option | Default | Meaning |
| --- | --- | --- |
| `url` | `http://127.0.0.1:7820/mcp` | The MCP endpoint of the shared-memory server. |
| `write` | `0` | `0` reads only. `1` also writes lessons to shared-memory. A person commits the written memories to Git. |
| `limit` | `5` | The number of memories recall reads. |
| `timeout` | `30.0` | The MCP request timeout in seconds. |

`write` also accepts `true` and `yes` for on, and `false` and `no` for off. `limit` must be 1 or more. `timeout` must be a number of seconds.

## What it writes and recalls

**What it writes.** It writes a memory only when a sharing name is set and `write` is on. The memory has these fields.

- Memory scope: `project:harness2.<benchmark>.<mode>.<sharing name>`. Characters outside `A-Za-z0-9._-` become `-`.
- Title: `<domain>: <task_id>`, at most 200 characters.
- Body: the cue, lesson and evidence as `- **cue**: ...` lines, then `## Why` when the harness gives a reason.
- Kind: `semantic`.
- Provenance: `agent_inferred`.
- Source agent: `harness2`.
- Tags: `harness2`, `domain:<domain>` and `task:<slug>`, where `<slug>` is the task's library entry name.
- Source path: the library entry directory of the task.

**What it recalls.** harness2 passes the task prompt as the search query. The first 2,000 characters are used; when the prompt is empty, the domain name is used.

- It searches only this memory scope, with kind `semantic` and the `domain:<domain>` tag. Memories of other agents live in other memory scopes, so they do not mix in.
- It leaves out the current task's own memory. It also leaves out the memories of tasks that this stream has not reached yet, that is, the entries the last `retain` call removed.
- It reads at most `limit` memories and joins them as `## <title>` blocks, cut to the recall length.

**Writing the same task again.** The connector keeps a ledger of the memory id it wrote for each task, in `shared-memory-ledger.json` under the library root. On a rewrite, it passes the old id as `supersedes`. If shared-memory rejects that id, the connector writes again without `supersedes`. The ledger is local to each PC. The same task written on another PC becomes a second memory; it is not replaced.

## When shared-memory is unavailable

The connector prints one warning line and keeps going with files only.

- Recall falls back to the file recall.
- A write saves the harness to files and stops there. The task does not fail.

A write that shared-memory rejects ends the same way.

## Development

Run these in WSL.

```bash
uv run --python 3.12 python -m unittest discover -s tests
uvx ruff@0.17.1 check .
uvx ruff@0.17.1 format --check .
```

## License

Apache-2.0. See [LICENSE](LICENSE).
