# harness2-shared-memory-connector

A Harness² memory connector that keeps the harness library in files and shares the lessons through a shared-memory server.

## Language

**Library entry**:
One adopted harness and its experience for one task, kept as files under the library root.
_Avoid_: Memory, record

**Lesson**:
The transferable part of an experience: its cue, lesson and evidence. It is the only thing written to shared-memory.
_Avoid_: Experience (the whole EXPERIENCE.md), memory

**Memory**:
One lesson as shared-memory stores it: a Markdown file with an id, written by this connector or by another agent.
_Avoid_: Entry, note

**Sharing name**:
The name given with `HARNESS2_MEMORY_SCOPE`. Runs with the same sharing name share their library and their memories; without one, each run keeps to itself.
_Avoid_: Scope (ambiguous), group, namespace

**Memory scope**:
The shared-memory `scope` a memory is written to and searched in, built from the benchmark, the mode and the sharing name.
_Avoid_: Scope (ambiguous), project

**Ledger**:
The local record of which memory id this connector wrote for each task, used to supersede it when the task is written again.
_Avoid_: Index, cache
