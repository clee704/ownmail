---
id: TASK-1.1
title: Benchmark notmuch query latency vs current SQLite FTS5
status: Done
assignee: []
created_date: '2026-07-23 18:44'
updated_date: '2026-09-13 09:41'
labels:
  - research
  - search
dependencies: []
parent_task_id: TASK-1
priority: high
ordinal: 2000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Measure whether notmuch (subprocess/CLI or Python bindings) is fast enough for interactive search-as-you-type in the web UI, before committing to replacing query.py/database.py FTS5 logic.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Measure notmuch query latency on archive-sized corpus (15k+ messages), including cold and warm cache
- [x] #2 Compare against current SQLite FTS5 latency baseline for the same queries
- [x] #3 Go/no-go decision recorded based on results
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Corpus: a real archive, benchmarked on a copy of the DB + a notmuch index built from the same .eml files (read-only; the source archive was never written to).

The benchmark included a cold notmuch index build before measuring query latency.

Query latency, 9 representative queries (single term, phrase, from:/subject: filters, AND/OR, prefix, rare term), each run 8x:

  Backend                         Cold        Warm median
  SQLite FTS5 (in-process)        2-21ms      0.2-1.5ms
  notmuch CLI (subprocess/call)   10-45ms     9-15ms
  notmuch2 (Python bindings,      1-7ms       0.5-5ms
    persistent DB handle)

Findings:
- notmuch via subprocess CLI is 15-20x slower than FTS5 due to per-call process spawn overhead (~10ms fixed cost regardless of query complexity). Not viable for search-as-you-type if each keystroke spawns a process.
- notmuch via in-process Python bindings (notmuch2, cffi) with a persistent Database handle kept open by the web server is roughly the same order of magnitude as FTS5 (both single-digit ms or better). Interactive-search viable IF integration uses bindings, not CLI.
- attachment: filter confirmed to have no notmuch equivalent (matches doc-1 assumption) - would need tag-on-ingest.
- Open concern not benchmarked: notmuch/Xapian single-writer-multi-reader model needs a re-open-on-change strategy for a long-lived server process reading while `download` indexes new mail concurrently - analogous to how SQLite WAL already handles this, but unverified for notmuch/Xapian.

Go/no-go: NO-GO on replacing FTS5 for the built-in web UI search as originally scoped. Current FTS5 is in-process, dependency-free, and already faster in the common case; notmuch only reaches parity (never wins) and only via the bindings integration path, which adds a system-package dependency, a concurrency model to solve, and no attachment: support, for no net performance or maintenance win. Recommend keeping FTS5 for now. notmuch could be revisited if a *different* driver emerges (e.g. external tool interop / letting notmuch/other MUAs read the same archive), which is not a current goal.
<!-- SECTION:NOTES:END -->
